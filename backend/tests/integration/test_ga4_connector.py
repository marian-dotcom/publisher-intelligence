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
from app.connectors.ga4.client import GA4Client
from app.connectors.ga4.service import GA4ConnectorService
from app.connectors.models import DataConnection, MetricPoint, MetricSeries, SourceExtract
from app.db.models import Job, Tenant
from app.db.session import get_session_factory
from app.jobs.queue import JobQueue
from app.worker import handle_job

pytestmark = pytest.mark.integration
FIXTURES = Path(__file__).parents[1] / "fixtures" / "connectors" / "ga4"


def load(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((FIXTURES / name).read_text()))


class FixtureResolver:
    async def resolve(self, secret_reference: str) -> AccessCredential:
        assert secret_reference == "env:GA4_INTEGRATION_ACCESS_TOKEN"
        return AccessCredential("sanitized-fixture-token")


class FixtureTransport:
    async def request(self, **kwargs: Any) -> Mapping[str, Any]:
        if kwargs["method"] == "GET":
            return load("metadata_core.json")
        metrics = [item["name"] for item in kwargs["json_body"]["metrics"]]
        if "engagementRate" in metrics:
            return load("behavior_complete.json")
        return load("traffic_complete.json")


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
                Tenant(id=tenant_id, slug=f"ga4-{tenant_id.hex[:10]}", name="GA4 Tenant"),
                Tenant(
                    id=other_tenant_id,
                    slug=f"ga4-other-{other_tenant_id.hex[:10]}",
                    name="Other Tenant",
                ),
                Publisher(
                    id=publisher_id,
                    tenant_id=tenant_id,
                    name="GA4 Publisher",
                    slug=f"publisher-{publisher_id.hex[:10]}",
                    default_timezone="Europe/Bucharest",
                    status="ACTIVE",
                ),
                Site(
                    id=site_id,
                    tenant_id=tenant_id,
                    publisher_id=publisher_id,
                    name="GA4 Site",
                    canonical_domain=f"{site_id.hex}.example.com",
                    canonical_scheme="https",
                    timezone="Europe/Bucharest",
                    status="ACTIVE",
                ),
            ]
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


async def test_ga4_validation_ingestion_idempotency_reconciliation_and_tenancy(
    connector_site: tuple[uuid.UUID, uuid.UUID, uuid.UUID],
) -> None:
    tenant_id, other_tenant_id, site_id = connector_site
    factory = get_session_factory()
    repository = ConnectorRepository(factory)
    service = GA4ConnectorService(
        repository,
        GA4Client(FixtureTransport()),
        cast(Any, FixtureResolver()),
    )
    connection_id = await service.register_connection(
        tenant_id=tenant_id,
        site_id=site_id,
        property_id="123456",
        secret_reference="env:GA4_INTEGRATION_ACCESS_TOKEN",
    )
    snapshot = await service.validate_connection(
        tenant_id=tenant_id,
        connection_id=connection_id,
        probe_date=date(2026, 8, 13),
    )
    assert snapshot["propertyTimezone"] == "Europe/Bucharest"

    period = ExtractPeriod(date(2026, 8, 12), date(2026, 8, 13))
    queue = JobQueue(factory)
    job_id = await queue.enqueue(
        tenant_id=tenant_id,
        job_type="GA4_EXTRACT",
        payload={
            "connection_id": str(connection_id),
            "definition_code": "GA4_TRAFFIC_HOURLY_V1",
            "start_date": period.start_date.isoformat(),
            "end_date": period.end_date.isoformat(),
            "freshness_status": "PRELIMINARY",
            "scheduled_run_key": "integration-preliminary",
        },
        idempotency_key="integration-preliminary",
        max_attempts=4,
    )
    lease = await queue.claim(worker_id="ga4-integration", lease_seconds=30)
    assert lease is not None and lease.id == job_id
    await handle_job(queue, lease, 1, service)
    repeated = await service.run_extract(
        tenant_id=tenant_id,
        connection_id=connection_id,
        definition_code="GA4_TRAFFIC_HOURLY_V1",
        period=period,
        freshness_status="PRELIMINARY",
        scheduled_run_key="integration-preliminary",
    )
    mature = await service.run_extract(
        tenant_id=tenant_id,
        connection_id=connection_id,
        definition_code="GA4_TRAFFIC_HOURLY_V1",
        period=period,
        freshness_status="MATURE",
        scheduled_run_key="integration-mature-traffic",
    )
    behavior = await service.run_extract(
        tenant_id=tenant_id,
        connection_id=connection_id,
        definition_code="GA4_BEHAVIOR_DAILY_V1",
        period=ExtractPeriod(date(2026, 8, 12), date(2026, 8, 12)),
        freshness_status="MATURE",
        scheduled_run_key="integration-mature-behavior",
    )

    assert repeated is None
    assert mature is not None and len(mature.points) == 8
    assert behavior is not None and len(behavior.points) == 6
    assert (
        await repository.load_connection(tenant_id=other_tenant_id, connection_id=connection_id)
        is None
    )

    async with factory() as session:
        connection = await session.get(DataConnection, connection_id)
        assert connection is not None
        assert connection.status == "CONNECTED"
        assert connection.secret_reference == "env:GA4_INTEGRATION_ACCESS_TOKEN"
        assert "token" not in json.dumps(connection.connection_metadata).lower()
        job = await session.get(Job, job_id)
        assert job is not None and job.status == "COMPLETE"
        assert (
            await session.scalar(
                select(func.count())
                .select_from(SourceExtract)
                .where(SourceExtract.connection_id == connection_id)
            )
            == 3
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(MetricPoint)
                .where(MetricPoint.tenant_id == tenant_id)
            )
            == 22
        )
        freshness = set(
            (
                await session.scalars(
                    select(SourceExtract.freshness_status).where(
                        SourceExtract.connection_id == connection_id
                    )
                )
            ).all()
        )
        assert freshness == {"PRELIMINARY", "MATURE"}
        extracts = (
            await session.scalars(
                select(SourceExtract).where(SourceExtract.connection_id == connection_id)
            )
        ).all()
        assert all(extract.status == "COMPLETE" for extract in extracts)
        assert all(extract.source_timezone == "Europe/Bucharest" for extract in extracts)
        assert all(extract.period_start is not None for extract in extracts)
        assert all(extract.period_end is not None for extract in extracts)
        assert all("definition" in extract.query_definition for extract in extracts)
        assert all(
            "access" not in json.dumps(extract.query_definition).lower() for extract in extracts
        )
