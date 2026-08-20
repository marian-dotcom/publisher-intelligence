import json
import re
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import pytest

from app.connectors.core.contracts import (
    AccessCredential,
    ConnectionSnapshot,
    ConnectorError,
    ExtractStart,
)
from app.connectors.gam.client import GAMClient
from app.connectors.gam.definitions import (
    GAM_DEFINITIONS,
    GAM_PROFILES,
    GAM_READONLY_SCOPE,
    binding_key,
)
from app.connectors.gam.service import GAMConnectorService

FIXTURES = Path(__file__).parents[3] / "fixtures" / "connectors" / "gam"


def load(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((FIXTURES / name).read_text()))


def bindings() -> dict[str, str]:
    result: dict[str, str] = {}
    report_id = 100
    for definition in GAM_DEFINITIONS.values():
        for profile in GAM_PROFILES:
            report_id += 1
            result[binding_key(definition.code, profile)] = f"networks/1234567/reports/{report_id}"
    return result


async def no_sleep(_: float) -> None:
    return None


class Resolver:
    def __init__(self) -> None:
        self.calls = 0

    async def resolve(self, secret_reference: str) -> AccessCredential:
        assert secret_reference == "env:GAM_TEST_ACCESS_TOKEN"
        self.calls += 1
        return AccessCredential("fixture-token")


class Transport:
    def __init__(self, configured: dict[str, str]) -> None:
        self.configured = configured
        self.calls: list[dict[str, Any]] = []
        self.changed_report: str | None = None

    async def request(self, **kwargs: Any) -> Mapping[str, Any]:
        self.calls.append(kwargs)
        url = kwargs["url"]
        method = kwargs["method"]
        if url.endswith("/networks"):
            return load("networks.json")
        if url.endswith("/networks/1234567"):
            return load("network.json")
        report_match = re.search(r"/reports/(\d+)$", url)
        if method == "GET" and report_match:
            report_id = report_match.group(1)
            resource = f"networks/1234567/reports/{report_id}"
            key = next(key for key, value in self.configured.items() if value == resource)
            definition_code, profile = key.rsplit(":", 1)
            definition = GAM_DEFINITIONS[definition_code]
            dimensions = list(definition.dimensions)
            if self.changed_report == resource:
                dimensions.append("COUNTRY_NAME")
            return {
                "name": resource,
                "displayName": f"Sanitized {key}",
                "reportDefinition": {
                    "dimensions": dimensions,
                    "metrics": [metric.api_name for metric in definition.metrics],
                    "timeZoneSource": "PUBLISHER",
                    "currencyCode": "EUR",
                    "dateRange": {"relative": profile},
                    "reportType": "HISTORICAL",
                    "expandedCompatibility": False,
                },
            }
        run_match = re.search(r"/reports/(\d+):run$", url)
        if run_match:
            report_id = run_match.group(1)
            return {
                "name": f"networks/1234567/operations/reports/{report_id}/runs/run-1",
                "done": False,
            }
        operation_match = re.search(r"/operations/reports/(\d+)/runs/run-1$", url)
        if operation_match:
            report_id = operation_match.group(1)
            return {
                "name": f"networks/1234567/operations/reports/{report_id}/runs/run-1",
                "done": True,
                "response": {
                    "reportResult": f"networks/1234567/reports/{report_id}/results/result-1"
                },
            }
        result_match = re.search(r"/reports/(\d+)/results/result-1:fetchRows$", url)
        if result_match:
            report_id = result_match.group(1)
            resource = f"networks/1234567/reports/{report_id}"
            key = next(key for key, value in self.configured.items() if value == resource)
            definition_code, profile = key.rsplit(":", 1)
            definition = GAM_DEFINITIONS[definition_code]
            dimension_values = []
            for dimension in definition.dimensions:
                if dimension == "DATE":
                    dimension_values.append({"stringValue": "2026-08-20"})
                elif dimension == "HOUR":
                    dimension_values.append({"intValue": "10"})
                elif dimension.endswith("_ID"):
                    dimension_values.append({"intValue": "2001"})
                else:
                    dimension_values.append({"stringValue": "Sanitized"})
            metric_values = [
                ({"doubleValue": 1.25} if metric.unit == "CURRENCY" else {"intValue": "10"})
                for metric in definition.metrics
            ]
            return {
                "rows": [
                    {
                        "dimensionValues": dimension_values,
                        "metricValueGroups": [{"primaryValues": metric_values}],
                    }
                ],
                "runTime": "2026-08-20T10:15:00Z",
                "dateRanges": [
                    {
                        "startDate": {"year": 2026, "month": 8, "day": 20},
                        "endDate": {"year": 2026, "month": 8, "day": 20},
                    }
                ],
                "comparisonDateRanges": [],
                "totalRowCount": 1,
            }
        raise AssertionError(f"unexpected request: {method} {url}")


class Repository:
    def __init__(
        self,
        configured: dict[str, str],
        *,
        scopes: tuple[str, ...] = (GAM_READONLY_SCOPE,),
    ) -> None:
        self.connection = ConnectionSnapshot(
            id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            site_id=uuid.uuid4(),
            provider="GAM",
            external_property_id="1234567",
            status="CONNECTED",
            scopes=scopes,
            secret_reference="env:GAM_TEST_ACCESS_TOKEN",
            metadata={"reportBindings": configured},
        )
        self.validated: dict[str, Any] | None = None
        self.completed: list[dict[str, Any]] = []
        self.failed: list[dict[str, Any]] = []
        self.start = ExtractStart(uuid.uuid4(), created=True, already_complete=False)

    async def load_connection(self, **kwargs: Any) -> ConnectionSnapshot | None:
        return self.connection if kwargs["tenant_id"] == self.connection.tenant_id else None

    async def mark_connection_validated(self, **kwargs: Any) -> None:
        self.validated = kwargs["capability_snapshot"]
        self.connection = ConnectionSnapshot(
            id=self.connection.id,
            tenant_id=self.connection.tenant_id,
            site_id=self.connection.site_id,
            provider=self.connection.provider,
            external_property_id=self.connection.external_property_id,
            status="CONNECTED",
            scopes=self.connection.scopes,
            secret_reference=self.connection.secret_reference,
            metadata=self.validated,
        )

    async def start_extract(self, **kwargs: Any) -> ExtractStart:
        return self.start

    async def complete_extract(self, **kwargs: Any) -> None:
        self.completed.append(kwargs)

    async def fail_extract(self, **kwargs: Any) -> None:
        self.failed.append(kwargs)


async def test_validation_proves_all_fixed_cubes_with_readonly_scope() -> None:
    configured = bindings()
    repository = Repository(configured)
    resolver = Resolver()
    service = GAMConnectorService(
        cast(Any, repository),
        GAMClient(Transport(configured), sleep=no_sleep, initial_poll_seconds=0),
        cast(Any, resolver),
    )
    snapshot = await service.validate_connection(
        tenant_id=repository.connection.tenant_id,
        connection_id=repository.connection.id,
    )
    assert snapshot["supportedCubes"] == sorted(GAM_DEFINITIONS)
    assert snapshot["sourceTimezone"] == "Europe/Bucharest"
    assert snapshot["currencyCode"] == "EUR"
    assert snapshot["reportCreation"] == "EXTERNAL_PRECONFIGURATION_REQUIRED"
    assert resolver.calls == 1


async def test_report_change_after_validation_fails_before_run() -> None:
    configured = bindings()
    repository = Repository(configured)
    transport = Transport(configured)
    service = GAMConnectorService(
        cast(Any, repository),
        GAMClient(transport, sleep=no_sleep, initial_poll_seconds=0),
        cast(Any, Resolver()),
    )
    await service.validate_connection(
        tenant_id=repository.connection.tenant_id,
        connection_id=repository.connection.id,
    )
    changed = configured[binding_key("GAM_INVENTORY_HEALTH_V1", "TODAY")]
    transport.changed_report = changed
    with pytest.raises(ConnectorError) as raised:
        await service.run_extract(
            tenant_id=repository.connection.tenant_id,
            connection_id=repository.connection.id,
            definition_code="GAM_INVENTORY_HEALTH_V1",
            profile="TODAY",
            freshness_status="PRELIMINARY",
            scheduled_run_key="gam-changed-report",
        )
    assert raised.value.code == "REPORT_INCOMPATIBLE"
    assert repository.completed == []


async def test_scope_must_be_exactly_readonly() -> None:
    configured = bindings()
    repository = Repository(configured, scopes=(GAM_READONLY_SCOPE, "write"))
    resolver = Resolver()
    service = GAMConnectorService(
        cast(Any, repository),
        GAMClient(Transport(configured), sleep=no_sleep, initial_poll_seconds=0),
        cast(Any, resolver),
    )
    with pytest.raises(ConnectorError) as raised:
        await service.validate_connection(
            tenant_id=repository.connection.tenant_id,
            connection_id=repository.connection.id,
        )
    assert raised.value.code == "SCOPE_INVALID"
    assert resolver.calls == 0
