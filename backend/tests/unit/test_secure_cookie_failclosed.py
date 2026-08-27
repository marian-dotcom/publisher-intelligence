"""EP-026 M1 - fail-closed negative config tests (SECURITY.md 201)."""

import pytest
from pydantic import SecretStr, ValidationError

from app.config.settings import Settings


def _production_kwargs() -> dict[str, object]:
    return dict(
        environment="production",
        cookie_secure=False,
        database_url="postgresql+psycopg://u:p@db:5432/publisher",
        s3_endpoint_url="https://s3.example.com",
        s3_access_key_id=SecretStr("k"),
        s3_secret_access_key=SecretStr("s"),
    )


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_pilot_production_rejects_secure_false(environment: str) -> None:
    kwargs = dict(_production_kwargs())
    kwargs["environment"] = environment
    with pytest.raises(ValidationError, match=r"secure-cookie hard gate"):
        Settings(**kwargs)  # type: ignore[arg-type]


def test_pilot_production_accepts_secure_true() -> None:
    settings = Settings(
        environment="staging",
        cookie_secure=True,
        secret_backend="oci",
        database_url="postgresql+psycopg://u:p@db:5432/publisher",
        s3_endpoint_url="https://s3.example.com",
        s3_access_key_id=SecretStr("k"),
        s3_secret_access_key=SecretStr("s"),
    )
    assert settings.cookie_secure is True


def test_local_remains_configurable_without_secure() -> None:
    assert Settings(environment="local").cookie_secure is False
    assert Settings(environment="test").cookie_secure is False
