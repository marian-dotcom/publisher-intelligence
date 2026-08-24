"""EP-026 M3a-1: deterministic, hold-aware retention enforcement.

Enforces the canonical SECURITY.md §105-106 retention policy for
RAW_MEDIUM browser artifacts via one auditable execution per run:

- eligibility = retention_class + artifact_type + UTC age cutoff
  (screenshots ~90 days; raw DOM ~30 days);
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
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import delete, func, or_, select
from sqlalchemy.engine import CursorResult
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
    # Any RAW_MEDIUM artifact type whose canonical period has elapsed.
    return or_(
        *[
            (Artifact.artifact_type == artifact_type)
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

    async def enforce(self, *, now: datetime | None = None) -> EnforcementResult:
        now = now or datetime.now(UTC)
        run_id = await self._open_run(now)
        deleted_total = 0
        holds_skipped = await self._count_hold_conflicts(now)
        while True:
            candidates = await self._select_batch(now)
            if not candidates:
                break
            for _artifact_id, object_key in candidates:
                # Object deletion first; a failure propagates and leaves both
                # the artifact row and the run unfinished (retry is safe:
                # absent objects are idempotent for S3-compatible deletes).
                await asyncio.to_thread(self._storage.delete, key=object_key)
            deleted = await self._delete_rows([row_id for row_id, _ in candidates])
            deleted_total += deleted
        result = EnforcementResult(
            run_id=run_id,
            rows_deleted_per_table={"artifacts": deleted_total},
            hold_conflicts_skipped=holds_skipped,
        )
        await self._finish_run(result, now or datetime.now(UTC))
        return result

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

    async def _delete_rows(self, ids: Sequence[uuid.UUID]) -> int:
        async with self._session_factory() as session, session.begin():
            result = cast(
                "CursorResult[Any]",
                await session.execute(delete(Artifact).where(Artifact.id.in_(ids))),
            )
            return int(result.rowcount or 0)
