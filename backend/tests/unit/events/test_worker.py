import uuid
from typing import Any, cast

from app.events.persistence import EventRunResult
from app.jobs.queue import JobLease
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
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def derive(self, **kwargs: Any) -> EventRunResult:
        self.calls.append(kwargs)
        return EventRunResult(2, 1, 1, ())


def lease(payload: dict[str, Any]) -> JobLease:
    return JobLease(
        uuid.uuid4(), uuid.uuid4(), "DERIVE_BROWSER_EVENTS", payload, 1, 3, uuid.uuid4()
    )


async def test_worker_derives_events_from_exact_payload() -> None:
    queue, service = Queue(), Service()
    checkpoint_run_id = uuid.uuid4()
    await handle_job(
        cast(Any, queue),
        lease({"checkpoint_run_id": str(checkpoint_run_id)}),
        5,
        None,
        None,
        None,
        None,
        cast(Any, service),
    )
    assert queue.completed is True and queue.failure is None
    assert service.calls[0]["checkpoint_run_id"] == checkpoint_run_id


async def test_worker_rejects_extra_rule_input() -> None:
    queue = Queue()
    await handle_job(
        cast(Any, queue),
        lease(
            {
                "checkpoint_run_id": str(uuid.uuid4()),
                "event_code": "CANONICAL_CHANGED",
            }
        ),
        5,
        None,
        None,
        None,
        None,
        cast(Any, Service()),
    )
    assert queue.completed is False
    assert queue.failure is not None and queue.failure["retryable"] is False
