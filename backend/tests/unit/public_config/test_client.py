import httpx
import pytest

from app.public_config.client import (
    ROBOTS_TXT_MAX_BYTES,
    PublicConfigClient,
    PublicConfigFetchError,
)


async def _public_resolver(hostname: str, port: int) -> set[str]:
    del hostname, port
    return {"93.184.216.34"}


async def test_client_fetches_fixed_path_without_automatic_redirects() -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        if request.url.host == "example.com":
            return httpx.Response(302, headers={"Location": "https://www.example.com/robots.txt"})
        return httpx.Response(
            200, headers={"Content-Type": "text/plain; charset=utf-8"}, content=b"ok"
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        result = await PublicConfigClient(client=http_client, resolver=_public_resolver).fetch(
            canonical_scheme="https",
            canonical_domain="example.com",
            config_type="ROBOTS_TXT",
        )

    assert requested == [
        "https://example.com/robots.txt",
        "https://www.example.com/robots.txt",
    ]
    assert result.url == "https://www.example.com/robots.txt"
    assert result.content == b"ok"
    assert result.content_type == "text/plain"
    assert result.redirect_count == 1
    assert len(result.content_hash) == 64


async def test_redirect_does_not_replay_response_cookies() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                302,
                headers={
                    "Location": "https://www.example.com/ads.txt",
                    "Set-Cookie": "session=untrusted",
                },
            )
        return httpx.Response(200, content=b"seller.example, account, DIRECT")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        await PublicConfigClient(client=http_client, resolver=_public_resolver).fetch(
            canonical_scheme="https",
            canonical_domain="example.com",
            config_type="ADS_TXT",
        )

    assert len(requests) == 2
    assert "cookie" not in requests[1].headers


async def test_cross_site_redirect_is_blocked_before_second_request() -> None:
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(302, headers={"Location": "https://attacker.example/private"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        with pytest.raises(PublicConfigFetchError) as raised:
            await PublicConfigClient(client=http_client, resolver=_public_resolver).fetch(
                canonical_scheme="https",
                canonical_domain="example.com",
                config_type="ADS_TXT",
            )

    assert raised.value.code == "PUBLIC_CONFIG_SECURITY_ERROR"
    assert not raised.value.retryable
    assert requests == 1


async def test_private_redirect_dns_answer_is_blocked_before_transport() -> None:
    requests = 0

    async def resolver(hostname: str, port: int) -> set[str]:
        del port
        return {"10.0.0.1"} if hostname.startswith("www.") else {"93.184.216.34"}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(302, headers={"Location": "https://www.example.com/ads.txt"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        with pytest.raises(PublicConfigFetchError) as raised:
            await PublicConfigClient(client=http_client, resolver=resolver).fetch(
                canonical_scheme="https",
                canonical_domain="example.com",
                config_type="ADS_TXT",
            )

    assert raised.value.code == "PUBLIC_CONFIG_SECURITY_ERROR"
    assert requests == 1


async def test_redirect_loop_and_limit_fail_closed() -> None:
    def loop_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": str(request.url)})

    async with httpx.AsyncClient(transport=httpx.MockTransport(loop_handler)) as http_client:
        with pytest.raises(PublicConfigFetchError, match="loop"):
            await PublicConfigClient(client=http_client, resolver=_public_resolver).fetch(
                canonical_scheme="https",
                canonical_domain="example.com",
                config_type="ROBOTS_TXT",
            )

    def chain_handler(request: httpx.Request) -> httpx.Response:
        step = int(request.url.params.get("step", "0"))
        return httpx.Response(302, headers={"Location": f"/robots.txt?step={step + 1}"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(chain_handler)) as http_client:
        with pytest.raises(PublicConfigFetchError, match="limit"):
            await PublicConfigClient(
                client=http_client, resolver=_public_resolver, max_redirects=2
            ).fetch(
                canonical_scheme="https",
                canonical_domain="example.com",
                config_type="ROBOTS_TXT",
            )


async def test_oversized_body_and_timeout_have_controlled_errors() -> None:
    def large_handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, content=b"x" * (ROBOTS_TXT_MAX_BYTES + 1))

    async with httpx.AsyncClient(transport=httpx.MockTransport(large_handler)) as http_client:
        with pytest.raises(PublicConfigFetchError) as raised:
            await PublicConfigClient(client=http_client, resolver=_public_resolver).fetch(
                canonical_scheme="https",
                canonical_domain="example.com",
                config_type="ROBOTS_TXT",
            )
    assert raised.value.code == "PUBLIC_CONFIG_TOO_LARGE"
    assert not raised.value.retryable

    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("secret upstream detail", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(timeout_handler)) as http_client:
        with pytest.raises(PublicConfigFetchError) as raised:
            await PublicConfigClient(client=http_client, resolver=_public_resolver).fetch(
                canonical_scheme="https",
                canonical_domain="example.com",
                config_type="ROBOTS_TXT",
            )
    assert raised.value.code == "PUBLIC_CONFIG_TIMEOUT"
    assert raised.value.retryable
    assert "secret" not in str(raised.value)
