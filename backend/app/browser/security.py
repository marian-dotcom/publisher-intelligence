import asyncio
import ipaddress
import socket
from dataclasses import dataclass, field
from urllib.parse import SplitResult, urlsplit, urlunsplit

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Request, Route

from app.browser.contracts import RequestFailure

SAFE_EMBEDDED_SCHEMES = {"about", "blob", "data"}
WEB_SCHEMES = {"http", "https"}
METADATA_HOSTS = {"metadata.google.internal"}


class BrowserBlockedError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def canonical_hostname(hostname: str) -> str:
    normalized = hostname.rstrip(".").lower()
    if not normalized:
        raise BrowserBlockedError("INVALID_HOST", "URL hostname is required")
    try:
        return normalized.encode("idna").decode("ascii")
    except UnicodeError as error:
        raise BrowserBlockedError("INVALID_HOST", "URL hostname is invalid") from error


def sanitize_url(url: str) -> str:
    parts = urlsplit(url)
    hostname = parts.hostname
    if hostname is None:
        return "[INVALID_URL]"
    try:
        host = canonical_hostname(hostname)
    except BrowserBlockedError:
        return "[INVALID_URL]"
    try:
        parsed_port = parts.port
    except ValueError:
        return "[INVALID_URL]"
    port = f":{parsed_port}" if parsed_port is not None else ""
    return urlunsplit((parts.scheme.lower(), f"{host}{port}", parts.path or "/", "", ""))


def _is_forbidden_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return not address.is_global


def _parse_web_url(url: str) -> tuple[SplitResult, str]:
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in WEB_SCHEMES:
        raise BrowserBlockedError("INVALID_SCHEME", "Only HTTP(S) browser targets are allowed")
    if parts.username is not None or parts.password is not None:
        raise BrowserBlockedError("URL_CREDENTIALS", "URL credentials are not allowed")
    if parts.hostname is None:
        raise BrowserBlockedError("INVALID_HOST", "URL hostname is required")
    try:
        parsed_port = parts.port
    except ValueError as error:
        raise BrowserBlockedError("INVALID_PORT", "URL port is invalid") from error
    del parsed_port
    return parts, canonical_hostname(parts.hostname)


# Playwright caches a wrapper attribute on bound route-handler instances.
@dataclass
class BrowserNetworkGuard:
    canonical_domain: str
    allow_private_networks: bool
    max_requests: int
    dns_timeout_seconds: float = 2.0
    request_count: int = 0
    blocked_requests: list[RequestFailure] = field(default_factory=list)
    blocked_top_level: bool = False

    def __post_init__(self) -> None:
        self.canonical_domain = canonical_hostname(self.canonical_domain)

    def _is_allowed_top_level_host(self, hostname: str) -> bool:
        expected = self.canonical_domain
        if hostname == expected:
            return True
        if expected.startswith("www.") and hostname == expected.removeprefix("www."):
            return True
        return hostname == f"www.{expected}"

    async def _resolve(self, hostname: str, port: int) -> set[str]:
        try:
            literal = ipaddress.ip_address(hostname)
        except ValueError:
            loop = asyncio.get_running_loop()
            try:
                results = await asyncio.wait_for(
                    loop.getaddrinfo(hostname, port, type=socket.SOCK_STREAM),
                    timeout=self.dns_timeout_seconds,
                )
            except TimeoutError as error:
                raise BrowserBlockedError(
                    "DNS_TIMEOUT", "Destination DNS lookup timed out"
                ) from error
            except socket.gaierror as error:
                raise BrowserBlockedError(
                    "DNS_ERROR", "Destination hostname did not resolve"
                ) from error
            return {item[4][0] for item in results}
        return {str(literal)}

    async def validate(self, url: str, *, top_level: bool) -> str:
        parts, hostname = _parse_web_url(url)
        if hostname in METADATA_HOSTS:
            raise BrowserBlockedError("METADATA_DESTINATION", "Metadata destinations are blocked")
        if top_level and not self._is_allowed_top_level_host(hostname):
            raise BrowserBlockedError(
                "CROSS_SITE_REDIRECT", "Unexpected cross-site redirect blocked"
            )
        addresses = await self._resolve(
            hostname, parts.port or (443 if parts.scheme == "https" else 80)
        )
        if not self.allow_private_networks:
            for raw_address in addresses:
                if _is_forbidden_ip(ipaddress.ip_address(raw_address)):
                    raise BrowserBlockedError(
                        "PRIVATE_DESTINATION", "Private or reserved destination blocked"
                    )
        return sanitize_url(url)

    async def validate_initial(self, url: str) -> str:
        return await self.validate(url, top_level=True)

    async def route(self, route: Route, request: Request) -> None:
        self.request_count += 1
        is_top_level = False
        if request.is_navigation_request():
            try:
                is_top_level = request.frame == request.frame.page.main_frame
            except (AttributeError, PlaywrightError):
                is_top_level = True
        if self.request_count > self.max_requests:
            self._record_block(request, "REQUEST_BUDGET", is_top_level)
            await route.abort("blockedbyclient")
            return
        scheme = urlsplit(request.url).scheme.lower()
        if scheme in SAFE_EMBEDDED_SCHEMES:
            await route.continue_()
            return
        try:
            await self.validate(request.url, top_level=is_top_level)
        except BrowserBlockedError as error:
            self._record_block(request, error.code, is_top_level)
            await route.abort("blockedbyclient")
            return
        await route.continue_()

    def _record_block(self, request: Request, code: str, top_level: bool) -> None:
        self.blocked_top_level = self.blocked_top_level or top_level
        self.blocked_requests.append(
            RequestFailure(
                url=sanitize_url(request.url),
                resource_type=request.resource_type,
                error_text=code,
            )
        )
