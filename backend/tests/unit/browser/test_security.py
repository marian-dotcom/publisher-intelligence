from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from playwright.async_api import Request

from app.browser.security import BrowserBlockedError, BrowserNetworkGuard, sanitize_url


def test_sanitize_url_removes_credentials_query_and_fragment() -> None:
    assert (
        sanitize_url("https://user:secret@Example.COM:8443/path?q=secret#fragment")
        == "https://example.com:8443/path"
    )
    assert sanitize_url("https://example.com:invalid/path") == "[INVALID_URL]"


def test_guard_supports_playwright_bound_handler_cache() -> None:
    guard = BrowserNetworkGuard(
        canonical_domain="example.com",
        allow_private_networks=False,
        max_requests=10,
    )

    guard.__dict__["_playwright_handler_wrapper"] = object()

    assert "_playwright_handler_wrapper" in guard.__dict__


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://10.0.0.1/",
    ],
)
async def test_private_and_metadata_destinations_are_blocked(url: str) -> None:
    hostname = url.split("//", 1)[1].split("/", 1)[0].strip("[]")
    guard = BrowserNetworkGuard(
        canonical_domain=hostname,
        allow_private_networks=False,
        max_requests=10,
    )
    with pytest.raises(BrowserBlockedError):
        await guard.validate_initial(url)


async def test_cross_site_top_level_redirect_is_blocked_before_dns() -> None:
    guard = BrowserNetworkGuard(
        canonical_domain="example.com",
        allow_private_networks=False,
        max_requests=10,
    )
    with pytest.raises(BrowserBlockedError, match="cross-site") as raised:
        await guard.validate("https://attacker.example/redirect", top_level=True)
    assert raised.value.code == "CROSS_SITE_REDIRECT"


async def test_same_site_www_redirect_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    async def public_address(self: BrowserNetworkGuard, hostname: str, port: int) -> set[str]:
        del self, hostname, port
        return {"93.184.216.34"}

    monkeypatch.setattr(BrowserNetworkGuard, "_resolve", public_address)
    guard = BrowserNetworkGuard(
        canonical_domain="example.com",
        allow_private_networks=False,
        max_requests=10,
    )

    assert (
        await guard.validate("https://www.example.com/redirect?q=secret", top_level=True)
        == "https://www.example.com/redirect"
    )


async def test_private_subresource_is_aborted_and_recorded() -> None:
    guard = BrowserNetworkGuard(
        canonical_domain="example.com",
        allow_private_networks=False,
        max_requests=10,
    )
    request = Mock()
    request.url = "http://127.0.0.1/private?token=secret"
    request.resource_type = "script"
    request.is_navigation_request.return_value = False
    route = Mock()
    route.abort = AsyncMock()
    route.continue_ = AsyncMock()

    await guard.route(route, request)

    route.abort.assert_awaited_once_with("blockedbyclient")
    route.continue_.assert_not_awaited()
    assert guard.blocked_requests[0].url == "http://127.0.0.1/private"
    assert guard.blocked_requests[0].error_text == "PRIVATE_DESTINATION"


async def test_navigation_without_available_frame_is_conservatively_top_level() -> None:
    class EarlyNavigationRequest:
        url = "https://attacker.example/redirect?token=secret"
        resource_type = "document"

        @property
        def frame(self) -> object:
            raise AttributeError("frame does not exist yet")

        def is_navigation_request(self) -> bool:
            return True

    guard = BrowserNetworkGuard(
        canonical_domain="example.com",
        allow_private_networks=False,
        max_requests=10,
    )
    route = Mock()
    route.abort = AsyncMock()
    route.continue_ = AsyncMock()

    await guard.route(route, cast(Request, EarlyNavigationRequest()))

    route.abort.assert_awaited_once_with("blockedbyclient")
    route.continue_.assert_not_awaited()
    assert guard.blocked_top_level
    assert guard.blocked_requests[0].error_text == "CROSS_SITE_REDIRECT"
    assert "secret" not in guard.blocked_requests[0].url
