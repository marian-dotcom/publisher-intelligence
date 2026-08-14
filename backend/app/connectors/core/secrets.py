import os
import re

from app.connectors.core.contracts import (
    AccessCredential,
    AccessTokenResolver,
    SecretResolutionError,
)

_ENV_REFERENCE = re.compile(r"^env:([A-Z][A-Z0-9_]{0,127})$")


class EnvironmentAccessTokenResolver(AccessTokenResolver):
    """Local/test resolver; production must replace it with a managed secret provider."""

    def __init__(self, *, environment: str) -> None:
        self._environment = environment

    async def resolve(self, secret_reference: str) -> AccessCredential:
        match = _ENV_REFERENCE.fullmatch(secret_reference)
        if match is None:
            raise SecretResolutionError(
                "SECRET_REFERENCE_INVALID",
                retryable=False,
                message="Unsupported connector secret reference",
            )
        if self._environment == "production":
            raise SecretResolutionError(
                "SECRET_PROVIDER_UNAVAILABLE",
                retryable=False,
                message="Managed connector secret provider is not configured",
            )
        token = os.getenv(match.group(1))
        if token is None or not token.strip():
            raise SecretResolutionError(
                "SECRET_NOT_FOUND",
                retryable=False,
                message="Connector credential is unavailable",
            )
        return AccessCredential(access_token=token.strip())
