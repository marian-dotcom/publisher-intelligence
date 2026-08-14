import uuid
from datetime import UTC, datetime
from typing import Any, cast

from app.connectors.core.contracts import ConnectionSnapshot
from app.connectors.gsc.definitions import GSC_READONLY_SCOPE
from app.connectors.gsc.scheduling import GSCSchedulingService


class Repository:
    async def schedulable_connections(self, *, provider: str) -> tuple[ConnectionSnapshot, ...]:
        assert provider == "GSC"
        return (
            ConnectionSnapshot(
                id=uuid.uuid4(),
                tenant_id=uuid.uuid4(),
                site_id=uuid.uuid4(),
                provider="GSC",
                external_property_id="sc-domain:example.com",
                status="CONNECTED",
                scopes=(GSC_READONLY_SCOPE,),
                secret_reference="env:GSC_TEST_ACCESS_TOKEN",
                metadata={"sourceTimezone": "America/Los_Angeles"},
            ),
        )


class Queue:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def enqueue(self, **kwargs: Any) -> uuid.UUID:
        self.calls.append(kwargs)
        return uuid.uuid4()


async def test_four_hour_fresh_and_after_six_daily_reconciliation_are_bounded() -> None:
    queue = Queue()
    service = GSCSchedulingService(cast(Any, Repository()), cast(Any, queue))
    result = await service.schedule_due(now=datetime(2026, 8, 14, 14, 30, tzinfo=UTC))

    assert result.connection_count == 1
    assert result.job_count == 3
    assert [call["payload"]["definition_code"] for call in queue.calls] == [
        "GSC_SEARCH_HOURLY_V1",
        "GSC_SEARCH_DAILY_V1",
        "GSC_DISCOVER_DAILY_V1",
    ]
    assert queue.calls[0]["payload"]["freshness_status"] == "PRELIMINARY"
    assert queue.calls[1]["payload"]["start_date"] == "2026-08-07"
    assert all("token" not in str(call).lower() for call in queue.calls)


async def test_before_six_pacific_only_fresh_job_is_scheduled() -> None:
    queue = Queue()
    service = GSCSchedulingService(cast(Any, Repository()), cast(Any, queue))
    result = await service.schedule_due(now=datetime(2026, 8, 14, 10, 30, tzinfo=UTC))
    assert result.job_count == 1
