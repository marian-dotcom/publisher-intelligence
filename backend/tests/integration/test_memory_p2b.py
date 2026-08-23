"""EP-025a P2-B incremental validation. Currently: T1 only."""

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session import get_session_factory
from app.events.models import Event
from app.main import app
from tests.integration.product import factories
from tests.integration.purge import make_purge

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _clean_db() -> None:
    asyncio.run(make_purge(get_session_factory)())


def _login_and_get_cookies(tenant_id: uuid.UUID, email: str) -> tuple[TestClient, dict[str, str]]:

    client = TestClient(app)
    response = client.post(
        "/auth/login",
        json={"email": email, "password": "correct-horse-battery", "tenant_id": str(tenant_id)},
    )
    assert response.status_code == 200
    return client, dict(response.cookies)


def test_t1_authenticated_tenant_can_read_own_timeline() -> None:
    factory = get_session_factory()

    async def setup() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, str]:
        slug = f"t1-{uuid.uuid4().hex[:8]}"
        tenant_id = await factories.create_tenant(slug)
        operator_id, email = await factories.create_operator(tenant_id, f"op-{slug}@example.com")
        site_id = await factories.create_site(tenant_id)
        event_id = await factories.add_scheduled_event(tenant_id, site_id)
        return tenant_id, site_id, event_id, email

    tenant_id, site_id, event_id, email = asyncio.run(setup())

    async def verify_event() -> tuple[str, str, str]:
        async with factory() as session:
            event = await session.scalar(select(Event).where(Event.id == event_id))
            assert event is not None
            return str(event.event_definition_id), str(event.site_id), str(event.tenant_id)

    definition_str, expected_site, expected_tenant = asyncio.run(verify_event())
    client, cookies = _login_and_get_cookies(tenant_id, email)

    response = client.get("/timeline", cookies=cookies)
    assert response.status_code == 200
    entries = response.json()["entries"]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["event_id"] == str(event_id)
    assert entry["event_type"] == definition_str
    assert entry["site_id"] == expected_site
    assert entry["provenance"] == "machine_observed"
    assert entry["observed_at"] is not None
    # No unrestricted raw payload dump in the product schema.
    assert "details" not in entry and "manifest" not in entry


def test_t2_tenant_a_timeline_excludes_tenant_b_events() -> None:
    factory = get_session_factory()

    async def setup_two_tenants() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, str]:
        slug_a = f"t2a-{uuid.uuid4().hex[:8]}"
        tenant_a = await factories.create_tenant(slug_a)
        operator_id_a, email_a = await factories.create_operator(
            tenant_a, f"op-{slug_a}@example.com"
        )
        site_a = await factories.create_site(tenant_a)
        await factories.add_scheduled_event(tenant_a, site_a)

        slug_b = f"t2b-{uuid.uuid4().hex[:8]}"
        tenant_b = await factories.create_tenant(slug_b)
        site_b = await factories.create_site(tenant_b)
        await factories.add_scheduled_event(tenant_b, site_b)
        return tenant_a, site_a, site_b, email_a

    tenant_a, site_a, site_b, email_a = asyncio.run(setup_two_tenants())
    client = TestClient(app)
    login_response = client.post(
        "/auth/login",
        json={
            "email": email_a,
            "password": "correct-horse-battery",
            "tenant_id": str(tenant_a),
        },
    )
    assert login_response.status_code == 200
    cookies = dict(login_response.cookies)

    response = client.get("/timeline", cookies=cookies)
    assert response.status_code == 200
    body = response.text
    entries = response.json()["entries"]
    # Server-side filtering: only tenant A events returned; no tenant B data.
    assert len(entries) == 1
    assert entries[0]["site_id"] == str(site_a)
    assert str(site_b) not in body
    assert entries[0]["provenance"] == "machine_observed"


def test_t3_machine_observed_provenance_is_explicitly_serialized() -> None:
    """The product contract must carry provenance as an explicit field —
    the frontend must not infer it from event type/source/timestamps."""
    factory = get_session_factory()

    async def setup() -> tuple[uuid.UUID, uuid.UUID, str]:
        slug = f"t3-{uuid.uuid4().hex[:8]}"
        tenant_id = await factories.create_tenant(slug)
        operator_id, email = await factories.create_operator(tenant_id, f"op-{slug}@example.com")
        site_id = await factories.create_site(tenant_id)
        await factories.add_scheduled_event(tenant_id, site_id)
        return tenant_id, site_id, email

    _tenant_id, _site_id, email_a = asyncio.run(setup())
    client = TestClient(app)
    login_response = client.post(
        "/auth/login",
        json={
            "email": email_a,
            "password": "correct-horse-battery",
            "tenant_id": str(_tenant_id),
        },
    )
    assert login_response.status_code == 200
    cookies = dict(login_response.cookies)

    response = client.get("/timeline", cookies=cookies)
    assert response.status_code == 200
    entries = response.json()["entries"]
    assert len(entries) >= 1
    for entry in entries:
        # Explicit field, canonical value — not inferred from source/type.
        assert "provenance" in entry
        assert entry["provenance"] == "machine_observed"


def test_t4_human_reported_provenance_distinct_from_machine() -> None:
    """T4: human_reported and machine_observed are explicit, distinguishable
    provenance classes in the serialized Timeline contract."""
    factory = get_session_factory()

    async def setup() -> tuple[uuid.UUID, uuid.UUID, str]:
        slug = f"t4-{uuid.uuid4().hex[:8]}"
        tenant_id = await factories.create_tenant(slug)
        _operator_id, email = await factories.create_operator(tenant_id, f"op-{slug}@example.com")
        site_id = await factories.create_site(tenant_id)
        note_id = await factories.create_manual_note(
            tenant_id, site_id, "Operator confirmed the CMP banner was removed."
        )
        return tenant_id, site_id, email

    tenant_id, site_id, email_a = asyncio.run(setup())
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

    response = client.get("/timeline", cookies=cookies)
    assert response.status_code == 200
    entries = response.json()["entries"]

    human_entries = [e for e in entries if e.get("provenance") == "human_reported"]
    machine_entries = [e for e in entries if e.get("provenance") == "machine_observed"]
    assert human_entries, "human_reported entry must appear when manual notes exist"
    assert all(e["provenance"] == "human_reported" for e in human_entries)
    assert all("text" in e for e in human_entries)
    for entry in machine_entries:
        assert entry["provenance"] == "machine_observed"
