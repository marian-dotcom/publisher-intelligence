import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.connectors.core.persistence import ConnectorRepository
from app.connectors.gsc.definitions import (
    GSC_DISCOVER_DAILY_V1,
    GSC_SEARCH_DAILY_V1,
    GSC_SEARCH_HOURLY_V1,
)
from app.jobs.queue import JobQueue


@dataclass(frozen=True, slots=True)
class GSCSchedulingResult:
    connection_count: int
    job_count: int


class GSCSchedulingService:
    def __init__(self, repository: ConnectorRepository, queue: JobQueue) -> None:
        self._repository = repository
        self._queue = queue

    async def schedule_due(self, *, now: datetime | None = None) -> GSCSchedulingResult:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        connections = await self._repository.schedulable_connections(provider="GSC")
        jobs = 0
        for connection in connections:
            timezone_name = connection.metadata.get("sourceTimezone")
            if not isinstance(timezone_name, str):
                continue
            try:
                local_now = current.astimezone(ZoneInfo(timezone_name))
            except ZoneInfoNotFoundError:
                continue
            slot_hour = local_now.hour - (local_now.hour % 4)
            slot = local_now.replace(hour=slot_hour, minute=0, second=0, microsecond=0)
            fresh_key = (
                f"gsc:{connection.id}:{GSC_SEARCH_HOURLY_V1.code}:preliminary:{slot.isoformat()}"
            )
            jobs += int(
                await self._enqueue(
                    connection_id=str(connection.id),
                    tenant_id=connection.tenant_id,
                    definition_code=GSC_SEARCH_HOURLY_V1.code,
                    start_date=local_now.date() - timedelta(days=1),
                    end_date=local_now.date(),
                    freshness="PRELIMINARY",
                    run_key=fresh_key,
                )
            )
            if local_now.hour < 6:
                continue
            mature_end = local_now.date() - timedelta(days=1)
            mature_start = mature_end - timedelta(days=6)
            for definition in (GSC_SEARCH_DAILY_V1, GSC_DISCOVER_DAILY_V1):
                key = f"gsc:{connection.id}:{definition.code}:mature:{mature_end.isoformat()}"
                jobs += int(
                    await self._enqueue(
                        connection_id=str(connection.id),
                        tenant_id=connection.tenant_id,
                        definition_code=definition.code,
                        start_date=mature_start,
                        end_date=mature_end,
                        freshness="MATURE",
                        run_key=key,
                    )
                )
        return GSCSchedulingResult(connection_count=len(connections), job_count=jobs)

    async def _enqueue(
        self,
        *,
        connection_id: str,
        tenant_id: uuid.UUID,
        definition_code: str,
        start_date: date,
        end_date: date,
        freshness: str,
        run_key: str,
    ) -> bool:
        job_id = await self._queue.enqueue(
            tenant_id=tenant_id,
            job_type="GSC_EXTRACT",
            payload={
                "connection_id": connection_id,
                "definition_code": definition_code,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "freshness_status": freshness,
                "scheduled_run_key": run_key,
            },
            idempotency_key=run_key,
            max_attempts=4,
        )
        return job_id is not None
