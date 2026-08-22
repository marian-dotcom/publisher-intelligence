import asyncio
import hashlib
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx

from app.public_config.contracts import ConfigType
from app.public_config.security import (
    PublicConfigNetworkGuard,
    PublicConfigSecurityError,
    Resolver,
    derive_public_config_url,
    resolve_public_addresses,
    sanitize_url,
)

ROBOTS_TXT_MAX_BYTES = 512_000
ADS_TXT_MAX_BYTES = 2_097_152
MAX_REDIRECTS = 5
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
USER_AGENT = "PublisherIntelligencePublicConfig/1.0"


@dataclass(frozen=True, slots=True)
class PublicConfigFetchResult:
    url: str
    http_status: int
    content: bytes
    content_hash: str
    content_type: str | None
    redirect_count: int


class PublicConfigFetchError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class PublicConfigClient:
    def __init__(
        self,
        *,
        connect_timeout_seconds: float = 5.0,
        read_timeout_seconds: float = 10.0,
        total_timeout_seconds: float = 20.0,
        dns_timeout_seconds: float = 2.0,
        max_redirects: int = MAX_REDIRECTS,
        resolver: Resolver = resolve_public_addresses,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._timeout = httpx.Timeout(
            read_timeout_seconds,
            connect=connect_timeout_seconds,
            write=connect_timeout_seconds,
            pool=connect_timeout_seconds,
        )
        self._total_timeout_seconds = total_timeout_seconds
        self._dns_timeout_seconds = dns_timeout_seconds
        self._max_redirects = max_redirects
        self._resolver = resolver
        self._client = client

    async def fetch(
        self,
        *,
        canonical_scheme: str,
        canonical_domain: str,
        config_type: ConfigType,
    ) -> PublicConfigFetchResult:
        try:
            initial_url = derive_public_config_url(
                canonical_scheme=canonical_scheme,
                canonical_domain=canonical_domain,
                config_type=config_type,
            )
        except PublicConfigSecurityError as error:
            raise PublicConfigFetchError(
                "PUBLIC_CONFIG_SECURITY_ERROR", str(error), retryable=False
            ) from error
        guard = PublicConfigNetworkGuard(
            canonical_domain=canonical_domain,
            dns_timeout_seconds=self._dns_timeout_seconds,
            resolver=self._resolver,
        )
        byte_limit = ROBOTS_TXT_MAX_BYTES if config_type == "ROBOTS_TXT" else ADS_TXT_MAX_BYTES
        try:
            async with asyncio.timeout(self._total_timeout_seconds):
                if self._client is not None:
                    return await self._fetch_with_client(
                        self._client, guard, initial_url, byte_limit
                    )
                async with httpx.AsyncClient(
                    timeout=self._timeout,
                    follow_redirects=False,
                    trust_env=False,
                    headers={
                        "Accept": "text/plain,*/*;q=0.1",
                        "Cache-Control": "no-cache",
                        "User-Agent": USER_AGENT,
                    },
                ) as client:
                    return await self._fetch_with_client(client, guard, initial_url, byte_limit)
        except PublicConfigFetchError:
            raise
        except PublicConfigSecurityError as error:
            code = (
                "PUBLIC_CONFIG_DNS_ERROR"
                if error.code in {"DNS_ERROR", "DNS_TIMEOUT"}
                else "PUBLIC_CONFIG_SECURITY_ERROR"
            )
            raise PublicConfigFetchError(
                code, str(error), retryable=code.endswith("DNS_ERROR")
            ) from error
        except (TimeoutError, httpx.TimeoutException) as error:
            raise PublicConfigFetchError(
                "PUBLIC_CONFIG_TIMEOUT", "Public configuration fetch timed out", retryable=True
            ) from error
        except httpx.RequestError as error:
            raise PublicConfigFetchError(
                "PUBLIC_CONFIG_HTTP_ERROR", "Public configuration request failed", retryable=True
            ) from error

    async def _fetch_with_client(
        self,
        client: httpx.AsyncClient,
        guard: PublicConfigNetworkGuard,
        initial_url: str,
        byte_limit: int,
    ) -> PublicConfigFetchResult:
        current_url = initial_url
        visited: set[str] = set()
        redirect_count = 0
        while True:
            validated = await guard.validate(current_url)
            if validated.request_url in visited:
                raise PublicConfigFetchError(
                    "PUBLIC_CONFIG_SECURITY_ERROR", "Redirect loop blocked", retryable=False
                )
            visited.add(validated.request_url)
            client.cookies.clear()
            async with client.stream(
                "GET",
                validated.request_url,
                auth=None,
                follow_redirects=False,
                timeout=self._timeout,
                headers={
                    "Accept": "text/plain,*/*;q=0.1",
                    "Cache-Control": "no-cache",
                    "User-Agent": USER_AGENT,
                },
            ) as response:
                client.cookies.clear()
                if response.status_code in REDIRECT_STATUSES:
                    location = response.headers.get("location")
                    if not location:
                        raise PublicConfigFetchError(
                            "PUBLIC_CONFIG_HTTP_ERROR",
                            "Redirect response omitted Location",
                            retryable=False,
                        )
                    if redirect_count >= self._max_redirects:
                        raise PublicConfigFetchError(
                            "PUBLIC_CONFIG_SECURITY_ERROR",
                            "Redirect limit exceeded",
                            retryable=False,
                        )
                    current_url = urljoin(validated.request_url, location)
                    redirect_count += 1
                    continue
                chunks: list[bytes] = []
                byte_count = 0
                async for chunk in response.aiter_bytes():
                    byte_count += len(chunk)
                    if byte_count > byte_limit:
                        raise PublicConfigFetchError(
                            "PUBLIC_CONFIG_TOO_LARGE",
                            "Public configuration response exceeded its byte limit",
                            retryable=False,
                        )
                    chunks.append(chunk)
                content = b"".join(chunks)
                content_type = response.headers.get("content-type")
                if content_type is not None:
                    content_type = content_type.split(";", 1)[0].strip().lower()[:200] or None
                return PublicConfigFetchResult(
                    url=sanitize_url(validated.request_url),
                    http_status=response.status_code,
                    content=content,
                    content_hash=hashlib.sha256(content).hexdigest(),
                    content_type=content_type,
                    redirect_count=redirect_count,
                )
