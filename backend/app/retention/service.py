"""EP-026 M3a-1: deterministic, hold-aware retention enforcement.

Enforces the canonical SECURITY.md §105-106 retention policy for
RAW_MEDIUM browser artifacts via one auditable execution per run:

- eligibility = retention_class + artifact_type + UTC age cutoff
  (screenshots ~90 days; raw DOM ~30 days);
- one execution drains the full eligible unheld backlog via repeated
  bounded batches (BATCH_SIZE bounds each query, not the run);
- active RetentionHold always prevents deletion (counted as skipped);
- object-store deletion happens BEFORE DB row deletion and must succeed
  (absent objects are idempotently acceptable) before any row is removed;
- every execution opens a RetentionRun at start; finished_at is set only
  on successful completion — an unfinished run truthfully represents an
  incomplete/failed execution whose error detail lives in the job
  lifecycle. No fake success records.
"""

import asyncio
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.elements import ColumnElement

from app.browser.models import Artifact
from app.incidents.models import RetentionHold
from app.retention.models import RetentionRun
from app.storage.s3 import S3Storage

# Deterministic bounded batch: no table-wide destructive statements.
BATCH_SIZE = 50

# Canonical policy (SECURITY.md §106): RAW_MEDIUM screenshots ~90 days,
# raw top-level DOM ~30 days. Keyed by artifact_type because RAW_MEDIUM
# alone does not distinguish the two periods.
RAW_MEDIUM_POLICY_DAYS: dict[str, int] = {
    "SCREENSHOT_VIEWPORT": 90,
    "SCREENSHOT_VIEWPORT_PRECONSENT": 90,
    "SCREENSHOT_VIEWPORT_POSTCONSENT": 90,
    "SCREENSHOT_FULL_PAGE": 90,
    "RAW_DOM": 30,
}


@dataclass(frozen=True, slots=True)
class EnforcementResult:
    run_id: uuid.UUID
    rows_deleted_per_table: dict[str, int]
    hold_conflicts_skipped: int


def _eligible_conditions(now: datetime) -> ColumnElement[bool]:
    # Eligibility requires ALL of: canonical RAW_MEDIUM retention class, a
    # supported artifact_type (unknown types are never eligible), and its
    # artifact-type-specific UTC age cutoff (SECURITY.md §106).
    return or_(
        *[
            (Artifact.retention_class == "RAW_MEDIUM")
            & (Artifact.artifact_type == artifact_type)
            & (Artifact.created_at.is_not(None))
            & (Artifact.created_at <= now - timedelta(days=days))
            for artifact_type, days in RAW_MEDIUM_POLICY_DAYS.items()
        ]
    )


def _active_hold_clause() -> ColumnElement[bool]:
    return (
        select(RetentionHold.id)
        .where(
            RetentionHold.artifact_id == Artifact.id,
            RetentionHold.released_at.is_(None),
        )
        .exists()
    )


class RetentionService:
    """Hold-aware, batched, audited deletion of expired RAW_MEDIUM artifacts."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession], storage: S3Storage):
        self._session_factory = session_factory
        self._storage = storage

    async def enforce(
        self,
        *,
        now: datetime | None = None,
        _after_selection: Callable[[Sequence[uuid.UUID]], Awaitable[None]] | None = None,
    ) -> EnforcementResult:
        """Enforce retention.

        Drains the full eligible unheld backlog through repeated bounded
        batches: select at most BATCH_SIZE rows, safely finalize each one,
        repeat until selection is empty. BATCH_SIZE is a per-query safety
        bound, never a per-run or per-day deletion cap.

        ``_after_selection`` is a private, non-behavioral test seam invoked
        after each batch selection and before that batch's destructive
        finalization; production callers never pass it.
        """
        now = now or datetime.now(UTC)
        run_id = await self._open_run(now)
        deleted_total = 0
        # Execution-level truthful hold count: holds present before any
        # selection are counted ONCE here; holds that appear later are counted
        # exactly once when finalization encounters them. A held artifact is
        # excluded from all subsequent selections, so it can never be
        # encountered (or counted) twice.
        holds_skipped = await self._count_hold_conflicts(now)
        stalled_on: frozenset[uuid.UUID] | None = None
        while True:
            candidates = await self._select_batch(now)
            if not candidates:
                break
            candidate_ids = frozenset(artifact_id for artifact_id, _ in candidates)
            if stalled_on is not None and candidate_ids <= stalled_on:
                # Deterministic non-progress guard: every skipped artifact is
                # either held or already finalized, so _select_batch must
                # exclude it from the next batch. Re-selecting an identical
                # fully-skipped batch is therefore pathological — fail loudly
                # instead of looping forever (run stays unfinished).
                raise RuntimeError("retention enforcement made no progress")
            if _after_selection is not None:
                await _after_selection([artifact_id for artifact_id, _ in candidates])
            progressed = False
            for artifact_id, object_key in candidates:
                finalized = await self._finalize_artifact(artifact_id)
                if not finalized:
                    # State changed between selection and finalization (e.g. an
                    # active RetentionHold appeared): the artifact stays.
                    holds_skipped += 1
                    continue
                deleted_total += 1
                progressed = True
                del object_key  # object already deleted inside the locked finalize
            stalled_on = None if progressed else candidate_ids
        result = EnforcementResult(
            run_id=run_id,
            rows_deleted_per_table={"artifacts": deleted_total},
            hold_conflicts_skipped=holds_skipped,
        )
        # Fresh completion timestamp: never reuse the start-time value, so
        # successful runs truthfully record when execution actually finished.
        await self._finish_run(result, datetime.now(UTC))
        return result

    async def _finalize_artifact(self, artifact_id: uuid.UUID) -> bool:
        """Authoritative destructive finalization for one artifact.

        A single short transaction re-checks full eligibility (class + type +
        age) and absence of an active RetentionHold under a row lock, then
        deletes the stored object and the DB row before committing. The row
        lock conflicts with the FK key-share lock that a concurrent
        ``create_retention_hold`` requires, so a hold cannot become ACTIVE
        between this check and the committed deletion; a hold that commits
        first makes this check skip the artifact entirely.         A storage failure
        rolls everything back — the row survives and the run stays open.
        A hard crash between successful object deletion and this transaction's
        commit leaves row-present/object-absent; the next run re-selects the
        row and repairs it idempotently (absent-object deletes are safe), so
        no false audit count is ever produced.
        """
        async with self._session_factory() as session, session.begin():
            object_key = await session.scalar(
                select(Artifact.object_key)
                .where(
                    Artifact.id == artifact_id,
                    _eligible_conditions(datetime.now(UTC)),
                    ~_active_hold_clause(),
                )
                .with_for_update()
            )
            if object_key is None:
                return False
            await asyncio.to_thread(self._storage.delete, key=object_key)
            await session.execute(delete(Artifact).where(Artifact.id == artifact_id))
            return True

    async def _open_run(self, started_at: datetime) -> uuid.UUID:
        run_id = uuid.uuid4()
        async with self._session_factory() as session, session.begin():
            session.add(RetentionRun(id=run_id, started_at=started_at))
        return run_id

    async def _finish_run(self, result: EnforcementResult, finished_at: datetime) -> None:
        async with self._session_factory() as session, session.begin():
            run = await session.get(RetentionRun, result.run_id)
            if run is None:
                raise RuntimeError("retention run record vanished mid-execution")
            run.finished_at = finished_at
            run.rows_deleted_per_table = dict(result.rows_deleted_per_table)
            run.hold_conflicts_skipped = result.hold_conflicts_skipped

    async def _select_batch(self, now: datetime) -> list[tuple[uuid.UUID, str]]:
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(Artifact.id, Artifact.object_key)
                    .where(_eligible_conditions(now), ~_active_hold_clause())
                    .order_by(Artifact.created_at, Artifact.id)
                    .limit(BATCH_SIZE)
                )
            ).all()
        return [(row[0], row[1]) for row in rows]

    async def _count_hold_conflicts(self, now: datetime) -> int:
        async with self._session_factory() as session:
            count = await session.scalar(
                select(func.count())
                .select_from(Artifact)
                .where(_eligible_conditions(now), _active_hold_clause())
            )
            return int(count or 0)
