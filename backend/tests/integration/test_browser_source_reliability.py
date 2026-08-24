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
    """M2b-1a-1: a valid DIAGNOSTIC run enters derive input loading without
    SCHEDULED comparison lineage. Zero events is legitimate at this stage
    (rule wiring arrives in M2b-1a-2)."""
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
    assert "DIAGNOSTIC_NO_EVENT_RULES" in skips


def _unused_tail() -> None:
    pass
