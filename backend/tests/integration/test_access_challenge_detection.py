"""EP-026 M2b-1b — bounded access-challenge detection through the REAL path.

Controlled local HTTP challenge fixture → real Playwright collection →
DIAGNOSTIC finalize → bounded classification → automatic DERIVE_BROWSER_EVENTS
→ real worker handle_job → canonical BROWSER_ACCESS_CHALLENGE_SUSPECTED Event.
No external WAF vendor; no raw page content persisted by this feature.
"""

import asyncio
import http.server
import threading
import uuid
from typing import cast

import pytest
from sqlalchemy import select

from app.browser.persistence import CheckpointRepository
from app.browser_worker import run as run_browser_worker
from app.config.settings import get_settings
from app.db.models import Job
from app.db.session import get_session_factory
from app.events.models import Event, EventEvidenceRef
from app.events.registry import definition_id
from app.jobs.queue import JobQueue
from app.worker import handle_job

pytestmark = pytest.mark.integration

# Distinctive sentinel proving no raw fixture text leaks into persistence.
CHALLENGE_SENTINEL = "PI-CHALLENGE-FIXTURE-9d41be7a"
CHALLENGE_BODY = (
    "<!doctype html><html><head><title>Attention Required! | Cloudflare</title>"
    "</head><body><p>checking your browser before accessing; complete the "
    "captcha to continue. sentinel:" + CHALLENGE_SENTINEL + "</p></body></html>"
).encode()
PLAIN_403_BODY = b"<!doctype html><html><body>fixture unavailable</body></html>"
HEALTHY_BODY = b"<!doctype html><html><body><h1>Fixture</h1></body></html>"


class ChallengeHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path.startswith("/challenge"):
            self._send(403, CHALLENGE_BODY)
        elif self.path.startswith("/plain-403"):
            self._send(403, PLAIN_403_BODY)
        else:
            self._send(200, HEALTHY_BODY)

    def _send(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        del format, args


@pytest.fixture()
def challenge_site() -> object:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), ChallengeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


async def _register_diagnostic(base_url: str, path: str) -> dict[str, uuid.UUID]:
    from app.browser.service import CheckpointService

    settings = get_settings()
    factory = get_session_factory()
    service = CheckpointService(factory, JobQueue(factory), settings)
    registered = await service.register_and_enqueue(
        tenant_slug=f"chal-{uuid.uuid4().hex}",
        tenant_name="Challenge Fixture Tenant",
        publisher_name="Challenge Fixture Publisher",
        site_name="Challenge Fixture Site",
        url=f"{base_url}{path}",
    )
    return {
        "tenant_id": registered.tenant_id,
        "checkpoint_run_id": registered.checkpoint_run_id,
    }


def _run_browser_once() -> None:
    asyncio.run(run_browser_worker(once=True))


def _process_one_derive_job() -> bool:
    from app.events.persistence import EventRepository
    from app.events.service import EventService

    async def act() -> bool:
        factory = get_session_factory()
        queue = JobQueue(factory)
        lease = await queue.claim(worker_id="challenge-derive-test", lease_seconds=60)
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
            EventService(EventRepository(get_session_factory())),
        )
        return True

    return asyncio.run(act())


def _stored_run(tenant_id: uuid.UUID, run_id: uuid.UUID) -> object:
    async def act() -> object:
        repository = CheckpointRepository(get_session_factory())
        run = await repository.get_for_tenant(tenant_id=tenant_id, checkpoint_run_id=run_id)
        assert run is not None
        return run

    return asyncio.run(act())


def _events_and_refs(
    tenant_id: uuid.UUID, site_id: uuid.UUID
) -> tuple[list[Event], list[EventEvidenceRef]]:
    async def act() -> tuple[list[Event], list[EventEvidenceRef]]:
        factory = get_session_factory()
        async with factory() as session:
            events = list(
                (
                    await session.scalars(
                        select(Event).where(Event.tenant_id == tenant_id, Event.site_id == site_id)
                    )
                ).all()
            )
            refs = list(
                (
                    await session.scalars(
                        select(EventEvidenceRef).where(EventEvidenceRef.tenant_id == tenant_id)
                    )
                ).all()
            )
        return events, refs

    return asyncio.run(act())


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


def test_challenge_fixture_yields_challenge_suspected_event_automatically(
    challenge_site: str,
) -> None:
    settings = get_settings()
    assert settings.browser_allow_private_networks, (
        "integration fixture requires explicit test opt-in"
    )
    registered = asyncio.run(_register_diagnostic(challenge_site, "/challenge"))
    tenant_id = registered["tenant_id"]
    run_id = registered["checkpoint_run_id"]

    # Real browser collection → persist → finalize (classification + enqueue).
    _run_browser_once()

    stored = _stored_run(tenant_id, run_id)
    classification = dict(stored.browser_access_classification or {})  # type: ignore[attr-defined]
    assert classification.get("state") == "challenge_suspected"
    reason = str(classification.get("reason", ""))
    assert "deterministic challenge markers observed" in reason

    site_id = cast(uuid.UUID, stored.site_id)  # type: ignore[attr-defined]

    # Automatic derivation through the real worker.
    jobs = _derive_jobs(tenant_id, run_id)
    assert len(jobs) == 1
    assert jobs[0].idempotency_key == f"derive-browser-events:{run_id}:e26-v1"
    assert _process_one_derive_job() is True

    events, refs = _events_and_refs(tenant_id, site_id)
    challenge_events = [
        event
        for event in events
        if event.event_definition_id == definition_id("BROWSER_ACCESS_CHALLENGE_SUSPECTED")
    ]
    degraded_events = [
        event
        for event in events
        if event.event_definition_id == definition_id("BROWSER_SOURCE_DEGRADED")
    ]
    assert len(challenge_events) == 1
    assert len(degraded_events) == 0
    assert challenge_events[0].severity == "MEDIUM"
    trigger_refs = [
        ref
        for ref in refs
        if ref.event_id == challenge_events[0].id
        and ref.evidence_kind == "CHECKPOINT_RUN"
        and ref.source_id == run_id
        and ref.relation == "TRIGGER_AFTER"
    ]
    assert len(trigger_refs) == 1

    # No raw fixture content in any field touched by this implementation.
    persisted_surfaces = {
        "classification": str(classification),
        "manifest": str(stored.manifest),  # type: ignore[attr-defined]
        "limitations": str(stored.limitations),  # type: ignore[attr-defined]
        "environment": str(stored.environment),  # type: ignore[attr-defined]
        "events": str([(event.summary, event.details) for event in events]),
        "refs": str([(ref.summary, ref.relation) for ref in refs]),
        "jobs": str([job.payload for job in jobs]),
    }
    for surface, value in persisted_surfaces.items():
        assert CHALLENGE_SENTINEL not in value, surface
        assert "captcha to continue" not in value.lower(), surface


def test_plain_403_without_marker_stays_degraded(challenge_site: str) -> None:
    settings = get_settings()
    assert settings.browser_allow_private_networks
    registered = asyncio.run(_register_diagnostic(challenge_site, "/plain-403"))
    tenant_id = registered["tenant_id"]
    run_id = registered["checkpoint_run_id"]

    _run_browser_once()

    stored = _stored_run(tenant_id, run_id)
    classification = dict(stored.browser_access_classification or {})  # type: ignore[attr-defined]
    assert classification.get("state") == "degraded"

    site_id = cast(uuid.UUID, stored.site_id)  # type: ignore[attr-defined]
    assert _process_one_derive_job() is True

    events, refs = _events_and_refs(tenant_id, site_id)
    challenge_events = [
        event
        for event in events
        if event.event_definition_id == definition_id("BROWSER_ACCESS_CHALLENGE_SUSPECTED")
    ]
    degraded_events = [
        event
        for event in events
        if event.event_definition_id == definition_id("BROWSER_SOURCE_DEGRADED")
    ]
    assert len(degraded_events) == 1
    assert len(challenge_events) == 0
    assert any(
        ref.evidence_kind == "CHECKPOINT_RUN"
        and ref.source_id == run_id
        and ref.relation == "TRIGGER_AFTER"
        and ref.event_id == degraded_events[0].id
        for ref in refs
    )


def test_healthy_page_produces_no_reliability_event(challenge_site: str) -> None:
    settings = get_settings()
    assert settings.browser_allow_private_networks
    registered = asyncio.run(_register_diagnostic(challenge_site, "/"))
    tenant_id = registered["tenant_id"]
    run_id = registered["checkpoint_run_id"]

    _run_browser_once()

    stored = _stored_run(tenant_id, run_id)
    classification = dict(stored.browser_access_classification or {})  # type: ignore[attr-defined]
    assert classification.get("state") == "ok"

    site_id = cast(uuid.UUID, stored.site_id)  # type: ignore[attr-defined]
    assert _process_one_derive_job() is True

    events, _ = _events_and_refs(tenant_id, site_id)
    reliability_events = [
        event
        for event in events
        if event.event_definition_id
        in {
            definition_id("BROWSER_SOURCE_DEGRADED"),
            definition_id("BROWSER_ACCESS_CHALLENGE_SUSPECTED"),
        }
    ]
    assert reliability_events == []


def test_challenge_derivation_is_idempotent(challenge_site: str) -> None:
    seeded_run = asyncio.run(_register_diagnostic(challenge_site, "/challenge"))
    tenant_id = seeded_run["tenant_id"]
    run_id = seeded_run["checkpoint_run_id"]

    _run_browser_once()
    stored = _stored_run(tenant_id, run_id)
    site_id = cast(uuid.UUID, stored.site_id)  # type: ignore[attr-defined]
    assert _process_one_derive_job() is True

    # Re-schedule identical derive work via the canonical enqueue API and let
    # the real worker process it again.
    async def reschedule() -> None:
        factory = get_session_factory()
        queue = JobQueue(factory)
        await queue.enqueue(
            tenant_id=tenant_id,
            job_type="DERIVE_BROWSER_EVENTS",
            payload={"checkpoint_run_id": str(run_id)},
            idempotency_key=f"derive-browser-events:{run_id}:retry-simulation",
        )

    asyncio.run(reschedule())
    assert _process_one_derive_job() is True

    assert len(_derive_jobs(tenant_id, run_id)) == 2  # original + retry-simulation key
    events, refs = _events_and_refs(tenant_id, site_id)
    challenge_events = [
        event
        for event in events
        if event.event_definition_id == definition_id("BROWSER_ACCESS_CHALLENGE_SUSPECTED")
    ]
    assert len(challenge_events) == 1
    trigger_refs = [
        ref
        for ref in refs
        if ref.event_id == challenge_events[0].id
        and ref.source_id == run_id
        and ref.relation == "TRIGGER_AFTER"
    ]
    assert len(trigger_refs) == 1
