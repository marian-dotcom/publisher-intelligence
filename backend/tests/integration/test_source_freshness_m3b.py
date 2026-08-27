"""EP-026 M3b: derived connector freshness — STALE source health.

A CONNECTED DataConnection whose last trustworthy success is older than its
source freshness threshold must be reported STALE, never silently HEALTHY.
Staleness is derived at read time from immutable evidence timestamps; no
health state is persisted. Stale is source-specific data-quality metadata and
never publisher/site failure.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.connectors.freshness import (
    SOURCE_FRESHNESS_THRESHOLDS,
    freshness_state,
)
from app.connectors.models import DataConnection
from app.db.session import get_session_factory
from app.main import app
from app.public_config.models import PublicConfigSnapshot
from tests.integration.purge import make_purge
from tests.integration.test_product_read_p2a import _seed_tenant_site

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _clean_db() -> None:
    asyncio.run(make_purge(get_session_factory)())


def _auth_cookies(client: TestClient, tenant_id: uuid.UUID) -> dict[str, str]:
    from app.auth.models import Operator, OperatorTenant
    from app.auth.security import hash_password

    factory = get_session_factory()
    operator_id = uuid.uuid4()
    email = f"fresh-{operator_id.hex[:8]}@example.com"

    async def seed() -> None:
        async with factory() as session, session.begin():
            session.add(
                Operator(
                    id=operator_id,
                    actor_subject_id=uuid.uuid4(),
                    email=email,
                    password_hash=hash_password("correct-horse-battery"),
                    role="OPERATOR",
                    is_active=True,
                )
            )
            await session.flush()
            session.add(OperatorTenant(operator_id=operator_id, tenant_id=tenant_id))

    asyncio.run(seed())
    login = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "tenant_id": str(tenant_id),
        },
    )
    assert login.status_code == 200
    return dict(login.cookies)


def _add_connection(
    tenant_id: uuid.UUID,
    site_id: uuid.UUID,
    *,
    provider: Literal["ga4", "gsc", "gam"],
    status: str = "CONNECTED",
    last_success_at: datetime | None = None,
) -> None:
    factory = get_session_factory()

    async def insert() -> None:
        async with factory() as session, session.begin():
            session.add(
                DataConnection(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    site_id=site_id,
                    provider=provider,
                    external_account_id=f"acct-{uuid.uuid4().hex[:6]}",
                    external_property_id=f"prop-{uuid.uuid4().hex[:6]}",
                    status=status,
                    secret_reference=f"ref-{uuid.uuid4().hex[:8]}",
                    monetization_capability="RELATIVE_ONLY",
                    scopes=[],
                    connected_at=datetime.now(UTC) - timedelta(days=30),
                    last_success_at=last_success_at,
                )
            )

    asyncio.run(insert())


def _sources(client: TestClient, cookies: dict[str, str], site_id: uuid.UUID) -> dict[str, str]:
    response = client.get(f"/product/source-health?site_id={site_id}", cookies=cookies)
    assert response.status_code == 200
    body: dict[str, object] = response.json()
    sources = body["sources"]
    assert isinstance(sources, dict)
    return {str(k): str(v) for k, v in sources.items()}


# Canonical policy sanity: thresholds are tied to scheduler cadence.
def test_thresholds_are_canonical() -> None:
    assert SOURCE_FRESHNESS_THRESHOLDS == {
        "GA4": timedelta(hours=6),
        "GSC": timedelta(hours=12),
        "GAM": timedelta(hours=6),
        "PUBLIC_CONFIG": timedelta(hours=18),
    }


def test_freshness_state_unit_boundaries() -> None:
    now = datetime.now(UTC)
    threshold = timedelta(hours=6)
    assert freshness_state(None, now=now, threshold=threshold) == "UNKNOWN"
    assert freshness_state(now - timedelta(hours=5), now=now, threshold=threshold) == "HEALTHY"
    # Exactly at the threshold is still fresh; strictly beyond is stale.
    assert freshness_state(now - threshold, now=now, threshold=threshold) == "HEALTHY"
    assert (
        freshness_state(now - threshold - timedelta(microseconds=1), now=now, threshold=threshold)
        == "STALE"
    )


def test_freshness_state_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="naive"):
        freshness_state(datetime.now(), now=datetime.now(UTC), threshold=timedelta(hours=6))


def test_stale_connected_ga4_is_reported_stale_not_healthy() -> None:
    """The confirmed false-HEALTHY defect: CONNECTED + arbitrarily old
    last_success_at must surface STALE at read time (silent scheduler/worker
    stoppage cannot leave a connector HEALTHY forever)."""
    tenant_id, site_id = asyncio.run(_seed_tenant_site(slug=f"m3b-ga4-{uuid.uuid4().hex[:8]}"))
    _add_connection(
        tenant_id,
        site_id,
        provider="ga4",
        status="CONNECTED",
        last_success_at=datetime.now(UTC) - timedelta(days=14),
    )
    client = TestClient(app)
    cookies = _auth_cookies(client, tenant_id)

    sources = _sources(client, cookies, site_id)
    assert sources["GA4"] == "STALE"
    # Stale source data-quality must not become publisher/site failure.
    home = client.get("/product/home/status", cookies=cookies).json()
    assert home["publisher_site_condition"] == "ACTIVE"


@pytest.mark.parametrize(
    "provider,code,threshold",
    [
        ("ga4", "GA4", timedelta(hours=6)),
        ("gsc", "GSC", timedelta(hours=12)),
        ("gam", "GAM", timedelta(hours=6)),
    ],
)
def test_connector_freshness_boundaries(provider: str, code: str, threshold: timedelta) -> None:
    """Deterministic just-inside / just-beyond boundary per connector."""
    tenant_id, site_id = asyncio.run(_seed_tenant_site(slug=f"m3b-{code}-{uuid.uuid4().hex[:8]}"))
    now = datetime.now(UTC)

    _add_connection(
        tenant_id,
        site_id,
        provider=provider,  # type: ignore[arg-type]
        status="CONNECTED",
        last_success_at=now - threshold + timedelta(minutes=1),
    )
    client = TestClient(app)
    cookies = _auth_cookies(client, tenant_id)
    assert _sources(client, cookies, site_id)[code] == "HEALTHY"

    factory = get_session_factory()

    async def reseed_beyond() -> None:
        async with factory() as session, session.begin():
            connection = await session.scalar(
                select(DataConnection).where(DataConnection.site_id == site_id)
            )
            assert connection is not None
            connection.last_success_at = now - threshold - timedelta(minutes=1)

    asyncio.run(reseed_beyond())
    assert _sources(client, cookies, site_id)[code] == "STALE"


@pytest.mark.parametrize("provider", ["ga4", "gsc", "gam"])
def test_never_synced_connected_is_unknown_not_healthy(provider: str) -> None:
    """CONNECTED but never successfully synced has no trustworthy success to
    have become stale: it stays UNKNOWN (absence of evidence), not HEALTHY."""
    code = {"ga4": "GA4", "gsc": "GSC", "gam": "GAM"}[provider]
    tenant_id, site_id = asyncio.run(_seed_tenant_site(slug=f"m3b-ns-{uuid.uuid4().hex[:8]}"))
    _add_connection(
        tenant_id,
        site_id,
        provider=provider,  # type: ignore[arg-type]
        status="CONNECTED",
        last_success_at=None,
    )
    client = TestClient(app)
    cookies = _auth_cookies(client, tenant_id)
    assert _sources(client, cookies, site_id)[code] == "UNKNOWN"


@pytest.mark.parametrize(
    "status,expected",
    [
        ("AUTH_EXPIRED", "ACTION_REQUIRED"),
        ("PERMISSION_ERROR", "BLOCKED"),
    ],
)
def test_explicit_failure_states_take_precedence_over_stale(status: str, expected: str) -> None:
    tenant_id, site_id = asyncio.run(_seed_tenant_site(slug=f"m3b-pr-{uuid.uuid4().hex[:8]}"))
    _add_connection(
        tenant_id,
        site_id,
        provider="ga4",
        status=status,
        last_success_at=datetime.now(UTC) - timedelta(days=14),
    )
    client = TestClient(app)
    cookies = _auth_cookies(client, tenant_id)
    assert _sources(client, cookies, site_id)["GA4"] == expected


def test_degraded_connection_with_old_success_stays_degraded() -> None:
    tenant_id, site_id = asyncio.run(_seed_tenant_site(slug=f"m3b-dg-{uuid.uuid4().hex[:8]}"))
    _add_connection(
        tenant_id,
        site_id,
        provider="ga4",
        status="DEGRADED",
        last_success_at=datetime.now(UTC) - timedelta(days=14),
    )
    client = TestClient(app)
    cookies = _auth_cookies(client, tenant_id)
    assert _sources(client, cookies, site_id)["GA4"] == "DEGRADED"


def test_one_stale_source_leaves_other_sources_unchanged() -> None:
    """Source independence: a stale GA4 must not touch GSC/GAM/browser state,
    nor imply any publisher/site failure."""
    tenant_id, site_id = asyncio.run(_seed_tenant_site(slug=f"m3b-ind-{uuid.uuid4().hex[:8]}"))
    now = datetime.now(UTC)
    _add_connection(
        tenant_id,
        site_id,
        provider="ga4",
        status="CONNECTED",
        last_success_at=now - timedelta(days=14),
    )
    _add_connection(
        tenant_id,
        site_id,
        provider="gsc",
        status="CONNECTED",
        last_success_at=now - timedelta(hours=1),
    )
    _add_connection(
        tenant_id,
        site_id,
        provider="gam",
        status="CONNECTED",
        last_success_at=now - timedelta(hours=2),
    )
    client = TestClient(app)
    cookies = _auth_cookies(client, tenant_id)

    sources = _sources(client, cookies, site_id)
    assert sources["GA4"] == "STALE"
    assert sources["GSC"] == "HEALTHY"
    assert sources["GAM"] == "HEALTHY"
    assert sources["BROWSER_MONITORING"] in ("HEALTHY", "UNKNOWN")

    home = client.get("/product/home/status", cookies=cookies).json()
    assert home["publisher_site_condition"] == "ACTIVE"
    assert home["source_health"]["GA4"] == "STALE"


def _add_snapshot(
    tenant_id: uuid.UUID,
    site_id: uuid.UUID,
    *,
    observed_at: datetime,
    parse_status: str = "VALID",
    fetch_kind: str = "SCHEDULED",
) -> None:
    factory = get_session_factory()

    async def insert() -> None:
        async with factory() as session, session.begin():
            validation_of: uuid.UUID | None = None
            if fetch_kind == "VALIDATION":
                primary = await session.scalar(
                    select(PublicConfigSnapshot.id)
                    .where(PublicConfigSnapshot.site_id == site_id)
                    .order_by(PublicConfigSnapshot.observed_at.desc())
                    .limit(1)
                )
                assert primary is not None
                validation_of = primary
            session.add(
                PublicConfigSnapshot(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    site_id=site_id,
                    config_type="ROBOTS_TXT",
                    observed_at=observed_at,
                    http_status=200 if parse_status in ("VALID", "VALID_WITH_WARNINGS") else 503,
                    content_hash=None,
                    parse_status=parse_status,
                    artifact_id=None,
                    normalizer_version="e3-v1",
                    summary={},
                    fetch_kind=fetch_kind,
                    validation_of_snapshot_id=validation_of,
                    observation_key=f"obs-{uuid.uuid4().hex[:24]}",
                )
            )

    asyncio.run(insert())


def test_public_config_freshness_states() -> None:
    """PUBLIC_CONFIG freshness derives from the latest successful SCHEDULED
    snapshot's observed_at; VALIDATION follow-ups are never the heartbeat."""
    tenant_id, site_id = asyncio.run(_seed_tenant_site(slug=f"m3b-pc-{uuid.uuid4().hex[:8]}"))
    now = datetime.now(UTC)
    client = TestClient(app)
    cookies = _auth_cookies(client, tenant_id)

    # No successful snapshot at all: absence of evidence.
    assert _sources(client, cookies, site_id)["PUBLIC_CONFIG"] == "UNKNOWN"

    # Recent good scheduled snapshot: HEALTHY.
    _add_snapshot(tenant_id, site_id, observed_at=now - timedelta(hours=2))
    assert _sources(client, cookies, site_id)["PUBLIC_CONFIG"] == "HEALTHY"

    # Old good snapshot only: STALE.
    factory = get_session_factory()

    async def age_snapshot() -> None:
        async with factory() as session, session.begin():
            snapshot = await session.scalar(select(PublicConfigSnapshot))
            assert snapshot is not None
            snapshot.observed_at = now - SOURCE_FRESHNESS_THRESHOLDS["PUBLIC_CONFIG"]
            snapshot.observed_at -= timedelta(minutes=1)

    asyncio.run(age_snapshot())
    assert _sources(client, cookies, site_id)["PUBLIC_CONFIG"] == "STALE"

    # A recent VALIDATION follow-up does not restore freshness.
    _add_snapshot(
        tenant_id, site_id, observed_at=now, parse_status="VALID", fetch_kind="VALIDATION"
    )
    assert _sources(client, cookies, site_id)["PUBLIC_CONFIG"] == "STALE"

    # A recent failed scheduled fetch does not count as a success heartbeat.
    _add_snapshot(tenant_id, site_id, observed_at=now, parse_status="HTTP_ERROR")
    assert _sources(client, cookies, site_id)["PUBLIC_CONFIG"] == "STALE"
