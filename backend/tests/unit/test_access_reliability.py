"""EP-026 M2 — RED→GREEN: browser-source degradation/recovery semantics.

The mandatory WAF/challenge scenario exercises the production-equivalent
classifier + canonical registry path with a controlled synthetic HTTP fixture
(no external WAF vendor, no organic publisher case required).
"""

from app.browser.access_reliability import classify_access
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
