import uuid
from datetime import UTC, datetime
from typing import Any, cast

from app.jobs.queue import JobLease
from app.public_config.contracts import PUBLIC_CONFIG_RULE_VERSION, PublicConfigRunResult
from app.public_config.persistence import PublicConfigStateError
from app.public_config.service import PublicConfigMonitoringSkippedError, PublicConfigRunError
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
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.scheduled_calls: list[dict[str, Any]] = []
        self.validation_calls: list[dict[str, Any]] = []

    async def run_scheduled(self, **kwargs: Any) -> PublicConfigRunResult:
        self.scheduled_calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return PublicConfigRunResult(uuid.uuid4(), True, "VALID", False)

    async def run_validation(self, **kwargs: Any) -> PublicConfigRunResult:
        self.validation_calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return PublicConfigRunResult(uuid.uuid4(), True, "VALID", False)


def lease(
    job_type: str,
    payload: dict[str, Any],
    *,
    attempt: int = 1,
    tenant_id: uuid.UUID | None = None,
) -> JobLease:
    return JobLease(
        id=uuid.uuid4(),
        tenant_id=tenant_id or uuid.uuid4(),
        job_type=job_type,
        payload=payload,
        attempt=attempt,
        max_attempts=3,
        lock_token=uuid.uuid4(),
    )


def fetch_payload() -> dict[str, Any]:
    return {
        "site_id": str(uuid.uuid4()),
        "config_type": "ROBOTS_TXT",
        "scheduled_for": datetime(2026, 8, 21, tzinfo=UTC).isoformat(),
        "rule_version": PUBLIC_CONFIG_RULE_VERSION,
    }


def validation_payload() -> dict[str, Any]:
    return {
        "site_id": str(uuid.uuid4()),
        "config_type": "ADS_TXT",
        "primary_snapshot_id": str(uuid.uuid4()),
        "rule_version": PUBLIC_CONFIG_RULE_VERSION,
    }


async def test_worker_runs_exact_scheduled_fetch_payload() -> None:
    queue, service = Queue(), Service()

    await handle_job(
        cast(Any, queue),
        lease("FETCH_PUBLIC_CONFIG", fetch_payload()),
        5,
        public_config_service=cast(Any, service),
    )

    assert queue.completed is True and queue.failure is None
    assert len(service.scheduled_calls) == 1
    assert service.scheduled_calls[0]["config_type"] == "ROBOTS_TXT"


async def test_worker_runs_exact_validation_payload() -> None:
    queue, service = Queue(), Service()

    await handle_job(
        cast(Any, queue),
        lease("VALIDATE_PUBLIC_CONFIG", validation_payload()),
        5,
        public_config_service=cast(Any, service),
    )

    assert queue.completed is True and queue.failure is None
    assert len(service.validation_calls) == 1


async def test_worker_rejects_malformed_payload_without_calling_service() -> None:
    queue, service = Queue(), Service()
    payload = fetch_payload()
    payload["scheduled_for"] = "2026-08-21T00:00:00"
    payload["event_code"] = "ADS_TXT_MISSING"

    await handle_job(
        cast(Any, queue),
        lease("FETCH_PUBLIC_CONFIG", payload),
        5,
        public_config_service=cast(Any, service),
    )

    assert queue.completed is False
    assert queue.failure is not None and queue.failure["retryable"] is False
    assert queue.failure["error_class"] == "INVALID_PUBLIC_CONFIG_JOB"
    assert service.scheduled_calls == []


async def test_worker_treats_cross_tenant_state_as_terminal() -> None:
    queue = Queue()
    service = Service(PublicConfigStateError("wrong tenant"))

    await handle_job(
        cast(Any, queue),
        lease("FETCH_PUBLIC_CONFIG", fetch_payload()),
        5,
        public_config_service=cast(Any, service),
    )

    assert queue.failure is not None and queue.failure["retryable"] is False
    assert queue.failure["error_class"] == "PUBLIC_CONFIG_STATE_ERROR"


async def test_worker_applies_bounded_retry_backoff_to_transport_failure() -> None:
    queue = Queue()
    service = Service(PublicConfigRunError("PUBLIC_CONFIG_TIMEOUT", retryable=True))

    await handle_job(
        cast(Any, queue),
        lease("FETCH_PUBLIC_CONFIG", fetch_payload(), attempt=3),
        7,
        public_config_service=cast(Any, service),
    )

    assert queue.failure is not None and queue.failure["retryable"] is True
    assert queue.failure["error_message"] == "PUBLIC_CONFIG_TIMEOUT"
    assert queue.failure["backoff_seconds"] == 28


async def test_worker_does_not_retry_security_failure() -> None:
    queue = Queue()
    service = Service(PublicConfigRunError("PUBLIC_CONFIG_SECURITY_ERROR", retryable=False))

    await handle_job(
        cast(Any, queue),
        lease("FETCH_PUBLIC_CONFIG", fetch_payload()),
        5,
        public_config_service=cast(Any, service),
    )

    assert queue.failure is not None and queue.failure["retryable"] is False
    assert queue.failure["error_message"] == "PUBLIC_CONFIG_SECURITY_ERROR"


async def test_worker_completes_fetch_on_monitoring_skipped() -> None:
    """PC-GATE-3 (EP-030 M2): an OFF/stale-epoch scheduled fetch completes the
    job as an intentional skip — zero retry, zero failure recorded."""
    queue = Queue()
    service = Service(PublicConfigMonitoringSkippedError("monitoring disabled"))

    await handle_job(
        cast(Any, queue),
        lease("FETCH_PUBLIC_CONFIG", fetch_payload()),
        5,
        public_config_service=cast(Any, service),
    )

    assert queue.completed is True and queue.failure is None
    assert len(service.scheduled_calls) == 1


async def test_worker_completes_validation_on_monitoring_skipped() -> None:
    """PC-GATE-3 (EP-030 M2): a stale-epoch validation completes as an
    intentional skip — zero retry, zero failure recorded."""
    queue = Queue()
    service = Service(PublicConfigMonitoringSkippedError("stale epoch"))

    await handle_job(
        cast(Any, queue),
        lease("VALIDATE_PUBLIC_CONFIG", validation_payload()),
        5,
        public_config_service=cast(Any, service),
    )

    assert queue.completed is True and queue.failure is None
    assert len(service.validation_calls) == 1
