import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.connectors.core.persistence import ConnectorRepository
from app.connectors.ga4.definitions import GA4_BEHAVIOR_DAILY_V1, GA4_TRAFFIC_HOURLY_V1
from app.jobs.queue import JobQueue


@dataclass(frozen=True, slots=True)
class GA4SchedulingResult:
    connection_count: int
    job_count: int


class GA4SchedulingService:
    def __init__(self, repository: ConnectorRepository, queue: JobQueue) -> None:
        self._repository = repository
        self._queue = queue

    async def schedule_due(self, *, now: datetime | None = None) -> GA4SchedulingResult:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        connections = await self._repository.schedulable_connections()
        jobs = 0
        for connection in connections:
            timezone_name = connection.metadata.get("propertyTimezone")
            if not isinstance(timezone_name, str):
                continue
            try:
                local_now = current.astimezone(ZoneInfo(timezone_name))
            except ZoneInfoNotFoundError:
                continue
            slot_hour = local_now.hour - (local_now.hour % 2)
            slot = local_now.replace(hour=slot_hour, minute=0, second=0, microsecond=0)
            operational_start = local_now.date() - timedelta(days=1)
            operational_end = local_now.date()
            operational_key = (
                f"ga4:{connection.id}:{GA4_TRAFFIC_HOURLY_V1.code}:preliminary:{slot.isoformat()}"
            )
            jobs += int(
                await self._enqueue(
                    connection_id=str(connection.id),
                    tenant_id=connection.tenant_id,
                    definition_code=GA4_TRAFFIC_HOURLY_V1.code,
                    start_date=operational_start,
                    end_date=operational_end,
                    freshness="PRELIMINARY",
                    run_key=operational_key,
                )
            )
            if local_now.hour < 3:
                continue
            mature_end = local_now.date() - timedelta(days=1)
            mature_start = mature_end - timedelta(days=2)
            for definition in (GA4_TRAFFIC_HOURLY_V1, GA4_BEHAVIOR_DAILY_V1):
                mature_key = (
                    f"ga4:{connection.id}:{definition.code}:mature:{mature_end.isoformat()}"
                )
                jobs += int(
                    await self._enqueue(
                        connection_id=str(connection.id),
                        tenant_id=connection.tenant_id,
                        definition_code=definition.code,
                        start_date=mature_start,
                        end_date=mature_end,
                        freshness="MATURE",
                        run_key=mature_key,
                    )
                )
        return GA4SchedulingResult(connection_count=len(connections), job_count=jobs)

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
            job_type="GA4_EXTRACT",
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
