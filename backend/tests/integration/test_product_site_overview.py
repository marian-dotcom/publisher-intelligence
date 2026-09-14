"""EP-031 M1: read-only per-site overview projection (data + authenticated API).

Integration coverage for the GET /product/sites/{site_id}/overview boundary:
- the full payload contract with byte-compatible reuse of the home/source-health
  projections (monitoring, initial_diagnostic, source_health, detail);
- cohort purity: latest_scheduled_run is SCHEDULED-only and excludes SKIPPED;
  initial_diagnostic is DIAGNOSTIC/OPERATOR_UI-only and excludes SCHEDULED;
- recent_runs lists newest five across all kinds incl. SKIPPED with limitations;
- recent_activity reuses the exact /timeline serializer and stays site-scoped;
- open_incidents are site-scoped OPEN/INVESTIGATING;
- cross-tenant/nonexistent sites return a non-disclosing 404; OPERATOR can read;
- empty sites render null/empty fields without a 5xx;
- the CheckpointStatus literal includes SKIPPED (typing-drift regression).
"""

import asyncio
import typing
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.models import Operator, OperatorTenant
from app.auth.security import hash_password
from app.browser import contracts
from app.browser.models import (
    BrowserScenario,
    CheckpointRun,
    CheckpointWindow,
    MonitoredUrl,
    Publisher,
    Site,
    Template,
)
from app.db.models import Tenant
from app.db.session import get_session_factory
from app.events.models import Event
from app.events.registry import definition_id
from app.evidence.models import ManualNote
from app.incidents.models import Incident
from app.main import app
from tests.integration.purge import make_purge

pytestmark = pytest.mark.integration

PASSWORD = "overview-password"
OVERVIEW_URL = "/product/sites/{site_id}/overview"


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
    email = f"overview-admin-{operator_id.hex[:8]}@example.com"
    async with factory() as session, session.begin():
        session.add(Tenant(id=tenant_id, slug=f"ovw-t-{tenant_id.hex[:8]}", name="EP-031"))
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


def _login(
    client: TestClient, *, email: str, password: str = PASSWORD, tenant_id: uuid.UUID
) -> tuple[str, dict[str, str]]:
    response = client.post(
        "/auth/login",
        json={"email": email, "password": password, "tenant_id": str(tenant_id)},
    )
    assert response.status_code == 200
    return response.json()["csrf_token"], dict(response.cookies)


async def _seed_site(
    tenant_id: uuid.UUID,
    *,
    monitoring_state: str = "OFF",
    monitoring_state_updated_at: datetime | None = None,
) -> tuple[uuid.UUID, str]:
    """One publisher + site; returns (site_id, publisher_name)."""
    factory = get_session_factory()
    publisher_id, site_id = uuid.uuid4(), uuid.uuid4()
    publisher_name = f"Publisher {site_id.hex[:8]}"
    async with factory() as session, session.begin():
        session.add(
            Publisher(
                id=publisher_id,
                tenant_id=tenant_id,
                name=publisher_name,
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
                name=f"Site {site_id.hex[:8]}",
                canonical_domain=f"{site_id.hex}.example.test",
                canonical_scheme="https",
                timezone="UTC",
                status="ACTIVE",
                monitoring_state=monitoring_state,
                monitoring_state_updated_at=(monitoring_state_updated_at or datetime.now(UTC)),
            )
        )
    return site_id, publisher_name


async def _add_run(
    tenant_id: uuid.UUID,
    site_id: uuid.UUID,
    *,
    created_at: datetime,
    observation_kind: str = "SCHEDULED",
    status: str = "COMPLETE",
    limitations: list[str] | None = None,
    browser_access_classification: dict[str, object] | None = None,
) -> uuid.UUID:
    """Canonical window/url/template/scenario chain plus one checkpoint run."""
    factory = get_session_factory()
    run_id = uuid.uuid4()
    window_id, url_id, template_id, scenario_id = (uuid.uuid4() for _ in range(4))
    async with factory() as session, session.begin():
        session.add(
            Template(
                id=template_id,
                tenant_id=tenant_id,
                site_id=site_id,
                code=f"ovw-{template_id.hex[:10]}",
                display_name="Overview",
                status="ACTIVE",
            )
        )
        await session.flush()
        session.add(
            MonitoredUrl(
                id=url_id,
                tenant_id=tenant_id,
                site_id=site_id,
                template_id=template_id,
                url=f"https://{site_id.hex}.example.test/{url_id.hex[:8]}",
                status="ACTIVE",
            )
        )
        session.add(
            BrowserScenario(
                id=scenario_id,
                tenant_id=tenant_id,
                site_id=site_id,
                code=f"ovw-{scenario_id.hex[:10]}",
                version=1,
                status="ACTIVE",
            )
        )
        session.add(
            CheckpointWindow(
                id=window_id,
                tenant_id=tenant_id,
                site_id=site_id,
                scheduled_for=created_at,
                window_start=created_at,
                window_end=created_at + timedelta(minutes=30),
            )
        )
        await session.flush()
        kwargs: dict[str, object] = {
            "id": run_id,
            "tenant_id": tenant_id,
            "site_id": site_id,
            "checkpoint_window_id": window_id,
            "monitored_url_id": url_id,
            "template_id": template_id,
            "scenario_id": scenario_id,
            "observation_kind": observation_kind,
            "scheduled_for": created_at,
            "started_at": created_at,
            "completed_at": created_at + timedelta(minutes=5),
            "status": status,
            "attempt_count": 1,
            "collector_bundle_version": "b8-v1",
            "environment": {},
            "limitations": limitations or [],
            "manifest": {},
            "created_at": created_at,
        }
        if observation_kind != "SCHEDULED":
            kwargs["trigger_source"] = "OPERATOR_UI"
            kwargs["trigger_correlation_id"] = uuid.uuid4()
        if browser_access_classification is not None:
            kwargs["browser_access_classification"] = browser_access_classification
        session.add(CheckpointRun(**kwargs))
    return run_id


async def _add_event(
    tenant_id: uuid.UUID, site_id: uuid.UUID, *, detected_at: datetime
) -> uuid.UUID:
    factory = get_session_factory()
    event_id = uuid.uuid4()
    async with factory() as session, session.begin():
        session.add(
            Event(
                id=event_id,
                tenant_id=tenant_id,
                site_id=site_id,
                event_definition_id=definition_id("NOINDEX_ADDED"),
                template_id=None,
                started_at=detected_at,
                occurred_after_at=None,
                occurred_before_at=detected_at,
                time_precision="EXACT",
                detected_at=detected_at,
                severity="MEDIUM",
                observation_confidence="HIGH",
                status="RECORDED",
                source_kind="BROWSER_CHECKPOINT",
                source_version="e3-v1",
                condition_key=None,
                scope={"config_type": "ROBOTS_TXT"},
                summary="Overview fixture event",
                details={},
            )
        )
    return event_id


async def _add_note(tenant_id: uuid.UUID, site_id: uuid.UUID, *, created_at: datetime) -> uuid.UUID:
    factory = get_session_factory()
    note_id = uuid.uuid4()
    async with factory() as session, session.begin():
        session.add(
            ManualNote(
                id=note_id,
                tenant_id=tenant_id,
                site_id=site_id,
                incident_id=None,
                note_type="OPERATOR_INTERVENTION",
                note_text="Overview fixture note",
                created_at=created_at,
                source="operator",
            )
        )
    return note_id


async def _add_incident(
    tenant_id: uuid.UUID,
    site_id: uuid.UUID,
    *,
    status: str = "OPEN",
    opened_at: datetime | None = None,
) -> uuid.UUID:
    factory = get_session_factory()
    incident_id = uuid.uuid4()
    async with factory() as session, session.begin():
        site = await session.scalar(select(Site.publisher_id).where(Site.id == site_id))
        assert site is not None
        session.add(
            Incident(
                id=incident_id,
                tenant_id=tenant_id,
                publisher_id=site,
                site_id=site_id,
                title="Overview OPEN incident",
                symptom_family="BROWSER_PERFORMANCE",
                description="Overview fixture incident",
                reported_start_at=opened_at or datetime.now(UTC) - timedelta(hours=2),
                reported_end_at=None,
                opened_at=opened_at or datetime.now(UTC),
                status=status,
                severity="MEDIUM",
            )
        )
    return incident_id


@pytest.mark.asyncio
async def test_happy_path_full_payload(
    admin_and_tenant: tuple[uuid.UUID, uuid.UUID, str],
) -> None:
    _operator_id, tenant_id, email = admin_and_tenant
    site_id, publisher_name = await _seed_site(
        tenant_id,
        monitoring_state="ON",
        monitoring_state_updated_at=datetime(2026, 9, 1, 7, 0, tzinfo=UTC),
    )
    now = datetime.now(UTC) - timedelta(hours=1)
    diagnostic_id = await _add_run(
        tenant_id,
        site_id,
        created_at=now,
        observation_kind="DIAGNOSTIC",
        status="COMPLETE",
        browser_access_classification={"state": "ok", "reason": "normal access"},
    )
    scheduled_id = await _add_run(
        tenant_id,
        site_id,
        created_at=now - timedelta(hours=6),
        observation_kind="SCHEDULED",
        status="COMPLETE",
    )
    incident_id = await _add_incident(tenant_id, site_id)
    await _add_event(tenant_id, site_id, detected_at=now - timedelta(minutes=30))

    client = TestClient(app)
    _csrf, cookies = _login(client, email=email, tenant_id=tenant_id)
    response = client.get(OVERVIEW_URL.format(site_id=site_id), cookies=cookies)
    assert response.status_code == 200
    body = response.json()

    site_block = body["site"]
    assert site_block["site_id"] == str(site_id)
    assert site_block["canonical_scheme"] == "https"
    assert site_block["url"] == f"https://{site_id.hex}.example.test"
    assert site_block["publisher_name"] == publisher_name
    assert site_block["status"] == "ACTIVE"
    assert site_block["timezone"] == "UTC"

    monitoring = body["monitoring"]
    assert monitoring["enabled"] is True
    assert monitoring["cadence"] == {"identifier": "six-hour", "hours": 6}
    assert monitoring["in_flight_scheduled_run_status"] is None
    assert monitoring["next_scheduled_for"] == "2026-09-01T12:00:00+00:00"

    initial = body["initial_diagnostic"]
    assert initial is not None
    assert initial["run_id"] == str(diagnostic_id)
    assert initial["status"] == "COMPLETE"
    assert initial["browser_access_classification"] == "ok"

    latest = body["latest_scheduled_run"]
    assert latest is not None
    assert latest["run_id"] == str(scheduled_id)
    assert latest["status"] == "COMPLETE"

    assert set(body["source_health"]) == {
        "BROWSER_MONITORING",
        "GA4",
        "GSC",
        "GAM",
        "PUBLIC_CONFIG",
    }
    assert body["browser_monitoring_detail"] is None

    assert body["open_incidents"] == [
        {
            "incident_id": str(incident_id),
            "title": "Overview OPEN incident",
            "symptom_family": "BROWSER_PERFORMANCE",
            "status": "OPEN",
            "severity": "MEDIUM",
            "reported_start_at": body["open_incidents"][0]["reported_start_at"],
            "reported_end_at": None,
            "opened_at": body["open_incidents"][0]["opened_at"],
            "site_id": str(site_id),
        }
    ]

    run_ids = [r["run_id"] for r in body["recent_runs"]]
    assert run_ids == [str(diagnostic_id), str(scheduled_id)]

    assert len(body["recent_activity"]) == 1
    activity_entry = body["recent_activity"][0]
    assert activity_entry["provenance"] == "machine_observed"
    assert activity_entry["event_id"]
    assert activity_entry["site_id"] == str(site_id)


@pytest.mark.asyncio
async def test_cohort_purity_skipped_and_diagnostic_excluded(
    admin_and_tenant: tuple[uuid.UUID, uuid.UUID, str],
) -> None:
    """latest_scheduled_run excludes DIAGNOSTIC and SKIPPED; initial_diagnostic
    excludes SCHEDULED."""
    _operator_id, tenant_id, email = admin_and_tenant
    site_id, _publisher_name = await _seed_site(tenant_id)
    now = datetime.now(UTC)
    scheduled_id = await _add_run(
        tenant_id, site_id, created_at=now - timedelta(hours=12), status="COMPLETE"
    )
    diagnostic_id = await _add_run(
        tenant_id,
        site_id,
        created_at=now - timedelta(hours=6),
        observation_kind="DIAGNOSTIC",
        status="COMPLETE",
    )
    skipped_id = await _add_run(
        tenant_id,
        site_id,
        created_at=now - timedelta(hours=1),
        status="SKIPPED",
        limitations=["monitoring-disabled-before-execution"],
    )

    client = TestClient(app)
    _csrf, cookies = _login(client, email=email, tenant_id=tenant_id)
    body = client.get(OVERVIEW_URL.format(site_id=site_id), cookies=cookies).json()

    assert body["latest_scheduled_run"]["run_id"] == str(scheduled_id)
    assert body["latest_scheduled_run"]["status"] == "COMPLETE"
    assert body["initial_diagnostic"]["run_id"] == str(diagnostic_id)

    recent = body["recent_runs"]
    assert [r["run_id"] for r in recent] == [
        str(skipped_id),
        str(diagnostic_id),
        str(scheduled_id),
    ]
    assert recent[0]["status"] == "SKIPPED"
    assert recent[0]["observation_kind"] == "SCHEDULED"
    assert recent[0]["limitations"] == ["monitoring-disabled-before-execution"]


@pytest.mark.asyncio
async def test_recent_runs_limit_five_newest(
    admin_and_tenant: tuple[uuid.UUID, uuid.UUID, str],
) -> None:
    _operator_id, tenant_id, email = admin_and_tenant
    site_id, _publisher_name = await _seed_site(tenant_id)
    now = datetime.now(UTC)
    old_run_id = None
    for index in range(6):
        old_run_id = await _add_run(
            tenant_id,
            site_id,
            created_at=now - timedelta(hours=index * 2 + 1),
            status="COMPLETE",
        )
    assert old_run_id is not None

    client = TestClient(app)
    _csrf, cookies = _login(client, email=email, tenant_id=tenant_id)
    recent = client.get(OVERVIEW_URL.format(site_id=site_id), cookies=cookies).json()["recent_runs"]
    assert len(recent) == 5
    assert old_run_id not in [uuid.UUID(r["run_id"]) for r in recent]
    statuses_since = [r["status"] for r in recent]
    assert statuses_since == ["COMPLETE"] * 5


@pytest.mark.asyncio
async def test_open_incidents_site_scoped(
    admin_and_tenant: tuple[uuid.UUID, uuid.UUID, str],
) -> None:
    _operator_id, tenant_id, email = admin_and_tenant
    site_a, _ = await _seed_site(tenant_id)
    site_b, _ = await _seed_site(tenant_id)
    incident_a = await _add_incident(tenant_id, site_a)
    await _add_incident(tenant_id, site_b)
    await _add_incident(tenant_id, site_b, status="RESOLVED")

    client = TestClient(app)
    _csrf, cookies = _login(client, email=email, tenant_id=tenant_id)
    body_a = client.get(OVERVIEW_URL.format(site_id=site_a), cookies=cookies).json()
    body_b = client.get(OVERVIEW_URL.format(site_id=site_b), cookies=cookies).json()

    assert [i["incident_id"] for i in body_a["open_incidents"]] == [str(incident_a)]
    for incident in body_a["open_incidents"]:
        assert incident["site_id"] == str(site_a)
    assert len(body_b["open_incidents"]) == 1
    assert body_b["open_incidents"][0]["site_id"] == str(site_b)
    assert body_b["open_incidents"][0]["status"] == "OPEN"
    assert "RESOLVED" not in [i["status"] for i in body_b["open_incidents"]]


@pytest.mark.asyncio
async def test_recent_activity_reuses_timeline_serializer_and_is_site_scoped(
    admin_and_tenant: tuple[uuid.UUID, uuid.UUID, str],
) -> None:
    _operator_id, tenant_id, email = admin_and_tenant
    site_a, _ = await _seed_site(tenant_id)
    site_b, _ = await _seed_site(tenant_id)
    t1 = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    t2 = datetime(2026, 9, 1, 13, 0, tzinfo=UTC)
    t3 = datetime(2026, 9, 1, 14, 0, tzinfo=UTC)
    await _add_event(tenant_id, site_b, detected_at=t3)
    await _add_note(tenant_id, site_a, created_at=t1)
    note_a = await _add_note(tenant_id, site_a, created_at=t3)
    await _add_event(tenant_id, site_a, detected_at=t2)
    await _add_event(tenant_id, site_a, detected_at=t1)

    client = TestClient(app)
    _csrf, cookies = _login(client, email=email, tenant_id=tenant_id)

    timeline = client.get(f"/timeline?site_id={site_a}", cookies=cookies).json()["entries"]
    body = client.get(OVERVIEW_URL.format(site_id=site_a), cookies=cookies).json()
    recent = body["recent_activity"]

    assert len(recent) == 4
    recent_ids = [(entry.get("event_id") or entry.get("note_id")) for entry in recent]
    timeline_ids = [(entry.get("event_id") or entry.get("note_id")) for entry in timeline]
    assert set(recent_ids) == set(timeline_ids)
    for entry in recent:
        assert entry in timeline
    expected = sorted(recent, key=lambda e: e["observed_at"], reverse=True)
    assert recent == expected
    assert body["recent_activity"][0].get("note_id") == str(note_a)


@pytest.mark.asyncio
async def test_tenant_boundary_and_nonexistent_are_non_disclosing_404(
    admin_and_tenant: tuple[uuid.UUID, uuid.UUID, str],
) -> None:
    _operator_id, tenant_id, email = admin_and_tenant
    other_tenant_id = uuid.uuid4()
    factory = get_session_factory()
    async with factory() as session, session.begin():
        session.add(
            Tenant(id=other_tenant_id, slug=f"ovw-other-{other_tenant_id.hex[:8]}", name="Other")
        )
    foreign_site_id, _ = await _seed_site(other_tenant_id)
    missing_site_id = uuid.uuid4()
    client = TestClient(app)
    _csrf, cookies = _login(client, email=email, tenant_id=tenant_id)

    foreign = client.get(OVERVIEW_URL.format(site_id=foreign_site_id), cookies=cookies)
    missing = client.get(OVERVIEW_URL.format(site_id=missing_site_id), cookies=cookies)
    assert foreign.status_code == 404
    assert missing.status_code == 404
    assert foreign.json() == missing.json() == {"detail": "resource not found"}


@pytest.mark.asyncio
async def test_operator_can_read_and_off_renders_null_boundary(
    admin_and_tenant: tuple[uuid.UUID, uuid.UUID, str],
) -> None:
    _admin_id, tenant_id, _email = admin_and_tenant
    site_id, _ = await _seed_site(tenant_id)
    factory = get_session_factory()
    member_id = uuid.uuid4()
    member_email = f"overview-member-{member_id.hex[:8]}@example.com"
    async with factory() as session, session.begin():
        session.add(
            Operator(
                id=member_id,
                actor_subject_id=uuid.uuid4(),
                email=member_email,
                password_hash=hash_password(PASSWORD),
                role="OPERATOR",
                is_active=True,
            )
        )
        session.add(OperatorTenant(operator_id=member_id, tenant_id=tenant_id))

    client = TestClient(app)
    _csrf, cookies = _login(client, email=member_email, tenant_id=tenant_id)
    response = client.get(OVERVIEW_URL.format(site_id=site_id), cookies=cookies)
    assert response.status_code == 200
    monitoring = response.json()["monitoring"]
    assert monitoring["enabled"] is False
    assert monitoring["next_scheduled_for"] is None


@pytest.mark.asyncio
async def test_empty_site_renders_null_empty_no_five_xx(
    admin_and_tenant: tuple[uuid.UUID, uuid.UUID, str],
) -> None:
    _operator_id, tenant_id, email = admin_and_tenant
    site_id, _ = await _seed_site(tenant_id)
    client = TestClient(app)
    _csrf, cookies = _login(client, email=email, tenant_id=tenant_id)
    response = client.get(OVERVIEW_URL.format(site_id=site_id), cookies=cookies)
    assert response.status_code == 200
    body = response.json()
    assert body["initial_diagnostic"] is None
    assert body["latest_scheduled_run"] is None
    assert body["browser_monitoring_detail"] is None
    assert body["open_incidents"] == []
    assert body["recent_runs"] == []
    assert body["recent_activity"] == []
    assert body["monitoring"]["enabled"] is False
    assert all("UNKNOWN" in sources for sources in [list(body["source_health"].values())])
    assert set(body["source_health"].values()) == {"UNKNOWN"}


@pytest.mark.asyncio
async def test_checkpoint_status_literal_includes_skipped() -> None:
    statuses = typing.get_args(contracts.CheckpointStatus)
    assert "SKIPPED" in statuses
    assert "COMPLETE" in statuses
