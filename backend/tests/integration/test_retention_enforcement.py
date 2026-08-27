"""EP-026 M3a-1 — retention enforcement + auditable execution proof.

Production chain under test: RetentionSchedulingService → ENFORCE_RETENTION
job → queue.claim → real worker handle_job → RetentionService → S3 delete →
DB delete → append-only retention_runs record.
"""

import asyncio
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from sqlalchemy import select

from app.browser.models import Artifact
from app.config.settings import get_settings
from app.db.models import Job
from app.db.session import get_session_factory
from app.incidents.models import RetentionHold
from app.jobs.queue import JobQueue
from app.retention.health import retention_health
from app.retention.models import RetentionRun
from app.retention.scheduling import JOB_TYPE, RetentionSchedulingService
from app.retention.service import RetentionService
from app.storage.s3 import S3Storage

pytestmark = pytest.mark.integration

EXPIRED_CUTOFF_DAYS = 400  # beyond every RAW_MEDIUM policy period


def _storage() -> S3Storage:
    return S3Storage(get_settings())


def _service(storage: S3Storage | None = None) -> RetentionService:
    return RetentionService(get_session_factory(), storage or _storage())


async def _seed_chain(slug: str) -> dict[str, uuid.UUID]:
    from tests.integration.product.factories import seed_diagnostic_event_chain

    seeded = await seed_diagnostic_event_chain(slug=slug)
    return {
        "tenant_id": cast(uuid.UUID, seeded["tenant_id"]),
        "site_id": cast(uuid.UUID, seeded["site_id"]),
        "run_id": cast(uuid.UUID, seeded["diagnostic_run_id"]),
        "baseline_run_id": cast(uuid.UUID, seeded["baseline_run_id"]),
    }


def _seed_artifact(
    ids: dict[str, uuid.UUID],
    *,
    artifact_type: str,
    retention_class: str,
    age_days: int,
    run_key: str = "run_id",
) -> tuple[uuid.UUID, str]:
    """Insert an expired/fresh Artifact row and a real object in test storage."""
    factory = get_session_factory()
    storage = _storage()
    created_at = datetime.now(UTC) - timedelta(days=age_days)
    key = f"retention-test/{uuid.uuid4()}/{artifact_type}.bin"
    storage.put_bytes(
        key=key, content=b"retention-fixture", content_type="application/octet-stream"
    )

    async def insert() -> uuid.UUID:
        async with factory() as session, session.begin():
            artifact_id = uuid.uuid4()
            session.add(
                Artifact(
                    id=artifact_id,
                    tenant_id=ids["tenant_id"],
                    site_id=ids["site_id"],
                    checkpoint_run_id=ids[run_key],
                    artifact_type=artifact_type,
                    storage_provider="S3_COMPATIBLE",
                    object_key=key,
                    content_type="application/octet-stream",
                    byte_size=16,
                    sha256="a" * 64,
                    retention_class=retention_class,
                    created_at=created_at,
                    metadata_json={},
                )
            )
            return artifact_id

    return asyncio.run(insert()), key


def _seed_hold(
    ids: dict[str, uuid.UUID], artifact_id: uuid.UUID, *, released: bool = False
) -> uuid.UUID:
    factory = get_session_factory()

    async def act() -> uuid.UUID:
        async with factory() as session, session.begin():
            hold_id = uuid.uuid4()
            session.add(
                RetentionHold(
                    id=hold_id,
                    tenant_id=ids["tenant_id"],
                    incident_id=None,
                    artifact_id=artifact_id,
                    source_extract_id=None,
                    reason="test-hold",
                    released_at=datetime.now(UTC) if released else None,
                )
            )
            return hold_id

    return asyncio.run(act())


def _object_exists(key: str) -> bool:
    storage = _storage()
    try:
        storage.head(key=key)
        return True
    except Exception:
        return False


def _artifact_exists(artifact_id: uuid.UUID) -> bool:
    async def act() -> bool:
        factory = get_session_factory()
        async with factory() as session:
            return (
                await session.scalar(select(Artifact.id).where(Artifact.id == artifact_id))
                is not None
            )

    return asyncio.run(act())


def _runs() -> list[RetentionRun]:
    async def act() -> list[RetentionRun]:
        factory = get_session_factory()
        async with factory() as session:
            return list((await session.scalars(select(RetentionRun))).all())

    return asyncio.run(act())


def _process_retention_job() -> bool:
    """Claim and process one ENFORCE_RETENTION job via the real worker."""
    from app.worker import handle_job

    async def act() -> bool:
        factory = get_session_factory()
        queue = JobQueue(factory)
        lease = await queue.claim(worker_id="retention-test", lease_seconds=60)
        if lease is None or lease.job_type != JOB_TYPE:
            return False
        await handle_job(
            queue,
            lease,
            1,
            None,
            None,
            None,
            None,
            None,
            None,
            _service(),
        )
        return True

    return asyncio.run(act())


@pytest.fixture()
def _chain() -> dict[str, uuid.UUID]:
    return asyncio.run(_seed_chain(f"m3a-{uuid.uuid4().hex[:8]}"))


def test_full_production_enforcement_chain(_chain: dict[str, uuid.UUID]) -> None:
    expired_id, expired_key = _seed_artifact(
        _chain,
        artifact_type="RAW_DOM",
        retention_class="RAW_MEDIUM",
        age_days=EXPIRED_CUTOFF_DAYS,
    )
    held_id, held_key = _seed_artifact(
        _chain,
        artifact_type="SCREENSHOT_FULL_PAGE",
        retention_class="RAW_MEDIUM",
        age_days=EXPIRED_CUTOFF_DAYS,
    )
    _seed_hold(_chain, held_id)
    fresh_id, fresh_key = _seed_artifact(
        _chain,
        artifact_type="RAW_DOM",
        retention_class="RAW_MEDIUM",
        age_days=1,
        run_key="baseline_run_id",
    )
    protected_id, protected_key = _seed_artifact(
        _chain,
        artifact_type="NORMALIZED_DOM",
        retention_class="CORE_LONG",
        age_days=EXPIRED_CUTOFF_DAYS,
        run_key="baseline_run_id",
    )
    assert len(_runs()) == 0

    # Deterministic daily scheduling.
    job_count = asyncio.run(
        RetentionSchedulingService(JobQueue(get_session_factory())).schedule_due()
    )
    assert job_count == 1

    # Real worker processes the queued enforcement job.
    assert _process_retention_job() is True

    # A. Expired unheld artifact: object + row deleted.
    assert not _object_exists(expired_key)
    assert not _artifact_exists(expired_id)
    # B. Held artifact fully preserved.
    assert _object_exists(held_key)
    assert _artifact_exists(held_id)
    # C. Fresh artifact preserved.
    assert _object_exists(fresh_key)
    assert _artifact_exists(fresh_id)
    # CORE_LONG evidence never eligible.
    assert _object_exists(protected_key)
    assert _artifact_exists(protected_id)

    runs = _runs()
    assert len(runs) == 1
    run = runs[0]
    assert run.started_at is not None
    assert run.finished_at is not None
    assert run.rows_deleted_per_table == {"artifacts": 1}
    assert run.hold_conflicts_skipped == 1


def test_scheduler_dedupes_per_day(_chain: dict[str, uuid.UUID]) -> None:
    service = RetentionSchedulingService(JobQueue(get_session_factory()))
    first = asyncio.run(service.schedule_due())
    second = asyncio.run(service.schedule_due())
    assert (first, second) == (1, 1)

    async def count_jobs() -> int:
        factory = get_session_factory()
        async with factory() as session:
            return len((await session.scalars(select(Job).where(Job.job_type == JOB_TYPE))).all())

    assert asyncio.run(count_jobs()) == 1


def test_second_execution_is_idempotent_and_appends_audit(_chain: dict[str, uuid.UUID]) -> None:
    expired_id, expired_key = _seed_artifact(
        _chain,
        artifact_type="RAW_DOM",
        retention_class="RAW_MEDIUM",
        age_days=EXPIRED_CUTOFF_DAYS,
    )
    service = _service()
    asyncio.run(service.enforce())
    assert not _object_exists(expired_key)
    assert not _artifact_exists(expired_id)

    result = asyncio.run(service.enforce())
    assert result.rows_deleted_per_table == {"artifacts": 0}
    assert result.hold_conflicts_skipped == 0
    assert len(_runs()) == 2  # append-only audit history retained


def test_object_deletion_failure_leaves_row_and_unfinished_run(
    _chain: dict[str, uuid.UUID],
) -> None:
    expired_id, expired_key = _seed_artifact(
        _chain,
        artifact_type="RAW_DOM",
        retention_class="RAW_MEDIUM",
        age_days=EXPIRED_CUTOFF_DAYS,
    )

    class FailingStorage(S3Storage):
        def delete(self, *, key: str) -> None:
            raise RuntimeError("simulated storage outage")

    failing_service = _service(FailingStorage(get_settings()))
    with pytest.raises(RuntimeError, match="simulated storage outage"):
        asyncio.run(failing_service.enforce())

    # DB row remains; no false success record.
    assert _artifact_exists(expired_id)
    assert _object_exists(expired_key)
    runs = _runs()
    assert len(runs) == 1
    assert runs[0].finished_at is None


def test_retention_health_states(_chain: dict[str, uuid.UUID]) -> None:
    from app.retention.models import EXPECTED_WINDOW

    factory = get_session_factory()

    # MISSED: nothing has ever executed.
    health = asyncio.run(retention_health(factory))
    assert health.state == "MISSED"

    # STALLED: the only/latest execution opened but never finished.
    stale_started = datetime.now(UTC) - timedelta(hours=12)

    def add_stale_run() -> uuid.UUID:
        from app.retention.models import RetentionRun as Run

        stale_run_id = uuid.uuid4()

        async def insert() -> None:
            async with factory() as session, session.begin():
                session.add(Run(id=stale_run_id, started_at=stale_started))

        asyncio.run(insert())
        return stale_run_id

    stale_run_id = add_stale_run()
    health = asyncio.run(retention_health(factory))
    assert health.state == "STALLED"

    # FAILED: once the stale run resolves outside the window, a recent
    # exhausted ENFORCE_RETENTION job dominates.
    async def resolve_run_and_fail_job() -> None:
        async with factory() as session, session.begin():
            run = await session.get(RetentionRun, stale_run_id)
            assert run is not None
            run.finished_at = datetime.now(UTC) - EXPECTED_WINDOW - timedelta(days=1)
            session.add(
                Job(
                    id=uuid.uuid4(),
                    job_type=JOB_TYPE,
                    payload={},
                    status="FAILED",
                    attempt=3,
                    max_attempts=3,
                    finished_at=datetime.now(UTC),
                    last_error_class="RETENTION_RUNTIME_ERROR",
                )
            )

    asyncio.run(resolve_run_and_fail_job())
    health = asyncio.run(retention_health(factory))
    assert health.state == "FAILED"

    # HEALTHY: a fresh completed execution dominates again.
    service = _service()
    result = asyncio.run(service.enforce())

    async def touch() -> None:
        async with factory() as session, session.begin():
            run = await session.get(RetentionRun, result.run_id)
            assert run is not None
            if run.finished_at is None:
                run.finished_at = datetime.now(UTC)

    asyncio.run(touch())
    health = asyncio.run(retention_health(factory))
    assert health.state == "HEALTHY"


def test_core_long_managed_type_is_never_deleted(_chain: dict[str, uuid.UUID]) -> None:
    """Defect-A regression: a retention-managed artifact_type with CORE_LONG
    class must NEVER be eligible, regardless of age."""
    dom_id, dom_key = _seed_artifact(
        _chain,
        artifact_type="RAW_DOM",
        retention_class="CORE_LONG",
        age_days=EXPIRED_CUTOFF_DAYS,
    )
    shot_id, shot_key = _seed_artifact(
        _chain,
        artifact_type="SCREENSHOT_VIEWPORT",
        retention_class="CORE_LONG",
        age_days=EXPIRED_CUTOFF_DAYS,
        run_key="baseline_run_id",
    )
    result = asyncio.run(_service().enforce())
    assert _object_exists(dom_key)
    assert _artifact_exists(dom_id)
    assert _object_exists(shot_key)
    assert _artifact_exists(shot_id)
    assert result.rows_deleted_per_table == {"artifacts": 0}


def test_hold_created_after_selection_protects_artifact(
    _chain: dict[str, uuid.UUID],
) -> None:
    """Defect-B regression: an ACTIVE RetentionHold that appears after batch
    selection must still prevent both object and DB deletion."""
    artifact_id, object_key = _seed_artifact(
        _chain,
        artifact_type="RAW_DOM",
        retention_class="RAW_MEDIUM",
        age_days=EXPIRED_CUTOFF_DAYS,
    )
    raced: list[uuid.UUID] = []

    async def inject_late_hold(candidate_ids: Sequence[uuid.UUID]) -> None:
        factory = get_session_factory()
        raced.extend(candidate_ids)
        for candidate_id in candidate_ids:
            async with factory() as session, session.begin():
                session.add(
                    RetentionHold(
                        id=uuid.uuid4(),
                        tenant_id=_chain["tenant_id"],
                        incident_id=None,
                        artifact_id=candidate_id,
                        source_extract_id=None,
                        reason="race-hold",
                        released_at=None,
                    )
                )

    result = asyncio.run(_service().enforce(_after_selection=inject_late_hold))
    assert raced == [artifact_id]
    # Protected despite the hold appearing after selection.
    assert _object_exists(object_key)
    assert _artifact_exists(artifact_id)
    assert result.rows_deleted_per_table == {"artifacts": 0}
    assert result.hold_conflicts_skipped >= 1


def test_supported_policy_types_are_explicit(_chain: dict[str, uuid.UUID]) -> None:
    """Unknown RAW_MEDIUM artifact types are never eligible: eligibility is
    keyed by the explicit canonical policy table only."""
    from app.retention.service import RAW_MEDIUM_POLICY_DAYS

    assert set(RAW_MEDIUM_POLICY_DAYS) == {
        "SCREENSHOT_VIEWPORT",
        "SCREENSHOT_VIEWPORT_PRECONSENT",
        "SCREENSHOT_VIEWPORT_POSTCONSENT",
        "SCREENSHOT_FULL_PAGE",
        "RAW_DOM",
    }
    unknown_type_id, unknown_type_key = _seed_artifact(
        _chain,
        artifact_type="SOME_FUTURE_RAW_TYPE",
        retention_class="RAW_MEDIUM",
        age_days=EXPIRED_CUTOFF_DAYS,
    )
    result = asyncio.run(_service().enforce())
    assert _object_exists(unknown_type_key)
    assert _artifact_exists(unknown_type_id)
    assert result.rows_deleted_per_table == {"artifacts": 0}


def _remaining(ids: list[uuid.UUID]) -> list[uuid.UUID]:
    return [artifact_id for artifact_id in ids if _artifact_exists(artifact_id)]


def _seed_expired_backlog(
    ids: dict[str, uuid.UUID],
    *,
    count: int,
) -> tuple[list[uuid.UUID], list[str]]:
    """Bulk-seed `count` eligible expired RAW_MEDIUM artifacts, each with a
    real stored object and its own checkpoint run (satisfies the
    artifacts(checkpoint_run_id, artifact_type) unique constraint)."""
    from datetime import timedelta

    from app.browser.models import CheckpointRun, CheckpointWindow

    factory = get_session_factory()
    storage = _storage()
    created_at = datetime.now(UTC) - timedelta(days=EXPIRED_CUTOFF_DAYS)
    canonical_types = [
        "SCREENSHOT_VIEWPORT",
        "SCREENSHOT_VIEWPORT_PRECONSENT",
        "SCREENSHOT_VIEWPORT_POSTCONSENT",
        "SCREENSHOT_FULL_PAGE",
        "RAW_DOM",
    ]
    artifact_ids: list[uuid.UUID] = []
    object_keys: list[str] = []

    async def insert() -> None:
        async with factory() as session, session.begin():
            base = await session.get(CheckpointRun, ids["run_id"])
            assert base is not None
            windows: list[CheckpointWindow] = []
            runs: list[CheckpointRun] = []
            rows: list[dict[str, Any]] = []
            for index in range(count):
                window_id, run_id, artifact_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
                scheduled_for = base.scheduled_for + timedelta(seconds=index + 1)
                windows.append(
                    CheckpointWindow(
                        id=window_id,
                        tenant_id=base.tenant_id,
                        site_id=base.site_id,
                        scheduled_for=scheduled_for,
                        window_start=scheduled_for,
                        window_end=scheduled_for,
                    )
                )
                runs.append(
                    CheckpointRun(
                        id=run_id,
                        tenant_id=base.tenant_id,
                        site_id=base.site_id,
                        checkpoint_window_id=window_id,
                        monitored_url_id=base.monitored_url_id,
                        template_id=base.template_id,
                        scenario_id=base.scenario_id,
                        observation_kind="SCHEDULED",
                        scheduled_for=scheduled_for,
                        status="COMPLETE",
                    )
                )
                key = f"retention-test/{artifact_id}/backlog.bin"
                storage.put_bytes(
                    key=key, content=b"retention-backlog", content_type="application/octet-stream"
                )
                rows.append(
                    {
                        "id": artifact_id,
                        "tenant_id": ids["tenant_id"],
                        "site_id": ids["site_id"],
                        "checkpoint_run_id": run_id,
                        "artifact_type": canonical_types[index % len(canonical_types)],
                        "storage_provider": "S3_COMPATIBLE",
                        "object_key": key,
                        "content_type": "application/octet-stream",
                        "byte_size": 16,
                        "sha256": "a" * 64,
                        "retention_class": "RAW_MEDIUM",
                        "created_at": created_at,
                        "metadata_json": {},
                    }
                )
            # Flush per dependency level: keeps FK insert ordering explicit.
            session.add_all(windows)
            await session.flush()
            session.add_all(runs)
            await session.flush()
            session.add_all([Artifact(**row) for row in rows])
            artifact_ids.extend(cast(uuid.UUID, row["id"]) for row in rows)
            object_keys.extend(str(row["object_key"]) for row in rows)

    asyncio.run(insert())
    return artifact_ids, object_keys


def test_backlog_larger_than_batch_size_drains_in_one_execution(
    _chain: dict[str, uuid.UUID],
) -> None:
    """Defect-C regression: one ENFORCE_RETENTION execution must drain the
    eligible unheld backlog beyond BATCH_SIZE via repeated bounded batches —
    BATCH_SIZE is a per-batch safety bound, never a per-run cap."""
    from app.retention.health import retention_health
    from app.retention.service import BATCH_SIZE

    seeded_count = BATCH_SIZE + 5
    seeded_ids, seeded_keys = _seed_expired_backlog(_chain, count=seeded_count)
    assert len(seeded_ids) == seeded_count
    assert len(_runs()) == 0

    result = asyncio.run(_service().enforce())

    # Every eligible artifact deleted in the SAME execution.
    assert result.rows_deleted_per_table == {"artifacts": seeded_count}
    assert _remaining(seeded_ids) == []
    assert not any(_object_exists(key) for key in seeded_keys)

    # No eligible unheld expired backlog remains.
    async def eligible_unheld_backlog() -> int:
        from sqlalchemy import func

        from app.retention.service import _active_hold_clause, _eligible_conditions

        factory = get_session_factory()
        async with factory() as session:
            count = await session.scalar(
                select(func.count())
                .select_from(Artifact)
                .where(_eligible_conditions(datetime.now(UTC)), ~_active_hold_clause())
            )
            return int(count or 0)

    assert asyncio.run(eligible_unheld_backlog()) == 0

    # Exactly one run belongs to this enforce() call, successfully finished.
    runs = _runs()
    assert len(runs) == 1
    run = runs[0]
    assert run.finished_at is not None
    assert run.started_at is not None
    assert run.finished_at >= run.started_at
    assert run.rows_deleted_per_table == {"artifacts": seeded_count}
    assert run.hold_conflicts_skipped == 0

    # Drained execution backed by HEALTHY retention health.
    health = asyncio.run(retention_health(get_session_factory()))
    assert health.state == "HEALTHY"


def test_large_backlog_with_active_hold_deletes_only_unheld(
    _chain: dict[str, uuid.UUID],
) -> None:
    """More than BATCH_SIZE eligible rows with pre-existing ACTIVE holds:
    every unheld artifact drains, held rows/objects/holds survive, and the
    hold count stays truthful (each held artifact counted exactly once)."""
    from app.retention.service import BATCH_SIZE

    seeded_count = BATCH_SIZE + 10
    seeded_ids, seeded_keys = _seed_expired_backlog(_chain, count=seeded_count)
    held_ids = seeded_ids[:2]
    for held_id in held_ids:
        _seed_hold(_chain, held_id)
    unheld_ids = [aid for aid in seeded_ids if aid not in held_ids]

    result = asyncio.run(_service().enforce())

    assert result.rows_deleted_per_table == {"artifacts": len(unheld_ids)}
    assert _remaining(unheld_ids) == []
    # Held artifacts fully preserved.
    assert sorted(_remaining(held_ids)) == sorted(held_ids)
    for held_id in held_ids:
        key = seeded_keys[seeded_ids.index(held_id)]
        assert _object_exists(key)

    async def active_holds() -> int:
        factory = get_session_factory()
        async with factory() as session:
            holds = await session.scalars(
                select(RetentionHold).where(RetentionHold.released_at.is_(None))
            )
            return len(holds.all())

    assert asyncio.run(active_holds()) == 2
    # Truthful, non-duplicated count: only the two pre-selection holds.
    assert result.hold_conflicts_skipped == 2

    run = _runs()[-1]
    assert run.finished_at is not None
    assert run.rows_deleted_per_table == {"artifacts": len(unheld_ids)}
    assert run.hold_conflicts_skipped == 2


def test_hold_conflicts_not_double_counted_across_batches(
    _chain: dict[str, uuid.UUID],
) -> None:
    """Execution-level truthful hold count under repeated batches: pre-existing
    holds counted once via the initial count; late holds counted once when
    encountered; no per-iteration recalculation duplicates either."""
    from app.retention.service import BATCH_SIZE, RetentionService

    seeded_count = BATCH_SIZE + 5
    seeded_ids, _ = _seed_expired_backlog(_chain, count=seeded_count)
    pre_held = seeded_ids[0]
    _seed_hold(_chain, pre_held)
    late_held = set(seeded_ids[1:4])  # injected as late holds after batch 1
    injected: set[uuid.UUID] = set()

    async def inject_late_holds(candidate_ids: Sequence[uuid.UUID]) -> None:
        factory = get_session_factory()
        for candidate_id in candidate_ids:
            if candidate_id not in late_held or candidate_id in injected:
                continue
            injected.add(candidate_id)
            async with factory() as session, session.begin():
                session.add(
                    RetentionHold(
                        id=uuid.uuid4(),
                        tenant_id=_chain["tenant_id"],
                        incident_id=None,
                        artifact_id=candidate_id,
                        source_extract_id=None,
                        reason="late-hold",
                        released_at=None,
                    )
                )

    service = RetentionService(get_session_factory(), _storage())
    result = asyncio.run(service.enforce(_after_selection=inject_late_holds))

    expected_deleted = seeded_count - 1 - len(late_held)
    assert result.rows_deleted_per_table == {"artifacts": expected_deleted}
    # Exactly pre-holds + late-holds, each counted once.
    assert result.hold_conflicts_skipped == 1 + len(late_held)
    assert sorted(_remaining(sorted(late_held))) == sorted(late_held)
    assert _artifact_exists(pre_held)


def test_successful_run_records_truthful_finished_at(
    _chain: dict[str, uuid.UUID],
) -> None:
    """Defect-D regression: finished_at must be a fresh completion timestamp,
    strictly distinguishable from started_at — never the reused start value.
    Real work (hold count + selection queries) separates the two reads."""
    before = datetime.now(UTC)
    result = asyncio.run(_service().enforce())
    completed_after = datetime.now(UTC)

    run = next(r for r in _runs() if r.id == result.run_id)
    assert run.finished_at is not None
    assert run.started_at is not None
    assert before <= run.started_at
    assert run.finished_at <= completed_after
    assert run.finished_at > run.started_at
