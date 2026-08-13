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
