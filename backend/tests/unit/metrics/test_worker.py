import uuid
from datetime import UTC, datetime
from typing import Any, cast

from app.jobs.queue import JobLease
from app.metrics.contracts import CROSS_SOURCE_RULE_VERSION, DerivationResult
from app.worker import handle_job


class Queue:
    completed = False
    failure: dict[str, Any] | None = None

    async def complete(self, **kwargs: Any) -> bool:
        self.completed = True
        return True

    async def fail_or_retry(self, **kwargs: Any) -> bool:
        self.failure = kwargs
        return True


class Service:
    calls: list[dict[str, Any]]

    def __init__(self) -> None:
        self.calls = []

    async def derive_site(self, **kwargs: Any) -> DerivationResult:
        self.calls.append(kwargs)
        return DerivationResult(2, 2, {})


def lease(payload: dict[str, Any]) -> JobLease:
    return JobLease(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        job_type="DERIVE_CROSS_SOURCE",
        payload=payload,
        attempt=1,
        max_attempts=3,
        lock_token=uuid.uuid4(),
    )


def valid_payload() -> dict[str, Any]:
    return {
        "site_id": str(uuid.uuid4()),
        "window_start": datetime(2026, 8, 18, tzinfo=UTC).isoformat(),
        "window_end": datetime(2026, 8, 20, tzinfo=UTC).isoformat(),
        "rule_version": CROSS_SOURCE_RULE_VERSION,
    }


async def test_worker_runs_valid_cross_source_job() -> None:
    queue = Queue()
    service = Service()

    await handle_job(
        cast(Any, queue),
        lease(valid_payload()),
        5,
        None,
        None,
        None,
        cast(Any, service),
    )

    assert queue.completed is True
    assert queue.failure is None
    assert len(service.calls) == 1


async def test_worker_rejects_unversioned_or_naive_payload() -> None:
    queue = Queue()
    payload = valid_payload()
    payload["window_start"] = "2026-08-18T00:00:00"

    await handle_job(
        cast(Any, queue),
        lease(payload),
        5,
        None,
        None,
        None,
        cast(Any, Service()),
    )

    assert queue.completed is False
    assert queue.failure is not None
    assert queue.failure["retryable"] is False
    assert queue.failure["error_class"] == "INVALID_DERIVATION_JOB"
