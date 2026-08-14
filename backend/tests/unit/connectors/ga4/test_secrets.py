import pytest

from app.connectors.core.contracts import SecretResolutionError
from app.connectors.core.secrets import EnvironmentAccessTokenResolver


async def test_local_environment_resolver_reads_only_an_explicit_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GA4_TEST_ACCESS_TOKEN", "fixture-token")
    credential = await EnvironmentAccessTokenResolver(environment="test").resolve(
        "env:GA4_TEST_ACCESS_TOKEN"
    )
    assert credential.access_token == "fixture-token"


async def test_environment_resolver_is_disabled_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GA4_TEST_ACCESS_TOKEN", "must-not-resolve")
    with pytest.raises(SecretResolutionError) as raised:
        await EnvironmentAccessTokenResolver(environment="production").resolve(
            "env:GA4_TEST_ACCESS_TOKEN"
        )
    assert raised.value.code == "SECRET_PROVIDER_UNAVAILABLE"
    assert "must-not-resolve" not in str(raised.value)
