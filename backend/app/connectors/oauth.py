"""First-party Google OAuth orchestration boundary (EP-024).

Least-privilege read-only scope declarations per connector, authorization-URL
construction, and token-refresh semantics behind this boundary. No provider
behavior may leak into domain logic; concrete token exchange uses an injected
HTTP client so tests never touch the network.
"""

import urllib.parse
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

CONNECTOR_SCOPES: dict[str, tuple[str, ...]] = {
    "GA4": ("https://www.googleapis.com/auth/analytics.readonly",),
    "GSC": ("https://www.googleapis.com/auth/webmasters.readonly",),
    "GAM": ("https://www.googleapis.com/auth/admanager.readonly",),
}
AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"


@dataclass(frozen=True, slots=True)
class AuthorizationRequest:
    connector: str
    url: str
    state: str
    scopes: tuple[str, ...]


class TokenExchangeClient(Protocol):
    def exchange(self, *, code: str, redirect_uri: str) -> dict[str, Any]: ...

    def refresh(self, *, refresh_token_reference_secret: str) -> dict[str, Any]: ...


def least_privilege_scopes(connector: str) -> tuple[str, ...]:
    if connector not in CONNECTOR_SCOPES:
        raise ValueError(f"unknown connector {connector!r}")
    return CONNECTOR_SCOPES[connector]


def build_authorization_request(
    *,
    client_id: str,
    redirect_uri: str,
    connector: str,
) -> AuthorizationRequest:
    scopes = least_privilege_scopes(connector)
    state = uuid.uuid4().hex
    query = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes),
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
    )
    return AuthorizationRequest(
        connector=connector, url=f"{AUTH_ENDPOINT}?{query}", state=state, scopes=scopes
    )


def map_refresh_failure(error_code: str) -> str:
    """Map provider refresh failures onto existing connection states."""
    mapping = {"invalid_grant": "AUTH_EXPIRED", "unauthorized_client": "PERMISSION_ERROR"}
    return mapping.get(error_code, "DEGRADED")
