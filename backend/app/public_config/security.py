import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit, urlunsplit

from app.public_config.contracts import ConfigType

WEB_SCHEMES = frozenset({"http", "https"})
METADATA_HOSTS = frozenset({"metadata.google.internal"})
CONFIG_PATHS: dict[ConfigType, str] = {
    "ROBOTS_TXT": "/robots.txt",
    "ADS_TXT": "/ads.txt",
}

Resolver = Callable[[str, int], Awaitable[set[str]]]


class PublicConfigSecurityError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ValidatedPublicUrl:
    request_url: str
    safe_url: str


def canonical_hostname(hostname: str) -> str:
    normalized = hostname.rstrip(".").lower()
    if not normalized:
        raise PublicConfigSecurityError("INVALID_HOST", "URL hostname is required")
    try:
        return normalized.encode("idna").decode("ascii")
    except UnicodeError as error:
        raise PublicConfigSecurityError("INVALID_HOST", "URL hostname is invalid") from error


def sanitize_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.hostname is None:
        return "[INVALID_URL]"
    try:
        hostname = canonical_hostname(parts.hostname)
        port_number = parts.port
    except (PublicConfigSecurityError, ValueError):
        return "[INVALID_URL]"
    port = f":{port_number}" if port_number is not None else ""
    return urlunsplit((parts.scheme.lower(), f"{hostname}{port}", parts.path or "/", "", ""))


def derive_public_config_url(
    *, canonical_scheme: str, canonical_domain: str, config_type: ConfigType
) -> str:
    scheme = canonical_scheme.strip().lower()
    if scheme not in WEB_SCHEMES:
        raise PublicConfigSecurityError("INVALID_SCHEME", "Configured scheme must be HTTP(S)")
    hostname = canonical_hostname(canonical_domain)
    if config_type not in CONFIG_PATHS:
        raise PublicConfigSecurityError("INVALID_CONFIG_TYPE", "Unsupported configuration type")
    return urlunsplit((scheme, hostname, CONFIG_PATHS[config_type], "", ""))


async def resolve_public_addresses(hostname: str, port: int) -> set[str]:
    loop = asyncio.get_running_loop()
    try:
        results = await loop.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as error:
        raise PublicConfigSecurityError(
            "DNS_ERROR", "Destination hostname did not resolve"
        ) from error
    return {result[4][0] for result in results}


def _parse_web_url(url: str) -> tuple[SplitResult, str, int]:
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in WEB_SCHEMES:
        raise PublicConfigSecurityError("INVALID_SCHEME", "Only HTTP(S) targets are allowed")
    if parts.username is not None or parts.password is not None:
        raise PublicConfigSecurityError("URL_CREDENTIALS", "URL credentials are not allowed")
    if parts.hostname is None:
        raise PublicConfigSecurityError("INVALID_HOST", "URL hostname is required")
    try:
        port = parts.port
    except ValueError as error:
        raise PublicConfigSecurityError("INVALID_PORT", "URL port is invalid") from error
    expected_port = 443 if scheme == "https" else 80
    if port is not None and port != expected_port:
        raise PublicConfigSecurityError("INVALID_PORT", "Non-default URL ports are not allowed")
    return parts, canonical_hostname(parts.hostname), port or expected_port


@dataclass(slots=True)
class PublicConfigNetworkGuard:
    canonical_domain: str
    dns_timeout_seconds: float = 2.0
    resolver: Resolver = resolve_public_addresses

    def __post_init__(self) -> None:
        self.canonical_domain = canonical_hostname(self.canonical_domain)

    def _host_is_allowed(self, hostname: str) -> bool:
        if hostname == self.canonical_domain:
            return True
        if self.canonical_domain.startswith("www."):
            return hostname == self.canonical_domain.removeprefix("www.")
        return hostname == f"www.{self.canonical_domain}"

    async def validate(self, url: str) -> ValidatedPublicUrl:
        parts, hostname, port = _parse_web_url(url)
        if hostname in METADATA_HOSTS:
            raise PublicConfigSecurityError(
                "METADATA_DESTINATION", "Metadata destinations are blocked"
            )
        try:
            ipaddress.ip_address(hostname)
        except ValueError:
            pass
        else:
            raise PublicConfigSecurityError("IP_LITERAL", "IP-literal targets are not allowed")
        if not self._host_is_allowed(hostname):
            raise PublicConfigSecurityError(
                "CROSS_SITE_REDIRECT", "Unexpected cross-site redirect blocked"
            )
        try:
            addresses = await asyncio.wait_for(
                self.resolver(hostname, port), timeout=self.dns_timeout_seconds
            )
        except TimeoutError as error:
            raise PublicConfigSecurityError(
                "DNS_TIMEOUT", "Destination DNS lookup timed out"
            ) from error
        if not addresses:
            raise PublicConfigSecurityError("DNS_ERROR", "Destination hostname did not resolve")
        for raw_address in addresses:
            try:
                address = ipaddress.ip_address(raw_address)
            except ValueError as error:
                raise PublicConfigSecurityError(
                    "DNS_ERROR", "Destination DNS answer was invalid"
                ) from error
            if not address.is_global:
                raise PublicConfigSecurityError(
                    "PRIVATE_DESTINATION", "Private or reserved destination blocked"
                )
        netloc = hostname
        if parts.port is not None:
            netloc = f"{hostname}:{parts.port}"
        request_url = urlunsplit((parts.scheme.lower(), netloc, parts.path or "/", parts.query, ""))
        return ValidatedPublicUrl(request_url=request_url, safe_url=sanitize_url(request_url))
