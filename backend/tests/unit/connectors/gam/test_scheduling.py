import uuid
from datetime import UTC, datetime
from typing import Any, cast

from app.connectors.core.contracts import ConnectionSnapshot
from app.connectors.gam.definitions import (
    GAM_DEFINITIONS,
    GAM_PROFILES,
    GAM_READONLY_SCOPE,
    binding_key,
)
from app.connectors.gam.scheduling import GAMSchedulingService


def bindings() -> dict[str, str]:
    return {
        binding_key(definition.code, profile): f"networks/1234567/reports/{index}"
        for index, (definition, profile) in enumerate(
            (
                (definition, profile)
                for definition in GAM_DEFINITIONS.values()
                for profile in GAM_PROFILES
            ),
            start=101,
        )
    }


class Repository:
    async def schedulable_connections(self, *, provider: str) -> tuple[ConnectionSnapshot, ...]:
        assert provider == "GAM"
        return (
            ConnectionSnapshot(
                id=uuid.uuid4(),
                tenant_id=uuid.uuid4(),
                site_id=uuid.uuid4(),
                provider="GAM",
                external_property_id="1234567",
                status="CONNECTED",
                scopes=(GAM_READONLY_SCOPE,),
                secret_reference="env:GAM_TEST_ACCESS_TOKEN",
                metadata={
                    "sourceTimezone": "Europe/Bucharest",
                    "reportBindings": bindings(),
                },
            ),
        )


class Queue:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def enqueue(self, **kwargs: Any) -> uuid.UUID:
        self.calls.append(kwargs)
        return uuid.uuid4()


async def test_two_hour_operational_and_daily_reconciliation_are_bounded() -> None:
    queue = Queue()
    service = GAMSchedulingService(cast(Any, Repository()), cast(Any, queue))
    result = await service.schedule_due(now=datetime(2026, 8, 20, 10, 30, tzinfo=UTC))
    assert result.connection_count == 1
    assert result.job_count == 6
    assert [call["payload"]["profile"] for call in queue.calls] == [
        "TODAY",
        "TODAY",
        "TODAY",
        "LAST_7_DAYS",
        "LAST_7_DAYS",
        "LAST_7_DAYS",
    ]
    assert all(call["payload"]["freshness_status"] == "PRELIMINARY" for call in queue.calls)
    assert all("token" not in str(call).lower() for call in queue.calls)


async def test_before_six_local_only_operational_cubes_are_scheduled() -> None:
    queue = Queue()
    service = GAMSchedulingService(cast(Any, Repository()), cast(Any, queue))
    result = await service.schedule_due(now=datetime(2026, 8, 20, 1, 30, tzinfo=UTC))
    assert result.job_count == 3
    assert all(call["payload"]["profile"] == "TODAY" for call in queue.calls)
