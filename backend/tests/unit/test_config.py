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
        Settings(environment="production")

    message = str(caught.value)
    assert "production configuration requires explicit values" in message
    assert "database_url" in message
    assert "s3_secret_access_key" in message
    assert "publisher-local" not in message
    assert "replace-with-local-only-secret" not in message
