import json
import uuid
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any, cast

import pytest

from app.connectors.core.contracts import (
    AccessCredential,
    ConnectionSnapshot,
    ConnectorError,
    ExtractPeriod,
    ExtractStart,
)
from app.connectors.ga4.client import GA4Client, GA4ProviderError
from app.connectors.ga4.definitions import GA4_READONLY_SCOPE
from app.connectors.ga4.service import GA4ConnectorService

FIXTURES = Path(__file__).parents[3] / "fixtures" / "connectors" / "ga4"


def load(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((FIXTURES / name).read_text()))


class Resolver:
    def __init__(self) -> None:
        self.calls = 0

    async def resolve(self, secret_reference: str) -> AccessCredential:
        assert secret_reference == "env:GA4_TEST_ACCESS_TOKEN"
        self.calls += 1
        return AccessCredential("fixture-token")


class Transport:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail: GA4ProviderError | None = None

    async def request(self, **kwargs: Any) -> Mapping[str, Any]:
        self.calls.append(kwargs["url"])
        if self.fail is not None:
            raise self.fail
        if kwargs["method"] == "GET":
            return load("metadata_core.json")
        return load("traffic_complete.json")


class Repository:
    def __init__(self, *, scopes: tuple[str, ...] = (GA4_READONLY_SCOPE,)) -> None:
        self.connection = ConnectionSnapshot(
            id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            site_id=uuid.uuid4(),
            provider="GA4",
            external_property_id="123456",
            status="CONNECTED",
            scopes=scopes,
            secret_reference="env:GA4_TEST_ACCESS_TOKEN",
            metadata={},
        )
        self.validated: dict[str, Any] | None = None
        self.completed = 0
        self.failed: tuple[str, str] | None = None
        self.start = ExtractStart(uuid.uuid4(), created=True, already_complete=False)

    async def load_connection(self, **kwargs: Any) -> ConnectionSnapshot | None:
        return self.connection if kwargs["tenant_id"] == self.connection.tenant_id else None

    async def mark_connection_validated(self, **kwargs: Any) -> None:
        self.validated = kwargs["capability_snapshot"]

    async def start_extract(self, **kwargs: Any) -> ExtractStart:
        return self.start

    async def complete_extract(self, **kwargs: Any) -> None:
        self.completed += 1

    async def fail_extract(self, **kwargs: Any) -> None:
        self.failed = (kwargs["error_class"], kwargs["error_code"])


async def test_connection_validation_probes_metadata_schema_and_property_timezone() -> None:
    repository = Repository()
    transport = Transport()
    resolver = Resolver()
    service = GA4ConnectorService(cast(Any, repository), GA4Client(transport), cast(Any, resolver))

    snapshot = await service.validate_connection(
        tenant_id=repository.connection.tenant_id,
        connection_id=repository.connection.id,
        probe_date=date(2026, 8, 13),
    )

    assert snapshot["propertyTimezone"] == "Europe/Bucharest"
    assert snapshot["definitions"] == ["GA4_TRAFFIC_HOURLY_V1", "GA4_BEHAVIOR_DAILY_V1"]
    assert repository.validated == snapshot
    assert resolver.calls == 1
    assert len(transport.calls) == 2


async def test_completed_logical_extract_is_reused_without_resolving_a_token() -> None:
    repository = Repository()
    repository.start = ExtractStart(uuid.uuid4(), created=False, already_complete=True)
    transport = Transport()
    resolver = Resolver()
    service = GA4ConnectorService(cast(Any, repository), GA4Client(transport), cast(Any, resolver))

    result = await service.run_extract(
        tenant_id=repository.connection.tenant_id,
        connection_id=repository.connection.id,
        definition_code="GA4_TRAFFIC_HOURLY_V1",
        period=ExtractPeriod(date(2026, 8, 12), date(2026, 8, 13)),
        freshness_status="PRELIMINARY",
        scheduled_run_key="logical-run",
    )

    assert result is None
    assert resolver.calls == 0
    assert transport.calls == []


async def test_quota_failure_is_recorded_without_metric_completion() -> None:
    repository = Repository()
    transport = Transport()
    transport.fail = GA4ProviderError("QUOTA_LIMIT", retryable=True, message="quota")
    service = GA4ConnectorService(
        cast(Any, repository), GA4Client(transport), cast(Any, Resolver())
    )

    with pytest.raises(ConnectorError) as raised:
        await service.run_extract(
            tenant_id=repository.connection.tenant_id,
            connection_id=repository.connection.id,
            definition_code="GA4_TRAFFIC_HOURLY_V1",
            period=ExtractPeriod(date(2026, 8, 12), date(2026, 8, 13)),
            freshness_status="PRELIMINARY",
            scheduled_run_key="quota-run",
        )

    assert raised.value.retryable is True
    assert repository.failed == ("GA4ProviderError", "QUOTA_LIMIT")
    assert repository.completed == 0


async def test_any_scope_other_than_exact_readonly_fails_before_secret_resolution() -> None:
    repository = Repository(scopes=(GA4_READONLY_SCOPE, "https://example.invalid/write"))
    resolver = Resolver()
    service = GA4ConnectorService(
        cast(Any, repository), GA4Client(Transport()), cast(Any, resolver)
    )

    with pytest.raises(ConnectorError) as raised:
        await service.validate_connection(
            tenant_id=repository.connection.tenant_id,
            connection_id=repository.connection.id,
            probe_date=date(2026, 8, 13),
        )
    assert raised.value.code == "SCOPE_INVALID"
    assert resolver.calls == 0
