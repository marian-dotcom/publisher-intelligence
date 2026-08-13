import uuid
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from app.browser.contracts import BrowserEvidence, BrowserTarget
from app.browser.persistence import CheckpointRepository, EvidencePersister
from app.browser.runner import BrowserRunner
from app.browser_worker import handle_browser_job
from app.jobs.queue import JobLease, JobQueue


def _target(lease: JobLease) -> BrowserTarget:
    assert lease.tenant_id is not None
    return BrowserTarget(
        checkpoint_run_id=uuid.UUID(str(lease.payload["checkpoint_run_id"])),
        tenant_id=lease.tenant_id,
        site_id=uuid.uuid4(),
        monitored_url_id=uuid.uuid4(),
        scenario_id=uuid.uuid4(),
        url="https://example.com/",
        canonical_domain="example.com",
        scenario_code="core_desktop_v1",
        scenario_version=1,
        locale="en-US",
        timezone="UTC",
        viewport_width=1440,
        viewport_height=900,
    )


def _evidence(status: str) -> BrowserEvidence:
    now = datetime.now(UTC)
    return BrowserEvidence(
        status=cast(Any, status),
        started_at=now,
        completed_at=now,
        final_url="https://example.com/",
        http_status=503 if status == "SITE_ERROR" else None,
        playwright_version="test",
        chromium_version="test",
        environment={},
        failure_class="PLAYWRIGHT_ERROR" if status == "BROWSER_ERROR" else None,
        failure_message="technical failure" if status == "BROWSER_ERROR" else None,
    )


class FakeQueue:
    def __init__(self) -> None:
        self.failed: list[dict[str, Any]] = []
        self.completed = False

    async def fail_or_retry(self, **kwargs: Any) -> bool:
        self.failed.append(kwargs)
        return True

    async def complete(self, **kwargs: Any) -> bool:
        del kwargs
        self.completed = True
        return True


class FakeRepository:
    def __init__(self, target: BrowserTarget) -> None:
        self.target = target
        self.retry_recorded = False

    async def begin_attempt(self, **kwargs: Any) -> BrowserTarget:
        del kwargs
        return self.target

    async def record_retryable_failure(self, **kwargs: Any) -> None:
        del kwargs
        self.retry_recorded = True


class FakePersister:
    def __init__(self) -> None:
        self.persisted = False

    async def persist(self, **kwargs: Any) -> dict[str, Any]:
        del kwargs
        self.persisted = True
        return {}


class FakeRunner:
    def __init__(self, evidence: BrowserEvidence) -> None:
        self.evidence = evidence

    async def run(self, target: BrowserTarget) -> BrowserEvidence:
        del target
        return self.evidence


class FailingRunner:
    async def run(self, target: BrowserTarget) -> BrowserEvidence:
        del target
        raise RuntimeError("sensitive details must not be persisted")


def _lease(*, attempt: int = 1, max_attempts: int = 2) -> JobLease:
    return JobLease(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        job_type="BROWSER_CHECKPOINT",
        payload={"checkpoint_run_id": str(uuid.uuid4())},
        attempt=attempt,
        max_attempts=max_attempts,
        lock_token=uuid.uuid4(),
    )


async def test_technical_browser_error_retries_before_persistence() -> None:
    lease = _lease()
    queue = FakeQueue()
    repository = FakeRepository(_target(lease))
    persister = FakePersister()

    await handle_browser_job(
        queue=cast(JobQueue, queue),
        repository=cast(CheckpointRepository, repository),
        persister=cast(EvidencePersister, persister),
        runner=cast(BrowserRunner, FakeRunner(_evidence("BROWSER_ERROR"))),
        lease=lease,
        backoff_seconds=0,
    )

    assert repository.retry_recorded
    assert queue.failed[0]["retryable"] is True
    assert not persister.persisted
    assert not queue.completed


async def test_site_error_is_persisted_without_retry() -> None:
    lease = _lease()
    queue = FakeQueue()
    repository = FakeRepository(_target(lease))
    persister = FakePersister()

    await handle_browser_job(
        queue=cast(JobQueue, queue),
        repository=cast(CheckpointRepository, repository),
        persister=cast(EvidencePersister, persister),
        runner=cast(BrowserRunner, FakeRunner(_evidence("SITE_ERROR"))),
        lease=lease,
        backoff_seconds=0,
    )

    assert not repository.retry_recorded
    assert queue.failed == []
    assert persister.persisted
    assert queue.completed


async def test_unexpected_runtime_error_records_only_safe_diagnostics(
    caplog: pytest.LogCaptureFixture,
) -> None:
    lease = _lease()
    queue = FakeQueue()
    repository = FakeRepository(_target(lease))
    persister = FakePersister()

    await handle_browser_job(
        queue=cast(JobQueue, queue),
        repository=cast(CheckpointRepository, repository),
        persister=cast(EvidencePersister, persister),
        runner=cast(BrowserRunner, FailingRunner()),
        lease=lease,
        backoff_seconds=0,
    )

    assert repository.retry_recorded
    assert queue.failed[0]["error_class"] == "RuntimeError"
    assert "sensitive" not in str(queue.failed)
    assert not persister.persisted
    record = next(item for item in caplog.records if item.getMessage() == "browser runtime failed")
    context = cast(dict[str, object], record.__dict__["context"])
    assert context["error_module"] == "test_worker.py"
    assert context["error_function"] == "run"
    assert isinstance(context["error_line"], int)
    assert "sensitive" not in str(context)
