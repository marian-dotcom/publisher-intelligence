"""EP-025a P2-A: Home/status, source health, publisher/site health contracts."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.browser.models import (
    BrowserScenario,
    CheckpointRun,
    CheckpointWindow,
    MonitoredUrl,
    Publisher,
    Site,
    Template,
)
from app.connectors.models import DataConnection
from app.db.models import Tenant
from app.db.session import get_session_factory
from app.main import app
from tests.integration.purge import make_purge

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _clean_db() -> None:
    asyncio.run(make_purge(get_session_factory)())


async def _seed_tenant_site(*, slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    factory = get_session_factory()
    tenant_id, publisher_id, site_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with factory() as session, session.begin():
        session.add(Tenant(id=tenant_id, slug=slug, name=slug.title()))
        await session.flush()
        session.add(
            Publisher(
                id=publisher_id,
                tenant_id=tenant_id,
                name=f"Publisher {slug}",
                slug=f"pub-{publisher_id.hex[:8]}",
                default_timezone="UTC",
                status="ACTIVE",
            )
        )
        await session.flush()
        session.add(
            Site(
                id=site_id,
                tenant_id=tenant_id,
                publisher_id=publisher_id,
                name=f"Site {slug}",
                canonical_domain=f"{site_id.hex}.example.com",
                canonical_scheme="https",
                timezone="UTC",
                status="ACTIVE",
            )
        )
        await session.flush()
        template_id, monitored_url_id, scenario_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        window_id = uuid.uuid4()
        session.add(
            Template(
                id=template_id,
                tenant_id=tenant_id,
                site_id=site_id,
                code="article",
                display_name="Article",
                status="ACTIVE",
            )
        )
        await session.flush()
        session.add(
            MonitoredUrl(
                id=monitored_url_id,
                tenant_id=tenant_id,
                site_id=site_id,
                template_id=template_id,
                url=f"https://{site_id.hex}.example.com/a",
                status="ACTIVE",
            )
        )
        session.add(
            BrowserScenario(
                id=scenario_id,
                tenant_id=tenant_id,
                site_id=site_id,
                code=f"core_desktop_{scenario_id.hex[:6]}",
                version=1,
                status="ACTIVE",
            )
        )
        now = datetime.now(UTC)
        session.add(
            CheckpointWindow(
                id=window_id,
                tenant_id=tenant_id,
                site_id=site_id,
                scheduled_for=now - timedelta(hours=1),
                window_start=now - timedelta(hours=1),
                window_end=now - timedelta(minutes=30),
            )
        )
        await session.flush()
        session.add(
            CheckpointRun(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                site_id=site_id,
                checkpoint_window_id=window_id,
                monitored_url_id=monitored_url_id,
                template_id=template_id,
                scenario_id=scenario_id,
                observation_kind="SCHEDULED",
                scheduled_for=now - timedelta(hours=1),
                started_at=now - timedelta(hours=1),
                completed_at=now - timedelta(minutes=55),
                status="COMPLETE",
                attempt_count=1,
                collector_bundle_version="b8-v1",
                environment={"is_mobile": False},
                limitations=[],
                manifest={},
            )
        )
    return tenant_id, site_id


async def _add_connection(tenant_id: uuid.UUID, site_id: uuid.UUID, *, status: str) -> None:
    factory = get_session_factory()
    async with factory() as session, session.begin():
        session.add(
            DataConnection(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                site_id=site_id,
                provider="ga4",
                external_account_id="acct-1",
                external_property_id="prop-1",
                status=status,
                secret_reference=f"ref-{uuid.uuid4().hex[:8]}",
                monetization_capability="RELATIVE_ONLY",
                scopes=[],
            )
        )


@pytest.mark.asyncio
async def test_home_status_and_source_health_healthy_and_isolated() -> None:

    client = TestClient(app)
    tenant_a, site_a = await _seed_tenant_site(slug="p2a-a")
    tenant_b, site_b = await _seed_tenant_site(slug="p2a-b")
    await _add_connection(tenant_a, site_a, status="CONNECTED")

    actor = uuid.uuid4()

    async def _fake_actor() -> None:
        return None

    del actor

    # Authenticate via the real auth boundary: seed an operator + membership.
    from app.auth.models import Operator, OperatorTenant
    from app.auth.security import hash_password

    factory = get_session_factory()
    operator_id = uuid.uuid4()
    email = f"home-{operator_id.hex[:8]}@example.com"
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
        session.add(OperatorTenant(operator_id=operator_id, tenant_id=tenant_a))
    login_response = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "tenant_id": str(tenant_a),
        },
    )
    assert login_response.status_code == 200
    cookies = dict(login_response.cookies)

    home = client.get("/product/home/status", cookies=cookies)
    assert home.status_code == 200
    body = home.json()
    assert body["open_incident_count"] == 0
    assert body["source_health"]["BROWSER_MONITORING"] == "HEALTHY"
    assert any(str(item["site_id"]) == str(site_a) for item in body["sites"])

    health = client.get(f"/product/source-health?site_id={site_a}", cookies=cookies)
    assert health.status_code == 200
    sources = health.json()["sources"]
    assert sources["BROWSER_MONITORING"] == "HEALTHY"
    assert sources["GA4"] in ("HEALTHY", "UNKNOWN")
    # Tenant B cannot see tenant A source state.
    other_health = client.get(f"/product/source-health?site_id={site_b}", cookies=cookies)
    assert other_health.status_code == 404


def test_degraded_source_health_does_not_become_publisher_site_failure() -> None:
    """Scenario #2: observation degradation stays at source level; the
    publisher/site condition is serialized independently and never derived
    from the degraded observation."""
    factory = get_session_factory()
    slug = f"p2a-degraded-{uuid.uuid4().hex[:8]}"
    tenant_id, site_id = asyncio.run(_seed_tenant_site(slug=slug))
    when = datetime.now(UTC) - timedelta(minutes=10)

    async def seed_degraded_run() -> None:
        from sqlalchemy import select

        window_id, run_id = uuid.uuid4(), uuid.uuid4()
        async with factory() as session, session.begin():
            template = await session.scalar(select(Template).where(Template.site_id == site_id))
            monitored_url = await session.scalar(
                select(MonitoredUrl).where(MonitoredUrl.site_id == site_id)
            )
            scenario = await session.scalar(
                select(BrowserScenario).where(BrowserScenario.site_id == site_id)
            )
            assert template is not None and monitored_url is not None and scenario is not None
            session.add(
                CheckpointWindow(
                    id=window_id,
                    tenant_id=tenant_id,
                    site_id=site_id,
                    scheduled_for=when,
                    window_start=when,
                    window_end=when + timedelta(minutes=30),
                )
            )
            await session.flush()
            # Canonical degraded observation: latest scheduled run PARTIAL.
            session.add(
                CheckpointRun(
                    id=run_id,
                    tenant_id=tenant_id,
                    site_id=site_id,
                    checkpoint_window_id=window_id,
                    monitored_url_id=monitored_url.id,
                    template_id=template.id,
                    scenario_id=scenario.id,
                    observation_kind="SCHEDULED",
                    scheduled_for=when,
                    started_at=when,
                    completed_at=when + timedelta(minutes=5),
                    status="PARTIAL",
                    attempt_count=1,
                    environment={},
                    limitations=["some_collectors_missing"],
                    manifest={},
                )
            )

    asyncio.run(seed_degraded_run())

    from app.auth.models import Operator, OperatorTenant
    from app.auth.security import hash_password

    email = f"deg-{uuid.uuid4().hex[:8]}@example.com"

    async def seed_operator() -> None:
        operator_id = uuid.uuid4()
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

    asyncio.run(seed_operator())

    client = TestClient(app)
    login_response = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "tenant_id": str(tenant_id),
        },
    )
    assert login_response.status_code == 200
    cookies = dict(login_response.cookies)

    home = client.get("/product/home/status", cookies=cookies)
    assert home.status_code == 200
    body = home.json()

    # Source level reports the degraded observation.
    assert body["source_health"]["BROWSER_MONITORING"] == "DEGRADED"
    # Publisher/site condition is independent: it does NOT inherit DEGRADED.
    assert body["publisher_site_condition"] != "DEGRADED"

    health = client.get(f"/product/source-health?site_id={site_id}", cookies=cookies)
    assert health.status_code == 200
    sources = health.json()["sources"]
    assert sources["BROWSER_MONITORING"] == "DEGRADED"
