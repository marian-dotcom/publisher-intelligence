"""EP-026 M3a-1: retention scheduling service."""

from datetime import UTC, datetime

from app.jobs.queue import JobQueue

JOB_TYPE = "ENFORCE_RETENTION"


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
