"""EP-026 M6: minimal self-observability over existing persisted truth.

Every signal is a deterministic read-time projection of data that already
survives restarts (jobs, retention runs, source-health projections). No new
persistence, no vendor, no global process state.

Signal map (signal -> source of truth -> derivation -> semantics):

- scheduler last-run age -> jobs.created_at (any enqueue is direct scheduler
  evidence) -> max(created_at) overall -> CURRENT within SCHEDULER_MAX_AGE
  (26h > the daily retention scheduling cadence plus margin).
- worker liveness -> jobs.started_at (a worker actually executing) ->
  max(started_at) -> CURRENT within WORKER_MAX_IDLE (48h; generous against
  the 6h browser / daily connector cadences). Old rows alone never prove
  health: age beyond the window reports STALE.
- queue depth/backlog -> jobs by status -> PENDING/RETRY are runnable;
  RUNNING with lock_expires_at in the future is leased; RUNNING with an
  expired lease is stale (same predicate as the existing reclaim path).
- run duration / failure rate -> jobs finished within EXECUTION_WINDOW (24h)
  with real started_at/finished_at; denominator = completed + failed in that
  bounded window. No inferred metrics, no unbounded scans.
- retention health -> M3 RetentionRun evidence via existing retention_health.
- connector staleness / browser reliability / cost breaker -> the EXISTING
  per-site source-health projection (M3b/M2/M4 semantics reused verbatim).

Semantic boundary: everything here describes PI OPERATIONAL INFRASTRUCTURE.
It never implies publisher/site failure; per-site source-health keeps its
own EP-025a states and stays reported separately.
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Job
from app.retention.health import RetentionHealth, retention_health
from app.retention.scheduling import JOB_TYPE as RETENTION_JOB_TYPE

# Scheduler enqueues at least the daily retention job; allow one cadence plus
# margin before calling the scheduler stale.
SCHEDULER_MAX_AGE = timedelta(hours=26)
# Worker activity envelope: well above combined cadences, tight enough to
# surface a dead worker materially earlier than "forever".
WORKER_MAX_IDLE = timedelta(hours=48)
# Bounded lookback for duration/failure-rate statistics.
EXECUTION_WINDOW = timedelta(hours=24)

OPERATIONAL_STATES = ("CURRENT", "STALE", "UNKNOWN")


def _age_seconds(now: datetime, moment: datetime | None) -> int | None:
    if moment is None:
        return None
    return max(0, int((now - moment).total_seconds()))


def freshness_state(*, moment: datetime | None, now: datetime, max_age: timedelta) -> str:
    """Deterministic CURRENT/STALE/UNKNOWN projection for one timestamp."""
    if moment is None:
        return "UNKNOWN"
    if moment.tzinfo is None or moment.utcoffset() is None:
        return "UNKNOWN"
    if now < moment - timedelta(minutes=5):  # clock skew guard
        return "UNKNOWN"
    return "CURRENT" if now - moment <= max_age else "STALE"


async def scheduler_signal(session: AsyncSession, *, now: datetime) -> dict[str, object]:
    # EP-026 M6 soundness repair: scheduler liveness must derive ONLY from
    # scheduler-exclusive evidence. ENFORCE_RETENTION jobs are created solely
    # by RetentionSchedulingService.schedule_due, whose single production
    # caller is scheduler.run_once; generic Job creation (diagnostic
    # checkpoints, incident diagnostics, VALIDATE_PUBLIC_CONFIG follow-ups,
    # drilldown planning) must never refresh this signal.
    last_run_at = await session.scalar(
        select(func.max(Job.created_at)).where(Job.job_type == RETENTION_JOB_TYPE)
    )
    return {
        "last_run_at": last_run_at,
        "age_seconds": _age_seconds(now, last_run_at),
        "state": freshness_state(moment=last_run_at, now=now, max_age=SCHEDULER_MAX_AGE),
        "max_age_hours": int(SCHEDULER_MAX_AGE.total_seconds() // 3600),
    }


async def worker_signal(session: AsyncSession, *, now: datetime) -> dict[str, object]:
    last_execution_at = await session.scalar(select(func.max(Job.started_at)))
    return {
        "last_execution_at": last_execution_at,
        "age_seconds": _age_seconds(now, last_execution_at),
        "state": freshness_state(moment=last_execution_at, now=now, max_age=WORKER_MAX_IDLE),
        "max_idle_hours": int(WORKER_MAX_IDLE.total_seconds() // 3600),
    }


async def queue_signal(session: AsyncSession, *, now: datetime) -> dict[str, int]:
    pending = await session.scalar(
        select(func.count()).select_from(Job).where(Job.status.in_(("PENDING", "RETRY")))
    )
    leased = await session.scalar(
        select(func.count())
        .select_from(Job)
        .where(
            Job.status == "RUNNING",
            Job.lock_expires_at.is_not(None),
            Job.lock_expires_at > now,
        )
    )
    # Same expiry predicate as the existing lease reclaim path: deterministic
    # from persisted timestamps, no fencing semantics weakened.
    stale_leases = await session.scalar(
        select(func.count())
        .select_from(Job)
        .where(
            Job.status == "RUNNING",
            (Job.lock_expires_at.is_(None)) | (Job.lock_expires_at <= now),
        )
    )
    return {
        "runnable": int(pending or 0),
        "leased": int(leased or 0),
        "stale_leases": int(stale_leases or 0),
    }


async def execution_signal(session: AsyncSession, *, now: datetime) -> dict[str, object]:
    """Real-duration/failure-rate statistics over the bounded window."""
    window_start = now - EXECUTION_WINDOW
    completed = await session.scalar(
        select(func.count())
        .select_from(Job)
        .where(
            Job.status == "COMPLETE",
            Job.finished_at.is_not(None),
            Job.finished_at >= window_start,
        )
    )
    failed = await session.scalar(
        select(func.count())
        .select_from(Job)
        .where(
            Job.status == "FAILED",
            Job.finished_at.is_not(None),
            Job.finished_at >= window_start,
        )
    )
    duration_rows = await session.execute(
        select(Job.finished_at - Job.started_at).where(
            Job.status.in_(("COMPLETE", "FAILED")),
            Job.finished_at.is_not(None),
            Job.started_at.is_not(None),
            Job.finished_at >= window_start,
        )
    )
    seconds = [
        max(0, int(cast(timedelta, duration).total_seconds()))
        for duration in duration_rows.scalars().all()
    ]
    finished_total = int(completed or 0) + int(failed or 0)
    failure_rate: float | None = (
        None if finished_total == 0 else round(int(failed or 0) / finished_total, 4)
    )
    return {
        "window_hours": int(EXECUTION_WINDOW.total_seconds() // 3600),
        "completed": int(completed or 0),
        "failed": int(failed or 0),
        "failure_rate": failure_rate,
        "avg_duration_seconds": (sum(seconds) // len(seconds)) if seconds else None,
        "max_duration_seconds": max(seconds) if seconds else None,
    }


async def operations_snapshot(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    tenant_id: uuid.UUID,
    now: datetime | None = None,
    source_health_for_site: Callable[[], Awaitable[list[tuple[str, str, dict[str, str]]]]]
    | None = None,
) -> dict[str, object]:
    """Assemble the operational snapshot; each sub-signal degrades to UNKNOWN
    independently instead of failing the whole read."""
    now = now or datetime.now(UTC)
    snapshot: dict[str, object] = {}
    async with session_factory() as session:
        for key, builder in (
            ("scheduler", scheduler_signal),
            ("workers", worker_signal),
            ("queue", queue_signal),
            ("execution_window", execution_signal),
        ):
            try:
                snapshot[key] = await builder(session, now=now)
            except Exception:
                snapshot[key] = {"state": "UNKNOWN"}
        try:
            health: RetentionHealth = await retention_health(session_factory, now=now)
            snapshot["retention"] = {
                "state": health.state,
                "detail": health.detail,
                "last_started_at": health.last_started_at,
                "last_finished_at": health.last_finished_at,
            }
        except Exception:
            snapshot["retention"] = {"state": "UNKNOWN"}
    if source_health_for_site is not None:
        sites: list[dict[str, object]] = []
        try:
            for site_id, name, site_health in await source_health_for_site():
                sites.append({"site_id": site_id, "name": name, "source_health": site_health})
            snapshot["sites"] = sites
        except Exception:
            snapshot["sites"] = {"state": "UNKNOWN"}
    return snapshot
