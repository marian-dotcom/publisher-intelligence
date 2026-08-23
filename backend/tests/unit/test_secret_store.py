"""SecretStore abstraction contract tests (EP-024)."""

import pytest

from app.incidents.contracts import InvestigationStateError
from app.secrets.store import EnvironmentSecretStore, InMemorySecretStore


def test_inmemory_store_round_trip_and_rotation() -> None:
    store = InMemorySecretStore()
    store.store("ref-1", "secret-a")
    assert store.resolve("ref-1") == "secret-a"
    assert store.exists("ref-1")
    store.replace("ref-1", "secret-b")
    assert store.resolve("ref-1") == "secret-b"
    store.delete("ref-1")
    assert not store.exists("ref-1")


def test_inmemory_store_rejects_duplicates_and_empty_secrets() -> None:
    store = InMemorySecretStore()
    store.store("ref", "s")
    with pytest.raises(InvestigationStateError, match="already exists"):
        store.store("ref", "other")
    with pytest.raises(InvestigationStateError, match="non-empty"):
        store.store("ref2", "  ")
    with pytest.raises(InvestigationStateError, match="does not exist"):
        store.replace("missing", "x")


def test_environment_store_is_read_only_resolver() -> None:
    store = EnvironmentSecretStore(environ={"PI_TEST_SECRET": "value"})
    assert store.resolve("PI_TEST_SECRET") == "value"
    assert store.resolve("MISSING") is None
    with pytest.raises(InvestigationStateError, match="read-only"):
        store.store("X", "y")
    with pytest.raises(InvestigationStateError, match="read-only"):
        store.replace("PI_TEST_SECRET", "z")
    with pytest.raises(InvestigationStateError, match="read-only"):
        store.delete("PI_TEST_SECRET")
