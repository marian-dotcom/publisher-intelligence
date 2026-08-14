import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.browser.models import BrowserScenario, CheckpointRun, CheckpointWindow, MonitoredUrl, Site
from app.browser.service import (
    B2_DESKTOP_SCENARIO_CODE,
    B2_MOBILE_SCENARIO_CODE,
    CheckpointService,
)
from app.config.settings import Settings
from app.jobs.queue import JobQueue

logger = logging.getLogger(__name__)

SIX_HOUR_BOUNDARIES = (0, 6, 12, 18)


@dataclass(frozen=True, slots=True)
class WindowBounds:
    scheduled_for: datetime
    window_start: datetime
    window_end: datetime


@dataclass(frozen=True, slots=True)
class ScheduledRun:
    tenant_id: uuid.UUID
    checkpoint_run_id: uuid.UUID
    scheduled_at: datetime


@dataclass(frozen=True, slots=True)
class SchedulingResult:
    site_count: int
    run_count: int
    job_count: int


def resolve_six_hour_window(instant: datetime, timezone_name: str) -> WindowBounds:
    if instant.tzinfo is None:
        raise ValueError("scheduler instant must be timezone-aware")
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as error:
        raise ValueError("site timezone is not recognized") from error

    local = instant.astimezone(timezone)
    start_hour = max(hour for hour in SIX_HOUR_BOUNDARIES if hour <= local.hour)
    start_date = local.date()
    end_hour = start_hour + 6
    end_date = start_date
    if end_hour == 24:
        end_hour = 0
        end_date = date.fromordinal(start_date.toordinal() + 1)

    local_start = datetime.combine(start_date, time(hour=start_hour), tzinfo=timezone)
    local_end = datetime.combine(end_date, time(hour=end_hour), tzinfo=timezone)
    start_utc = local_start.astimezone(UTC)
    end_utc = local_end.astimezone(UTC)
    return WindowBounds(
        scheduled_for=start_utc,
        window_start=start_utc,
        window_end=end_utc,
    )


class CheckpointSchedulingService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        queue: JobQueue,
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._queue = queue
        self._settings = settings

    async def schedule_due(self, *, now: datetime | None = None) -> SchedulingResult:
        instant = now or datetime.now(UTC)
        if instant.tzinfo is None:
            raise ValueError("scheduler instant must be timezone-aware")
        await CheckpointService(
            self._session_factory, self._queue, self._settings
        ).ensure_b2_configuration_for_active_sites()
        async with self._session_factory() as session:
            sites = list(
                (
                    await session.scalars(
                        select(Site).where(Site.status == "ACTIVE").order_by(Site.id)
                    )
                ).all()
            )

        scheduled_runs: list[ScheduledRun] = []
        valid_site_count = 0
        for site in sites:
            try:
                bounds = resolve_six_hour_window(instant, site.timezone)
            except ValueError as error:
                logger.error(
                    "browser schedule timezone rejected",
                    extra={
                        "context": {
                            "tenant_id": str(site.tenant_id),
                            "site_id": str(site.id),
                            "error_class": type(error).__name__,
                        }
                    },
                )
                continue
            valid_site_count += 1
            scheduled_runs.extend(await self._materialize_site(site, bounds, instant))

        job_count = 0
        for scheduled in scheduled_runs:
            await self._queue.enqueue(
                job_type="BROWSER_CHECKPOINT",
                tenant_id=scheduled.tenant_id,
                payload={"checkpoint_run_id": str(scheduled.checkpoint_run_id)},
                idempotency_key=f"browser-checkpoint:{scheduled.checkpoint_run_id}",
                max_attempts=2,
                scheduled_at=scheduled.scheduled_at,
            )
            job_count += 1
        return SchedulingResult(
            site_count=valid_site_count,
            run_count=len(scheduled_runs),
            job_count=job_count,
        )

    async def _materialize_site(
        self,
        site: Site,
        bounds: WindowBounds,
        now: datetime,
    ) -> list[ScheduledRun]:
        async with self._session_factory() as session, session.begin():
            window_id = await self._window_id(session, site, bounds)
            monitored_urls = list(
                (
                    await session.scalars(
                        select(MonitoredUrl)
                        .where(
                            MonitoredUrl.tenant_id == site.tenant_id,
                            MonitoredUrl.site_id == site.id,
                            MonitoredUrl.status == "ACTIVE",
                            MonitoredUrl.valid_from <= bounds.window_end,
                            (MonitoredUrl.valid_to.is_(None))
                            | (MonitoredUrl.valid_to > bounds.window_start),
                        )
                        .order_by(MonitoredUrl.priority.desc(), MonitoredUrl.id)
                    )
                ).all()
            )
            scenarios = list(
                (
                    await session.scalars(
                        select(BrowserScenario)
                        .where(
                            BrowserScenario.tenant_id == site.tenant_id,
                            BrowserScenario.site_id == site.id,
                            BrowserScenario.status == "ACTIVE",
                            BrowserScenario.retired_at.is_(None),
                            BrowserScenario.interaction_profile_id.is_not(None),
                            BrowserScenario.code.in_(
                                (B2_DESKTOP_SCENARIO_CODE, B2_MOBILE_SCENARIO_CODE)
                            ),
                        )
                        .order_by(BrowserScenario.device_class, BrowserScenario.code)
                    )
                ).all()
            )
            runs: list[ScheduledRun] = []
            ordinal = 0
            for monitored_url in monitored_urls:
                for scenario in scenarios:
                    run_id = await self._run_id(
                        session,
                        site=site,
                        window_id=window_id,
                        monitored_url=monitored_url,
                        scenario=scenario,
                        scheduled_for=bounds.scheduled_for,
                    )
                    offset = timedelta(
                        seconds=ordinal * self._settings.browser_schedule_stagger_seconds
                    )
                    desired = bounds.window_start + offset
                    latest = bounds.window_end - timedelta(seconds=1)
                    scheduled_at = min(max(desired, now), latest)
                    runs.append(
                        ScheduledRun(
                            tenant_id=site.tenant_id,
                            checkpoint_run_id=run_id,
                            scheduled_at=scheduled_at,
                        )
                    )
                    ordinal += 1
            return runs

    @staticmethod
    async def _window_id(
        session: AsyncSession,
        site: Site,
        bounds: WindowBounds,
    ) -> uuid.UUID:
        candidate_id = uuid.uuid4()
        inserted = (
            await session.execute(
                insert(CheckpointWindow)
                .values(
                    id=candidate_id,
                    tenant_id=site.tenant_id,
                    site_id=site.id,
                    scheduled_for=bounds.scheduled_for,
                    window_start=bounds.window_start,
                    window_end=bounds.window_end,
                    status="SCHEDULED",
                )
                .on_conflict_do_nothing(index_elements=["site_id", "scheduled_for"])
                .returning(CheckpointWindow.id)
            )
        ).scalar_one_or_none()
        if inserted is not None:
            return inserted
        existing = await session.scalar(
            select(CheckpointWindow.id).where(
                CheckpointWindow.tenant_id == site.tenant_id,
                CheckpointWindow.site_id == site.id,
                CheckpointWindow.scheduled_for == bounds.scheduled_for,
            )
        )
        if existing is None:
            raise RuntimeError("checkpoint window conflict could not be resolved")
        return existing

    @staticmethod
    async def _run_id(
        session: AsyncSession,
        *,
        site: Site,
        window_id: uuid.UUID,
        monitored_url: MonitoredUrl,
        scenario: BrowserScenario,
        scheduled_for: datetime,
    ) -> uuid.UUID:
        candidate_id = uuid.uuid4()
        inserted = (
            await session.execute(
                insert(CheckpointRun)
                .values(
                    id=candidate_id,
                    tenant_id=site.tenant_id,
                    site_id=site.id,
                    checkpoint_window_id=window_id,
                    monitored_url_id=monitored_url.id,
                    template_id=monitored_url.template_id,
                    scenario_id=scenario.id,
                    scheduled_for=scheduled_for,
                    status="PENDING",
                    attempt_count=0,
                    collector_bundle_version="b8-v1",
                    environment={},
                    limitations=[],
                    manifest={},
                )
                .on_conflict_do_nothing(
                    index_elements=["checkpoint_window_id", "monitored_url_id", "scenario_id"]
                )
                .returning(CheckpointRun.id)
            )
        ).scalar_one_or_none()
        if inserted is not None:
            return inserted
        existing = await session.scalar(
            select(CheckpointRun.id).where(
                CheckpointRun.tenant_id == site.tenant_id,
                CheckpointRun.checkpoint_window_id == window_id,
                CheckpointRun.monitored_url_id == monitored_url.id,
                CheckpointRun.scenario_id == scenario.id,
            )
        )
        if existing is None:
            raise RuntimeError("checkpoint run conflict could not be resolved")
        return existing
