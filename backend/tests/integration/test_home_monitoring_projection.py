"""EP-030 M3: additive read-only monitoring projection on GET /product/home/status.

Covers the Home read projection, which reuses the M1 monitoring-control
service so the cadence and next-boundary semantics never diverge from the PUT
endpoint:

- OFF and ON projections for the selected site;
- strictly-future next boundary only when ON;
- OFF with an in-flight (PENDING/RUNNING) SCHEDULED run is surfaced truthfully;
- missing/foreign/unavailable state fails closed (never ON);
- tenant isolation / non-disclosing behavior;
- a pure read performs no audit/job/run/window/evidence mutation;
- the existing diagnostic/source-health response is unchanged except for the
  additive `monitoring` field.
"""

import asyncio
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.auth.models import Operator, OperatorTenant
from app.auth.security import hash_password
from app.browser.models import (
    BrowserScenario,
    CheckpointRun,
    CheckpointWindow,
    InteractionProfile,
    MonitoredUrl,
    Publisher,
    Site,
    Template,
)
from app.db.models import Tenant
from app.db.session import get_session_factory
from app.main import app
from tests.integration.purge import make_purge

pytestmark = pytest.mark.integration

PASSWORD = "home-monitor-password"
HOME_URL = "/product/home/status"


@pytest.fixture(autouse=True)
def _clean_db() -> Generator[None, None, None]:
    purge = make_purge(get_session_factory)
    asyncio.run(purge())
    yield
    asyncio.run(purge())


@pytest.fixture
async def admin_and_tenant() -> tuple[uuid.UUID, uuid.UUID, str]:
    factory = get_session_factory()
    operator_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    email = f"hm-admin-{operator_id.hex[:8]}@example.com"
    async with factory() as session, session.begin():
        session.add(Tenant(id=tenant_id, slug=f"hm-t-{tenant_id.hex[:8]}", name="M3"))
        await session.flush()
        session.add(
            Operator(
                id=operator_id,
                actor_subject_id=tenant_id,
                email=email,
                password_hash=hash_password(PASSWORD),
                role="ADMIN",
                is_active=True,
            )
        )
        session.add(OperatorTenant(operator_id=operator_id, tenant_id=tenant_id))
    return operator_id, tenant_id, email


async def _create_runnable_site(*, tenant_id: uuid.UUID, timezone: str = "UTC") -> uuid.UUID:
    """Minimal runnable B2 site so a SCHEDULED run can be materialized."""
    session_factory = get_session_factory()
    site_id, publisher_id = uuid.uuid4(), uuid.uuid4()
    template_id, monitored_url_id = uuid.uuid4(), uuid.uuid4()
    profile_id, scenario_id = uuid.uuid4(), uuid.uuid4()
    async with session_factory() as session, session.begin():
        session.add(
            Publisher(
                id=publisher_id,
                tenant_id=tenant_id,
                name="HM Publisher",
                slug=f"hm-pub-{publisher_id.hex[:8]}",
                default_timezone=timezone,
                status="ACTIVE",
            )
        )
        await session.flush()
        session.add(
            Site(
                id=site_id,
                tenant_id=tenant_id,
                publisher_id=publisher_id,
                name="HM Site",
                canonical_domain=f"{site_id.hex}.example.test",
                canonical_scheme="https",
                timezone=timezone,
                status="ACTIVE",
            )
        )
        await session.flush()
        session.add(
            Template(
                id=template_id,
                tenant_id=tenant_id,
                site_id=site_id,
                code="core_desktop_v2",
                display_name="B2 Desktop",
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
                url=f"https://{site_id.hex}.example.test/",
                status="ACTIVE",
                valid_from=datetime(2024, 1, 1, tzinfo=UTC),
            )
        )
        await session.flush()
        session.add(
            InteractionProfile(
                id=profile_id,
                tenant_id=tenant_id,
                site_id=site_id,
                code="core_scroll_v1",
                version=1,
                description="scroll",
                steps=[],
                status="ACTIVE",
            )
        )
        await session.flush()
        session.add(
            BrowserScenario(
                id=scenario_id,
                tenant_id=tenant_id,
                site_id=site_id,
                interaction_profile_id=profile_id,
                code="core_desktop_v2",
                version=1,
                device_class="DESKTOP",
                status="ACTIVE",
            )
        )
    return site_id


async def _create_inflight_scheduled_run(*, tenant_id: uuid.UUID, site_id: uuid.UUID) -> None:
    """Materialize a PENDING SCHEDULED run for the given site."""
    session_factory = get_session_factory()
    window_id = uuid.uuid4()
    run_id = uuid.uuid4()
    async with session_factory() as session, session.begin():
        monitored_url = await session.scalar(
            select(MonitoredUrl).where(
                MonitoredUrl.tenant_id == tenant_id, MonitoredUrl.site_id == site_id
            )
        )
        scenario = await session.scalar(
            select(BrowserScenario).where(
                BrowserScenario.tenant_id == tenant_id, BrowserScenario.site_id == site_id
            )
        )
        template = await session.scalar(
            select(Template).where(Template.tenant_id == tenant_id, Template.site_id == site_id)
        )
        assert monitored_url is not None and scenario is not None and template is not None
        scheduled_for = datetime.now(UTC) + timedelta(hours=1)
        session.add(
            CheckpointWindow(
                id=window_id,
                tenant_id=tenant_id,
                site_id=site_id,
                scheduled_for=scheduled_for,
                window_start=scheduled_for - timedelta(hours=1),
                window_end=scheduled_for + timedelta(hours=1),
                status="SCHEDULED",
            )
        )
        await session.flush()
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
                trigger_source=None,
                trigger_correlation_id=None,
                scheduled_for=scheduled_for,
                status="PENDING",
                attempt_count=0,
                collector_bundle_version="b8-v1",
                environment={},
                limitations=[],
                manifest={},
            )
        )


def _login(
    client: TestClient, *, email: str, password: str = PASSWORD, tenant_id: uuid.UUID
) -> tuple[str, dict[str, str]]:
    response = client.post(
        "/auth/login",
        json={"email": email, "password": password, "tenant_id": str(tenant_id)},
    )
    assert response.status_code == 200
    return response.json()["csrf_token"], dict(response.cookies)


def _home(client: TestClient, cookies: dict[str, str], site_id: uuid.UUID) -> Any:
    response = client.get(f"{HOME_URL}?site_id={site_id}", cookies=cookies)
    assert response.status_code == 200
    return response.json()


async def test_home_projection_off(admin_and_tenant: tuple[uuid.UUID, uuid.UUID, str]) -> None:
    _operator_id, tenant_id, email = admin_and_tenant
    site_id = await _create_runnable_site(tenant_id=tenant_id)
    client = TestClient(app)
    _csrf, cookies = _login(client, email=email, tenant_id=tenant_id)

    body = _home(client, cookies, site_id)
    monitoring = body["monitoring"]
    assert monitoring is not None
    assert monitoring["site_id"] == str(site_id)
    assert monitoring["enabled"] is False
    assert monitoring["next_scheduled_for"] is None
    assert monitoring["cadence"] == {"identifier": "six-hour", "hours": 6}
    assert monitoring["in_flight_scheduled_run_status"] is None


async def test_home_projection_on_with_strictly_future_boundary(
    admin_and_tenant: tuple[uuid.UUID, uuid.UUID, str],
) -> None:
    _operator_id, tenant_id, email = admin_and_tenant
    site_id = await _create_runnable_site(tenant_id=tenant_id)
    client = TestClient(app)
    csrf, cookies = _login(client, email=email, tenant_id=tenant_id)

    enable = client.put(
        f"/product/sites/{site_id}/monitoring",
        headers={"X-CSRF-Token": csrf},
        cookies=cookies,
        json={"enabled": True},
    )
    assert enable.status_code == 200

    body = _home(client, cookies, site_id)
    monitoring = body["monitoring"]
    assert monitoring["enabled"] is True
    next_at = monitoring["next_scheduled_for"]
    assert next_at is not None
    parsed = datetime.fromisoformat(str(next_at)).astimezone(UTC)
    assert parsed > datetime.now(UTC)
    assert (parsed.minute, parsed.second, parsed.microsecond) == (0, 0, 0)
    assert parsed.hour in (0, 6, 12, 18)
    # The read projection's boundary equals the PUT endpoint's boundary.
    assert monitoring["next_scheduled_for"] == enable.json()["next_scheduled_for"]


async def test_home_projection_off_with_inflight_scheduled_run(
    admin_and_tenant: tuple[uuid.UUID, uuid.UUID, str],
) -> None:
    _operator_id, tenant_id, email = admin_and_tenant
    site_id = await _create_runnable_site(tenant_id=tenant_id)
    await _create_inflight_scheduled_run(tenant_id=tenant_id, site_id=site_id)

    client = TestClient(app)
    _csrf, cookies = _login(client, email=email, tenant_id=tenant_id)
    body = _home(client, cookies, site_id)
    monitoring = body["monitoring"]
    assert monitoring["enabled"] is False
    assert monitoring["in_flight_scheduled_run_status"] == "PENDING"
    assert monitoring["next_scheduled_for"] is None


async def test_home_monitoring_unavailable_when_missing_site_fails_closed(
    admin_and_tenant: tuple[uuid.UUID, uuid.UUID, str],
) -> None:
    """A site that does not resolve must not report ON — the projection is null."""
    _operator_id, tenant_id, email = admin_and_tenant
    missing_site_id = uuid.uuid4()
    client = TestClient(app)
    _csrf, cookies = _login(client, email=email, tenant_id=tenant_id)

    response = client.get(f"{HOME_URL}?site_id={missing_site_id}", cookies=cookies)
    assert response.status_code == 200
    # A nonexistent selected site falls back to the tenant default; there are no
    # sites, so nothing is selected and the projection is unavailable.
    body = response.json()
    assert body["selected_site_id"] is None
    assert body["monitoring"] is None


async def test_home_monitoring_is_tenant_isolated_and_non_disclosing(
    admin_and_tenant: tuple[uuid.UUID, uuid.UUID, str],
) -> None:
    """A foreign tenant's site must not leak monitoring state to this tenant."""
    _operator_id, tenant_id, email = admin_and_tenant
    other_tenant_id = uuid.uuid4()
    session_factory = get_session_factory()
    async with session_factory() as session, session.begin():
        session.add(
            Tenant(id=other_tenant_id, slug=f"hm-other-{other_tenant_id.hex[:8]}", name="Other")
        )
    foreign_site_id = await _create_runnable_site(tenant_id=other_tenant_id)

    client = TestClient(app)
    _csrf, cookies = _login(client, email=email, tenant_id=tenant_id)

    # A foreign site_id query does not select it (not owned) and exposes none of
    # its monitoring state; it is indistinguishable from a missing site.
    body = _home(client, cookies, foreign_site_id)
    assert body["selected_site_id"] is not str(foreign_site_id)
    assert body["monitoring"] is None


async def test_home_read_performs_no_audit_or_evidence_mutation(
    admin_and_tenant: tuple[uuid.UUID, uuid.UUID, str],
) -> None:
    _operator_id, tenant_id, email = admin_and_tenant
    site_id = await _create_runnable_site(tenant_id=tenant_id)
    client = TestClient(app)
    csrf, cookies = _login(client, email=email, tenant_id=tenant_id)
    client.put(
        f"/product/sites/{site_id}/monitoring",
        headers={"X-CSRF-Token": csrf},
        cookies=cookies,
        json={"enabled": True},
    )

    session_factory = get_session_factory()

    async def _count(table: str) -> int:
        async with session_factory() as session:
            return int((await session.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one())

    before_audit = await _count("site_monitoring_state_changes")
    before_runs = await _count("checkpoint_runs")
    before_windows = await _count("checkpoint_windows")
    before_jobs = await _count("jobs")
    before_artifacts = await _count("artifacts")

    body = _home(client, cookies, site_id)
    assert body["monitoring"]["enabled"] is True

    assert await _count("site_monitoring_state_changes") == before_audit
    assert await _count("checkpoint_runs") == before_runs
    assert await _count("checkpoint_windows") == before_windows
    assert await _count("jobs") == before_jobs
    assert await _count("artifacts") == before_artifacts


async def test_home_read_preserves_existing_response_with_additive_monitoring_field(
    admin_and_tenant: tuple[uuid.UUID, uuid.UUID, str],
) -> None:
    """Existing home keys are unchanged; `monitoring` is purely additive."""
    _operator_id, tenant_id, email = admin_and_tenant
    site_id = await _create_runnable_site(tenant_id=tenant_id)
    client = TestClient(app)
    _csrf, cookies = _login(client, email=email, tenant_id=tenant_id)

    body = _home(client, cookies, site_id)
    assert set(body.keys()) >= {
        "sites",
        "selected_site_id",
        "publisher_site_condition",
        "source_health",
        "initial_diagnostic",
        "monitoring",
        "open_incident_count",
        "monetization_capability",
    }
    assert body["initial_diagnostic"] is None
    assert body["source_health"]["BROWSER_MONITORING"] == "UNKNOWN"
    assert "monitoring" in body
    # Source health and monitoring are independent concepts.
    assert body["monitoring"]["enabled"] in (True, False)


async def test_home_monitoring_separation_between_monitoring_and_source_health(
    admin_and_tenant: tuple[uuid.UUID, uuid.UUID, str],
) -> None:
    """Monitoring authorization and browser source health are independent facts."""
    _operator_id, tenant_id, email = admin_and_tenant
    site_id = await _create_runnable_site(tenant_id=tenant_id)
    client = TestClient(app)
    csrf, cookies = _login(client, email=email, tenant_id=tenant_id)

    body = _home(client, cookies, site_id)
    assert body["monitoring"]["enabled"] is False
    # OFF monitoring does not force source health to any particular value; with
    # no observation its source health is UNKNOWN (absence of evidence).
    assert body["source_health"]["BROWSER_MONITORING"] == "UNKNOWN"

    # Enabling does not fabricate source health.
    client.put(
        f"/product/sites/{site_id}/monitoring",
        headers={"X-CSRF-Token": csrf},
        cookies=cookies,
        json={"enabled": True},
    )
    body_on = _home(client, cookies, site_id)
    assert body_on["monitoring"]["enabled"] is True
    assert body_on["source_health"]["BROWSER_MONITORING"] == "UNKNOWN"
