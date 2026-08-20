import uuid
from datetime import UTC, datetime
from typing import Any, cast

from app.metrics.contracts import CROSS_SOURCE_RULE_VERSION
from app.metrics.scheduling import CrossSourceSchedulingService


class Repository:
    tenant_id = uuid.uuid4()
    site_id = uuid.uuid4()

    async def schedulable_sites(self) -> tuple[tuple[uuid.UUID, uuid.UUID], ...]:
        return ((self.tenant_id, self.site_id),)


class Queue:
    calls: list[dict[str, Any]]

    def __init__(self) -> None:
        self.calls = []

    async def enqueue(self, **kwargs: Any) -> uuid.UUID:
        self.calls.append(kwargs)
        return uuid.uuid4()


async def test_schedules_low_priority_bounded_utc_derivation() -> None:
    repository = Repository()
    queue = Queue()
    result = await CrossSourceSchedulingService(
        cast(Any, repository), cast(Any, queue)
    ).schedule_due(now=datetime(2026, 8, 20, 11, 37, tzinfo=UTC))

    assert result.site_count == 1 and result.job_count == 1
    call = queue.calls[0]
    assert call["job_type"] == "DERIVE_CROSS_SOURCE"
    assert call["tenant_id"] == repository.tenant_id
    assert call["priority"] == -10
    assert call["payload"] == {
        "site_id": str(repository.site_id),
        "window_start": "2026-08-18T10:00:00+00:00",
        "window_end": "2026-08-20T10:00:00+00:00",
        "rule_version": CROSS_SOURCE_RULE_VERSION,
    }
