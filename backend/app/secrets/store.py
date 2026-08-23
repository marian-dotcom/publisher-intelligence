"""Cloud-agnostic SecretStore abstraction (EP-024, human-approved architecture).

PostgreSQL stores only opaque references; token material lives behind this
contract. Concrete managed providers are a deployment-time human gate
(OPEN-005). Implementations here: in-memory (tests), environment-backed
(local/dev), and a reference resolver suitable for integration stubs.
"""

from typing import Any, Protocol

from app.incidents.contracts import InvestigationStateError


class SecretStore(Protocol):
    def store(self, reference: str, secret: str) -> None: ...
    def resolve(self, reference: str) -> str | None: ...
    def replace(self, reference: str, secret: str) -> None: ...
    def delete(self, reference: str) -> None: ...
    def exists(self, reference: str) -> bool: ...


class InMemorySecretStore:
    """Test/dev implementation. NOT for production."""

    def __init__(self) -> None:
        self._secrets: dict[str, str] = {}

    def store(self, reference: str, secret: str) -> None:
        self._guard(reference, secret)
        if reference in self._secrets:
            raise InvestigationStateError("secret reference already exists")
        self._secrets[reference] = secret

    def resolve(self, reference: str) -> str | None:
        return self._secrets.get(reference)

    def replace(self, reference: str, secret: str) -> None:
        self._guard(reference, secret)
        if reference not in self._secrets:
            raise InvestigationStateError("cannot rotate a secret that does not exist")
        self._secrets[reference] = secret

    def delete(self, reference: str) -> None:
        self._secrets.pop(reference, None)

    def exists(self, reference: str) -> bool:
        return reference in self._secrets

    @staticmethod
    def _guard(reference: str, secret: str) -> None:
        del reference
        if not secret.strip():
            raise InvestigationStateError("secret material must be non-empty")


class EnvironmentSecretStore:
    """Local/dev resolver backed by process environment variables."""

    def __init__(self, environ: Any = None) -> None:
        import os

        self._environ = os.environ if environ is None else environ

    def store(self, reference: str, secret: str) -> None:
        raise InvestigationStateError(
            "environment secret store is read-only; inject values out of band"
        )

    def resolve(self, reference: str) -> str | None:
        return self._environ.get(reference)

    def replace(self, reference: str, secret: str) -> None:
        raise InvestigationStateError("environment secret store is read-only")

    def delete(self, reference: str) -> None:
        raise InvestigationStateError("environment secret store is read-only")

    def exists(self, reference: str) -> bool:
        return reference in self._environ
