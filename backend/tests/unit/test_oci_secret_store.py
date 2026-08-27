"""OCI SecretStore unit tests (EP-024 M2).

All OCI HTTP calls are mocked — no live OCI API access.
Google token refresh calls are mocked — no real OAuth.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import httpx
import oci.exceptions
import pytest

from app.connectors.core.contracts import AccessCredential, SecretResolutionError
from app.incidents.contracts import InvestigationStateError
from app.secrets.oci import (
    GoogleCredentialBundle,
    OciAccessTokenResolver,
    OciSecretStore,
    _refresh_access_token,
    parse_credential_bundle,
    parse_secret_ocid,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_VALID_SECRET_OCID = "ocid1.secret.oc1.eu-frankfurt-1.exampleuniqueid"
_VALID_REFERENCE = f"oci:{_VALID_SECRET_OCID}"

_VALID_BUNDLE_JSON = json.dumps(
    {
        "client_id": "test-client-id.apps.googleusercontent.com",
        "client_secret": "test-client-secret",
        "refresh_token": "test-refresh-token",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
)

_GOOGLE_TOKEN_RESPONSE_200 = {
    "access_token": "ya29.test-access-token",
    "token_type": "Bearer",
    "expires_in": 3600,
}


def _make_oci_service_error(status: int, code: str, message: str) -> oci.exceptions.ServiceError:
    """Create a real OCI ServiceError for testing."""
    return oci.exceptions.ServiceError(status, code, {}, message)


# ---------------------------------------------------------------------------
# Reference format tests
# ---------------------------------------------------------------------------


class TestParseSecretOcid:
    def test_valid_ocid(self) -> None:
        result = parse_secret_ocid(_VALID_REFERENCE)
        assert result == _VALID_SECRET_OCID

    def test_rejects_missing_prefix(self) -> None:
        with pytest.raises(SecretResolutionError) as exc_info:
            parse_secret_ocid(_VALID_SECRET_OCID)
        assert exc_info.value.code == "SECRET_REFERENCE_INVALID"

    def test_rejects_wrong_prefix(self) -> None:
        with pytest.raises(SecretResolutionError) as exc_info:
            parse_secret_ocid("aws:some-secret")
        assert exc_info.value.code == "SECRET_REFERENCE_INVALID"

    def test_rejects_env_prefix(self) -> None:
        with pytest.raises(SecretResolutionError) as exc_info:
            parse_secret_ocid("env:SOME_VAR")
        assert exc_info.value.code == "SECRET_REFERENCE_INVALID"

    def test_rejects_empty_string(self) -> None:
        with pytest.raises(SecretResolutionError) as exc_info:
            parse_secret_ocid("")
        assert exc_info.value.code == "SECRET_REFERENCE_INVALID"

    def test_rejects_non_ocid_shape(self) -> None:
        with pytest.raises(SecretResolutionError) as exc_info:
            parse_secret_ocid("oci:not-an-ocid")
        assert exc_info.value.code == "SECRET_REFERENCE_INVALID"

    def test_rejects_ocid_with_semicolon(self) -> None:
        with pytest.raises(SecretResolutionError) as exc_info:
            parse_secret_ocid(f"oci:{_VALID_SECRET_OCID};rm -rf /")
        assert exc_info.value.code == "SECRET_REFERENCE_INVALID"

    def test_rejects_trailing_content(self) -> None:
        with pytest.raises(SecretResolutionError) as exc_info:
            parse_secret_ocid(f"oci:{_VALID_SECRET_OCID}/extra")
        assert exc_info.value.code == "SECRET_REFERENCE_INVALID"

    def test_accepts_various_ocid_shapes(self) -> None:
        shapes = [
            "ocid1.secret.oc1.iad.aaaaaaaa",
            "ocid1.secret.oc2.us-ashburn-1.abc123",
            "ocid1.secret.oc1.eu-frankfurt-1.x",
        ]
        for shape in shapes:
            result = parse_secret_ocid(f"oci:{shape}")
            assert result == shape


# ---------------------------------------------------------------------------
# OciSecretStore read-only behavior
# ---------------------------------------------------------------------------


class TestOciSecretStoreReadOnly:
    def test_store_raises(self) -> None:
        store = OciSecretStore.__new__(OciSecretStore)
        with pytest.raises(InvestigationStateError, match="read-only"):
            store.store("oci:some-ref", "value")

    def test_replace_raises(self) -> None:
        store = OciSecretStore.__new__(OciSecretStore)
        with pytest.raises(InvestigationStateError, match="read-only"):
            store.replace("oci:some-ref", "value")

    def test_delete_raises(self) -> None:
        store = OciSecretStore.__new__(OciSecretStore)
        with pytest.raises(InvestigationStateError, match="read-only"):
            store.delete("oci:some-ref")


# ---------------------------------------------------------------------------
# OciSecretStore.resolve — success and OCI service errors
# ---------------------------------------------------------------------------


def _make_mock_client(response_content: str = "secret-value") -> MagicMock:
    """Create a mock OCI SecretsClient with a successful response."""
    mock_response = MagicMock()
    mock_response.data.secret_bundle_content.content = response_content
    mock_client = MagicMock()
    mock_client.get_secret_bundle.return_value = mock_response
    return mock_client


def test_resolve_success() -> None:
    store = OciSecretStore.__new__(OciSecretStore)
    store._client = _make_mock_client("resolved-secret")
    result = store.resolve(_VALID_REFERENCE)
    assert result == "resolved-secret"


def test_resolve_invalid_reference() -> None:
    store = OciSecretStore.__new__(OciSecretStore)
    store._client = _make_mock_client()
    with pytest.raises(SecretResolutionError) as exc_info:
        store.resolve("env:SOME_VAR")
    assert exc_info.value.code == "SECRET_REFERENCE_INVALID"


def test_resolve_unauthorized() -> None:
    store = OciSecretStore.__new__(OciSecretStore)
    store._client = MagicMock(
        get_secret_bundle=MagicMock(
            side_effect=_make_oci_service_error(401, "NotAuthenticatedOrAuthorized", "auth failed")
        )
    )
    with pytest.raises(SecretResolutionError) as exc_info:
        store.resolve(_VALID_REFERENCE)
    assert exc_info.value.code == "SECRET_PROVIDER_UNAUTHORIZED"
    assert not exc_info.value.retryable


def test_resolve_forbidden() -> None:
    store = OciSecretStore.__new__(OciSecretStore)
    store._client = MagicMock(
        get_secret_bundle=MagicMock(
            side_effect=_make_oci_service_error(403, "NotAuthorizedOrResourceNotFound", "forbidden")
        )
    )
    with pytest.raises(SecretResolutionError) as exc_info:
        store.resolve(_VALID_REFERENCE)
    assert exc_info.value.code == "SECRET_PROVIDER_UNAUTHORIZED"


def test_resolve_not_found() -> None:
    store = OciSecretStore.__new__(OciSecretStore)
    store._client = MagicMock(
        get_secret_bundle=MagicMock(
            side_effect=_make_oci_service_error(404, "ResourceNotFound", "not found")
        )
    )
    with pytest.raises(SecretResolutionError) as exc_info:
        store.resolve(_VALID_REFERENCE)
    assert exc_info.value.code == "SECRET_NOT_FOUND"
    assert not exc_info.value.retryable


def test_resolve_server_error() -> None:
    store = OciSecretStore.__new__(OciSecretStore)
    store._client = MagicMock(
        get_secret_bundle=MagicMock(
            side_effect=_make_oci_service_error(500, "InternalError", "server error")
        )
    )
    with pytest.raises(SecretResolutionError) as exc_info:
        store.resolve(_VALID_REFERENCE)
    assert exc_info.value.code == "SECRET_PROVIDER_UNAVAILABLE"
    assert exc_info.value.retryable


def test_resolve_secret_disabled() -> None:
    store = OciSecretStore.__new__(OciSecretStore)
    store._client = MagicMock(
        get_secret_bundle=MagicMock(
            side_effect=_make_oci_service_error(404, "SecretDisabled", "disabled")
        )
    )
    with pytest.raises(SecretResolutionError) as exc_info:
        store.resolve(_VALID_REFERENCE)
    assert exc_info.value.code == "SECRET_NOT_FOUND"


# ---------------------------------------------------------------------------
# OciSecretStore.exists
# ---------------------------------------------------------------------------


def test_exists_true() -> None:
    store = OciSecretStore.__new__(OciSecretStore)
    store._client = _make_mock_client("value")
    assert store.exists(_VALID_REFERENCE) is True


def test_exists_false_on_not_found() -> None:
    store = OciSecretStore.__new__(OciSecretStore)
    store._client = MagicMock(
        get_secret_bundle=MagicMock(
            side_effect=_make_oci_service_error(404, "ResourceNotFound", "not found")
        )
    )
    assert store.exists(_VALID_REFERENCE) is False


# ---------------------------------------------------------------------------
# Credential bundle parsing
# ---------------------------------------------------------------------------


class TestParseCredentialBundle:
    def test_valid_bundle(self) -> None:
        bundle = parse_credential_bundle(_VALID_BUNDLE_JSON)
        assert bundle.client_id == "test-client-id.apps.googleusercontent.com"
        assert bundle.client_secret == "test-client-secret"
        assert bundle.refresh_token == "test-refresh-token"
        assert bundle.token_uri == "https://oauth2.googleapis.com/token"

    def test_rejects_invalid_json(self) -> None:
        with pytest.raises(SecretResolutionError) as exc_info:
            parse_credential_bundle("not-json")
        assert exc_info.value.code == "SECRET_BUNDLE_INVALID"

    def test_rejects_non_dict_json(self) -> None:
        with pytest.raises(SecretResolutionError) as exc_info:
            parse_credential_bundle('["a", "b"]')
        assert exc_info.value.code == "SECRET_BUNDLE_INVALID"

    def test_rejects_missing_client_id(self) -> None:
        bundle = json.dumps(
            {
                "client_secret": "s",
                "refresh_token": "r",
                "token_uri": "https://example.com/token",
            }
        )
        with pytest.raises(SecretResolutionError) as exc_info:
            parse_credential_bundle(bundle)
        assert exc_info.value.code == "SECRET_BUNDLE_INVALID"

    def test_rejects_missing_refresh_token(self) -> None:
        bundle = json.dumps(
            {
                "client_id": "id",
                "client_secret": "s",
                "token_uri": "https://example.com/token",
            }
        )
        with pytest.raises(SecretResolutionError) as exc_info:
            parse_credential_bundle(bundle)
        assert exc_info.value.code == "SECRET_BUNDLE_INVALID"

    def test_rejects_empty_client_secret(self) -> None:
        bundle = json.dumps(
            {
                "client_id": "id",
                "client_secret": "",
                "refresh_token": "r",
                "token_uri": "https://example.com/token",
            }
        )
        with pytest.raises(SecretResolutionError) as exc_info:
            parse_credential_bundle(bundle)
        assert exc_info.value.code == "SECRET_BUNDLE_INVALID"

    def test_rejects_whitespace_refresh_token(self) -> None:
        bundle = json.dumps(
            {
                "client_id": "id",
                "client_secret": "s",
                "refresh_token": "  ",
                "token_uri": "https://example.com/token",
            }
        )
        with pytest.raises(SecretResolutionError) as exc_info:
            parse_credential_bundle(bundle)
        assert exc_info.value.code == "SECRET_BUNDLE_INVALID"

    def test_rejects_missing_token_uri(self) -> None:
        bundle = json.dumps(
            {
                "client_id": "id",
                "client_secret": "s",
                "refresh_token": "r",
            }
        )
        with pytest.raises(SecretResolutionError) as exc_info:
            parse_credential_bundle(bundle)
        assert exc_info.value.code == "SECRET_BUNDLE_INVALID"

    def test_no_credential_in_error_message(self) -> None:
        bundle_json = json.dumps({"client_id": "leaked-id"})
        with pytest.raises(SecretResolutionError) as exc_info:
            parse_credential_bundle(bundle_json)
        error_str = str(exc_info.value)
        assert "leaked-id" not in error_str

    def test_extra_fields_ignored(self) -> None:
        bundle_data = json.loads(_VALID_BUNDLE_JSON)
        bundle_data["extra_field"] = "ignored"
        bundle = parse_credential_bundle(json.dumps(bundle_data))
        assert bundle.client_id == "test-client-id.apps.googleusercontent.com"


# ---------------------------------------------------------------------------
# Google token refresh
# ---------------------------------------------------------------------------


class TestRefreshAccessToken:
    def _make_bundle(self, **overrides: str) -> GoogleCredentialBundle:
        defaults = {
            "client_id": "test-client-id",
            "client_secret": "test-client-secret",
            "refresh_token": "test-refresh-token",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
        defaults.update(overrides)
        return GoogleCredentialBundle(**defaults)

    def test_success(self) -> None:
        bundle = self._make_bundle()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = _GOOGLE_TOKEN_RESPONSE_200
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.return_value = mock_response

        token = _refresh_access_token(bundle, client=mock_client)
        assert token == "ya29.test-access-token"

    def test_missing_access_token_in_response(self) -> None:
        bundle = self._make_bundle()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"token_type": "Bearer"}
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.return_value = mock_response

        with pytest.raises(SecretResolutionError) as exc_info:
            _refresh_access_token(bundle, client=mock_client)
        assert exc_info.value.code == "GOOGLE_TOKEN_INVALID"

    def test_invalid_grant(self) -> None:
        bundle = self._make_bundle()
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "error": "invalid_grant",
            "error_description": "Token has been expired or revoked.",
        }
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.return_value = mock_response

        with pytest.raises(SecretResolutionError) as exc_info:
            _refresh_access_token(bundle, client=mock_client)
        assert exc_info.value.code == "GOOGLE_INVALID_GRANT"
        assert not exc_info.value.retryable

    def test_invalid_client(self) -> None:
        bundle = self._make_bundle()
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {
            "error": "invalid_client",
            "error_description": "Unauthorized",
        }
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.return_value = mock_response

        with pytest.raises(SecretResolutionError) as exc_info:
            _refresh_access_token(bundle, client=mock_client)
        assert exc_info.value.code == "GOOGLE_INVALID_CLIENT"

    def test_insufficient_scope(self) -> None:
        bundle = self._make_bundle()
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.json.return_value = {
            "error": "access_denied",
            "error_description": "Insufficient scope",
        }
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.return_value = mock_response

        with pytest.raises(SecretResolutionError) as exc_info:
            _refresh_access_token(bundle, client=mock_client)
        assert exc_info.value.code == "GOOGLE_INSUFFICIENT_SCOPE"

    def test_google_server_error_retryable(self) -> None:
        bundle = self._make_bundle()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.return_value = {
            "error": "server_error",
            "error_description": "Internal error",
        }
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.return_value = mock_response

        with pytest.raises(SecretResolutionError) as exc_info:
            _refresh_access_token(bundle, client=mock_client)
        assert exc_info.value.code == "GOOGLE_TOKEN_UNAVAILABLE"
        assert exc_info.value.retryable

    def test_generic_error(self) -> None:
        bundle = self._make_bundle()
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.json.return_value = {
            "error": "rate_limit_exceeded",
            "error_description": "Too many requests",
        }
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.return_value = mock_response

        with pytest.raises(SecretResolutionError) as exc_info:
            _refresh_access_token(bundle, client=mock_client)
        assert exc_info.value.code == "GOOGLE_TOKEN_ERROR"

    def test_no_credential_in_exception(self) -> None:
        bundle = self._make_bundle()
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "error": "invalid_grant",
            "error_description": "Token revoked",
        }
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.return_value = mock_response

        with pytest.raises(SecretResolutionError) as exc_info:
            _refresh_access_token(bundle, client=mock_client)
        error_str = str(exc_info.value)
        assert "test-client-secret" not in error_str
        assert "test-refresh-token" not in error_str
        assert "test-client-id" not in error_str

    def test_client_not_closed_when_not_owned(self) -> None:
        """When a client is passed in, the caller owns it — we must NOT close it."""
        bundle = self._make_bundle()
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"error": "invalid_grant"}
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.return_value = mock_response

        with pytest.raises(SecretResolutionError):
            _refresh_access_token(bundle, client=mock_client)
        mock_client.close.assert_not_called()

    def test_no_credential_in_request(self) -> None:
        """Verify refresh token is sent in the POST body but not in headers."""
        bundle = self._make_bundle()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = _GOOGLE_TOKEN_RESPONSE_200
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.return_value = mock_response

        _refresh_access_token(bundle, client=mock_client)
        call_kwargs = mock_client.post.call_args
        assert "refresh_token" in call_kwargs.kwargs["data"]


# ---------------------------------------------------------------------------
# OciAccessTokenResolver — end-to-end with mocked OCI + Google
# ---------------------------------------------------------------------------


class TestOciAccessTokenResolver:
    def _make_resolver_with_mock_store(
        self, bundle_json: str | None
    ) -> OciAccessTokenResolver:
        mock_store = MagicMock(spec=OciSecretStore)
        mock_store.resolve.return_value = bundle_json
        resolver = OciAccessTokenResolver.__new__(OciAccessTokenResolver)
        resolver._store = mock_store
        return resolver

    async def test_resolve_success(self) -> None:
        resolver = self._make_resolver_with_mock_store(_VALID_BUNDLE_JSON)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = _GOOGLE_TOKEN_RESPONSE_200
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.return_value = mock_response

        with patch("app.secrets.oci.httpx.Client", return_value=mock_client):
            credential = await resolver.resolve(_VALID_REFERENCE)
        assert isinstance(credential, AccessCredential)
        assert credential.access_token == "ya29.test-access-token"

    async def test_resolve_empty_secret_content(self) -> None:
        resolver = self._make_resolver_with_mock_store(None)

        with pytest.raises(SecretResolutionError) as exc_info:
            await resolver.resolve(_VALID_REFERENCE)
        assert exc_info.value.code == "SECRET_NOT_FOUND"

    async def test_resolve_invalid_reference(self) -> None:
        mock_store = MagicMock(spec=OciSecretStore)
        mock_store.resolve.side_effect = SecretResolutionError(
            "SECRET_REFERENCE_INVALID",
            retryable=False,
            message="Unsupported connector secret reference",
        )
        resolver = OciAccessTokenResolver.__new__(OciAccessTokenResolver)
        resolver._store = mock_store

        with pytest.raises(SecretResolutionError) as exc_info:
            await resolver.resolve("env:SOME_VAR")
        assert exc_info.value.code == "SECRET_REFERENCE_INVALID"

    async def test_resolve_malformed_bundle(self) -> None:
        resolver = self._make_resolver_with_mock_store("not-a-json-bundle")

        with pytest.raises(SecretResolutionError) as exc_info:
            await resolver.resolve(_VALID_REFERENCE)
        assert exc_info.value.code == "SECRET_BUNDLE_INVALID"

    async def test_resolve_missing_refresh_token(self) -> None:
        incomplete = json.dumps({"client_id": "id"})
        resolver = self._make_resolver_with_mock_store(incomplete)

        with pytest.raises(SecretResolutionError) as exc_info:
            await resolver.resolve(_VALID_REFERENCE)
        assert exc_info.value.code == "SECRET_BUNDLE_INVALID"

    async def test_resolve_google_invalid_grant(self) -> None:
        resolver = self._make_resolver_with_mock_store(_VALID_BUNDLE_JSON)

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"error": "invalid_grant"}
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.return_value = mock_response

        with patch("app.secrets.oci.httpx.Client", return_value=mock_client):
            with pytest.raises(SecretResolutionError) as exc_info:
                await resolver.resolve(_VALID_REFERENCE)
        assert exc_info.value.code == "GOOGLE_INVALID_GRANT"

    async def test_no_credential_material_in_errors(self) -> None:
        resolver = self._make_resolver_with_mock_store(_VALID_BUNDLE_JSON)

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"error": "invalid_grant"}
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.return_value = mock_response

        with patch("app.secrets.oci.httpx.Client", return_value=mock_client):
            with pytest.raises(SecretResolutionError) as exc_info:
                await resolver.resolve(_VALID_REFERENCE)
        error_str = str(exc_info.value)
        assert "test-client-secret" not in error_str
        assert "test-refresh-token" not in error_str

    def test_connectors_use_protocol_interface(self) -> None:
        """Verify OciAccessTokenResolver has the resolve method matching the protocol."""
        resolver = OciAccessTokenResolver.__new__(OciAccessTokenResolver)
        assert hasattr(resolver, "resolve")
        assert callable(resolver.resolve)


# ---------------------------------------------------------------------------
# Settings fail-closed
# ---------------------------------------------------------------------------


class TestSecretBackendSettings:
    def test_staging_requires_oci(self) -> None:
        from pydantic import ValidationError

        from app.config.settings import Settings

        with pytest.raises(ValidationError) as exc_info:
            Settings(
                environment="staging",
                secret_backend="environment",
                cookie_secure=True,
            )
        assert "secret_backend=oci" in str(exc_info.value)

    def test_production_requires_oci(self) -> None:
        from pydantic import ValidationError

        from app.config.settings import Settings

        with pytest.raises(ValidationError) as exc_info:
            Settings(
                environment="production",
                secret_backend="memory",
                cookie_secure=True,
                database_url="postgresql+psycopg://user:pass@host:5432/db",
                s3_endpoint_url="https://s3.example.com",
                s3_access_key_id="AKIAIOSFODNN7EXAMPLE",
                s3_secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            )
        assert "secret_backend=oci" in str(exc_info.value)

    def test_staging_allows_oci(self) -> None:
        from app.config.settings import Settings

        settings = Settings(
            environment="staging",
            secret_backend="oci",
            cookie_secure=True,
        )
        assert settings.secret_backend == "oci"

    def test_local_allows_environment(self) -> None:
        from app.config.settings import Settings

        settings = Settings(environment="local", secret_backend="environment")
        assert settings.secret_backend == "environment"

    def test_local_allows_memory(self) -> None:
        from app.config.settings import Settings

        settings = Settings(environment="local", secret_backend="memory")
        assert settings.secret_backend == "memory"

    def test_default_backend_is_environment(self) -> None:
        from app.config.settings import Settings

        settings = Settings(environment="local")
        assert settings.secret_backend == "environment"

    def test_oci_region_in_safe_summary(self) -> None:
        from app.config.settings import Settings

        settings = Settings(
            environment="staging",
            secret_backend="oci",
            cookie_secure=True,
        )
        summary = settings.safe_summary()
        assert summary["secret_backend"] == "oci"
        assert summary["oci_region"] == "eu-frankfurt-1"


# ---------------------------------------------------------------------------
# Worker factory function
# ---------------------------------------------------------------------------


class TestWorkerTokenResolverFactory:
    def test_oci_backend_returns_oci_resolver(self) -> None:
        from app.worker import _build_token_resolver

        mock_settings = MagicMock()
        mock_settings.secret_backend = "oci"
        mock_settings.oci_region = "eu-frankfurt-1"
        mock_settings.environment = "staging"

        resolver = _build_token_resolver(mock_settings)
        assert isinstance(resolver, OciAccessTokenResolver)

    def test_environment_backend_returns_env_resolver(self) -> None:
        from app.connectors.core.secrets import EnvironmentAccessTokenResolver
        from app.worker import _build_token_resolver

        mock_settings = MagicMock()
        mock_settings.secret_backend = "environment"
        mock_settings.environment = "local"

        resolver = _build_token_resolver(mock_settings)
        assert isinstance(resolver, EnvironmentAccessTokenResolver)

    def test_memory_backend_returns_env_resolver(self) -> None:
        from app.connectors.core.secrets import EnvironmentAccessTokenResolver
        from app.worker import _build_token_resolver

        mock_settings = MagicMock()
        mock_settings.secret_backend = "memory"
        mock_settings.environment = "local"

        resolver = _build_token_resolver(mock_settings)
        assert isinstance(resolver, EnvironmentAccessTokenResolver)
