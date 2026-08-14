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
from app.connectors.gsc.client import GSCClient, GSCProviderError
from app.connectors.gsc.definitions import GSC_READONLY_SCOPE
from app.connectors.gsc.service import GSCConnectorService

FIXTURES = Path(__file__).parents[3] / "fixtures" / "connectors" / "gsc"


def load(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((FIXTURES / name).read_text()))


class Resolver:
    def __init__(self) -> None:
        self.calls = 0

    async def resolve(self, secret_reference: str) -> AccessCredential:
        assert secret_reference == "env:GSC_TEST_ACCESS_TOKEN"
        self.calls += 1
        return AccessCredential("fixture-token")


class Transport:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.fail_inspection = False

    async def request(self, **kwargs: Any) -> Mapping[str, Any]:
        self.calls.append(kwargs)
        if kwargs["method"] == "GET":
            return load("sites_accessible.json")
        if kwargs["url"].endswith("/urlInspection/index:inspect"):
            if self.fail_inspection:
                raise GSCProviderError("QUOTA_LIMIT", retryable=True, message="quota")
            return load("url_inspection.json")
        if kwargs["json_body"]["type"] == "discover":
            payload = load("discover_empty.json")
        else:
            payload = load("search_daily.json")
        payload.pop("pagination")
        return payload


class Repository:
    def __init__(self, *, scopes: tuple[str, ...] = (GSC_READONLY_SCOPE,)) -> None:
        self.connection = ConnectionSnapshot(
            id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            site_id=uuid.uuid4(),
            provider="GSC",
            external_property_id="sc-domain:example.com",
            status="CONNECTED",
            scopes=scopes,
            secret_reference="env:GSC_TEST_ACCESS_TOKEN",
            metadata={},
        )
        self.validated: dict[str, Any] | None = None
        self.completed: list[dict[str, Any]] = []
        self.failed: list[dict[str, Any]] = []
        self.start = ExtractStart(uuid.uuid4(), created=True, already_complete=False)

    async def load_connection(self, **kwargs: Any) -> ConnectionSnapshot | None:
        return self.connection if kwargs["tenant_id"] == self.connection.tenant_id else None

    async def mark_connection_validated(self, **kwargs: Any) -> None:
        self.validated = kwargs["capability_snapshot"]

    async def start_extract(self, **kwargs: Any) -> ExtractStart:
        return self.start

    async def complete_extract(self, **kwargs: Any) -> None:
        self.completed.append(kwargs)

    async def fail_extract(self, **kwargs: Any) -> None:
        self.failed.append(kwargs)


async def test_validation_requires_property_permission_and_probes_both_surfaces() -> None:
    repository = Repository()
    transport = Transport()
    resolver = Resolver()
    service = GSCConnectorService(cast(Any, repository), GSCClient(transport), cast(Any, resolver))

    snapshot = await service.validate_connection(
        tenant_id=repository.connection.tenant_id,
        connection_id=repository.connection.id,
        probe_date=date(2026, 8, 12),
    )

    assert snapshot["propertyType"] == "DOMAIN"
    assert snapshot["permissionLevel"] == "siteFullUser"
    assert snapshot["discoverAvailable"] is False
    assert repository.validated == snapshot
    assert resolver.calls == 1
    assert len(transport.calls) == 3


async def test_completed_extract_reuses_history_without_token() -> None:
    repository = Repository()
    repository.start = ExtractStart(uuid.uuid4(), created=False, already_complete=True)
    resolver = Resolver()
    service = GSCConnectorService(
        cast(Any, repository), GSCClient(Transport()), cast(Any, resolver)
    )
    result = await service.run_extract(
        tenant_id=repository.connection.tenant_id,
        connection_id=repository.connection.id,
        definition_code="GSC_SEARCH_DAILY_V1",
        period=ExtractPeriod(date(2026, 8, 12), date(2026, 8, 12)),
        freshness_status="MATURE",
        scheduled_run_key="gsc-logical-run",
    )
    assert result is None
    assert resolver.calls == 0


async def test_fixed_data_state_rejects_wrong_freshness() -> None:
    repository = Repository()
    service = GSCConnectorService(
        cast(Any, repository), GSCClient(Transport()), cast(Any, Resolver())
    )
    with pytest.raises(ConnectorError) as raised:
        await service.run_extract(
            tenant_id=repository.connection.tenant_id,
            connection_id=repository.connection.id,
            definition_code="GSC_SEARCH_HOURLY_V1",
            period=ExtractPeriod(date(2026, 8, 12), date(2026, 8, 12)),
            freshness_status="MATURE",
            scheduled_run_key="wrong-freshness",
        )
    assert raised.value.code == "FRESHNESS_INVALID"


async def test_url_inspection_quota_failure_does_not_degrade_routine_connection() -> None:
    repository = Repository()
    transport = Transport()
    transport.fail_inspection = True
    service = GSCConnectorService(
        cast(Any, repository), GSCClient(transport), cast(Any, Resolver())
    )
    with pytest.raises(ConnectorError) as raised:
        await service.inspect_url(
            tenant_id=repository.connection.tenant_id,
            connection_id=repository.connection.id,
            inspection_url="https://www.example.com/article/",
            inspection_date=date(2026, 8, 14),
            scheduled_run_key="inspection-quota",
        )
    assert raised.value.code == "QUOTA_LIMIT"
    assert repository.failed[-1]["affect_connection"] is False


async def test_scope_must_be_exactly_readonly() -> None:
    repository = Repository(scopes=(GSC_READONLY_SCOPE, "https://example.invalid/write"))
    resolver = Resolver()
    service = GSCConnectorService(
        cast(Any, repository), GSCClient(Transport()), cast(Any, resolver)
    )
    with pytest.raises(ConnectorError) as raised:
        await service.validate_connection(
            tenant_id=repository.connection.tenant_id,
            connection_id=repository.connection.id,
            probe_date=date(2026, 8, 12),
        )
    assert raised.value.code == "SCOPE_INVALID"
    assert resolver.calls == 0
