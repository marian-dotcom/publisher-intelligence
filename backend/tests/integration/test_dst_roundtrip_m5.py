"""EP-026 M5 — PostgreSQL UTC-aware round-trip across a DST boundary.

Proves that DST-normalized absolute instants survive an actual PostgreSQL
round trip timezone-aware and instant-exact: SourceExtract periods derived
from GA4 normalization and browser CheckpointWindow bounds are persisted,
read back, compared by absolute instant, and ordered consistently.
"""

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.browser.cost import site_window_scope  # noqa: F401  (scope parity check)
from app.browser.models import CheckpointWindow, Publisher, Site
from app.connectors.core.contracts import ExtractPeriod, NormalizedMetricPoint
from app.connectors.ga4.definitions import GA4_TRAFFIC_HOURLY_V1
from app.connectors.ga4.normalization import normalize_report as ga4_normalize
from app.connectors.models import DataConnection, SourceExtract
from app.db.models import Tenant
from app.db.session import get_session_factory
from tests.integration.purge import make_purge

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _clean_db() -> None:
    asyncio.run(make_purge(get_session_factory)())


def _ga4_boundary_point() -> "NormalizedMetricPoint":
    """GA4-normalized point for Bucharest's repeated fall-back local hour."""
    fixtures = __import__("pathlib").Path(__file__).parents[1] / "fixtures" / "connectors"
    payload = __import__("json").loads((fixtures / "ga4/traffic_complete.json").read_text())
    payload["rows"] = [
        {
            "dimensionValues": [
                {"value": "2026102503"},
                {"value": "mobile"},
                {"value": "Organic Search"},
            ],
            "metricValues": [
                {"value": "120"},
                {"value": "150"},
                {"value": "225"},
                {"value": "95"},
            ],
        }
    ]
    normalized = ga4_normalize(payload, GA4_TRAFFIC_HOURLY_V1)
    return normalized.points[0]


async def _seed_chain_and_extract(period: ExtractPeriod) -> uuid.UUID:
    factory = get_session_factory()
    tenant_id, publisher_id, site_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    connection_id = uuid.uuid4()
    extract_id = uuid.uuid4()
    async with factory() as session, session.begin():
        session.add(Tenant(id=tenant_id, slug=f"m5-{tenant_id.hex[:8]}", name="M5"))
        await session.flush()
        session.add(
            Publisher(
                id=publisher_id,
                tenant_id=tenant_id,
                name="P",
                slug=f"pub-{publisher_id.hex[:8]}",
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
                name="S",
                canonical_domain=f"{site_id.hex}.example.com",
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
                external_property_id="prop-1",
                status="CONNECTED",
                secret_reference=f"ref-{uuid.uuid4().hex[:8]}",
                monetization_capability="UNKNOWN",
                scopes=[],
            )
        )
        await session.flush()
        session.add(
            SourceExtract(
                id=extract_id,
                tenant_id=tenant_id,
                site_id=site_id,
                connection_id=connection_id,
                source="GA4",
                extract_type=GA4_TRAFFIC_HOURLY_V1.code,
                scheduled_run_key=f"m5:{uuid.uuid4()}",
                query_definition={"definition_code": GA4_TRAFFIC_HOURLY_V1.code},
                period_start=period.start_date,
                period_end=period.end_date,
                source_timezone="Europe/Bucharest",
                retrieved_at=datetime.now(UTC),
                status="COMPLETE",
                freshness_status="MATURE",
                response_metadata={},
                connector_version=GA4_TRAFFIC_HOURLY_V1.connector_version,
            )
        )
    return extract_id


async def _seed_window(start: datetime, end: datetime) -> tuple[uuid.UUID, uuid.UUID]:
    factory = get_session_factory()
    tenant_id, publisher_id, site_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    window_id = uuid.uuid4()
    async with factory() as session, session.begin():
        session.add(Tenant(id=tenant_id, slug=f"m5w-{tenant_id.hex[:8]}", name="M5W"))
        await session.flush()
        session.add(
            Publisher(
                id=publisher_id,
                tenant_id=tenant_id,
                name="P2",
                slug=f"pub-{publisher_id.hex[:8]}",
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
                name="S2",
                canonical_domain=f"{site_id.hex}.example.com",
                canonical_scheme="https",
                timezone="Europe/Bucharest",
                status="ACTIVE",
            )
        )
        await session.flush()
        session.add(
            CheckpointWindow(
                id=window_id,
                tenant_id=tenant_id,
                site_id=site_id,
                scheduled_for=start,
                window_start=start,
                window_end=end,
            )
        )
    return window_id, site_id


def test_postgres_round_trip_preserves_dst_absolute_instants() -> None:
    point = _ga4_boundary_point()
    assert point.period_start == datetime(2026, 10, 25, 0, 0, tzinfo=UTC)

    # Browser fall-back window bracketing the same boundary (21:00Z..04:00Z).
    window_start = datetime(2026, 10, 24, 21, 0, tzinfo=UTC)
    window_end = datetime(2026, 10, 25, 4, 0, tzinfo=UTC)
    window_id, _site_id = asyncio.run(_seed_window(window_start, window_end))
    extract_id = asyncio.run(
        _seed_chain_and_extract(ExtractPeriod(point.period_start, point.period_end))
    )

    factory = get_session_factory()

    async def read_back() -> tuple[SourceExtract | None, CheckpointWindow | None]:
        async with factory() as session:
            extract = await session.scalar(
                select(SourceExtract).where(SourceExtract.id == extract_id)
            )
            window = await session.scalar(
                select(CheckpointWindow).where(CheckpointWindow.id == window_id)
            )
            return extract, window

    extract, window = asyncio.run(read_back())
    assert extract is not None and window is not None
    # Timezone-aware after the real PostgreSQL timestamptz round trip.
    for stamp in (
        extract.period_start,
        extract.period_end,
        extract.retrieved_at,
        window.window_start,
        window.window_end,
    ):
        assert stamp is not None and stamp.tzinfo is not None
    # Instants are exactly preserved through storage.
    assert extract.period_start == point.period_start == datetime(2026, 10, 25, 0, 0, tzinfo=UTC)
    assert extract.period_end == point.period_end
    assert extract.source_timezone == "Europe/Bucharest"
    assert (window.window_start, window.window_end) == (window_start, window_end)
    # Absolute-instant ordering across sources survives persistence.
    assert window.window_start <= extract.period_start <= window.window_end
