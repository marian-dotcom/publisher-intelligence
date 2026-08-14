import uuid
from datetime import UTC, datetime
from typing import Any, cast

from app.connectors.core.contracts import ConnectionSnapshot
from app.connectors.ga4.definitions import GA4_READONLY_SCOPE
from app.connectors.ga4.scheduling import GA4SchedulingService


class Repository:
    async def schedulable_connections(self) -> tuple[ConnectionSnapshot, ...]:
        return (
            ConnectionSnapshot(
                id=uuid.uuid4(),
                tenant_id=uuid.uuid4(),
                site_id=uuid.uuid4(),
                provider="GA4",
                external_property_id="123456",
                status="CONNECTED",
                scopes=(GA4_READONLY_SCOPE,),
                secret_reference="env:GA4_TEST_ACCESS_TOKEN",
                metadata={"propertyTimezone": "Europe/Bucharest"},
            ),
        )


class Queue:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def enqueue(self, **kwargs: Any) -> uuid.UUID:
        self.calls.append(kwargs)
        return uuid.uuid4()


async def test_every_two_hour_operational_and_after_three_nightly_jobs_are_bounded() -> None:
    queue = Queue()
    service = GA4SchedulingService(cast(Any, Repository()), cast(Any, queue))

    result = await service.schedule_due(now=datetime(2026, 8, 14, 2, 15, tzinfo=UTC))

    assert result.connection_count == 1
    assert result.job_count == 3
    assert [call["payload"]["definition_code"] for call in queue.calls] == [
        "GA4_TRAFFIC_HOURLY_V1",
        "GA4_TRAFFIC_HOURLY_V1",
        "GA4_BEHAVIOR_DAILY_V1",
    ]
    assert queue.calls[0]["payload"]["freshness_status"] == "PRELIMINARY"
    assert queue.calls[1]["payload"]["freshness_status"] == "MATURE"
    assert all("token" not in str(call).lower() for call in queue.calls)


async def test_before_three_local_only_operational_job_is_scheduled() -> None:
    queue = Queue()
    service = GA4SchedulingService(cast(Any, Repository()), cast(Any, queue))

    result = await service.schedule_due(now=datetime(2026, 8, 13, 22, 15, tzinfo=UTC))

    assert result.job_count == 1
    assert len(queue.calls) == 1
