"""EP-025a P2-B Incidents: I1/I2 — incident read contracts."""

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.browser.models import Publisher, Site
from app.db.models import Tenant
from app.incidents.models import Incident
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
