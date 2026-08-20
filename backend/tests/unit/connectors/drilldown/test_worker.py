import uuid
from typing import Any, cast

from app.connectors.core.contracts import NormalizedExtract
from app.jobs.queue import JobLease
from app.worker import handle_job


class Queue:
    def __init__(self) -> None:
        self.completed = False
        self.failure: dict[str, Any] | None = None

    async def complete(self, **kwargs: Any) -> bool:
        self.completed = True
        return True

    async def fail_or_retry(self, **kwargs: Any) -> bool:
        self.failure = kwargs
        return True


class Service:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def run_drilldown(self, **kwargs: Any) -> NormalizedExtract:
        self.calls.append(kwargs)
        return NormalizedExtract("UTC", (), {}, ())


def payload() -> dict[str, Any]:
    return {
        "catalog_version": "incident-drilldown-v1",
        "connection_id": str(uuid.uuid4()),
        "definition_code": "traffic_by_page_device",
        "end_date": "2026-08-20",
        "investigation_id": str(uuid.uuid4()),
        "parameters": {},
        "profile": None,
        "request_key": "a" * 64,
        "site_id": str(uuid.uuid4()),
        "start_date": "2026-08-19",
    }


def lease(job_payload: dict[str, Any]) -> JobLease:
    return JobLease(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        job_type="CONNECTOR_DRILLDOWN",
        payload=job_payload,
        attempt=1,
        max_attempts=3,
        lock_token=uuid.uuid4(),
    )


async def test_worker_resolves_semantic_request_without_arbitrary_query_fields() -> None:
    queue = Queue()
    ga4 = Service()
    await handle_job(
        cast(Any, queue),
        lease(payload()),
        5,
        cast(Any, ga4),
        cast(Any, Service()),
        cast(Any, Service()),
    )
    assert queue.completed is True
    assert queue.failure is None
    assert len(ga4.calls) == 1
    assert ga4.calls[0]["definition_code"] == "traffic_by_page_device"
    assert "token" not in str(ga4.calls[0]).lower()


async def test_worker_rejects_injected_dimensions_before_provider_execution() -> None:
    queue = Queue()
    ga4 = Service()
    invalid = payload()
    invalid["dimensions"] = ["userId", "city"]
    await handle_job(
        cast(Any, queue),
        lease(invalid),
        5,
        cast(Any, ga4),
        cast(Any, Service()),
        cast(Any, Service()),
    )
    assert queue.completed is False
    assert queue.failure is not None
    assert queue.failure["error_message"] == "INVALID_JOB_PAYLOAD"
    assert ga4.calls == []
