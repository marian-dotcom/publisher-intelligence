import pytest
from pydantic import ValidationError

from app.config.settings import Settings


def test_settings_summary_redacts_secrets() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://user:password@example.invalid/db",
        s3_access_key_id="visible-id-is-still-secret",
        s3_secret_access_key="very-secret",
    )

    summary = settings.safe_summary()

    assert summary["database_url"] == "[REDACTED]"
    assert summary["s3_access_key_id"] == "[REDACTED]"
    assert summary["s3_secret_access_key"] == "[REDACTED]"
    assert "very-secret" not in str(summary)
    assert "very-secret" not in repr(settings)


def test_production_rejects_local_defaults_without_exposing_them() -> None:
    with pytest.raises(ValidationError) as caught:
        Settings(
            environment="production",
            cookie_secure=True,
            secret_backend="oci",
        )

    message = str(caught.value)
    assert "production configuration requires explicit values" in message
    assert "database_url" in message
    assert "s3_secret_access_key" in message
    assert "publisher-local" not in message
    assert "replace-with-local-only-secret" not in message


def test_production_rejects_private_network_browser_opt_in() -> None:
    with pytest.raises(ValidationError) as caught:
        Settings(
            environment="production",
            cookie_secure=True,
            secret_backend="oci",
            database_url="postgresql+psycopg://service:secret@database.internal/app",
            s3_endpoint_url="https://objects.example.com",
            s3_access_key_id="explicit-key",
            s3_secret_access_key="explicit-secret",
            s3_use_ssl=True,
            browser_allow_private_networks=True,
        )

    assert "browser_allow_private_networks" in str(caught.value)
