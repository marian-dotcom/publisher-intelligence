import json
import re
import uuid
from collections.abc import AsyncIterator, Mapping
from datetime import date
from typing import Any, cast

import pytest
from sqlalchemy import delete, func, select

from app.browser.models import Publisher, Site
from app.connectors.core.contracts import AccessCredential
from app.connectors.core.persistence import ConnectorRepository
from app.connectors.gam.client import GAMClient
from app.connectors.gam.definitions import GAM_DEFINITIONS, GAM_PROFILES, binding_key
from app.connectors.gam.service import GAMConnectorService
from app.connectors.models import DataConnection, MetricPoint, MetricSeries, SourceExtract
from app.db.models import Job, Tenant
from app.db.session import get_session_factory
from app.jobs.queue import JobQueue
from app.worker import handle_job

pytestmark = pytest.mark.integration


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


class FixtureResolver:
    async def resolve(self, secret_reference: str) -> AccessCredential:
        assert secret_reference == "env:GAM_INTEGRATION_ACCESS_TOKEN"
        return AccessCredential("sanitized-fixture-token")


class FixtureTransport:
    def __init__(self, configured: dict[str, str]) -> None:
        self.configured = configured

    def _definition_profile(self, report_id: str) -> tuple[Any, str]:
        resource = f"networks/1234567/reports/{report_id}"
        key = next(key for key, value in self.configured.items() if value == resource)
        definition_code, profile = key.rsplit(":", 1)
        return GAM_DEFINITIONS[definition_code], profile

    async def request(self, **kwargs: Any) -> Mapping[str, Any]:
        url = kwargs["url"]
        method = kwargs["method"]
        if url.endswith("/networks"):
            return {
                "networks": [
                    {
                        "name": "networks/1234567",
                        "networkCode": "1234567",
                        "displayName": "Sanitized Publisher Network",
                        "timeZone": "Europe/Bucharest",
                        "currencyCode": "EUR",
                    }
                ]
            }
        if url.endswith("/networks/1234567"):
            return {
                "name": "networks/1234567",
                "networkCode": "1234567",
                "displayName": "Sanitized Publisher Network",
                "timeZone": "Europe/Bucharest",
                "currencyCode": "EUR",
            }
        report_match = re.search(r"/reports/(\d+)$", url)
        if method == "GET" and report_match:
            report_id = report_match.group(1)
            definition, profile = self._definition_profile(report_id)
            return {
                "name": f"networks/1234567/reports/{report_id}",
                "displayName": f"Sanitized {definition.code} {profile}",
                "reportDefinition": {
                    "dimensions": list(definition.dimensions),
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
            definition, profile = self._definition_profile(report_id)
            report_date = date(2026, 8, 20) if profile == "TODAY" else date(2026, 8, 19)
            start_date = report_date if profile == "TODAY" else date(2026, 8, 13)
            dimension_values: list[dict[str, Any]] = []
            for dimension in definition.dimensions:
                if dimension == "DATE":
                    dimension_values.append({"stringValue": report_date.isoformat()})
                elif dimension == "HOUR":
                    dimension_values.append({"intValue": "10"})
                elif dimension.endswith("_ID"):
                    dimension_values.append({"intValue": "2001"})
                else:
                    dimension_values.append({"stringValue": "Sanitized"})
            metrics = [
                ({"doubleValue": 1.25} if metric.unit == "CURRENCY" else {"intValue": "10"})
                for metric in definition.metrics
            ]
            return {
                "rows": [
                    {
                        "dimensionValues": dimension_values,
                        "metricValueGroups": [{"primaryValues": metrics}],
                    }
                ],
                "runTime": "2026-08-20T10:15:00Z",
                "dateRanges": [
                    {
                        "startDate": {
                            "year": start_date.year,
                            "month": start_date.month,
                            "day": start_date.day,
                        },
                        "endDate": {
                            "year": report_date.year,
                            "month": report_date.month,
                            "day": report_date.day,
                        },
                    }
                ],
                "comparisonDateRanges": [],
                "totalRowCount": 1,
            }
        raise AssertionError(f"unexpected GAM request: {method} {url}")


@pytest.fixture
async def connector_site() -> AsyncIterator[tuple[uuid.UUID, uuid.UUID, uuid.UUID]]:
    tenant_id = uuid.uuid4()
    other_tenant_id = uuid.uuid4()
    publisher_id = uuid.uuid4()
    site_id = uuid.uuid4()
    factory = get_session_factory()
    async with factory() as session, session.begin():
        session.add_all(
            [
                Tenant(id=tenant_id, slug=f"gam-{tenant_id.hex[:10]}", name="GAM Tenant"),
                Tenant(
                    id=other_tenant_id,
                    slug=f"gam-other-{other_tenant_id.hex[:10]}",
                    name="Other Tenant",
                ),
            ]
        )
        await session.flush()
        session.add(
            Publisher(
                id=publisher_id,
                tenant_id=tenant_id,
                name="GAM Publisher",
                slug=f"publisher-{publisher_id.hex[:10]}",
                default_timezone="Europe/Bucharest",
                status="ACTIVE",
            )
        )
        await session.flush()
        session.add(
            Site(
                id=site_id,
                tenant_id=tenant_id,
                publisher_id=publisher_id,
                name="GAM Site",
                canonical_domain="example.com",
                canonical_scheme="https",
                timezone="Europe/Bucharest",
                status="ACTIVE",
            )
        )
    yield tenant_id, other_tenant_id, site_id
    async with factory() as session, session.begin():
        await session.execute(delete(Job).where(Job.tenant_id == tenant_id))
        await session.execute(delete(MetricPoint).where(MetricPoint.tenant_id == tenant_id))
        await session.execute(delete(MetricSeries).where(MetricSeries.tenant_id == tenant_id))
        await session.execute(delete(SourceExtract).where(SourceExtract.tenant_id == tenant_id))
        await session.execute(delete(DataConnection).where(DataConnection.tenant_id == tenant_id))
        await session.execute(delete(Site).where(Site.id == site_id))
        await session.execute(delete(Publisher).where(Publisher.id == publisher_id))
        await session.execute(delete(Tenant).where(Tenant.id.in_([tenant_id, other_tenant_id])))


async def test_gam_queue_ingestion_reconciliation_and_tenancy(
    connector_site: tuple[uuid.UUID, uuid.UUID, uuid.UUID],
) -> None:
    tenant_id, other_tenant_id, site_id = connector_site
    configured = bindings()
    factory = get_session_factory()
    repository = ConnectorRepository(factory)
    service = GAMConnectorService(
        repository,
        GAMClient(FixtureTransport(configured), sleep=no_sleep, initial_poll_seconds=0),
        cast(Any, FixtureResolver()),
    )
    connection_id = await service.register_connection(
        tenant_id=tenant_id,
        site_id=site_id,
        network_code="1234567",
        report_bindings=configured,
        secret_reference="env:GAM_INTEGRATION_ACCESS_TOKEN",
    )
    snapshot = await service.validate_connection(tenant_id=tenant_id, connection_id=connection_id)
    assert snapshot["sourceTimezone"] == "Europe/Bucharest"
    assert snapshot["currencyCode"] == "EUR"

    queue = JobQueue(factory)
    job_id = await queue.enqueue(
        tenant_id=tenant_id,
        job_type="GAM_EXTRACT",
        payload={
            "connection_id": str(connection_id),
            "definition_code": "GAM_INVENTORY_HEALTH_V1",
            "profile": "TODAY",
            "freshness_status": "PRELIMINARY",
            "scheduled_run_key": "gam-integration-today",
        },
        idempotency_key="gam-integration-today",
        max_attempts=4,
    )
    lease = await queue.claim(worker_id="gam-integration", lease_seconds=30)
    assert lease is not None and lease.id == job_id
    await handle_job(queue, lease, 1, None, None, service)

    repeated = await service.run_extract(
        tenant_id=tenant_id,
        connection_id=connection_id,
        definition_code="GAM_INVENTORY_HEALTH_V1",
        profile="TODAY",
        freshness_status="PRELIMINARY",
        scheduled_run_key="gam-integration-today",
    )
    reconciled = await service.run_extract(
        tenant_id=tenant_id,
        connection_id=connection_id,
        definition_code="GAM_DEMAND_HEALTH_V1",
        profile="LAST_7_DAYS",
        freshness_status="PRELIMINARY",
        scheduled_run_key="gam-integration-last7",
    )
    assert repeated is None
    assert reconciled is not None and len(reconciled.points) == 3
    assert (
        await repository.load_connection(tenant_id=other_tenant_id, connection_id=connection_id)
        is None
    )

    async with factory() as session:
        connection = await session.get(DataConnection, connection_id)
        assert connection is not None and connection.status == "CONNECTED"
        assert connection.secret_reference == "env:GAM_INTEGRATION_ACCESS_TOKEN"
        assert "token" not in json.dumps(connection.connection_metadata).lower()
        job = await session.get(Job, job_id)
        assert job is not None and job.status == "COMPLETE"
        extracts = (
            await session.scalars(
                select(SourceExtract).where(SourceExtract.connection_id == connection_id)
            )
        ).all()
        assert len(extracts) == 2
        assert all(extract.source == "GAM" and extract.status == "COMPLETE" for extract in extracts)
        assert all(extract.source_timezone == "Europe/Bucharest" for extract in extracts)
        assert all("reportResource" in extract.query_definition for extract in extracts)
        assert all(
            "access" not in json.dumps(extract.query_definition).lower() for extract in extracts
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(MetricPoint)
                .where(MetricPoint.tenant_id == tenant_id)
            )
            == 6
        )
        series = (
            await session.scalars(select(MetricSeries).where(MetricSeries.tenant_id == tenant_id))
        ).all()
        assert all(item.source == "GAM" for item in series)
        assert all(item.dimensions["currency_code"] == "EUR" for item in series)
