import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import delete, func, select

from app.browser.models import Publisher, Site
from app.connectors.core.contracts import ConnectorError
from app.connectors.drilldown.catalog import provider_codes
from app.connectors.drilldown.service import DrilldownJobRequest, DrilldownPlanningService
from app.connectors.ga4.definitions import GA4_READONLY_SCOPE
from app.connectors.models import DataConnection
from app.db.models import Job, Tenant
from app.db.session import get_session_factory

pytestmark = pytest.mark.integration


@pytest.fixture
async def drilldown_connection() -> AsyncIterator[
    tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]
]:
    tenant_id = uuid.uuid4()
    other_tenant_id = uuid.uuid4()
    publisher_id = uuid.uuid4()
    site_id = uuid.uuid4()
    connection_id = uuid.uuid4()
    factory = get_session_factory()
    async with factory() as session, session.begin():
        session.add_all(
            [
                Tenant(
                    id=tenant_id,
                    slug=f"drilldown-{tenant_id.hex[:10]}",
                    name="Drill-down Tenant",
                ),
                Tenant(
                    id=other_tenant_id,
                    slug=f"drilldown-other-{other_tenant_id.hex[:10]}",
                    name="Other Tenant",
                ),
            ]
        )
        await session.flush()
        session.add(
            Publisher(
                id=publisher_id,
                tenant_id=tenant_id,
                name="Drill-down Publisher",
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
                name="Drill-down Site",
                canonical_domain="example.com",
                canonical_scheme="https",
                timezone="Europe/Bucharest",
                status="ACTIVE",
            )
        )
        await session.flush()
        session.add(
            DataConnection(
                id=connection_id,
                tenant_id=tenant_id,
                site_id=site_id,
                provider="GA4",
                external_property_id="123456",
                status="CONNECTED",
                scopes=[GA4_READONLY_SCOPE],
                secret_reference="env:DRILLDOWN_TEST_ACCESS_TOKEN",
                connection_metadata={
                    "drilldownCatalogVersion": "incident-drilldown-v1",
                    "validatedDrilldowns": list(provider_codes("GA4")),
                },
            )
        )
    yield tenant_id, other_tenant_id, site_id, connection_id
    async with factory() as session, session.begin():
        await session.execute(delete(Job).where(Job.tenant_id == tenant_id))
        await session.execute(delete(DataConnection).where(DataConnection.id == connection_id))
        await session.execute(delete(Site).where(Site.id == site_id))
        await session.execute(delete(Publisher).where(Publisher.id == publisher_id))
        await session.execute(delete(Tenant).where(Tenant.id.in_([tenant_id, other_tenant_id])))


async def test_planner_is_idempotent_tenant_owned_and_enforces_both_budgets(
    drilldown_connection: tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID],
) -> None:
    tenant_id, other_tenant_id, site_id, connection_id = drilldown_connection
    service = DrilldownPlanningService(get_session_factory())
    now = datetime(2026, 8, 20, 10, tzinfo=UTC)
    first_investigation = uuid.uuid4()
    first = DrilldownJobRequest(
        tenant_id=tenant_id,
        site_id=site_id,
        connection_id=connection_id,
        investigation_id=first_investigation,
        definition_code="traffic_by_page_device",
        start_date=date(2026, 8, 19),
        end_date=date(2026, 8, 20),
    )
    created = await service.request(first, now=now)
    reused = await service.request(first, now=now)
    assert created.created is True
    assert reused == type(reused)(created.job_id, False, created.request_key)

    for index, definition_code in enumerate(
        (
            "traffic_by_hour_device_channel",
            "traffic_by_country_device",
            "landing_page_by_channel",
        )
    ):
        await service.request(
            DrilldownJobRequest(
                tenant_id=tenant_id,
                site_id=site_id,
                connection_id=connection_id,
                investigation_id=first_investigation,
                definition_code=definition_code,
                start_date=date(2026, 8, 18 - index),
                end_date=date(2026, 8, 20),
            ),
            now=now,
        )
    with pytest.raises(ConnectorError) as investigation_budget:
        await service.request(
            DrilldownJobRequest(
                tenant_id=tenant_id,
                site_id=site_id,
                connection_id=connection_id,
                investigation_id=first_investigation,
                definition_code="traffic_by_page_device",
                start_date=date(2026, 8, 18),
                end_date=date(2026, 8, 20),
            ),
            now=now,
        )
    assert investigation_budget.value.code == "DRILLDOWN_INVESTIGATION_BUDGET_EXCEEDED"

    second_investigation = uuid.uuid4()
    for index, definition_code in enumerate(provider_codes("GA4")):
        await service.request(
            DrilldownJobRequest(
                tenant_id=tenant_id,
                site_id=site_id,
                connection_id=connection_id,
                investigation_id=second_investigation,
                definition_code=definition_code,
                start_date=date(2026, 8, 14 + index),
                end_date=date(2026, 8, 20),
            ),
            now=now,
        )
    with pytest.raises(ConnectorError) as daily_budget:
        await service.request(
            DrilldownJobRequest(
                tenant_id=tenant_id,
                site_id=site_id,
                connection_id=connection_id,
                investigation_id=uuid.uuid4(),
                definition_code="traffic_by_page_device",
                start_date=date(2026, 8, 20),
                end_date=date(2026, 8, 20),
            ),
            now=now,
        )
    assert daily_budget.value.code == "DRILLDOWN_DAILY_BUDGET_EXCEEDED"

    with pytest.raises(ConnectorError) as tenant_error:
        await service.request(
            DrilldownJobRequest(
                tenant_id=other_tenant_id,
                site_id=site_id,
                connection_id=connection_id,
                investigation_id=uuid.uuid4(),
                definition_code="traffic_by_page_device",
                start_date=date(2026, 8, 20),
                end_date=date(2026, 8, 20),
            ),
            now=now,
        )
    assert tenant_error.value.code == "DRILLDOWN_SCOPE_INVALID"

    async with get_session_factory()() as session:
        jobs = await session.scalar(
            select(func.count(Job.id)).where(
                Job.tenant_id == tenant_id,
                Job.job_type == "CONNECTOR_DRILLDOWN",
            )
        )
        payloads = (
            await session.scalars(
                select(Job.payload).where(
                    Job.tenant_id == tenant_id,
                    Job.job_type == "CONNECTOR_DRILLDOWN",
                )
            )
        ).all()
    assert jobs == 8
    assert all("token" not in str(payload).lower() for payload in payloads)
    assert all(
        set(payload)
        == {
            "catalog_version",
            "connection_id",
            "definition_code",
            "end_date",
            "investigation_id",
            "parameters",
            "profile",
            "request_key",
            "site_id",
            "start_date",
        }
        for payload in payloads
    )
