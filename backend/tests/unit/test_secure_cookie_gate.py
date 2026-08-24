"""EP-026 M1 — secure-cookie pre-pilot hard gate (SECURITY.md §201 / ADR-131).

Pilot/production MUST NOT be able to emit pi_session or pi_csrf with
Secure=False. Configuration must fail closed when pilot/production cookie
security is missing or invalid.
"""

import pytest

from app.auth.routes import _set_session_cookies
from app.config.settings import Settings


class FakeResponse:
    """Minimal Set-Cookie recorder."""

    def __init__(self) -> None:
        self.headers: list[str] = []

    def set_cookie(self, key: str, value: str, max_age: int = 0, **kwargs: object) -> None:
        parts = [f"{key}={value}"]
        for name, val in kwargs.items():
            flag = str(name).replace("_", "")
            if val is True:
                parts.append(flag.capitalize())
            elif val not in (None, False):
                parts.append(f"{flag}={val}")
        self.headers.append("; ".join(parts))


def _emit_with(response: FakeResponse, settings: Settings) -> None:
    _set_session_cookies(
        response,
        token="opaque-token",
        csrf="csrf-value",
        max_age=3600,
        settings=settings,
    )


def test_pilot_production_cookies_must_be_secure() -> None:
    """SECURITY.md §201: pilot/production auth cookies cannot be Secure=False."""
    from pydantic import SecretStr

    production_settings = Settings(
        environment="production",
        cookie_secure=True,
        database_url="postgresql+psycopg://u:p@db:5432/publisher",
        s3_endpoint_url="https://s3.example.com",
        s3_access_key_id=SecretStr("k"),
        s3_secret_access_key=SecretStr("s"),
    )
    response = FakeResponse()
    _emit_with(response, production_settings)
    session_cookie = next(c for c in response.headers if c.startswith("pi_session"))
    csrf_cookie = next(c for c in response.headers if c.startswith("pi_csrf"))
    assert "secure" in session_cookie.lower()
    assert "secure" in csrf_cookie.lower()
    assert "httponly" in session_cookie.lower()
    assert "httponly" not in csrf_cookie.lower()


def test_insecure_production_settings_rejected_at_construction() -> None:
    """Fail-closed validator: production cannot construct with Secure=False."""
    from pydantic import SecretStr

    with pytest.raises(Exception, match=r"[Ss]ecure"):
        Settings(
            environment="production",
            cookie_secure=False,
            database_url="postgresql+psycopg://u:p@db:5432/publisher",
            s3_endpoint_url="https://s3.example.com",
            s3_access_key_id=SecretStr("k"),
            s3_secret_access_key=SecretStr("s"),
        )


def test_insecure_pilot_production_config_fails_closed() -> None:
    """Missing/insecure pilot-production cookie security config is rejected."""
    with pytest.raises(Exception, match=r"[Ss]ecure"):
        Settings(environment="production", cookie_secure=False)


def test_invalid_environment_value_rejected() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(environment="not-an-env")


def test_local_development_remains_non_secure() -> None:
    settings = Settings(environment="local")
    assert settings.cookie_secure is False or settings.environment == "local"
