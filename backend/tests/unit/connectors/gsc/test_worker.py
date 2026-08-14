import uuid
from typing import Any, cast

from app.connectors.core.contracts import ConnectorError, NormalizedExtract
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
    def __init__(self, error: ConnectorError | None = None) -> None:
        self.error = error
        self.calls: list[dict[str, Any]] = []

    async def run_extract(self, **kwargs: Any) -> NormalizedExtract:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return NormalizedExtract("America/Los_Angeles", (), {}, ())


def lease(payload: dict[str, Any], *, attempt: int = 1) -> JobLease:
    return JobLease(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        job_type="GSC_EXTRACT",
        payload=payload,
        attempt=attempt,
        max_attempts=4,
        lock_token=uuid.uuid4(),
    )


def valid_payload() -> dict[str, Any]:
    return {
        "connection_id": str(uuid.uuid4()),
        "definition_code": "GSC_SEARCH_HOURLY_V1",
        "start_date": "2026-08-13",
        "end_date": "2026-08-14",
        "freshness_status": "PRELIMINARY",
        "scheduled_run_key": "gsc-unit-run",
    }


async def test_worker_accepts_only_tenant_owned_gsc_payload_without_token() -> None:
    queue = Queue()
    service = Service()
    await handle_job(cast(Any, queue), lease(valid_payload()), 5, None, cast(Any, service))
    assert queue.completed is True
    assert len(service.calls) == 1
    assert "token" not in str(service.calls[0]).lower()


async def test_worker_retries_quota_with_bounded_exponential_backoff() -> None:
    queue = Queue()
    service = Service(ConnectorError("QUOTA_LIMIT", retryable=True, message="quota"))
    await handle_job(
        cast(Any, queue), lease(valid_payload(), attempt=3), 5, None, cast(Any, service)
    )
    assert queue.failure is not None
    assert queue.failure["retryable"] is True
    assert queue.failure["backoff_seconds"] == 20


async def test_worker_rejects_extra_token_field() -> None:
    queue = Queue()
    service = Service()
    payload = valid_payload()
    payload["access_token"] = "forbidden"
    await handle_job(cast(Any, queue), lease(payload), 5, None, cast(Any, service))
    assert queue.failure is not None
    assert queue.failure["error_message"] == "INVALID_JOB_PAYLOAD"
    assert service.calls == []
