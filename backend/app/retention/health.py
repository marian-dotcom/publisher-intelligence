"""EP-026 M3a-1: retention scheduling + missed/stalled visibility."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Job
from app.jobs.queue import JobQueue
from app.retention.models import EXPECTED_WINDOW, RetentionRun

JOB_TYPE = "ENFORCE_RETENTION"
# Stall threshold for an open execution: well above one worker pass cycle.
STALL_THRESHOLD = timedelta(hours=6)


class RetentionSchedulingService:
    """Enqueue one deterministic daily enforcement job (global scope)."""

    def __init__(self, queue: JobQueue) -> None:
        self._queue = queue

    async def schedule_due(self, *, now: datetime | None = None) -> int:
        now = now or datetime.now(UTC)
        await self._queue.enqueue(
            job_type=JOB_TYPE,
            payload={},
            tenant_id=None,
            idempotency_key=f"enforce-retention:{now.strftime('%Y-%m-%d')}",
            priority=-20,
            max_attempts=3,
        )
        return 1


@dataclass(frozen=True, slots=True)
class RetentionHealth:
    """Deterministic answer to 'is retention silently stalled?'."""

    state: str  # HEALTHY | MISSED | STALLED | FAILED
    detail: str
    last_started_at: datetime | None = None
    last_finished_at: datetime | None = None


async def retention_health(
    session_factory: async_sessionmaker[AsyncSession], *, now: datetime | None = None
) -> RetentionHealth:
    """Resolve retention execution health from runs + job lifecycle.

    Precedence (deterministic):
    1. STALLED — an execution opened but never finished beyond the threshold;
    2. FAILED  — an ENFORCE_RETENTION job reached FAILED within the window;
    3. HEALTHY — a completed run exists within the expected window;
    4. MISSED  — otherwise (including never executed).
    """
    now = now or datetime.now(UTC)
    run: RetentionRun | None
    async with session_factory() as session:
        run = await session.scalar(
            select(RetentionRun).order_by(RetentionRun.started_at.desc()).limit(1)
        )
        latest_failed_finished_at: datetime | None = await session.scalar(
            select(Job.finished_at)
            .where(
                Job.job_type == JOB_TYPE,
                Job.status == "FAILED",
                Job.finished_at.is_not(None),
                Job.finished_at >= now - EXPECTED_WINDOW,
            )
            .order_by(Job.finished_at.desc())
            .limit(1)
        )
    last_finished = run.finished_at if run else None
    if run is not None and run.finished_at is None and run.started_at is not None:
        if now - run.started_at > STALL_THRESHOLD:
            return RetentionHealth(
                state="STALLED",
                detail=f"retention run {run.id} started but never finished",
                last_started_at=run.started_at,
            )
    if latest_failed_finished_at is not None and (
        last_finished is None or latest_failed_finished_at > last_finished
    ):
        # The most recent observable outcome was an exhausted failure.
        return RetentionHealth(
            state="FAILED",
            detail="recent ENFORCE_RETENTION job exhausted its attempts",
            last_started_at=run.started_at if run else None,
            last_finished_at=last_finished,
        )
    if last_finished is not None and now - last_finished <= EXPECTED_WINDOW:
        return RetentionHealth(
            state="HEALTHY",
            detail="retention executed within the expected window",
            last_started_at=run.started_at,
            last_finished_at=last_finished,
        )
    return RetentionHealth(
        state="MISSED",
        detail="no completed retention execution within the expected window",
        last_started_at=run.started_at if run else None,
        last_finished_at=last_finished,
    )
