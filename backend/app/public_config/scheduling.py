import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.jobs.queue import JobQueue
from app.public_config.contracts import PUBLIC_CONFIG_RULE_VERSION, ConfigType
from app.public_config.persistence import PublicConfigRepository, PublicConfigStateError

logger = logging.getLogger(__name__)

PUBLIC_CONFIG_TYPES: tuple[ConfigType, ...] = ("ROBOTS_TXT", "ADS_TXT")


@dataclass(frozen=True, slots=True)
class PublicConfigSchedulingResult:
    site_count: int
    job_count: int


def resolve_public_config_slot(instant: datetime, timezone_name: str) -> datetime:
    if instant.tzinfo is None:
        raise ValueError("scheduler instant must be timezone-aware")
    try:
        local = instant.astimezone(ZoneInfo(timezone_name))
    except ZoneInfoNotFoundError as error:
        raise ValueError("site timezone is not recognized") from error
    slot_hour = local.hour - (local.hour % 6)
    return local.replace(hour=slot_hour, minute=0, second=0, microsecond=0).astimezone(UTC)


class PublicConfigSchedulingService:
    def __init__(self, repository: PublicConfigRepository, queue: JobQueue) -> None:
        self._repository = repository
        self._queue = queue

    async def schedule_due(self, *, now: datetime | None = None) -> PublicConfigSchedulingResult:
        current = now or datetime.now(UTC)
        if current.tzinfo is None:
            raise ValueError("scheduler instant must be timezone-aware")
        sites = await self._repository.schedulable_sites()
        jobs = 0
        valid_sites = 0
        for site in sites:
            try:
                scheduled_for = resolve_public_config_slot(current, site.timezone)
            except ValueError as error:
                logger.error(
                    "public configuration schedule timezone rejected",
                    extra={
                        "context": {
                            "tenant_id": str(site.tenant_id),
                            "site_id": str(site.site_id),
                            "error_class": type(error).__name__,
                        }
                    },
                )
                continue
            # PC-GATE-2 (EP-030 M2): re-lock the tenant-owned Site FOR UPDATE and
            # re-read the monitoring authorization. Enqueue nothing unless the
            # site is STILL ON and this scheduled slot is strictly after the
            # latest enable watermark (i.e., in the current authorization epoch,
            # not a stale OFF-era backfill). The lock never spans network I/O and
            # serializes against a concurrent enable/disable write (PC-R1).
            try:
                authorization = await self._repository.lock_monitoring_authorization(
                    tenant_id=site.tenant_id,
                    site_id=site.site_id,
                )
            except PublicConfigStateError:
                continue
            if authorization.monitoring_state != "ON":
                continue
            if not scheduled_for > authorization.watermark_updated_at:
                continue
            valid_sites += 1
            for config_type in PUBLIC_CONFIG_TYPES:
                idempotency_key = (
                    f"public-config:{site.site_id}:{config_type}:{scheduled_for.isoformat()}"
                )
                await self._queue.enqueue(
                    tenant_id=site.tenant_id,
                    job_type="FETCH_PUBLIC_CONFIG",
                    payload={
                        "site_id": str(site.site_id),
                        "config_type": config_type,
                        "scheduled_for": scheduled_for.isoformat(),
                        "rule_version": PUBLIC_CONFIG_RULE_VERSION,
                    },
                    idempotency_key=idempotency_key,
                    max_attempts=3,
                    scheduled_at=current,
                )
                jobs += 1
        return PublicConfigSchedulingResult(site_count=valid_sites, job_count=jobs)
