import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.connectors.core.persistence import ConnectorRepository
from app.connectors.gam.definitions import GAM_DEFINITIONS, binding_key
from app.jobs.queue import JobQueue


@dataclass(frozen=True, slots=True)
class GAMSchedulingResult:
    connection_count: int
    job_count: int


class GAMSchedulingService:
    def __init__(self, repository: ConnectorRepository, queue: JobQueue) -> None:
        self._repository = repository
        self._queue = queue

    async def schedule_due(self, *, now: datetime | None = None) -> GAMSchedulingResult:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        connections = await self._repository.schedulable_connections(provider="GAM")
        jobs = 0
        for connection in connections:
            timezone_name = connection.metadata.get("sourceTimezone")
            bindings = connection.metadata.get("reportBindings")
            if not isinstance(timezone_name, str) or not isinstance(bindings, dict):
                continue
            try:
                local_now = current.astimezone(ZoneInfo(timezone_name))
            except ZoneInfoNotFoundError:
                continue
            slot_hour = local_now.hour - (local_now.hour % 2)
            slot = local_now.replace(hour=slot_hour, minute=0, second=0, microsecond=0)
            for definition in GAM_DEFINITIONS.values():
                if binding_key(definition.code, "TODAY") not in bindings:
                    continue
                key = f"gam:{connection.id}:{definition.code}:today:{slot.isoformat()}"
                jobs += int(
                    await self._enqueue(
                        connection_id=str(connection.id),
                        tenant_id=connection.tenant_id,
                        definition_code=definition.code,
                        profile="TODAY",
                        freshness="PRELIMINARY",
                        run_key=key,
                    )
                )
            if local_now.hour < 6:
                continue
            for definition in GAM_DEFINITIONS.values():
                if binding_key(definition.code, "LAST_7_DAYS") not in bindings:
                    continue
                key = f"gam:{connection.id}:{definition.code}:last7:{local_now.date().isoformat()}"
                jobs += int(
                    await self._enqueue(
                        connection_id=str(connection.id),
                        tenant_id=connection.tenant_id,
                        definition_code=definition.code,
                        profile="LAST_7_DAYS",
                        freshness="PRELIMINARY",
                        run_key=key,
                    )
                )
        return GAMSchedulingResult(connection_count=len(connections), job_count=jobs)

    async def _enqueue(
        self,
        *,
        connection_id: str,
        tenant_id: uuid.UUID,
        definition_code: str,
        profile: str,
        freshness: str,
        run_key: str,
    ) -> bool:
        job_id = await self._queue.enqueue(
            tenant_id=tenant_id,
            job_type="GAM_EXTRACT",
            payload={
                "connection_id": connection_id,
                "definition_code": definition_code,
                "profile": profile,
                "freshness_status": freshness,
                "scheduled_run_key": run_key,
            },
            idempotency_key=run_key,
            max_attempts=4,
        )
        return job_id is not None
