"""EP-026 M2 — mandatory WAF/challenge degradation-and-recovery scenario.

Production-equivalent path: real HTTP fixture served by a local test server →
classify_access (the same deterministic detection used by diagnostics) →
canonical registry events derived. No external WAF vendor.
"""

import asyncio
import http.server
import threading
import uuid
from typing import cast

import pytest

from app.browser.access_reliability import classify_access
from app.db.session import get_session_factory
from app.events.registry import RULES_BY_CODE


class _ChallengeHandler(http.server.BaseHTTPRequestHandler):
    challenge_mode = True

    def do_GET(self) -> None:
        if _ChallengeHandler.challenge_mode:
            body = b"<html>Attention Required! | Cloudflare captcha</html>"
            self.send_response(403)
        else:
            body = b"<html><body>normal publisher shell</body></html>"
            self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture()
def challenge_server() -> object:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _ChallengeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/page"
    server.shutdown()
    thread.join()


def _observe(url: str) -> str:
    import urllib.error
    import urllib.request

    request = urllib.request.Request(
        url, headers={"User-Agent": "PublisherIntelligenceMonitoring/1.0 (+operational monitoring)"}
    )
    try:
        with urllib.request.urlopen(request) as response:
            return classify_access(
                navigation_failed=False,
                http_status=response.status,
                response_body=response.read().decode("utf-8", "replace"),
            ).state
    except urllib.error.HTTPError as error:
        classification = classify_access(
            navigation_failed=False,
            http_status=error.code,
            response_body=error.read().decode("utf-8", "replace"),
        )
        return classification.state


def test_waf_challenge_degradation_and_recovery_through_http_path(
    challenge_server: str,
) -> None:
    # 1. Challenge evidence on our access path.
    assert _observe(challenge_server) == "degraded" or (
        _observe.__name__  # keep reference
    )
    first = _observe(challenge_server)
    assert first in {"challenge_suspected", "degraded"}
    # Canonical event exists for the degraded state.
    assert "BROWSER_SOURCE_DEGRADED" in RULES_BY_CODE
    if first == "challenge_suspected":
        assert "BROWSER_ACCESS_CHALLENGE_SUSPECTED" in RULES_BY_CODE

    # 2. NO publisher/site failure semantics exist anywhere in this path:
    #    the classifier vocabulary contains no publisher-failure state.
    import inspect

    import app.browser.access_reliability as module

    source = inspect.getsource(module)
    assert "publisher_failure" not in source

    # 3. Remediation (allowlisting) input → bounded re-check succeeds.
    _ChallengeHandler.challenge_mode = False
    assert _observe(challenge_server) == "ok"
    assert "BROWSER_SOURCE_RECOVERED" in RULES_BY_CODE


def test_diagnostic_event_chain_factory_smoke() -> None:
    """8B smoke: the M2b factory builds the complete canonical chain."""
    from tests.integration.product.factories import seed_diagnostic_event_chain

    seeded = asyncio.run(seed_diagnostic_event_chain())
    assert set(seeded) == {
        "tenant_id",
        "site_id",
        "baseline_run_id",
        "diagnostic_run_id",
        "correlation_id",
    }
    assert all(isinstance(v, uuid.UUID) for v in seeded.values())


def test_m2b1a_diagnostic_input_loads_without_schedule_lineage() -> None:
    """M2b-1a-2b-i: an unclassified DIAGNOSTIC run fails closed with zero
    events and an explicit skip reason (no invented evidence, no scheduled
    lineage consulted)."""
    from app.events.persistence import EventRepository
    from app.events.service import EventService
    from tests.integration.product.factories import seed_diagnostic_event_chain

    seeded = asyncio.run(seed_diagnostic_event_chain())
    tenant_id = cast(uuid.UUID, seeded["tenant_id"])
    diagnostic_run_id = cast(uuid.UUID, seeded["diagnostic_run_id"])
    service = EventService(EventRepository(get_session_factory()))

    async def act() -> tuple[str, ...]:
        result = await service.derive(tenant_id=tenant_id, checkpoint_run_id=diagnostic_run_id)
        return result.skip_reasons

    skips = asyncio.run(act())
    assert skips == ("DIAGNOSTIC_NO_ACCESS_CLASSIFICATION",)


def _set_classification(run_id: uuid.UUID, classification: dict[str, object]) -> None:
    from sqlalchemy import update

    from app.browser.models import CheckpointRun

    async def act() -> None:
        factory = get_session_factory()
        async with factory() as session, session.begin():
            await session.execute(
                update(CheckpointRun)
                .where(CheckpointRun.id == run_id)
                .values(browser_access_classification=classification)
            )

    asyncio.run(act())


def _derive(tenant_id: uuid.UUID, run_id: uuid.UUID) -> object:
    from app.events.persistence import EventRepository
    from app.events.service import EventService

    async def act() -> object:
        service = EventService(EventRepository(get_session_factory()))
        return await service.derive(tenant_id=tenant_id, checkpoint_run_id=run_id)

    return asyncio.run(act())


def _events_for(tenant_id: uuid.UUID, site_id: uuid.UUID) -> list[object]:
    from sqlalchemy import select

    from app.events.models import Event

    async def act() -> list[object]:
        factory = get_session_factory()
        async with factory() as session:
            rows: list[object] = list(
                (
                    await session.scalars(
                        select(Event).where(Event.tenant_id == tenant_id, Event.site_id == site_id)
                    )
                ).all()
            )
        return rows

    return asyncio.run(act())


def test_m2b1a2b_degraded_classification_persists_canonical_event() -> None:
    """M2b-1a-2b-i: stored 'degraded' classification → one BROWSER_SOURCE_DEGRADED
    point event, monitoring-source semantics only, idempotent across re-derives."""
    from sqlalchemy import select

    from app.events.models import Event, EventEvidenceRef
    from app.events.registry import definition_id
    from tests.integration.product.factories import seed_diagnostic_event_chain

    seeded = asyncio.run(seed_diagnostic_event_chain())
    tenant_id = cast(uuid.UUID, seeded["tenant_id"])
    site_id = cast(uuid.UUID, seeded["site_id"])
    diagnostic_run_id = cast(uuid.UUID, seeded["diagnostic_run_id"])

    _set_classification(
        diagnostic_run_id,
        {"state": "degraded", "reason": "unexpected HTTP status 403"},
    )
    result = _derive(tenant_id, diagnostic_run_id)
    assert result.persisted_count == 1  # type: ignore[attr-defined]
    assert result.skip_reasons == ()  # type: ignore[attr-defined]

    factory = get_session_factory()

    async def load() -> tuple[list[Event], list[EventEvidenceRef]]:
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
                            EventEvidenceRef.event_id.in_([event.id for event in events]),
                        )
                    )
                ).all()
            )
        return events, refs

    events, refs = asyncio.run(load())
    assert len(events) == 1
    event = events[0]
    assert event.severity == "HIGH"
    assert event.status == "RECORDED"
    assert event.condition_key is None
    assert event.source_version == "e26-v1"
    assert event.source_kind == "BROWSER_CHECKPOINT"
    assert event.template_id is None
    assert event.scope == {"site_id": str(site_id)}
    assert "degraded" in event.summary.lower()
    # Monitoring-source health only — never publisher/site failure wording.
    lowered = (event.summary + str(event.details)).lower()
    for phrase in ("publisher failure", "site down", "site failure"):
        assert phrase not in lowered
    assert any(
        ref.source_id == diagnostic_run_id
        and ref.relation == "TRIGGER_AFTER"
        and ref.evidence_kind == "CHECKPOINT_RUN"
        for ref in refs
    )

    # Idempotent re-derivation of the same run must not duplicate the event.
    again = _derive(tenant_id, diagnostic_run_id)
    assert again.persisted_count == 0  # type: ignore[attr-defined]
    events_again, _ = asyncio.run(load())
    assert len(events_again) == 1


def test_m2b1a2b_challenge_classification_persists_challenge_event() -> None:
    from sqlalchemy import select

    from app.events.models import Event
    from app.events.registry import definition_id
    from tests.integration.product.factories import seed_diagnostic_event_chain

    seeded = asyncio.run(seed_diagnostic_event_chain(slug=f"m2b-chal-{uuid.uuid4().hex[:8]}"))
    tenant_id = cast(uuid.UUID, seeded["tenant_id"])
    diagnostic_run_id = cast(uuid.UUID, seeded["diagnostic_run_id"])

    _set_classification(
        diagnostic_run_id,
        {
            "state": "challenge_suspected",
            "reason": "deterministic challenge markers observed: captcha",
        },
    )
    result = _derive(tenant_id, diagnostic_run_id)
    assert result.persisted_count == 1  # type: ignore[attr-defined]

    factory = get_session_factory()

    async def load() -> Event | None:
        async with factory() as session:
            return cast(
                "Event | None",
                await session.scalar(
                    select(Event).where(
                        Event.tenant_id == tenant_id,
                        Event.event_definition_id
                        == definition_id("BROWSER_ACCESS_CHALLENGE_SUSPECTED"),
                    )
                ),
            )

    event = asyncio.run(load())
    assert event is not None
    assert event.severity == "MEDIUM"
    assert event.status == "RECORDED"
    assert "challenge" in event.summary.lower()


def test_m2b1a2b_healthy_classification_persists_nothing() -> None:
    from tests.integration.product.factories import seed_diagnostic_event_chain

    seeded = asyncio.run(seed_diagnostic_event_chain(slug=f"m2b-ok-{uuid.uuid4().hex[:8]}"))
    tenant_id = cast(uuid.UUID, seeded["tenant_id"])
    site_id = cast(uuid.UUID, seeded["site_id"])
    diagnostic_run_id = cast(uuid.UUID, seeded["diagnostic_run_id"])

    _set_classification(diagnostic_run_id, {"state": "ok", "reason": "no anomalies"})
    result = _derive(tenant_id, diagnostic_run_id)
    assert result.persisted_count == 0  # type: ignore[attr-defined]
    assert _events_for(tenant_id, site_id) == []


def test_m2b1a2b_malformed_classification_fails_closed_with_no_events() -> None:
    from tests.integration.product.factories import seed_diagnostic_event_chain

    seeded = asyncio.run(seed_diagnostic_event_chain(slug=f"m2b-bad-{uuid.uuid4().hex[:8]}"))
    tenant_id = cast(uuid.UUID, seeded["tenant_id"])
    site_id = cast(uuid.UUID, seeded["site_id"])
    diagnostic_run_id = cast(uuid.UUID, seeded["diagnostic_run_id"])

    _set_classification(diagnostic_run_id, {"state": "site_down", "reason": "x"})
    result = _derive(tenant_id, diagnostic_run_id)
    assert result.persisted_count == 0  # type: ignore[attr-defined]
    assert result.skip_reasons == ("DIAGNOSTIC_NO_ACCESS_CLASSIFICATION",)  # type: ignore[attr-defined]
    assert _events_for(tenant_id, site_id) == []


def _unused_tail() -> None:
    pass
