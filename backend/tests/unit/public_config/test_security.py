import asyncio

import pytest

from app.public_config.security import (
    PublicConfigNetworkGuard,
    PublicConfigSecurityError,
    derive_public_config_url,
    sanitize_url,
)


async def _public_resolver(hostname: str, port: int) -> set[str]:
    del hostname, port
    return {"93.184.216.34"}


def test_derived_urls_use_only_fixed_paths_and_sanitize_secrets() -> None:
    assert (
        derive_public_config_url(
            canonical_scheme="HTTPS", canonical_domain="Example.COM.", config_type="ROBOTS_TXT"
        )
        == "https://example.com/robots.txt"
    )
    assert sanitize_url("https://user:secret@example.com/a?q=secret#fragment") == (
        "https://example.com/a"
    )


@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("ftp://example.com/robots.txt", "INVALID_SCHEME"),
        ("https://user:secret@example.com/robots.txt", "URL_CREDENTIALS"),
        ("https://127.0.0.1/robots.txt", "IP_LITERAL"),
        ("https://example.com:8443/robots.txt", "INVALID_PORT"),
        ("https://attacker.example/robots.txt", "CROSS_SITE_REDIRECT"),
    ],
)
async def test_guard_rejects_unsafe_url_forms(url: str, code: str) -> None:
    guard = PublicConfigNetworkGuard("example.com", resolver=_public_resolver)

    with pytest.raises(PublicConfigSecurityError) as raised:
        await guard.validate(url)

    assert raised.value.code == code


async def test_guard_allows_only_canonical_and_www_alias() -> None:
    guard = PublicConfigNetworkGuard("example.com", resolver=_public_resolver)

    validated = await guard.validate("https://www.example.com/robots.txt?q=ignored")

    assert validated.request_url == "https://www.example.com/robots.txt?q=ignored"
    assert validated.safe_url == "https://www.example.com/robots.txt"


@pytest.mark.parametrize("address", ["127.0.0.1", "169.254.169.254", "10.0.0.1", "::1"])
async def test_guard_rejects_any_non_global_dns_answer(address: str) -> None:
    async def resolver(hostname: str, port: int) -> set[str]:
        del hostname, port
        return {"93.184.216.34", address}

    guard = PublicConfigNetworkGuard("example.com", resolver=resolver)

    with pytest.raises(PublicConfigSecurityError) as raised:
        await guard.validate("https://example.com/robots.txt")

    assert raised.value.code == "PRIVATE_DESTINATION"


async def test_guard_bounds_dns_resolution_time() -> None:
    async def slow_resolver(hostname: str, port: int) -> set[str]:
        del hostname, port
        await asyncio.sleep(0.05)
        return {"93.184.216.34"}

    guard = PublicConfigNetworkGuard(
        "example.com", dns_timeout_seconds=0.001, resolver=slow_resolver
    )

    with pytest.raises(PublicConfigSecurityError) as raised:
        await guard.validate("https://example.com/robots.txt")

    assert raised.value.code == "DNS_TIMEOUT"


async def test_metadata_hostname_is_blocked_even_when_configured() -> None:
    guard = PublicConfigNetworkGuard("metadata.google.internal", resolver=_public_resolver)

    with pytest.raises(PublicConfigSecurityError) as raised:
        await guard.validate("http://metadata.google.internal/robots.txt")

    assert raised.value.code == "METADATA_DESTINATION"
