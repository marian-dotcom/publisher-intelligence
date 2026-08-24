"""EP-026 M2b-1a-2b-ii — automatic DIAGNOSTIC reliability derivation.

Production flow under test: real CheckpointRepository.begin_attempt/finalize →
DERIVE_BROWSER_EVENTS job → real worker handle_job → EventService.derive →
canonical browser-source reliability Event. No manual derive substitution on
the main acceptance path.
"""

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Literal, cast

import pytest
from sqlalchemy import select

from app.browser.contracts import BrowserEvidence
from app.browser.models import CheckpointRun
from app.browser.persistence import CheckpointRepository
from app.db.models import Job
from app.db.session import get_session_factory
from app.events.models import Event, EventEvidenceRef
from app.events.registry import definition_id
from app.events.service import EventService
from app.jobs.queue import JobQueue
from app.worker import handle_job

pytestmark = pytest.mark.integration


def _seed(slug: str) -> dict[str, object]:
    from tests.integration.product.factories import seed_diagnostic_event_chain

    return asyncio.run(seed_diagnostic_event_chain(slug=slug))


def _repository() -> CheckpointRepository:
    return CheckpointRepository(get_session_factory())


def _evidence(
    status: Literal["COMPLETE", "PARTIAL", "SITE_ERROR", "BROWSER_ERROR", "TIMEOUT"],
    http_status: int | None,
    url: str | None,
) -> BrowserEvidence:
    now = datetime.now(UTC)
    return BrowserEvidence(
        status=status,
        started_at=now,
        completed_at=now,
        final_url=url,
        http_status=http_status,
        playwright_version="1.0.0-test",
        chromium_version=None,
        environment={"is_mobile": False},
    )


def _derive_jobs(tenant_id: uuid.UUID, run_id: uuid.UUID) -> list[Job]:
    async def act() -> list[Job]:
        factory = get_session_factory()
        async with factory() as session:
            return list(
                (
                    await session.scalars(
                        select(Job).where(
                            Job.tenant_id == tenant_id,
                            Job.job_type == "DERIVE_BROWSER_EVENTS",
                            Job.payload["checkpoint_run_id"].as_string() == str(run_id),
                        )
                    )
                ).all()
            )

    return asyncio.run(act())


def _degraded_events_and_refs(
    tenant_id: uuid.UUID, site_id: uuid.UUID
) -> tuple[list[Event], list[EventEvidenceRef]]:
    async def act() -> tuple[list[Event], list[EventEvidenceRef]]:
        factory = get_session_factory()
        async with factory() as session:
            events = list(
                (
                    await session.scalars(
                        select(Event).where(
                            Event.tenant_id == tenant_id,
                            Event.site_id == site_id,
                            Event.event_definition_id == definition_id("BROWSER_SOURCE_DEGRADED"),
                        )
                    )
                ).all()
            )
            refs = list(
                (
                    await session.scalars(
                        select(EventEvidenceRef).where(
                            EventEvidenceRef.tenant_id == tenant_id,
                            EventEvidenceRef.source_id.in_([event.id for event in events])
                            | EventEvidenceRef.event_id.in_([event.id for event in events]),
                        )
                    )
                ).all()
            )
        return events, refs

    return asyncio.run(act())


def _process_one_derive_job(event_service: EventService) -> bool:
    """Claim and process one runnable DERIVE_BROWSER_EVENTS job via the real
    worker handler. Returns True when a job was processed."""

    async def act() -> bool:
        factory = get_session_factory()
        queue = JobQueue(factory)
        lease = await queue.claim(worker_id="diag-reliability-test", lease_seconds=60)
        if lease is None:
            return False
        assert lease.job_type == "DERIVE_BROWSER_EVENTS"
        await handle_job(
            queue,
            lease,
            1,
            None,
            None,
            None,
            None,
            event_service,
        )
        return True

    return asyncio.run(act())


def _finalize_once(tenant_id: uuid.UUID, run_id: uuid.UUID, attempt_number: int) -> None:
    repository = _repository()

    async def act() -> None:
        target = await repository.begin_attempt(
            tenant_id=tenant_id, checkpoint_run_id=run_id, attempt_number=attempt_number
        )
        await repository.finalize(
            target=target,
            attempt_number=attempt_number,
            evidence=_evidence("PARTIAL", 403, target.url),
            artifacts=[],
            manifest={},
        )

    asyncio.run(act())


def test_red_then_green_full_automatic_diagnostic_derivation() -> None:
    from app.events.persistence import EventRepository

    seeded = _seed(f"m2bii-auto-{uuid.uuid4().hex[:8]}")
    tenant_id = cast(uuid.UUID, seeded["tenant_id"])
    site_id = cast(uuid.UUID, seeded["site_id"])
    diagnostic_run_id = cast(uuid.UUID, seeded["diagnostic_run_id"])

    # Production finalize of a degraded diagnostic observation.
    _finalize_once(tenant_id, diagnostic_run_id, attempt_number=1)

    # Finalize must have queued exactly one dedicated derive job.
    jobs = _derive_jobs(tenant_id, diagnostic_run_id)
    assert len(jobs) == 1
    assert jobs[0].idempotency_key == f"derive-browser-events:{diagnostic_run_id}:e26-v1"
    assert jobs[0].payload == {"checkpoint_run_id": str(diagnostic_run_id)}

    # The real worker processes the queued job — no manual derive anywhere.
    event_service = EventService(EventRepository(get_session_factory()))
    assert _process_one_derive_job(event_service) is True

    events, refs = _degraded_events_and_refs(tenant_id, site_id)
    assert len(events) == 1
    event = events[0]
    assert event.severity == "HIGH"
    assert event.status == "RECORDED"
    assert event.source_version == "e26-v1"
    assert event.scope == {"site_id": str(site_id)}
    trigger_refs = [
        ref
        for ref in refs
        if ref.event_id == event.id
        and ref.evidence_kind == "CHECKPOINT_RUN"
        and ref.source_id == diagnostic_run_id
        and ref.relation == "TRIGGER_AFTER"
    ]
    assert len(trigger_refs) == 1


def test_duplicate_diagnostic_jobs_prevented_across_retry_attempts() -> None:
    seeded = _seed(f"m2bii-idem-{uuid.uuid4().hex[:8]}")
    tenant_id = cast(uuid.UUID, seeded["tenant_id"])
    diagnostic_run_id = cast(uuid.UUID, seeded["diagnostic_run_id"])

    _finalize_once(tenant_id, diagnostic_run_id, attempt_number=1)

    # Canonical retry reset (same pattern as test_observation_run_semantics):
    # move the finalized run back into a runnable state, then re-attempt.
    async def make_retryable() -> None:
        factory = get_session_factory()
        async with factory() as session, session.begin():
            run = await session.scalar(
                select(CheckpointRun).where(CheckpointRun.id == diagnostic_run_id)
            )
            assert run is not None
            assert run.browser_access_classification is not None
            run.status = "RUNNING"

    asyncio.run(make_retryable())
    _finalize_once(tenant_id, diagnostic_run_id, attempt_number=2)

    jobs = _derive_jobs(tenant_id, diagnostic_run_id)
    assert len(jobs) == 1
    assert jobs[0].idempotency_key == f"derive-browser-events:{diagnostic_run_id}:e26-v1"


def test_worker_rederivation_stays_single_event_and_ref() -> None:
    from app.events.persistence import EventRepository

    seeded = _seed(f"m2bii-redo-{uuid.uuid4().hex[:8]}")
    tenant_id = cast(uuid.UUID, seeded["tenant_id"])
    site_id = cast(uuid.UUID, seeded["site_id"])
    diagnostic_run_id = cast(uuid.UUID, seeded["diagnostic_run_id"])

    _finalize_once(tenant_id, diagnostic_run_id, attempt_number=1)
    event_service = EventService(EventRepository(get_session_factory()))
    assert _process_one_derive_job(event_service) is True

    # A legitimate re-scheduling of the same derive work (canonical enqueue
    # API, fresh idempotency key) must not duplicate events or evidence.
    async def reschedule() -> None:
        factory = get_session_factory()
        queue = JobQueue(factory)
        await queue.enqueue(
            tenant_id=tenant_id,
            job_type="DERIVE_BROWSER_EVENTS",
            payload={"checkpoint_run_id": str(diagnostic_run_id)},
            idempotency_key=f"derive-browser-events:{diagnostic_run_id}:retry-simulation",
        )

    asyncio.run(reschedule())
    assert _process_one_derive_job(event_service) is True

    events, refs = _degraded_events_and_refs(tenant_id, site_id)
    assert len(events) == 1
    trigger_refs = [
        ref
        for ref in refs
        if ref.event_id == events[0].id
        and ref.evidence_kind == "CHECKPOINT_RUN"
        and ref.source_id == diagnostic_run_id
        and ref.relation == "TRIGGER_AFTER"
    ]
    assert len(trigger_refs) == 1


def test_healthy_diagnostic_derives_zero_events_through_worker() -> None:
    from app.events.persistence import EventRepository

    seeded = _seed(f"m2bii-ok-{uuid.uuid4().hex[:8]}")
    tenant_id = cast(uuid.UUID, seeded["tenant_id"])
    site_id = cast(uuid.UUID, seeded["site_id"])
    diagnostic_run_id = cast(uuid.UUID, seeded["diagnostic_run_id"])

    repository = _repository()

    async def healthy_finalize() -> None:
        target = await repository.begin_attempt(
            tenant_id=tenant_id, checkpoint_run_id=diagnostic_run_id, attempt_number=1
        )
        await repository.finalize(
            target=target,
            attempt_number=1,
            evidence=_evidence("COMPLETE", 200, target.url),
            artifacts=[],
            manifest={},
        )

    asyncio.run(healthy_finalize())

    # Enqueued (classification present) but the derivation is quiet: a healthy
    # monitoring source must never produce a degradation event.
    assert len(_derive_jobs(tenant_id, diagnostic_run_id)) == 1
    event_service = EventService(EventRepository(get_session_factory()))
    assert _process_one_derive_job(event_service) is True

    async def all_events() -> int:
        factory = get_session_factory()
        async with factory() as session:
            return len(
                (
                    await session.scalars(
                        select(Event).where(Event.tenant_id == tenant_id, Event.site_id == site_id)
                    )
                ).all()
            )

    assert asyncio.run(all_events()) == 0
