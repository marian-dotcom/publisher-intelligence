"""EP-025a P2-B Incidents: I1/I2 — incident read contracts."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

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
from app.incidents.models import Incident, LastKnownGoodRef
from app.main import app
from tests.integration.product.factories import (
    create_incident,
    create_operator,
    create_site,
    create_tenant,
)
from tests.integration.purge import make_purge

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _clean_db() -> None:
    asyncio.run(make_purge(get_session_factory)())


from app.db.session import get_session_factory  # noqa: E402


def _login(client: TestClient, email: str, tenant_id: uuid.UUID) -> object:
    return client.post(
        "/auth/login",
        json={"email": email, "password": "correct-horse-battery", "tenant_id": str(tenant_id)},
    )


def test_i1_authenticated_tenant_can_list_own_incidents() -> None:
    """I1: authenticated tenant can list its own incidents."""
    get_session_factory()

    async def seed() -> tuple[uuid.UUID, uuid.UUID, str]:
        slug = f"i1-{uuid.uuid4().hex[:8]}"
        tenant_id = await create_tenant(slug)
        site_id = await create_site(tenant_id)
        incident_id = await create_incident(tenant_id, site_id, title="Revenue dropped on mobile")
        _operator_id, email = await create_operator(tenant_id, f"op-{slug}@example.com")
        return tenant_id, incident_id, email

    tenant_id, incident_id, email = asyncio.run(seed())

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

    response = client.get("/incidents", cookies=cookies)
    assert response.status_code == 200
    incidents = response.json()["incidents"]
    assert len(incidents) == 1

    inc = incidents[0]
    assert inc["incident_id"] == str(incident_id)
    assert inc["title"] == "Revenue dropped on mobile"
    assert inc["symptom_family"] == "GAM_ADSERVING"
    assert inc["status"] == "OPEN"


def test_i2_tenant_a_incident_list_excludes_tenant_b_incidents() -> None:
    """I2: tenant A incident list excludes tenant B incidents server-side."""
    factory = get_session_factory()

    async def seed_two_tenants() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, str]:
        slug_a = f"i2a-{uuid.uuid4().hex[:8]}"
        slug_b = f"i2b-{uuid.uuid4().hex[:8]}"

        # Tenant A: publisher + site + incident.
        tenant_a_id = uuid.uuid4()
        pub_a = uuid.uuid4()
        site_a = uuid.uuid4()
        incident_a = uuid.uuid4()
        async with factory() as session, session.begin():
            session.add(Tenant(id=tenant_a_id, slug=slug_a, name=f"T {slug_a}"))
            await session.flush()
            session.add(
                Publisher(
                    id=pub_a,
                    tenant_id=tenant_a_id,
                    name=f"P {slug_a}",
                    slug=f"pub-{pub_a.hex[:8]}",
                    default_timezone="UTC",
                    status="ACTIVE",
                )
            )
            await session.flush()
            session.add(
                Site(
                    id=site_a,
                    tenant_id=tenant_a_id,
                    publisher_id=pub_a,
                    name=f"S {slug_a}",
                    canonical_domain=f"{site_a.hex}.example.com",
                    canonical_scheme="https",
                    timezone="UTC",
                    status="ACTIVE",
                )
            )
            await session.flush()
            session.add(
                Incident(
                    id=incident_a,
                    tenant_id=tenant_a_id,
                    publisher_id=pub_a,
                    site_id=site_a,
                    title="Tenant A incident",
                    symptom_family="GAM_ADSERVING",
                    description="A's incident.",
                    opened_at=datetime.now(UTC),
                    status="OPEN",
                )
            )

        # Tenant B: independent publisher + site + incident.
        tenant_b_id = uuid.uuid4()
        pub_b = uuid.uuid4()
        site_b = uuid.uuid4()
        incident_b = uuid.uuid4()
        async with factory() as session, session.begin():
            session.add(Tenant(id=tenant_b_id, slug=slug_b, name=f"T {slug_b}"))
            await session.flush()
            session.add(
                Publisher(
                    id=pub_b,
                    tenant_id=tenant_b_id,
                    name=f"P {slug_b}",
                    slug=f"pub-{pub_b.hex[:8]}",
                    default_timezone="UTC",
                    status="ACTIVE",
                )
            )
            await session.flush()
            session.add(
                Site(
                    id=site_b,
                    tenant_id=tenant_b_id,
                    publisher_id=pub_b,
                    name=f"S {slug_b}",
                    canonical_domain=f"{site_b.hex}.example.com",
                    canonical_scheme="https",
                    timezone="UTC",
                    status="ACTIVE",
                )
            )
            await session.flush()
            session.add(
                Incident(
                    id=incident_b,
                    tenant_id=tenant_b_id,
                    publisher_id=pub_b,
                    site_id=site_b,
                    title="Tenant B incident",
                    symptom_family="OTHER",
                    description="B's incident.",
                    opened_at=datetime.now(UTC),
                    status="OPEN",
                )
            )

        _op_a_id, op_a_email = await create_operator(tenant_a_id, f"op-{slug_a}@example.com")
        return tenant_a_id, incident_a, incident_b, site_b, op_a_email

    (
        tenant_a_id,
        incident_a_id,
        incident_b_id,
        site_b_id,
        op_a_email,
    ) = asyncio.run(seed_two_tenants())

    client = TestClient(app)
    login_response = client.post(
        "/auth/login",
        json={
            "email": op_a_email,
            "password": "correct-horse-battery",
            "tenant_id": str(tenant_a_id),
        },
    )
    assert login_response.status_code == 200
    cookies = dict(login_response.cookies)

    response = client.get("/incidents", cookies=cookies)
    assert response.status_code == 200
    incidents = response.json()["incidents"]

    # Only tenant A's incident appears in the serialized response.
    listed_ids = [inc["incident_id"] for inc in incidents]
    assert str(incident_a_id) in listed_ids
    assert str(incident_b_id) not in listed_ids
    assert str(incident_b_id) not in response.text
    assert str(site_b_id) not in response.text


def test_i3_authenticated_tenant_can_fetch_own_incident_detail() -> None:
    """I3: authenticated tenant can fetch its own incident detail."""
    get_session_factory()

    async def seed() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, str]:
        slug = f"i3-{uuid.uuid4().hex[:8]}"
        tenant_id = await create_tenant(slug)
        site_id = await create_site(tenant_id)
        incident_id = await create_incident(tenant_id, site_id, title="Detail view revenue drop")
        _operator_id, email = await create_operator(tenant_id, f"op-{slug}@example.com")
        return tenant_id, site_id, incident_id, email

    tenant_id, site_id, incident_id, email = asyncio.run(seed())

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

    response = client.get(f"/incidents/{incident_id}", cookies=cookies)
    assert response.status_code == 200

    body = response.json()
    incident = body["incident"]
    assert incident["incident_id"] == str(incident_id)
    assert incident["title"] == "Detail view revenue drop"
    assert incident["symptom_family"] == "GAM_ADSERVING"
    assert incident["description"] == "Description for Detail view revenue drop"
    assert incident["status"] == "OPEN"
    assert incident["site_id"] == str(site_id)

    # No symptom segments were seeded; the detail contract exposes them explicitly.
    assert body["symptom_segments"] == []


def test_i4_cross_tenant_incident_detail_is_non_disclosing() -> None:
    """I4: tenant A cannot read tenant B's incident detail."""
    get_session_factory()

    async def seed() -> tuple[uuid.UUID, str, uuid.UUID, uuid.UUID, uuid.UUID]:
        slug_a = f"i4a-{uuid.uuid4().hex[:8]}"
        slug_b = f"i4b-{uuid.uuid4().hex[:8]}"
        tenant_a_id = await create_tenant(slug_a)
        await create_site(tenant_a_id)
        _operator_id_a, email_a = await create_operator(tenant_a_id, f"op-{slug_a}@example.com")
        tenant_b_id = await create_tenant(slug_b)
        site_b_id = await create_site(tenant_b_id)
        incident_b_id = await create_incident(
            tenant_b_id, site_b_id, title="Tenant B secret incident"
        )
        return tenant_a_id, email_a, incident_b_id, site_b_id, tenant_b_id

    tenant_a_id, email_a, incident_b_id, site_b_id, _tenant_b_id = asyncio.run(seed())

    client = TestClient(app)
    login_response = client.post(
        "/auth/login",
        json={
            "email": email_a,
            "password": "correct-horse-battery",
            "tenant_id": str(tenant_a_id),
        },
    )
    assert login_response.status_code == 200
    cookies = dict(login_response.cookies)

    response = client.get(f"/incidents/{incident_b_id}", cookies=cookies)
    assert response.status_code == 404

    # No tenant B data may leak in any serialized form.
    body_text = response.text
    assert str(incident_b_id) not in body_text
    assert str(site_b_id) not in body_text
    assert "Tenant B secret incident" not in body_text
    assert "GAM_ADSERVING" not in body_text


def test_i5_symptom_scope_status_serialize_correctly() -> None:
    """I5: canonical symptom/scope/status fields serialize exactly as stored."""
    get_session_factory()

    async def seed() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, str]:
        slug = f"i5-{uuid.uuid4().hex[:8]}"
        tenant_id = await create_tenant(slug)
        site_id = await create_site(tenant_id)
        incident_id = await create_incident(
            tenant_id,
            site_id,
            title="Canonical serialization probe",
            status="RESOLVED",
        )
        _operator_id, email = await create_operator(tenant_id, f"op-{slug}@example.com")
        return tenant_id, site_id, incident_id, email

    tenant_id, site_id, incident_id, email = asyncio.run(seed())

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

    response = client.get(f"/incidents/{incident_id}", cookies=cookies)
    assert response.status_code == 200

    incident = response.json()["incident"]
    assert incident["symptom_family"] == "GAM_ADSERVING"
    assert incident["status"] == "RESOLVED"
    assert incident["site_id"] == str(site_id)
    assert incident["title"] == "Canonical serialization probe"
    assert incident["description"] == "Description for Canonical serialization probe"


def test_i6_incident_onset_window_semantics_remain_accurate() -> None:
    """I6: bounded onset/window round-trips exactly; unknown times stay unknown."""
    factory = get_session_factory()

    async def seed_and_set_window() -> tuple[
        str, "datetime", "datetime", "datetime", uuid.UUID, uuid.UUID
    ]:
        slug = f"i6-{uuid.uuid4().hex[:8]}"
        tenant_id = await create_tenant(slug)
        site_id = await create_site(tenant_id)
        incident_id = await create_incident(tenant_id, site_id, title="Onset window probe")
        _operator_id, email = await create_operator(tenant_id, f"op-{slug}@example.com")

        # Canonical bounded onset/window: known start/end, unresolved end state absent.
        window_start = datetime(2026, 8, 10, 6, 30, 15, 123456, tzinfo=UTC)
        window_end = datetime(2026, 8, 10, 11, 0, 0, 654321, tzinfo=UTC)
        async with factory() as session, session.begin():
            incident = await session.scalar(select(Incident).where(Incident.id == incident_id))
            assert incident is not None
            incident.reported_start_at = window_start
            incident.reported_end_at = window_end
            await session.flush()
            return (
                email,
                incident.opened_at,
                incident.reported_start_at,
                incident.reported_end_at,
                tenant_id,
                incident_id,
            )

    (
        email_a,
        opened_at_db,
        reported_start_db,
        reported_end_db,
        tenant_id,
        incident_id,
    ) = asyncio.run(seed_and_set_window())

    client = TestClient(app)
    login_response = client.post(
        "/auth/login",
        json={
            "email": email_a,
            "password": "correct-horse-battery",
            "tenant_id": str(tenant_id),
        },
    )
    assert login_response.status_code == 200
    cookies = dict(login_response.cookies)

    response = client.get(f"/incidents/{incident_id}", cookies=cookies)
    assert response.status_code == 200

    incident = response.json()["incident"]
    # Bounded window round-trips exactly — no rounding, no re-zoning drift beyond ISO form.
    assert incident["reported_start_at"] == reported_start_db.isoformat()
    assert incident["reported_end_at"] == reported_end_db.isoformat()
    assert incident["reported_start_at"] != incident["reported_end_at"]
    # Known onset round-trips exactly.
    assert incident["opened_at"] == opened_at_db.isoformat()
    # Unknown resolution time must remain explicitly unknown — never substituted
    # with another observation timestamp.
    assert incident["resolved_at"] is None


def test_i8_frozen_lkg_reference_remains_tenant_safe() -> None:
    """I8: incident detail returns only the authenticated tenant's frozen LKG refs."""
    factory = get_session_factory()

    async def seed_lkg_ref(
        tenant_id: uuid.UUID,
        site_id: uuid.UUID,
        incident_id: uuid.UUID,
        *,
        scope_key: str,
    ) -> tuple[uuid.UUID, str]:
        """Minimal canonical frozen LKG reference: template/url/scenario/window/run."""
        template_id, monitored_url_id, scenario_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        run_id, window_id = uuid.uuid4(), uuid.uuid4()
        ref_id = uuid.uuid4()
        selected_at = datetime(2026, 8, 20, 9, 0, tzinfo=UTC)
        when = datetime.now(UTC) - timedelta(hours=2)
        async with factory() as session, session.begin():
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
            session.add(
                CheckpointRun(
                    id=run_id,
                    tenant_id=tenant_id,
                    site_id=site_id,
                    checkpoint_window_id=window_id,
                    monitored_url_id=monitored_url_id,
                    template_id=template_id,
                    scenario_id=scenario_id,
                    observation_kind="SCHEDULED",
                    scheduled_for=when,
                    started_at=when,
                    completed_at=when + timedelta(minutes=5),
                    status="COMPLETE",
                    attempt_count=1,
                    environment={},
                    limitations=[],
                    manifest={},
                )
            )
            session.add(
                LastKnownGoodRef(
                    id=ref_id,
                    tenant_id=tenant_id,
                    site_id=site_id,
                    scope_key=scope_key,
                    checkpoint_run_id=run_id,
                    valid_for_incident_id=incident_id,
                    selected_at=selected_at,
                    selection_method="MANUAL_OPERATOR",
                    selection_version="lkg-v1",
                    reason=f"Frozen baseline for {scope_key}",
                    fingerprints={"collector_bundle": "b8-v1", "robots": "robots-rfc9309-v1"},
                )
            )
        return ref_id, scope_key

    async def seed_two_tenants_with_lkg() -> tuple[
        tuple[uuid.UUID, str, uuid.UUID, uuid.UUID, uuid.UUID, str, uuid.UUID], str
    ]:
        slug_a, slug_b = f"i8a-{uuid.uuid4().hex[:8]}", f"i8b-{uuid.uuid4().hex[:8]}"
        tenant_a_id = await create_tenant(slug_a)
        site_a_id = await create_site(tenant_a_id)
        incident_a_id = await create_incident(tenant_a_id, site_a_id, title="Incident A LKG")
        _op_id_a, email_a = await create_operator(tenant_a_id, f"op-{slug_a}@example.com")
        ref_a_id, ref_a_scope = await seed_lkg_ref(
            tenant_a_id, site_a_id, incident_a_id, scope_key="site-a::desktop"
        )

        tenant_b_id = await create_tenant(slug_b)
        site_b_id = await create_site(tenant_b_id)
        incident_b_id = await create_incident(tenant_b_id, site_b_id, title="Incident B LKG")
        ref_b_id, ref_b_scope = await seed_lkg_ref(
            tenant_b_id, site_b_id, incident_b_id, scope_key="site-b::desktop"
        )
        return (
            tenant_a_id,
            email_a,
            incident_a_id,
            ref_a_id,
            ref_b_id,
            ref_b_scope,
            site_b_id,
        ), ref_a_scope

    seeded, ref_a_scope = asyncio.run(seed_two_tenants_with_lkg())
    (
        tenant_a_id,
        email_a,
        incident_a_id,
        ref_a_id,
        ref_b_id,
        ref_b_scope,
        site_b_id,
    ) = seeded

    client = TestClient(app)
    login_response = client.post(
        "/auth/login",
        json={
            "email": email_a,
            "password": "correct-horse-battery",
            "tenant_id": str(tenant_a_id),
        },
    )
    assert login_response.status_code == 200
    cookies = dict(login_response.cookies)

    response = client.get(f"/incidents/{incident_a_id}", cookies=cookies)
    assert response.status_code == 200

    body = response.json()
    lkg_refs = body["last_known_good_references"]
    assert len(lkg_refs) == 1

    # Tenant A's frozen reference is returned with canonical frozen fields intact.
    ref = lkg_refs[0]
    assert ref["reference_id"] == str(ref_a_id)
    assert ref["scope_key"] == ref_a_scope
    assert ref["selection_method"] == "MANUAL_OPERATOR"
    assert ref["selection_version"] == "lkg-v1"
    assert ref["selected_at"] is not None
    assert ref["fingerprints"] == {"collector_bundle": "b8-v1", "robots": "robots-rfc9309-v1"}

    # Tenant B's frozen reference and identifiers must not leak anywhere.
    assert str(ref_b_id) not in response.text
    assert ref_b_scope not in response.text
    assert str(site_b_id) not in response.text


def test_i9_incident_detail_read_does_not_mutate_frozen_lkg() -> None:
    """I9: GET /incidents/{id} is observational only for frozen LKG state."""
    factory = get_session_factory()

    async def seed_lkg_ref(
        tenant_id: uuid.UUID,
        site_id: uuid.UUID,
        incident_id: uuid.UUID,
        *,
        scope_key: str,
    ) -> tuple[uuid.UUID, uuid.UUID]:
        """Minimal canonical frozen LKG reference (same shape as I8)."""
        template_id, monitored_url_id, scenario_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        run_id, window_id = uuid.uuid4(), uuid.uuid4()
        ref_id = uuid.uuid4()
        when = datetime.now(UTC) - timedelta(hours=2)
        async with factory() as session, session.begin():
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
            session.add(
                CheckpointRun(
                    id=run_id,
                    tenant_id=tenant_id,
                    site_id=site_id,
                    checkpoint_window_id=window_id,
                    monitored_url_id=monitored_url_id,
                    template_id=template_id,
                    scenario_id=scenario_id,
                    observation_kind="SCHEDULED",
                    scheduled_for=when,
                    started_at=when,
                    completed_at=when + timedelta(minutes=5),
                    status="COMPLETE",
                    attempt_count=1,
                    environment={},
                    limitations=[],
                    manifest={},
                )
            )
            session.add(
                LastKnownGoodRef(
                    id=ref_id,
                    tenant_id=tenant_id,
                    site_id=site_id,
                    scope_key=scope_key,
                    checkpoint_run_id=run_id,
                    valid_for_incident_id=incident_id,
                    selected_at=datetime(2026, 8, 20, 9, 0, tzinfo=UTC),
                    selection_method="MANUAL_OPERATOR",
                    selection_version="lkg-v1",
                    reason=f"Frozen baseline for {scope_key}",
                    fingerprints={"collector_bundle": "b8-v1", "robots": "robots-rfc9309-v1"},
                )
            )
        return ref_id, run_id

    async def seed_one_tenant_with_lkg() -> tuple[str, uuid.UUID, uuid.UUID, tuple[Any, ...]]:
        slug = f"i9-{uuid.uuid4().hex[:8]}"
        tenant_id = await create_tenant(slug)
        site_id = await create_site(tenant_id)
        incident_id = await create_incident(tenant_id, site_id, title="LKG immutability probe")
        _op_id, email = await create_operator(tenant_id, f"op-{slug}@example.com")
        _ref_id, _run_id = await seed_lkg_ref(
            tenant_id, site_id, incident_id, scope_key="site::desktop"
        )

        async def read_persisted_lkg() -> tuple[Any, ...]:
            async with factory() as session:
                rows = (
                    await session.scalars(
                        select(LastKnownGoodRef).where(
                            LastKnownGoodRef.valid_for_incident_id == incident_id
                        )
                    )
                ).all()
                assert len(rows) == 1
                row = rows[0]
                return (
                    row.id,
                    row.scope_key,
                    row.checkpoint_run_id,
                    row.valid_for_incident_id,
                    row.selected_at.isoformat(),
                    row.selection_method,
                    row.selection_version,
                    row.reason,
                    dict(row.fingerprints),
                )

        before = await read_persisted_lkg()
        return email, tenant_id, incident_id, before

    email, tenant_id, incident_id, before = asyncio.run(seed_one_tenant_with_lkg())

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

    response = client.get(f"/incidents/{incident_id}", cookies=dict(login_response.cookies))
    assert response.status_code == 200

    async def verify_after_read() -> tuple[tuple[Any, ...], int]:
        async with factory() as session:
            rows = (
                await session.scalars(
                    select(LastKnownGoodRef).where(
                        LastKnownGoodRef.valid_for_incident_id == incident_id
                    )
                )
            ).all()
            row = rows[0]
            after = (
                row.id,
                row.scope_key,
                row.checkpoint_run_id,
                row.valid_for_incident_id,
                row.selected_at.isoformat(),
                row.selection_method,
                row.selection_version,
                row.reason,
                dict(row.fingerprints),
            )
            return after, len(rows)

    after, lkg_row_count = asyncio.run(verify_after_read())

    # Exactly one LKG row still exists — the read created/removed/replaced nothing.
    assert lkg_row_count == 1
    # Every persisted field is identical before vs after the HTTP read.
    assert after == before

    # The response still carries the same single frozen reference.
    body = response.json()
    lkg_refs = body["last_known_good_references"]
    assert len(lkg_refs) == 1
    assert lkg_refs[0]["reference_id"] == str(before[0])
    assert lkg_refs[0]["scope_key"] == before[1]
    assert lkg_refs[0]["checkpoint_run_id"] == str(before[2])
