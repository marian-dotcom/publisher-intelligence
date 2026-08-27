"""OCI SecretStore provider (EP-024 M2).

Read-only secret retrieval from OCI Vault using Instance Principal
authentication.  Option C: operator-assisted persistent Google credential
bundles stored as OCI secrets; short-lived access tokens produced at
resolve-time via the standard Google token refresh endpoint.

Secret reference format: ``oci:<vaultsecret-ocid>``
where ``<vaultsecret-ocid>`` is a valid OCI Vault secret OCID.

Credential bundle stored in OCI Vault (JSON)::

    {
      "client_id": "...",
      "client_secret": "...",
      "refresh_token": "..."
    }

OCI Vault stores secret content as Base64-encoded; this module decodes
it at retrieval time.  The Google token refresh endpoint is hardcoded
(``_GOOGLE_TOKEN_ENDPOINT``) and cannot be overridden via the bundle.

PostgreSQL stores only the opaque reference.  No credential material
enters the database.  Refreshed access tokens exist only in process
memory and are never persisted.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass
from typing import Any

import httpx

from app.connectors.core.contracts import (
    AccessCredential,
    SecretResolutionError,
)
from app.incidents.contracts import InvestigationStateError

try:
    import oci
    from oci.auth.signers import InstancePrincipalsSecurityTokenSigner
    from oci.secrets import SecretsClient

    _OCI_AVAILABLE = True
except ImportError:  # pragma: no cover — SDK present in production
    _OCI_AVAILABLE = False

_SECRET_REF_RE = re.compile(r"^oci:(ocid1\.vaultsecret\.[a-zA-Z0-9._:-]+)$")

_GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
_GOOGLE_SCOPES = (
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/admanager.readonly",
)


def _require_oci() -> None:
    if not _OCI_AVAILABLE:
        raise ImportError(
            "oci SDK is required for OCI secret backend; "
            "install the oci package: pip install 'oci>=2.150,<3'"
        )


def parse_secret_ocid(reference: str) -> str:
    """Extract the secret OCID from a provider-qualified reference.

    Raises ``SecretResolutionError`` with code ``SECRET_REFERENCE_INVALID``
    if the reference does not match the expected format.
    """
    match = _SECRET_REF_RE.fullmatch(reference)
    if match is None:
        raise SecretResolutionError(
            "SECRET_REFERENCE_INVALID",
            retryable=False,
            message="Unsupported connector secret reference",
        )
    return match.group(1)


# ---------------------------------------------------------------------------
# OciSecretStore — read-only SecretStore implementation
# ---------------------------------------------------------------------------


class OciSecretStore:
    """Read-only OCI Vault secret store.

    Implements the ``SecretStore`` protocol for structural compatibility.
    Write operations (``store``, ``replace``, ``delete``) are explicitly
    unsupported and raise ``InvestigationStateError``.

    Uses Instance Principal authentication — no API key on disk.
    """

    def __init__(self, *, region: str) -> None:
        _require_oci()
        self._region = region
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            signer = InstancePrincipalsSecurityTokenSigner()
            config = {"region": signer.region or self._region}
            self._client = SecretsClient(config, signer=signer)
        return self._client

    # -- read path (allowed) -----------------------------------------------

    def resolve(self, reference: str) -> str | None:
        """Fetch the CURRENT secret bundle from OCI Vault.

        OCI Vault returns Base64-encoded content with content_type="BASE64".
        This method validates the content type, decodes Base64, and decodes
        the result as UTF-8, raising ``SECRET_BUNDLE_INVALID`` on any
        malformation.
        """
        secret_ocid = parse_secret_ocid(reference)
        try:
            client = self._get_client()
            response = client.get_secret_bundle(secret_ocid, stage="CURRENT")
            bundle_content = response.data.secret_bundle_content
            if bundle_content is None:
                raise SecretResolutionError(
                    "SECRET_BUNDLE_INVALID",
                    retryable=False,
                    message="OCI secret has no content",
                )
            content_type = getattr(bundle_content, "content_type", None)
            if content_type != "BASE64":
                raise SecretResolutionError(
                    "SECRET_BUNDLE_INVALID",
                    retryable=False,
                    message="Unsupported OCI secret content type",
                )
            raw_content: str | None = getattr(bundle_content, "content", None)
            if not isinstance(raw_content, str) or not raw_content:
                raise SecretResolutionError(
                    "SECRET_BUNDLE_INVALID",
                    retryable=False,
                    message="OCI secret content is empty",
                )
            try:
                decoded = base64.b64decode(raw_content, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise SecretResolutionError(
                    "SECRET_BUNDLE_INVALID",
                    retryable=False,
                    message="OCI secret content is not valid Base64",
                ) from exc
            try:
                return decoded.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise SecretResolutionError(
                    "SECRET_BUNDLE_INVALID",
                    retryable=False,
                    message="OCI secret content is not valid UTF-8",
                ) from exc
        except SecretResolutionError:
            raise
        except oci.exceptions.ServiceError as exc:
            self._raise_service_error(exc)
        return None  # unreachable but satisfies type checker

    def exists(self, reference: str) -> bool:
        """Check whether the secret exists and is accessible."""
        try:
            self.resolve(reference)
            return True
        except SecretResolutionError:
            return False

    # -- write path (disabled) ---------------------------------------------

    def store(self, reference: str, secret: str) -> None:
        del reference, secret
        raise InvestigationStateError(
            "OCI secret store is read-only; secrets are provisioned out of band"
        )

    def replace(self, reference: str, secret: str) -> None:
        del reference, secret
        raise InvestigationStateError(
            "OCI secret store is read-only; secrets are provisioned out of band"
        )

    def delete(self, reference: str) -> None:
        del reference
        raise InvestigationStateError(
            "OCI secret store is read-only; secrets are provisioned out of band"
        )

    # -- error mapping ------------------------------------------------------

    @staticmethod
    def _raise_service_error(exc: Any) -> None:
        status = getattr(exc, "status", 0)
        if status in (401, 403):
            raise SecretResolutionError(
                "SECRET_PROVIDER_UNAUTHORIZED",
                retryable=False,
                message="OCI Instance Principal is not authorized to access the secret",
            ) from exc
        if status == 404:
            raise SecretResolutionError(
                "SECRET_NOT_FOUND",
                retryable=False,
                message="OCI secret is not found or disabled",
            ) from exc
        raise SecretResolutionError(
            "SECRET_PROVIDER_UNAVAILABLE",
            retryable=500 <= status < 600,
            message="OCI Vault service error",
        ) from exc


# ---------------------------------------------------------------------------
# Google credential bundle
# ---------------------------------------------------------------------------

_REQUIRED_BUNDLE_FIELDS = ("client_id", "client_secret", "refresh_token")


@dataclass(frozen=True, slots=True)
class GoogleCredentialBundle:
    """Parsed Google OAuth credential bundle from an OCI secret."""

    client_id: str
    client_secret: str
    refresh_token: str


def parse_credential_bundle(raw_json: str) -> GoogleCredentialBundle:
    """Parse and validate a Google credential bundle from raw JSON.

    Raises ``SecretResolutionError`` on malformed or incomplete bundles.
    Never includes credential material in error messages.
    """
    try:
        data = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError) as exc:
        raise SecretResolutionError(
            "SECRET_BUNDLE_INVALID",
            retryable=False,
            message="Secret bundle is not valid JSON",
        ) from exc

    if not isinstance(data, dict):
        raise SecretResolutionError(
            "SECRET_BUNDLE_INVALID",
            retryable=False,
            message="Secret bundle structure is invalid",
        )

    missing = [
        f
        for f in _REQUIRED_BUNDLE_FIELDS
        if not isinstance(data.get(f), str) or not data[f].strip()
    ]
    if missing:
        raise SecretResolutionError(
            "SECRET_BUNDLE_INVALID",
            retryable=False,
            message="Secret bundle is missing required credential fields",
        )

    return GoogleCredentialBundle(
        client_id=str(data["client_id"]),
        client_secret=str(data["client_secret"]),
        refresh_token=str(data["refresh_token"]),
    )


# ---------------------------------------------------------------------------
# Google token refresh
# ---------------------------------------------------------------------------


def _refresh_access_token(
    bundle: GoogleCredentialBundle,
    *,
    client: httpx.Client | None = None,
) -> str:
    """Exchange a Google refresh token for a short-lived access token.

    Never logs or returns credential material beyond the access token.
    """
    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=30.0)
    assert client is not None
    try:
        response = client.post(
            _GOOGLE_TOKEN_ENDPOINT,
            data={
                "client_id": bundle.client_id,
                "client_secret": bundle.client_secret,
                "refresh_token": bundle.refresh_token,
                "grant_type": "refresh_token",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        _raise_for_google_response(response)
        payload = response.json()
        access_token = payload.get("access_token")
        if not access_token:
            raise SecretResolutionError(
                "GOOGLE_TOKEN_INVALID",
                retryable=False,
                message="Google token response is missing access_token",
            )
        return str(access_token)
    finally:
        if owns_client:
            client.close()


def _raise_for_google_response(response: httpx.Response) -> None:
    """Map Google token endpoint errors to SecretResolutionError."""
    if response.status_code == 200:
        return
    try:
        error_data = response.json()
        google_error = error_data.get("error", "unknown_error")
        google_desc = error_data.get("error_description", "")
    except Exception:
        google_error = "unknown_error"
        google_desc = ""

    if google_error == "invalid_grant":
        raise SecretResolutionError(
            "GOOGLE_INVALID_GRANT",
            retryable=False,
            message="Google refresh token is invalid or revoked",
        )
    if google_error == "invalid_client":
        raise SecretResolutionError(
            "GOOGLE_INVALID_CLIENT",
            retryable=False,
            message="Google OAuth client credentials are invalid",
        )
    if response.status_code == 403 or "insufficient" in google_desc.lower():
        raise SecretResolutionError(
            "GOOGLE_INSUFFICIENT_SCOPE",
            retryable=False,
            message="Google credentials lack required scopes",
        )
    if response.status_code >= 500:
        raise SecretResolutionError(
            "GOOGLE_TOKEN_UNAVAILABLE",
            retryable=True,
            message="Google token endpoint error",
        )
    raise SecretResolutionError(
        "GOOGLE_TOKEN_ERROR",
        retryable=False,
        message="Google token exchange failed",
    )


# ---------------------------------------------------------------------------
# OciAccessTokenResolver — connector-level resolution
# ---------------------------------------------------------------------------


class OciAccessTokenResolver:
    """Resolve connector secret references via OCI Vault + Google token refresh.

    Reference format: ``oci:<secret-ocid>``

    Flow:
        1. Parse the OCI secret OCID from the reference.
        2. Fetch the credential bundle from OCI Vault (Instance Principal).
        3. Parse and validate the bundle structure.
        4. Exchange the refresh token for a short-lived access token.
        5. Return ``AccessCredential(access_token=...)``.

    No credential material is persisted in PostgreSQL beyond the opaque
    reference.  Refreshed access tokens exist only in process memory.
    """

    def __init__(self, *, region: str) -> None:
        self._store = OciSecretStore(region=region)

    async def resolve(self, secret_reference: str) -> AccessCredential:
        raw = self._store.resolve(secret_reference)
        if raw is None:
            raise SecretResolutionError(
                "SECRET_NOT_FOUND",
                retryable=False,
                message="OCI secret returned empty content",
            )
        bundle = parse_credential_bundle(raw)
        access_token = _refresh_access_token(bundle)
        return AccessCredential(access_token=access_token)
