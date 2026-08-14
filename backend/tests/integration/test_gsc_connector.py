import json
import uuid
from collections.abc import AsyncIterator, Mapping
from datetime import date
from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy import delete, func, select

from app.browser.models import Publisher, Site
from app.connectors.core.contracts import AccessCredential, ExtractPeriod
from app.connectors.core.persistence import ConnectorRepository
from app.connectors.gsc.client import GSCClient
from app.connectors.gsc.service import GSCConnectorService
from app.connectors.models import DataConnection, MetricPoint, MetricSeries, SourceExtract
from app.db.models import Job, Tenant
from app.db.session import get_session_factory
from app.jobs.queue import JobQueue
from app.worker import handle_job

pytestmark = pytest.mark.integration
FIXTURES = Path(__file__).parents[1] / "fixtures" / "connectors" / "gsc"


def load(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((FIXTURES / name).read_text()))


class FixtureResolver:
    async def resolve(self, secret_reference: str) -> AccessCredential:
        assert secret_reference == "env:GSC_INTEGRATION_ACCESS_TOKEN"
        return AccessCredential("sanitized-fixture-token")


class FixtureTransport:
    async def request(self, **kwargs: Any) -> Mapping[str, Any]:
        if kwargs["method"] == "GET":
            return load("sites_accessible.json")
        if kwargs["url"].endswith("/urlInspection/index:inspect"):
            return load("url_inspection.json")
        body = kwargs["json_body"]
        if body["type"] == "discover":
            payload = load("discover_empty.json")
        elif body["dataState"] == "hourly_all":
            payload = load("search_hourly_incomplete.json")
        else:
            payload = load("search_daily.json")
        payload.pop("pagination")
        return payload


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
                Tenant(id=tenant_id, slug=f"gsc-{tenant_id.hex[:10]}", name="GSC Tenant"),
                Tenant(
                    id=other_tenant_id,
                    slug=f"gsc-other-{other_tenant_id.hex[:10]}",
                    name="Other Tenant",
                ),
            ]
        )
        await session.flush()
        session.add(
            Publisher(
                id=publisher_id,
                tenant_id=tenant_id,
                name="GSC Publisher",
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
                name="GSC Site",
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


async def test_gsc_queue_ingestion_reconciliation_inspection_and_tenancy(
    connector_site: tuple[uuid.UUID, uuid.UUID, uuid.UUID],
) -> None:
    tenant_id, other_tenant_id, site_id = connector_site
    factory = get_session_factory()
    repository = ConnectorRepository(factory)
    service = GSCConnectorService(
        repository,
        GSCClient(FixtureTransport()),
        cast(Any, FixtureResolver()),
    )
    connection_id = await service.register_connection(
        tenant_id=tenant_id,
        site_id=site_id,
        property_id="sc-domain:example.com",
        secret_reference="env:GSC_INTEGRATION_ACCESS_TOKEN",
    )
    snapshot = await service.validate_connection(
        tenant_id=tenant_id,
        connection_id=connection_id,
        probe_date=date(2026, 8, 12),
    )
    assert snapshot["sourceTimezone"] == "America/Los_Angeles"
    assert snapshot["discoverAvailable"] is False

    period = ExtractPeriod(date(2026, 8, 12), date(2026, 8, 13))
    queue = JobQueue(factory)
    job_id = await queue.enqueue(
        tenant_id=tenant_id,
        job_type="GSC_EXTRACT",
        payload={
            "connection_id": str(connection_id),
            "definition_code": "GSC_SEARCH_HOURLY_V1",
            "start_date": period.start_date.isoformat(),
            "end_date": period.end_date.isoformat(),
            "freshness_status": "PRELIMINARY",
            "scheduled_run_key": "gsc-integration-preliminary",
        },
        idempotency_key="gsc-integration-preliminary",
        max_attempts=4,
    )
    lease = await queue.claim(worker_id="gsc-integration", lease_seconds=30)
    assert lease is not None and lease.id == job_id
    await handle_job(queue, lease, 1, None, service)

    repeated = await service.run_extract(
        tenant_id=tenant_id,
        connection_id=connection_id,
        definition_code="GSC_SEARCH_HOURLY_V1",
        period=period,
        freshness_status="PRELIMINARY",
        scheduled_run_key="gsc-integration-preliminary",
    )
    mature = await service.run_extract(
        tenant_id=tenant_id,
        connection_id=connection_id,
        definition_code="GSC_SEARCH_DAILY_V1",
        period=ExtractPeriod(date(2026, 8, 12), date(2026, 8, 12)),
        freshness_status="MATURE",
        scheduled_run_key="gsc-integration-mature-search",
    )
    discover = await service.run_extract(
        tenant_id=tenant_id,
        connection_id=connection_id,
        definition_code="GSC_DISCOVER_DAILY_V1",
        period=ExtractPeriod(date(2026, 8, 12), date(2026, 8, 12)),
        freshness_status="MATURE",
        scheduled_run_key="gsc-integration-mature-discover",
    )
    inspection = await service.inspect_url(
        tenant_id=tenant_id,
        connection_id=connection_id,
        inspection_url="https://www.example.com/article/",
        inspection_date=date(2026, 8, 14),
        scheduled_run_key="gsc-integration-inspection",
    )

    assert repeated is None
    assert mature is not None and len(mature.points) == 8
    assert discover is not None and discover.points == ()
    assert inspection is not None and inspection["indexStatusResult"]["verdict"] == "PASS"
    assert (
        await repository.load_connection(tenant_id=other_tenant_id, connection_id=connection_id)
        is None
    )

    async with factory() as session:
        connection = await session.get(DataConnection, connection_id)
        assert connection is not None and connection.status == "CONNECTED"
        assert connection.secret_reference == "env:GSC_INTEGRATION_ACCESS_TOKEN"
        assert "token" not in json.dumps(connection.connection_metadata).lower()
        job = await session.get(Job, job_id)
        assert job is not None and job.status == "COMPLETE"
        extracts = (
            await session.scalars(
                select(SourceExtract).where(SourceExtract.connection_id == connection_id)
            )
        ).all()
        assert len(extracts) == 4
        assert all(extract.source == "GSC" for extract in extracts)
        assert all(extract.source_timezone == "America/Los_Angeles" for extract in extracts)
        assert all(extract.status == "COMPLETE" for extract in extracts)
        assert all("definition" in extract.query_definition for extract in extracts)
        assert all(
            "access" not in json.dumps(extract.query_definition).lower() for extract in extracts
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(MetricPoint)
                .where(MetricPoint.tenant_id == tenant_id)
            )
            == 16
        )
        point_freshness = set(
            (
                await session.scalars(
                    select(MetricPoint.freshness_status).where(MetricPoint.tenant_id == tenant_id)
                )
            ).all()
        )
        assert point_freshness == {"PRELIMINARY", "MATURE"}
        series_sources = set(
            (
                await session.scalars(
                    select(MetricSeries.source).where(MetricSeries.tenant_id == tenant_id)
                )
            ).all()
        )
        assert series_sources == {"GSC"}
        inspection_extract = next(
            extract for extract in extracts if extract.extract_type == "GSC_URL_INSPECTION_V1"
        )
        assert (
            inspection_extract.response_metadata["inspection"]["indexStatusResult"]["verdict"]
            == "PASS"
        )
