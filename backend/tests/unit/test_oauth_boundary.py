import urllib.parse

from app.connectors.oauth import (
    build_authorization_request,
    least_privilege_scopes,
    map_refresh_failure,
)


def test_scopes_are_least_privilege_and_read_only() -> None:
    assert least_privilege_scopes("GA4") == ("https://www.googleapis.com/auth/analytics.readonly",)
    assert least_privilege_scopes("GSC") == ("https://www.googleapis.com/auth/webmasters.readonly",)
    assert least_privilege_scopes("GAM") == ("https://www.googleapis.com/auth/admanager.readonly",)


def test_unknown_connector_is_rejected() -> None:
    import pytest

    with pytest.raises(ValueError, match="unknown connector"):
        least_privilege_scopes("GAM_WRITE")


def test_authorization_url_contains_consent_and_state() -> None:
    request = build_authorization_request(
        client_id="client-1", redirect_uri="https://pi.example/cb", connector="GA4"
    )
    parsed = urllib.parse.urlparse(request.url)
    query = urllib.parse.parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert parsed.netloc == "accounts.google.com"
    assert query["response_type"] == ["code"]
    assert query["access_type"] == ["offline"]
    assert query["prompt"] == ["consent"]
    assert query["scope"] == [" ".join(request.scopes)]
    assert len(query["state"][0]) >= 16


def test_refresh_failures_map_to_connection_states() -> None:
    assert map_refresh_failure("invalid_grant") == "AUTH_EXPIRED"
    assert map_refresh_failure("unauthorized_client") == "PERMISSION_ERROR"
    assert map_refresh_failure("anything_else") == "DEGRADED"
