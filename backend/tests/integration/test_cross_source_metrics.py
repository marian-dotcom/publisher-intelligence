import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select

from app.browser.models import Publisher, Site
from app.connectors.core.persistence import _series_key
from app.connectors.models import DataConnection, MetricPoint, MetricSeries, SourceExtract
from app.db.models import Tenant
from app.db.session import get_session_factory
from app.metrics.models import MetricDerivation, MetricDerivationInput
from app.metrics.persistence import MetricDerivationRepository, MetricDerivationStateError
from app.metrics.service import CrossSourceMetricService

pytestmark = pytest.mark.integration


@pytest.fixture
async def metric_site() -> AsyncIterator[tuple[uuid.UUID, uuid.UUID, uuid.UUID]]:
    tenant_id = uuid.uuid4()
    other_tenant_id = uuid.uuid4()
    publisher_id = uuid.uuid4()
    site_id = uuid.uuid4()
    factory = get_session_factory()
    async with factory() as session, session.begin():
        session.add_all(
            [
                Tenant(id=tenant_id, slug=f"metrics-{tenant_id.hex[:10]}", name="Metrics Tenant"),
                Tenant(
                    id=other_tenant_id,
                    slug=f"metrics-other-{other_tenant_id.hex[:10]}",
                    name="Other Metrics Tenant",
                ),
            ]
        )
        await session.flush()
        session.add(
            Publisher(
                id=publisher_id,
                tenant_id=tenant_id,
                name="Metrics Publisher",
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
                name="Metrics Site",
                canonical_domain=f"{site_id.hex}.example.com",
                canonical_scheme="https",
                timezone="Europe/Bucharest",
                status="ACTIVE",
            )
        )
    yield tenant_id, other_tenant_id, site_id
    async with factory() as session, session.begin():
        await session.execute(
            delete(MetricDerivationInput).where(MetricDerivationInput.tenant_id == tenant_id)
        )
        await session.execute(delete(MetricPoint).where(MetricPoint.tenant_id == tenant_id))
        await session.execute(
            delete(MetricDerivation).where(MetricDerivation.tenant_id == tenant_id)
        )
        await session.execute(delete(MetricSeries).where(MetricSeries.tenant_id == tenant_id))
        await session.execute(delete(SourceExtract).where(SourceExtract.tenant_id == tenant_id))
        await session.execute(delete(DataConnection).where(DataConnection.tenant_id == tenant_id))
        await session.execute(delete(Site).where(Site.id == site_id))
        await session.execute(delete(Publisher).where(Publisher.id == publisher_id))
        await session.execute(delete(Tenant).where(Tenant.id.in_([tenant_id, other_tenant_id])))


async def test_cross_source_ratios_are_auditable_idempotent_and_append_only(
    metric_site: tuple[uuid.UUID, uuid.UUID, uuid.UUID],
) -> None:
    tenant_id, other_tenant_id, site_id = metric_site
    factory = get_session_factory()
    start = datetime(2026, 8, 19, 10, tzinfo=UTC)
    end = start + timedelta(hours=1)
    async with factory() as session, session.begin():
        ga4_connection = _connection(tenant_id, site_id, "GA4")
        gam_connection = _connection(tenant_id, site_id, "GAM")
        session.add_all([ga4_connection, gam_connection])
        await session.flush()
        ga4_extract = _extract(
            tenant_id, site_id, ga4_connection.id, "GA4", "GA4_TRAFFIC_HOURLY_V1", start, end
        )
        gam_extract = _extract(
            tenant_id, site_id, gam_connection.id, "GAM", "GAM_INVENTORY_HEALTH_V1", start, end
        )
        session.add_all([ga4_extract, gam_extract])
        await session.flush()
        views = _series(tenant_id, site_id, "GA4", "ga4.screen_page_views", "ga4-core-v1")
        requests = _series(tenant_id, site_id, "GAM", "gam.ad_requests", "gam-historical-v1")
        impressions = _series(
            tenant_id, site_id, "GAM", "gam.ad_server_impressions", "gam-historical-v1"
        )
        session.add_all([views, requests, impressions])
        await session.flush()
        session.add_all(
            [
                _point(tenant_id, site_id, views.id, ga4_extract.id, start, end, 100, end),
                _point(tenant_id, site_id, requests.id, gam_extract.id, start, end, 250, end),
                _point(tenant_id, site_id, impressions.id, gam_extract.id, start, end, 200, end),
            ]
        )

    repository = MetricDerivationRepository(factory)
    service = CrossSourceMetricService(repository)
    first = await service.derive_site(
        tenant_id=tenant_id,
        site_id=site_id,
        window_start=start,
        window_end=end,
    )
    repeated = await service.derive_site(
        tenant_id=tenant_id,
        site_id=site_id,
        window_start=start,
        window_end=end,
    )

    assert first.candidate_count == 2 and first.created_count == 2
    assert repeated.candidate_count == 2 and repeated.created_count == 0
    assert (tenant_id, site_id) in await repository.schedulable_sites()
    with pytest.raises(MetricDerivationStateError, match="does not belong"):
        await service.derive_site(
            tenant_id=other_tenant_id,
            site_id=site_id,
            window_start=start,
            window_end=end,
        )

    async with factory() as session:
        derived_series = (
            await session.scalars(
                select(MetricSeries).where(
                    MetricSeries.tenant_id == tenant_id, MetricSeries.source == "DERIVED"
                )
            )
        ).all()
        derived_points = (
            await session.scalars(
                select(MetricPoint)
                .join(MetricSeries, MetricSeries.id == MetricPoint.series_id)
                .where(MetricSeries.source == "DERIVED", MetricPoint.tenant_id == tenant_id)
            )
        ).all()
        assert {series.metric_code for series in derived_series} == {
            "derived.requests_per_view_v1",
            "derived.impressions_per_view_v1",
        }
        assert {(point.numerator, point.denominator, point.value) for point in derived_points} == {
            (250, 100, 2.5),
            (200, 100, 2.0),
        }
        assert all(point.source_extract_id is None for point in derived_points)
        assert all(point.derivation_id is not None for point in derived_points)
        assert (
            await session.scalar(
                select(func.count())
                .select_from(MetricDerivationInput)
                .where(MetricDerivationInput.tenant_id == tenant_id)
            )
            == 4
        )

    async with factory() as session, session.begin():
        reconciled = _extract(
            tenant_id,
            site_id,
            gam_connection.id,
            "GAM",
            "GAM_INVENTORY_HEALTH_V1",
            start,
            end,
            run_key="reconciled",
            retrieved=end + timedelta(hours=1),
        )
        session.add(reconciled)
        await session.flush()
        session.add_all(
            [
                _point(
                    tenant_id,
                    site_id,
                    requests.id,
                    reconciled.id,
                    start,
                    end,
                    300,
                    end + timedelta(hours=1),
                ),
                _point(
                    tenant_id,
                    site_id,
                    impressions.id,
                    reconciled.id,
                    start,
                    end,
                    240,
                    end + timedelta(hours=1),
                ),
            ]
        )
    reconciled_result = await service.derive_site(
        tenant_id=tenant_id,
        site_id=site_id,
        window_start=start,
        window_end=end,
    )
    assert reconciled_result.created_count == 2
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(MetricDerivation)
                .where(MetricDerivation.tenant_id == tenant_id)
            )
            == 4
        )


def _connection(tenant_id: uuid.UUID, site_id: uuid.UUID, provider: str) -> DataConnection:
    return DataConnection(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        site_id=site_id,
        provider=provider,
        external_property_id=f"{provider.lower()}-{uuid.uuid4().hex[:8]}",
        status="CONNECTED",
        scopes=[],
        secret_reference=f"env:{provider}_TEST_TOKEN",
        connection_metadata={},
    )


def _extract(
    tenant_id: uuid.UUID,
    site_id: uuid.UUID,
    connection_id: uuid.UUID,
    source: str,
    extract_type: str,
    start: datetime,
    end: datetime,
    *,
    run_key: str | None = None,
    retrieved: datetime | None = None,
) -> SourceExtract:
    return SourceExtract(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        site_id=site_id,
        connection_id=connection_id,
        source=source,
        extract_type=extract_type,
        scheduled_run_key=run_key or f"{source.lower()}-source",
        query_definition={"definition": extract_type},
        period_start=start,
        period_end=end,
        source_timezone="UTC",
        requested_at=start,
        retrieved_at=retrieved or end,
        status="COMPLETE",
        freshness_status="MATURE",
        response_metadata={"limitations": []},
        connector_version=f"{source.lower()}-test-v1",
    )


def _series(
    tenant_id: uuid.UUID,
    site_id: uuid.UUID,
    source: str,
    metric_code: str,
    semantics: str,
) -> MetricSeries:
    dimensions = {"fixture": metric_code}
    return MetricSeries(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        site_id=site_id,
        source=source,
        metric_code=metric_code,
        metric_semantics_version=semantics,
        unit="COUNT",
        granularity="HOUR",
        dimensions=dimensions,
        series_key=_series_key(
            tenant_id=tenant_id,
            site_id=site_id,
            source=source,
            metric_code=metric_code,
            semantics_version=semantics,
            granularity="HOUR",
            dimensions=dimensions,
        ),
    )


def _point(
    tenant_id: uuid.UUID,
    site_id: uuid.UUID,
    series_id: uuid.UUID,
    extract_id: uuid.UUID,
    start: datetime,
    end: datetime,
    value: float,
    retrieved: datetime,
) -> MetricPoint:
    return MetricPoint(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        site_id=site_id,
        series_id=series_id,
        source_extract_id=extract_id,
        derivation_id=None,
        source_time=start.isoformat(),
        period_start=start,
        period_end=end,
        value=value,
        sample_status="COMPLETE",
        freshness_status="MATURE",
        retrieved_at=retrieved,
    )
