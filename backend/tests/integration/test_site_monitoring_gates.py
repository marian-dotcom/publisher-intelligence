"""EP-030 M2: scheduler (GATE-1/2) and worker (GATE-3) monitoring-control gates.

Integration coverage for the three-gate OFF contract and the R1-R7 race matrix:
- GATE-1 never selects OFF sites; GATE-2 re-checks state/watermark under a
  site-row FOR UPDATE and materializes nothing for OFF/pre-watermark sites;
- GATE-3 pre-flight terminalizes queued SCHEDULED runs as SKIPPED with zero
  contact, completes the claimed job, enqueues no DERIVE, and never retries;
- DIAGNOSTIC runs are unaffected by GATE-3;
- a run already past pre-flight finalizes normally even after a disable (R4/R5);
- a window of only SKIPPED runs becomes COMPLETE (orchestration, not success);
- SKIPPED never becomes the latest source-health observation.
"""

import asyncio
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from sqlalchemy import func, select, update

from app.browser.contracts import BrowserEvidence, BrowserTarget
from app.browser.models import (
    BrowserScenario,
    CheckpointAttempt,
    CheckpointRun,
    CheckpointWindow,
    InteractionProfile,
    MonitoredUrl,
    Publisher,
    Site,
    Template,
)
from app.browser.monitoring_control import set_monitoring_state
from app.browser.persistence import (
    SKIP_LIMITATION_ID,
    CheckpointRepository,
    CheckpointSkippedError,
    EvidencePersister,
)
from app.browser.scheduling import (
    CheckpointSchedulingService,
    resolve_six_hour_window,
)
from app.browser_worker import handle_browser_job
from app.db.models import Job, Tenant
from app.db.session import get_session_factory
from app.jobs.queue import JobQueue

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _clean_db() -> Generator[None, None, None]:
    from tests.integration.purge import make_purge

    purge = make_purge(get_session_factory)
    asyncio.run(purge())
    yield
    asyncio.run(purge())


async def _create_runnable_site(
    *,
    tenant_id: uuid.UUID,
    monitoring_state: str = "OFF",
    timezone: str = "UTC",
) -> uuid.UUID:
    """Minimal runnable B2 site: Publisher + Site + Template + MonitoredUrl +
    InteractionProfile + B2 desktop scenario bound to an interaction profile."""
    session_factory = get_session_factory()
    site_id, publisher_id = uuid.uuid4(), uuid.uuid4()
    template_id, monitored_url_id = uuid.uuid4(), uuid.uuid4()
    profile_id, scenario_id = uuid.uuid4(), uuid.uuid4()
    async with session_factory() as session, session.begin():
        session.add(
            Publisher(
                id=publisher_id,
                tenant_id=tenant_id,
                name="Gates Publisher",
                slug=f"gates-pub-{publisher_id.hex[:8]}",
                default_timezone=timezone,
                status="ACTIVE",
            )
        )
        await session.flush()
        session.add(
            Site(
                id=site_id,
                tenant_id=tenant_id,
                publisher_id=publisher_id,
                name="Gates Site",
                canonical_domain=f"{site_id.hex}.example.test",
                canonical_scheme="https",
                timezone=timezone,
                status="ACTIVE",
                monitoring_state=monitoring_state,
            )
        )
        await session.flush()
        session.add(
            Template(
                id=template_id,
                tenant_id=tenant_id,
                site_id=site_id,
                code="core_desktop_v2",
                display_name="B2 Desktop",
                status="ACTIVE",
            )
        )
        await session.flush()
        session.add(
            MonitoredUrl(
                id=monitored_url_id,
                tenant_id=tenant_id,
                site_id=site_id,
                template_id=template_id,
                url=f"https://{site_id.hex}.example.test/",
                status="ACTIVE",
                valid_from=datetime(2024, 1, 1, tzinfo=UTC),
            )
        )
        await session.flush()
        session.add(
            InteractionProfile(
                id=profile_id,
                tenant_id=tenant_id,
                site_id=site_id,
                code="core_scroll_v1",
                version=1,
                description="scroll",
                steps=[],
                status="ACTIVE",
            )
        )
        await session.flush()
        session.add(
            BrowserScenario(
                id=scenario_id,
                tenant_id=tenant_id,
                site_id=site_id,
                interaction_profile_id=profile_id,
                code="core_desktop_v2",
                version=1,
                device_class="DESKTOP",
                status="ACTIVE",
            )
        )
    return site_id


async def _create_tenant(slug: str) -> uuid.UUID:
    session_factory = get_session_factory()
    tenant_id = uuid.uuid4()
    async with session_factory() as session, session.begin():
        session.add(Tenant(id=tenant_id, slug=f"{slug}-{tenant_id.hex[:8]}", name=slug))
    return tenant_id


async def _set_state(site_id: uuid.UUID, tenant_id: uuid.UUID, enabled: bool) -> None:
    await set_monitoring_state(
        get_session_factory(),
        tenant_id=tenant_id,
        site_id=site_id,
        enabled=enabled,
        actor_id=tenant_id,
    )


async def _await_lock_waiter(*, timeout_seconds: float = 5.0) -> bool:
    """Deterministic lock barrier witness: returns True once a genuine waiting
    lock exists in pg_stat_activity against the sites table (a FOR UPDATE that
    is blocked in the transactionid lock wait), proving a concurrent writer is
    blocked on the site row lock rather than merely being scheduled. Polls with
    a bounded deadline so a missing block fails the test instead of hanging."""
    from sqlalchemy import text

    session_factory = get_session_factory()
    query = text(
        """
        SELECT count(*)
        FROM pg_stat_activity AS act
        WHERE act.state = 'active'
          AND act.wait_event_type = 'Lock'
          AND act.wait_event = 'transactionid'
          AND lower(act.query) LIKE '%sites%'
          AND lower(act.query) LIKE '%for update%'
        """
    )
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout_seconds
    while True:
        async with session_factory() as session:
            waiting = await session.scalar(query)
            if waiting is not None and waiting > 0:
                return True
        if loop.time() >= deadline:
            return False
        await asyncio.sleep(0.01)


async def _set_watermark(site_id: uuid.UUID, at: datetime) -> None:
    """Force the monitoring authorization watermark (bypasses the OFF<->ON guard;
    used only to establish a deterministic boundary-independent state)."""
    session_factory = get_session_factory()
    async with session_factory() as session, session.begin():
        await session.execute(
            update(Site)
            .where(Site.id == site_id)
            .values(monitoring_state="ON", monitoring_state_updated_at=at)
        )


async def _create_scheduled_run(
    *,
    tenant_id: uuid.UUID,
    site_id: uuid.UUID,
    scheduled_for: datetime,
    status: str = "PENDING",
    observation_kind: str = "SCHEDULED",
    trigger_source: str | None = None,
    trigger_correlation_id: uuid.UUID | None = None,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Create a SCHEDULED window + run for the site's (first) monitored url /
    scenario; returns (window_id, run_id, monitored_url_id)."""
    session_factory = get_session_factory()
    window_id, run_id = uuid.uuid4(), uuid.uuid4()
    async with session_factory() as session, session.begin():
        monitored_url = await session.scalar(
            select(MonitoredUrl).where(
                MonitoredUrl.tenant_id == tenant_id, MonitoredUrl.site_id == site_id
            )
        )
        scenario = await session.scalar(
            select(BrowserScenario).where(
                BrowserScenario.tenant_id == tenant_id, BrowserScenario.site_id == site_id
            )
        )
        assert monitored_url is not None
        assert scenario is not None
        session.add(
            CheckpointWindow(
                id=window_id,
                tenant_id=tenant_id,
                site_id=site_id,
                scheduled_for=scheduled_for,
                window_start=scheduled_for - timedelta(hours=1),
                window_end=scheduled_for + timedelta(hours=1),
                status="SCHEDULED",
            )
        )
        await session.flush()
        session.add(
            CheckpointRun(
                id=run_id,
                tenant_id=tenant_id,
                site_id=site_id,
                checkpoint_window_id=window_id,
                monitored_url_id=monitored_url.id,
                template_id=monitored_url.template_id,
                scenario_id=scenario.id,
                observation_kind=observation_kind,
                trigger_source=trigger_source,
                trigger_correlation_id=trigger_correlation_id,
                scheduled_for=scheduled_for,
                status=status,
                attempt_count=0,
                collector_bundle_version="b8-v1",
                environment={},
                limitations=[],
                manifest={},
            )
        )
    return window_id, run_id, monitored_url.id


async def _scenario_id(tenant_id: uuid.UUID, site_id: uuid.UUID) -> uuid.UUID:
    session_factory = get_session_factory()
    async with session_factory() as session:
        value = await session.scalar(
            select(BrowserScenario.id).where(
                BrowserScenario.tenant_id == tenant_id, BrowserScenario.site_id == site_id
            )
        )
        assert value is not None
        return value


async def _run_row(run_id: uuid.UUID) -> CheckpointRun:
    session_factory = get_session_factory()
    async with session_factory() as session:
        run = await session.get(CheckpointRun, run_id)
        assert run is not None
        return run


async def _job_rows(tenant_id: uuid.UUID, job_type: str) -> list[Job]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        return list(
            (
                await session.scalars(
                    select(Job).where(Job.tenant_id == tenant_id, Job.job_type == job_type)
                )
            ).all()
        )


async def _attempt_rows(run_id: uuid.UUID) -> list[CheckpointAttempt]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        return list(
            (
                await session.scalars(
                    select(CheckpointAttempt).where(CheckpointAttempt.checkpoint_run_id == run_id)
                )
            ).all()
        )


class _ProbeRunner:
    """Raises if navigation is ever attempted; proves GATE-3 teleports past it."""

    def __init__(self) -> None:
        self.called = False

    async def run(self, target: BrowserTarget) -> BrowserEvidence:
        self.called = True
        raise AssertionError("navigation must not occur after an administrative skip")


class _FakePersister:
    def __init__(self) -> None:
        self.persisted = False

    async def persist(self, **kwargs: Any) -> dict[str, Any]:
        del kwargs
        self.persisted = True
        return {}


@pytest.mark.asyncio
async def test_gate1_never_selects_off_sites_and_all_off_creates_nothing() -> None:
    tenant_id = await _create_tenant("gate1")
    on_site_id = await _create_runnable_site(tenant_id=tenant_id, monitoring_state="ON")
    off_site_id = await _create_runnable_site(tenant_id=tenant_id, monitoring_state="OFF")
    # Deterministic boundary-independent state: watermark in the deep past, a
    # fixed scheduler instant whose current window is strictly future.
    watermark = datetime(2025, 6, 1, 0, 0, tzinfo=UTC)
    await _set_watermark(on_site_id, watermark)
    scheduler = CheckpointSchedulingService(
        get_session_factory(), JobQueue(get_session_factory()), _settings()
    )
    result = await scheduler.schedule_due(now=datetime(2026, 3, 5, 18, 0, tzinfo=UTC))
    assert result.site_count == 1  # only the ON site entered the valid-site loop
    assert result.run_count >= 1
    assert result.job_count == result.run_count

    session_factory = get_session_factory()
    async with session_factory() as session:
        windows = list(
            (
                await session.scalars(
                    select(CheckpointWindow).where(CheckpointWindow.site_id == on_site_id)
                )
            ).all()
        )
        assert len(windows) == 1
        off_windows = list(
            (
                await session.scalars(
                    select(CheckpointWindow).where(CheckpointWindow.site_id == off_site_id)
                )
            ).all()
        )
        assert off_windows == []
        runs = list(
            (
                await session.scalars(
                    select(CheckpointRun).where(CheckpointRun.site_id == on_site_id)
                )
            ).all()
        )
        assert len(runs) >= 1
        assert all(run.observation_kind == "SCHEDULED" for run in runs)
    jobs = await _job_rows(tenant_id, "BROWSER_CHECKPOINT")
    assert len(jobs) == result.run_count


@pytest.mark.asyncio
async def test_gate2_materializes_nothing_when_disabled_before_materialize() -> None:
    """GATE-2 (R1): a disable that commits after the coarse GATE-1 candidate
    read but before the GATE-2 locked re-read yields nothing materialized. Run
    as a deterministic real-concurrency race: hold the site row lock, start the
    disable so it genuinely blocks (barrier confirmed via pg_locks), release,
    then materialize. The materialize transaction re-locks and reads the
    committed OFF, so no window/run/job is ever created."""
    tenant_id = await _create_tenant("gate2-r1")
    site_id = await _create_runnable_site(tenant_id=tenant_id, monitoring_state="ON")
    watermark = datetime(2025, 6, 1, 0, 0, tzinfo=UTC)
    await _set_watermark(site_id, watermark)
    now = datetime(2026, 3, 5, 18, 0, tzinfo=UTC)
    bounds = resolve_six_hour_window(now, "UTC")
    session_factory = get_session_factory()

    # Barrier: hold the tenant-owned site row FOR UPDATE so the disable blocks.
    async with session_factory() as session, session.begin():
        await session.scalar(
            select(Site).where(Site.tenant_id == tenant_id, Site.id == site_id).with_for_update()
        )
        disable_task = asyncio.create_task(
            _set_state(site_id, tenant_id, enabled=False),
            name="disable-holding",
        )
        assert await _await_lock_waiter() is True  # disable is genuinely blocked
    # The disable task only proceeds after the outer transaction commits,
    # reacquiring the lock and writing OFF. Await it to completion.
    await disable_task

    scheduler = CheckpointSchedulingService(
        get_session_factory(), JobQueue(get_session_factory()), _settings()
    )
    async with session_factory() as session:
        site = await session.get(Site, site_id)
        assert site is not None
        materialized = await scheduler._materialize_site(site, bounds, now)
    assert materialized == []
    async with session_factory() as session:
        assert (
            await session.scalar(
                select(func.count(CheckpointWindow.id)).where(CheckpointWindow.site_id == site_id)
            )
        ) == 0
        assert (
            await session.scalar(
                select(func.count(CheckpointRun.id)).where(CheckpointRun.site_id == site_id)
            )
        ) == 0
    assert await _job_rows(tenant_id, "BROWSER_CHECKPOINT") == []


@pytest.mark.asyncio
async def test_gate2_materializes_nothing_before_watermark() -> None:
    """An ON site whose candidate window start is not strictly after the enable
    watermark produces no window/run/job (enable 14:10 -> first boundary 18:00)."""
    tenant_id = await _create_tenant("gate2-watermark")
    site_id = await _create_runnable_site(tenant_id=tenant_id, monitoring_state="ON")
    # Establish a watermark at 14:10 within the 12:00-18:00 window.
    watermark = datetime(2026, 3, 5, 14, 10, 0, tzinfo=UTC)
    session_factory = get_session_factory()
    async with session_factory() as session:
        await session.execute(
            update(Site)
            .where(Site.id == site_id)
            .values(monitoring_state="ON", monitoring_state_updated_at=watermark)
        )
    scheduler = CheckpointSchedulingService(
        get_session_factory(), JobQueue(get_session_factory()), _settings()
    )
    # Tick inside the still-current 12-18 window (16:00): window_start(12:00) is
    # not strictly after the 14:10 watermark -> nothing materialized.
    bounds = resolve_six_hour_window(datetime(2026, 3, 5, 16, 0, tzinfo=UTC), "UTC")
    async with session_factory() as session:
        site = await session.get(Site, site_id)
        assert site is not None
        materialized = await scheduler._materialize_site(
            site, bounds, datetime(2026, 3, 5, 16, 0, tzinfo=UTC)
        )
    assert materialized == []
    async with session_factory() as session:
        assert (
            await session.scalar(
                select(func.count(CheckpointWindow.id)).where(CheckpointWindow.site_id == site_id)
            )
        ) == 0


@pytest.mark.asyncio
async def test_repeated_scheduler_pass_is_idempotent_r7() -> None:
    """Two scheduler passes over an ON site yield a single window/run/job set."""
    tenant_id = await _create_tenant("gate2-r7")
    site_id = await _create_runnable_site(tenant_id=tenant_id, monitoring_state="ON")
    await _set_watermark(site_id, datetime(2025, 6, 1, 0, 0, tzinfo=UTC))
    scheduler = CheckpointSchedulingService(
        get_session_factory(), JobQueue(get_session_factory()), _settings()
    )
    now = datetime(2026, 3, 5, 18, 0, tzinfo=UTC)
    first = await scheduler.schedule_due(now=now)
    second = await scheduler.schedule_due(now=now)
    assert second.run_count == first.run_count
    assert second.run_count >= 1
    session_factory = get_session_factory()
    async with session_factory() as session:
        window_count = int(
            await session.scalar(
                select(func.count(CheckpointWindow.id)).where(CheckpointWindow.site_id == site_id)
            )
        )
        run_count = int(
            await session.scalar(
                select(func.count(CheckpointRun.id)).where(CheckpointRun.site_id == site_id)
            )
        )
    assert window_count == 1
    assert run_count == first.run_count
    assert len(await _job_rows(tenant_id, "BROWSER_CHECKPOINT")) == first.run_count


@pytest.mark.asyncio
async def test_queued_then_disabled_worker_skips_no_contact_job_complete_r2() -> None:
    """A SCHEDULED run materialized+enqueued then disabled before claim is
    terminalized SKIPPED by GATE-3 with zero navigation; job completes with no
    retry or DERIVE."""
    tenant_id = await _create_tenant("r2")
    site_id = await _create_runnable_site(tenant_id=tenant_id, monitoring_state="ON")
    now = datetime.now(UTC)
    _window_id, run_id, _monitored_url_id = await _create_scheduled_run(
        tenant_id=tenant_id, site_id=site_id, scheduled_for=now - timedelta(minutes=5)
    )
    queue = JobQueue(get_session_factory())
    await queue.enqueue(
        job_type="BROWSER_CHECKPOINT",
        tenant_id=tenant_id,
        payload={"checkpoint_run_id": str(run_id)},
        idempotency_key=f"browser-checkpoint:{run_id}",
        max_attempts=2,
        scheduled_at=datetime(2000, 1, 1, tzinfo=UTC),
    )
    await _set_state(site_id, tenant_id, enabled=False)  # disable after enqueue (R2)

    repository = CheckpointRepository(get_session_factory())
    runner = _ProbeRunner()
    persister = _FakePersister()

    lease = await queue.claim(worker_id="test-w", lease_seconds=30, job_type="BROWSER_CHECKPOINT")
    assert lease is not None
    await handle_browser_job(
        queue=queue,
        repository=repository,
        persister=cast(EvidencePersister, persister),
        runner=cast("Any", runner),
        lease=lease,
        backoff_seconds=0,
    )

    run = await _run_row(run_id)
    assert run.status == "SKIPPED"
    assert SKIP_LIMITATION_ID in run.limitations
    assert run.completed_at is not None
    attempts = await _attempt_rows(run_id)
    assert len(attempts) == 1
    assert attempts[0].status == "SKIPPED"
    assert attempts[0].completed_at is not None
    assert runner.called is False
    assert persister.persisted is False
    job = (await _job_rows(tenant_id, "BROWSER_CHECKPOINT"))[0]
    assert job.status == "COMPLETE"
    assert job.attempt == 1  # no retry recorded
    assert job.last_error_class is None
    assert await _job_rows(tenant_id, "DERIVE_BROWSER_EVENTS") == []


@pytest.mark.asyncio
async def test_skipped_run_redelivered_after_crash_completes_not_fails() -> None:
    """Crash/recovery (EP-030 M2): a worker that claims a job, gets GATE-3
    SKIPPED terminalized+committed, then crashes before queue.complete leaves the
    run terminal SKIPPED. After lease expiry + reclaim, the redelivered
    begin_attempt must raise CheckpointSkippedError (intentional skip), and the
    worker completes the job with no retry, no DERIVE, no new attempt row, and
    zero navigation contacts on the second pass."""
    tenant_id = await _create_tenant("r2-redelivery")
    site_id = await _create_runnable_site(tenant_id=tenant_id, monitoring_state="ON")
    now = datetime.now(UTC)
    _window_id, run_id, _monitored_url_id = await _create_scheduled_run(
        tenant_id=tenant_id, site_id=site_id, scheduled_for=now - timedelta(minutes=5)
    )
    await _set_state(site_id, tenant_id, enabled=False)
    queue = JobQueue(get_session_factory())
    await queue.enqueue(
        job_type="BROWSER_CHECKPOINT",
        tenant_id=tenant_id,
        payload={"checkpoint_run_id": str(run_id)},
        idempotency_key=f"browser-checkpoint:{run_id}",
        max_attempts=2,
        scheduled_at=datetime(2000, 1, 1, tzinfo=UTC),
    )

    repository = CheckpointRepository(get_session_factory())
    first = await queue.claim(worker_id="w1", lease_seconds=30, job_type="BROWSER_CHECKPOINT")
    assert first is not None
    assert first.attempt == 1
    # Simulate the worker crash: begin_attempt runs, GATE-3 terminalizes the run
    # as SKIPPED (commit-immediately), raises CheckpointSkippedError, but the job
    # is never completed (no queue.complete) before the process dies.
    with pytest.raises(CheckpointSkippedError):
        await repository.begin_attempt(
            tenant_id=tenant_id, checkpoint_run_id=run_id, attempt_number=first.attempt
        )
    run = await _run_row(run_id)
    assert run.status == "SKIPPED"
    assert SKIP_LIMITATION_ID in run.limitations

    # Redelivery: expire the lease, reclaim the job, and hand it to a fresh worker.
    session_factory = get_session_factory()
    async with session_factory() as session, session.begin():
        await session.execute(
            update(Job)
            .where(Job.id == first.id)
            .values(lock_expires_at=datetime(2000, 1, 1, tzinfo=UTC))
        )
    reclaimed = await queue.reclaim_expired(backoff_seconds=0)
    assert reclaimed == 1
    second = await queue.claim(worker_id="w2", lease_seconds=30, job_type="BROWSER_CHECKPOINT")
    assert second is not None
    assert second.attempt == 2

    runner = _ProbeRunner()
    persister = _FakePersister()
    await handle_browser_job(
        queue=queue,
        repository=repository,
        persister=cast(EvidencePersister, persister),
        runner=cast("Any", runner),
        lease=second,
        backoff_seconds=0,
    )

    run = await _run_row(run_id)
    assert run.status == "SKIPPED"
    assert SKIP_LIMITATION_ID in run.limitations
    attempts = await _attempt_rows(run_id)
    assert len(attempts) == 1  # no second attempt materialized
    assert attempts[0].status == "SKIPPED"
    assert runner.called is False
    assert persister.persisted is False
    job = (await _job_rows(tenant_id, "BROWSER_CHECKPOINT"))[0]
    assert job.status == "COMPLETE"
    assert job.last_error_class is None  # a monitoring-disabled skip is not a failure
    assert job.attempt == 2  # completed on redelivery, not failed/retried further
    assert await _job_rows(tenant_id, "DERIVE_BROWSER_EVENTS") == []


@pytest.mark.asyncio
async def test_claimed_before_disable_preflight_skips_r3() -> None:
    """Claiming the job first, then disabling, then running pre-flight still
    yields an atomic SKIPPED terminalization (GATE-3 reads the committed OFF)."""
    tenant_id = await _create_tenant("r3")
    site_id = await _create_runnable_site(tenant_id=tenant_id, monitoring_state="ON")
    now = datetime.now(UTC)
    _window_id, run_id, _monitored_url_id = await _create_scheduled_run(
        tenant_id=tenant_id, site_id=site_id, scheduled_for=now - timedelta(minutes=1)
    )
    queue = JobQueue(get_session_factory())
    await queue.enqueue(
        job_type="BROWSER_CHECKPOINT",
        tenant_id=tenant_id,
        payload={"checkpoint_run_id": str(run_id)},
        idempotency_key=f"browser-checkpoint:{run_id}",
        max_attempts=2,
        scheduled_at=datetime(2000, 1, 1, tzinfo=UTC),
    )
    lease = await queue.claim(worker_id="test-w", lease_seconds=30, job_type="BROWSER_CHECKPOINT")
    assert lease is not None
    await _set_state(site_id, tenant_id, enabled=False)  # disable after claim (R3)

    repository = CheckpointRepository(get_session_factory())
    runner = _ProbeRunner()
    persister = _FakePersister()
    await handle_browser_job(
        queue=queue,
        repository=repository,
        persister=cast(EvidencePersister, persister),
        runner=cast("Any", runner),
        lease=lease,
        backoff_seconds=0,
    )
    run = await _run_row(run_id)
    assert run.status == "SKIPPED"
    assert runner.called is False
    job = (await _job_rows(tenant_id, "BROWSER_CHECKPOINT"))[0]
    assert job.status == "COMPLETE"
    assert await _job_rows(tenant_id, "DERIVE_BROWSER_EVENTS") == []


@pytest.mark.asyncio
async def test_begins_attempt_directly_raises_skipped_when_off() -> None:
    tenant_id = await _create_tenant("r3-direct")
    site_id = await _create_runnable_site(tenant_id=tenant_id, monitoring_state="ON")
    now = datetime.now(UTC)
    _window_id, run_id, _monitored_url_id = await _create_scheduled_run(
        tenant_id=tenant_id, site_id=site_id, scheduled_for=now - timedelta(minutes=1)
    )
    await _set_state(site_id, tenant_id, enabled=False)
    repository = CheckpointRepository(get_session_factory())
    with pytest.raises(CheckpointSkippedError):
        await repository.begin_attempt(
            tenant_id=tenant_id, checkpoint_run_id=run_id, attempt_number=1
        )
    run = await _run_row(run_id)
    assert run.status == "SKIPPED"
    # EP-030 M2 (crash/redelivery): re-beginning an already-terminal SKIPPED run
    # with the canonical limitation is an intentional skip, never a silent
    # restart or a failure.
    with pytest.raises(CheckpointSkippedError):
        await repository.begin_attempt(
            tenant_id=tenant_id, checkpoint_run_id=run_id, attempt_number=1
        )


def _healthy_evidence() -> BrowserEvidence:
    now = datetime.now(UTC)
    return BrowserEvidence(
        status="COMPLETE",
        started_at=now,
        completed_at=now,
        final_url="https://example.test/",
        http_status=200,
        playwright_version="test",
        chromium_version="test",
        environment={},
    )


@pytest.mark.asyncio
async def test_in_flight_run_finalizes_normally_after_disable_r4r5() -> None:
    """A run already past GATE-3 (RUNNING) finalizes normally even after a
    disable commits; evidence is retained and never rewritten to SKIPPED."""
    tenant_id = await _create_tenant("r4r5")
    site_id = await _create_runnable_site(tenant_id=tenant_id, monitoring_state="ON")
    now = datetime.now(UTC)
    window_id, run_id, monitored_url_id = await _create_scheduled_run(
        tenant_id=tenant_id, site_id=site_id, scheduled_for=now - timedelta(minutes=5)
    )
    repository = CheckpointRepository(get_session_factory())
    target = await repository.begin_attempt(
        tenant_id=tenant_id, checkpoint_run_id=run_id, attempt_number=1
    )
    run_after = await _run_row(run_id)
    assert run_after.status == "RUNNING"

    await _set_state(site_id, tenant_id, enabled=False)  # disable after pre-flight (R4)

    # Validate the scenario target is consistent with the persisted row.
    scenario_id = await _scenario_id(tenant_id, site_id)
    assert target.scenario_id == scenario_id
    assert target.monitored_url_id == monitored_url_id

    # Complete the in-flight run with healthy evidence; it must NOT become SKIPPED.
    evidence = _healthy_evidence()
    await repository.finalize(
        target=target, attempt_number=1, evidence=evidence, artifacts=[], manifest={}
    )
    run = await _run_row(run_id)
    assert run.status == "COMPLETE"
    assert run.completed_at == evidence.completed_at
    assert SKIP_LIMITATION_ID not in run.limitations
    attempts = await _attempt_rows(run_id)
    assert attempts[0].status == "COMPLETE"

    # A window whose run finished normally is COMPLETE (not FAILED, not SKIPPED).
    session_factory = get_session_factory()
    async with session_factory() as session:
        window = await session.get(CheckpointWindow, window_id)
        assert window is not None
        assert window.status in ("COMPLETE", "PARTIAL")


@pytest.mark.asyncio
async def test_window_of_only_skipped_runs_is_complete() -> None:
    """A window whose scheduled runs are all terminal non-ERROR (SKIPPED) is
    COMPLETE — orchestration completed even though nothing was observed."""
    tenant_id = await _create_tenant("window-skip")
    site_id = await _create_runnable_site(tenant_id=tenant_id, monitoring_state="ON")
    now = datetime.now(UTC)
    window_id, _run_id, _monitored_url_id = await _create_scheduled_run(
        tenant_id=tenant_id, site_id=site_id, scheduled_for=now - timedelta(minutes=5)
    )

    async def _run_window() -> None:
        session_factory = get_session_factory()
        async with session_factory() as session, session.begin():
            await CheckpointRepository._refresh_window_status(session, window_id, datetime.now(UTC))

    await _run_window()

    session_factory = get_session_factory()
    async with session_factory() as session, session.begin():
        run = await session.scalar(
            select(CheckpointRun).where(CheckpointRun.checkpoint_window_id == window_id)
        )
        assert run is not None
        run.status = "SKIPPED"
        run.completed_at = now
        run.limitations = [SKIP_LIMITATION_ID]
    await _run_window()

    session_factory = get_session_factory()
    async with session_factory() as session:
        window = await session.get(CheckpointWindow, window_id)
        assert window is not None
        assert window.status == "COMPLETE"


@pytest.mark.asyncio
async def test_diagnostic_run_is_unaffected_by_gate3_when_off() -> None:
    """A DIAGNOSTIC run against a disabled site begins normally (never SKIPPED)."""
    tenant_id = await _create_tenant("diagnostic")
    site_id = await _create_runnable_site(tenant_id=tenant_id, monitoring_state="OFF")
    now = datetime.now(UTC)
    _window_id, run_id, _monitored_url_id = await _create_scheduled_run(
        tenant_id=tenant_id,
        site_id=site_id,
        scheduled_for=now - timedelta(minutes=5),
        observation_kind="DIAGNOSTIC",
        trigger_source="OPERATOR_UI",
        trigger_correlation_id=uuid.uuid4(),
    )
    repository = CheckpointRepository(get_session_factory())
    target = await repository.begin_attempt(
        tenant_id=tenant_id, checkpoint_run_id=run_id, attempt_number=1
    )
    assert target.checkpoint_run_id == run_id
    run = await _run_row(run_id)
    assert run.status == "RUNNING"


@pytest.mark.asyncio
async def test_concurrent_disable_vs_preflight_is_truthful() -> None:
    """R3/R4 serialize on the site row lock: the outcome is either a normal
    RUNNING begin or an atomic SKIPPED, never a contradiction."""
    tenant_id = await _create_tenant("r3-concurrent")
    site_id = await _create_runnable_site(tenant_id=tenant_id, monitoring_state="ON")
    now = datetime.now(UTC)
    _window_id, run_id, _monitored_url_id = await _create_scheduled_run(
        tenant_id=tenant_id, site_id=site_id, scheduled_for=now - timedelta(minutes=5)
    )
    repository = CheckpointRepository(get_session_factory())

    results = await asyncio.gather(
        repository.begin_attempt(tenant_id=tenant_id, checkpoint_run_id=run_id, attempt_number=1),
        _set_state(site_id, tenant_id, enabled=False),
        return_exceptions=True,
    )
    skipped = any(isinstance(r, CheckpointSkippedError) for r in results)
    normal = any(isinstance(r, BrowserTarget) for r in results)
    assert (skipped or normal) and not (skipped and normal)
    run = await _run_row(run_id)
    if normal:
        assert run.status == "RUNNING"
    else:
        assert run.status == "SKIPPED"
        assert SKIP_LIMITATION_ID in run.limitations


@pytest.mark.asyncio
async def test_re_enable_does_not_backfill_past_window() -> None:
    """EP-030 M2: disabling then re-enabling creates a new authorization
    watermark; a candidate window that is not strictly after that watermark must
    not materialize (no backfill of the disable-era window)."""
    tenant_id = await _create_tenant("re-enable")
    site_id = await _create_runnable_site(tenant_id=tenant_id, monitoring_state="ON")
    # Turn OFF then re-enable, landing the watermark inside a six-hour window.
    await _set_state(site_id, tenant_id, enabled=False)
    session_factory = get_session_factory()
    async with session_factory() as session, session.begin():
        await session.execute(
            update(Site)
            .where(Site.id == site_id)
            .values(
                monitoring_state="ON",
                monitoring_state_updated_at=datetime(2026, 3, 5, 14, 10, tzinfo=UTC),
            )
        )
    scheduler = CheckpointSchedulingService(
        get_session_factory(), JobQueue(get_session_factory()), _settings()
    )
    # Tick inside the still-current 12:00-18:00 window: window_start (12:00) is
    # not strictly after the 14:10 re-enable watermark -> nothing materialized.
    bounds = resolve_six_hour_window(datetime(2026, 3, 5, 16, 0, tzinfo=UTC), "UTC")
    async with session_factory() as session:
        site = await session.get(Site, site_id)
        assert site is not None
        materialized = await scheduler._materialize_site(
            site, bounds, datetime(2026, 3, 5, 16, 0, tzinfo=UTC)
        )
    assert materialized == []
    async with session_factory() as session:
        assert (
            await session.scalar(
                select(func.count(CheckpointWindow.id)).where(CheckpointWindow.site_id == site_id)
            )
        ) == 0


@pytest.mark.asyncio
async def test_monitoring_control_is_tenant_independent() -> None:
    """Disabling a site in one tenant must not suppress scheduling for an ON
    site in a different tenant (server-side tenant isolation of GATE-1)."""
    tenant_a = await _create_tenant("tenant-a")
    tenant_b = await _create_tenant("tenant-b")
    site_a = await _create_runnable_site(tenant_id=tenant_a, monitoring_state="ON")
    site_b = await _create_runnable_site(tenant_id=tenant_b, monitoring_state="ON")
    watermark = datetime(2025, 6, 1, 0, 0, tzinfo=UTC)
    await _set_watermark(site_a, watermark)
    await _set_watermark(site_b, watermark)
    await _set_state(site_a, tenant_a, enabled=False)  # OFF only in tenant A

    scheduler = CheckpointSchedulingService(
        get_session_factory(), JobQueue(get_session_factory()), _settings()
    )
    result = await scheduler.schedule_due(now=datetime(2026, 3, 5, 18, 0, tzinfo=UTC))
    assert result.site_count == 1
    assert result.run_count >= 1
    session_factory = get_session_factory()
    async with session_factory() as session:
        a_windows = int(
            await session.scalar(
                select(func.count(CheckpointWindow.id)).where(CheckpointWindow.site_id == site_a)
            )
        )
        b_windows = int(
            await session.scalar(
                select(func.count(CheckpointWindow.id)).where(CheckpointWindow.site_id == site_b)
            )
        )
    assert a_windows == 0
    assert b_windows >= 1
    assert await _job_rows(tenant_b, "BROWSER_CHECKPOINT") != []
    assert await _job_rows(tenant_a, "BROWSER_CHECKPOINT") == []


@pytest.mark.asyncio
async def test_skipped_run_does_not_displace_genuine_health_observation() -> None:
    """EP-030 M2: an administrative SKIPPED run carries no observation and must
    not become the latest source-health row — the last genuine COMPLETE run
    keeps determining BROWSER_MONITORING health."""
    from app.api.product import _source_health_rows

    tenant_id = await _create_tenant("health-skip")
    site_id = await _create_runnable_site(tenant_id=tenant_id, monitoring_state="ON")
    now = datetime.now(UTC)
    # A genuine COMPLETE observation at T0.
    _window_id, complete_run_id, _monitored_url_id = await _create_scheduled_run(
        tenant_id=tenant_id, site_id=site_id, scheduled_for=now - timedelta(minutes=20)
    )
    # A later administrative SKIPPED run (crash/redelivery style) that must not
    # displace the genuine observation.
    _skip_window, skipped_run_id, _monitored_url_id = await _create_scheduled_run(
        tenant_id=tenant_id, site_id=site_id, scheduled_for=now - timedelta(minutes=10)
    )
    session_factory = get_session_factory()
    async with session_factory() as session, session.begin():
        complete_run = await session.get(CheckpointRun, complete_run_id)
        assert complete_run is not None
        complete_run.status = "COMPLETE"
        complete_run.started_at = now - timedelta(minutes=20)
        complete_run.completed_at = now - timedelta(minutes=18)
        skipped_run = await session.get(CheckpointRun, skipped_run_id)
        assert skipped_run is not None
        skipped_run.status = "SKIPPED"
        skipped_run.started_at = now - timedelta(minutes=10)
        skipped_run.completed_at = now - timedelta(minutes=10)
        skipped_run.limitations = [SKIP_LIMITATION_ID]

    async with session_factory() as session:
        health = await _source_health_rows(session, tenant_id=tenant_id, site_id=site_id)
    # The genuine observation wins; SKIPPED (started later) is excluded.
    assert health["BROWSER_MONITORING"] == "HEALTHY"


def _settings() -> Any:
    from app.config.settings import get_settings

    return get_settings()
