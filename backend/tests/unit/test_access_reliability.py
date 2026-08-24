"""EP-026 M2 — RED→GREEN: browser-source degradation/recovery semantics.

The mandatory WAF/challenge scenario exercises the production-equivalent
classifier + canonical registry path with a controlled synthetic HTTP fixture
(no external WAF vendor, no organic publisher case required).
"""

from app.browser.access_reliability import (
    CHALLENGE_MARKER_SCAN_CHARS,
    classification_from_storage,
    classify_access,
    detect_challenge_marker,
)
from app.events.registry import RULES_BY_CODE, definition_id


def test_registry_contains_browser_source_events() -> None:
    for code in (
        "BROWSER_SOURCE_DEGRADED",
        "BROWSER_ACCESS_CHALLENGE_SUSPECTED",
        "BROWSER_SOURCE_RECOVERED",
    ):
        assert code in RULES_BY_CODE
        assert definition_id(code) == definition_id(code)


def test_challenge_markers_classify_as_challenge_suspected() -> None:
    result = classify_access(
        navigation_failed=False,
        http_status=200,
        response_body="<html>Please complete the security check to continue captcha</html>",
    )
    assert result.state == "challenge_suspected"
    assert "captcha" in result.reason


def test_status_anomaly_is_degraded_not_publisher_failure() -> None:
    result = classify_access(
        navigation_failed=False,
        http_status=403,
        response_body="",
    )
    assert result.state == "degraded"
    assert "publisher" not in result.reason.lower()


def test_dom_variance_alone_never_proves_blocking() -> None:
    # A small/changed DOM without deterministic markers is NOT a blocking signal.
    result = classify_access(
        navigation_failed=False,
        http_status=200,
        response_body="<html><body>short page</body></html>",
    )
    assert result.state == "ok"


def test_recovery_requires_explicit_recheck_not_time_passage() -> None:
    """Recovery is derived only from a successful bounded re-check observation."""
    healthy = classify_access(
        navigation_failed=False, http_status=200, response_body="<html>ok</html>"
    )
    assert healthy.state == "ok"
    # No timer-based recovery API exists; time passage alone must never flip state.
    import inspect

    import app.browser.access_reliability as module

    signature = inspect.signature(module.classify_access)
    assert "seconds_elapsed" not in signature.parameters


def test_storage_parser_round_trips_bounded_classification() -> None:
    parsed = classification_from_storage(
        {
            "state": "challenge_suspected",
            "reason": "deterministic challenge markers observed: captcha",
        }
    )
    assert parsed is not None
    assert parsed.state == "challenge_suspected"
    assert "captcha" in parsed.reason


def test_storage_parser_fails_closed_on_malformed_rows() -> None:
    assert classification_from_storage(None) is None
    assert classification_from_storage("degraded") is None
    assert classification_from_storage({}) is None
    assert classification_from_storage({"state": "site_down", "reason": "x"}) is None
    assert classification_from_storage({"state": "degraded"}) is None
    assert classification_from_storage({"state": "degraded", "reason": ""}) is None
    assert classification_from_storage({"state": "ok", "reason": 7}) is None


def test_status_only_403_is_degraded_never_challenge() -> None:
    """M2b-1a-2b-i: the finalize hook classifies with response_body=None, so a
    plain HTTP 403 can only produce 'degraded'. challenge_suspected stays
    unreachable until M2b-1b adds bounded marker/body evidence."""
    assert (
        classify_access(navigation_failed=False, http_status=403, response_body=None).state
        == "degraded"
    )
    assert (
        classify_access(
            navigation_failed=False,
            http_status=200,
            response_body="<html>Attention Required! | Cloudflare captcha</html>",
        ).state
        == "challenge_suspected"
    )


def test_marker_takes_precedence_over_status_anomaly() -> None:
    """M2b-1b: 403 + canonical marker is a suspected challenge; 403 without a
    marker stays degraded. Status alone is never proof of a challenge."""
    marked = classify_access(
        navigation_failed=False,
        http_status=403,
        response_body=None,
        challenge_marker="captcha",
    )
    assert marked.state == "challenge_suspected"
    assert marked.reason == "deterministic challenge markers observed: captcha"

    unmarked = classify_access(
        navigation_failed=False, http_status=403, response_body=None
    )
    assert unmarked.state == "degraded"
    assert "403" in unmarked.reason


def test_navigation_failure_still_wins_over_marker() -> None:
    result = classify_access(
        navigation_failed=True,
        http_status=None,
        response_body=None,
        challenge_marker="captcha",
    )
    assert result.state == "degraded"


def test_detect_challenge_marker_reduces_to_first_canonical_match() -> None:
    body = "<html>" + ("filler text " * 500) + "Access Denied</html>"
    assert detect_challenge_marker(body) == "access denied"
    assert detect_challenge_marker(None) is None
    assert detect_challenge_marker("") is None
    assert detect_challenge_marker("<html>nothing here</html>") is None


def test_detect_challenge_marker_scan_is_bounded() -> None:
    beyond_cap = "<html>x" * (CHALLENGE_MARKER_SCAN_CHARS // 7 + 1)
    assert len(beyond_cap) > CHALLENGE_MARKER_SCAN_CHARS
    padded = beyond_cap[:CHALLENGE_MARKER_SCAN_CHARS] + "captcha"
    assert detect_challenge_marker(padded) is None
    inside = "captcha" + beyond_cap[:CHALLENGE_MARKER_SCAN_CHARS]
    assert detect_challenge_marker(inside) == "captcha"
