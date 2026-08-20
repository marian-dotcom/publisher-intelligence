import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.jobs.queue import JobQueue
from app.metrics.contracts import CROSS_SOURCE_RULE_VERSION
from app.metrics.persistence import MetricDerivationRepository


@dataclass(frozen=True, slots=True)
class CrossSourceSchedulingResult:
    site_count: int
    job_count: int


class CrossSourceSchedulingService:
    def __init__(self, repository: MetricDerivationRepository, queue: JobQueue) -> None:
        self._repository = repository
        self._queue = queue

    async def schedule_due(self, *, now: datetime | None = None) -> CrossSourceSchedulingResult:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        slot = current.replace(
            hour=current.hour - (current.hour % 2), minute=0, second=0, microsecond=0
        )
        window_start = slot - timedelta(hours=48)
        sites = await self._repository.schedulable_sites()
        jobs = 0
        for tenant_id, site_id in sites:
            key = f"derived:{site_id}:{CROSS_SOURCE_RULE_VERSION}:{slot.isoformat()}"
            jobs += int(
                await self._enqueue(
                    tenant_id=tenant_id,
                    site_id=site_id,
                    window_start=window_start,
                    window_end=slot,
                    run_key=key,
                )
            )
        return CrossSourceSchedulingResult(site_count=len(sites), job_count=jobs)

    async def _enqueue(
        self,
        *,
        tenant_id: uuid.UUID,
        site_id: uuid.UUID,
        window_start: datetime,
        window_end: datetime,
        run_key: str,
    ) -> bool:
        job_id = await self._queue.enqueue(
            tenant_id=tenant_id,
            job_type="DERIVE_CROSS_SOURCE",
            payload={
                "site_id": str(site_id),
                "window_start": window_start.isoformat(),
                "window_end": window_end.isoformat(),
                "rule_version": CROSS_SOURCE_RULE_VERSION,
            },
            idempotency_key=run_key,
            priority=-10,
            max_attempts=3,
        )
        return job_id is not None
