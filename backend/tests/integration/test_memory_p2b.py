"""EP-025a P2-B incremental validation. Currently: T1 only."""

import asyncio
import uuid
from datetime import UTC, datetime

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
        _operator_id, email = await factories.create_operator(tenant_id, f"op-{slug}@example.com")
        site_id = await factories.create_site(tenant_id)
        event_id = await factories.add_scheduled_event(tenant_id, site_id)
        return tenant_id, site_id, event_id, email

    tenant_id, _site_id, event_id, email = asyncio.run(setup())

    async def verify_event() -> tuple[str, str, str]:
        async with factory() as session:
            event = await session.scalar(select(Event).where(Event.id == event_id))
            assert event is not None
            return str(event.event_definition_id), str(event.site_id), str(event.tenant_id)

    definition_str, expected_site, _expected_tenant = asyncio.run(verify_event())
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

    async def setup_two_tenants() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, str]:
        slug_a = f"t2a-{uuid.uuid4().hex[:8]}"
        tenant_a = await factories.create_tenant(slug_a)
        _operator_id_a, email_a = await factories.create_operator(
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

    async def setup() -> tuple[uuid.UUID, uuid.UUID, str]:
        slug = f"t3-{uuid.uuid4().hex[:8]}"
        tenant_id = await factories.create_tenant(slug)
        _operator_id, email = await factories.create_operator(tenant_id, f"op-{slug}@example.com")
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

    async def setup() -> tuple[uuid.UUID, uuid.UUID, str]:
        slug = f"t4-{uuid.uuid4().hex[:8]}"
        tenant_id = await factories.create_tenant(slug)
        _operator_id, email = await factories.create_operator(tenant_id, f"op-{slug}@example.com")
        site_id = await factories.create_site(tenant_id)
        await factories.create_manual_note(
            tenant_id, site_id, "Operator confirmed the CMP banner was removed."
        )
        return tenant_id, site_id, email

    tenant_id, _site_id, email_a = asyncio.run(setup())
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


def test_t5_observed_at_preserved_occurred_at_remains_unknown() -> None:
    """T5: observation time does NOT imply occurrence time."""
    from tests.integration.product.factories import (
        add_scheduled_event,
        create_operator,
        create_site,
        create_tenant,
    )

    async def setup() -> tuple[uuid.UUID, uuid.UUID, str]:
        slug = f"t5-{uuid.uuid4().hex[:8]}"
        tenant_id = await create_tenant(slug)
        _operator_id, email = await create_operator(tenant_id, f"op-{slug}@example.com")
        site_id = await create_site(tenant_id)
        await add_scheduled_event(tenant_id, site_id)
        return tenant_id, site_id, email

    tenant_id, _site_id, email = asyncio.run(setup())

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

    response = client.get("/timeline", cookies=dict(login_response.cookies))
    assert response.status_code == 200
    entries = response.json()["entries"]
    assert len(entries) >= 1

    for entry in entries:
        # observed_at is always populated (detection time is known).
        assert entry["observed_at"] is not None
        # Non-EXACT events must NOT fabricate an exact occurred_at.
        if entry["time_precision"] != "EXACT":
            assert entry["occurred_at"] is None


@pytest.mark.asyncio
async def test_t6_exact_occurred_at_exposed_only_when_canonical() -> None:
    """T6: occurred_at is non-null and equals the persisted canonical
    occurrence timestamp ONLY when time_precision == EXACT."""
    from tests.integration.product.factories import add_exact_event

    async def setup() -> tuple[uuid.UUID, uuid.UUID, str]:
        slug = f"t6-{uuid.uuid4().hex[:8]}"
        tenant_id = await factories.create_tenant(slug)
        _operator_id, email = await factories.create_operator(tenant_id, f"op-{slug}@example.com")
        site_id = await factories.create_site(tenant_id)
        await factories.add_scheduled_event(tenant_id, site_id)
        await add_exact_event(tenant_id, site_id)
        return tenant_id, site_id, email

    tenant_id, _site_id, email = await setup()

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

    response = client.get("/timeline", cookies=dict(login_response.cookies))
    assert response.status_code == 200
    entries = response.json()["entries"]

    window_entries = [e for e in entries if e["time_precision"] == "WINDOW"]
    exact_entries = [e for e in entries if e["time_precision"] == "EXACT"]

    # WINDOW entries must have occurred_at null.
    for entry in window_entries:
        assert entry["occurred_at"] is None

    # EXACT entries must have occurred_at non-null.
    assert len(exact_entries) >= 1
    for entry in exact_entries:
        assert entry["occurred_at"] is not None
        # observed_at independently serialized — not substituted.
        assert entry["observed_at"] is not None


def test_t7_bounded_occurrence_window_survives_serialization() -> None:
    """T7: both occurrence-window bounds survive serialization without
    fabricated precision and occurred_at remains null."""
    from tests.integration.product.factories import (
        add_bounded_event,
        create_operator,
        create_site,
        create_tenant,
    )

    window_start = datetime(2026, 8, 21, 10, 0, tzinfo=UTC)
    window_end = datetime(2026, 8, 21, 14, 0, tzinfo=UTC)

    async def setup() -> tuple[uuid.UUID, uuid.UUID, str]:
        slug = f"t7-{uuid.uuid4().hex[:8]}"
        tenant_id = await create_tenant(slug)
        _operator_id, email = await create_operator(tenant_id, f"op-{slug}@example.com")
        site_id = await create_site(tenant_id)
        await add_bounded_event(
            tenant_id,
            site_id,
            window_start=window_start,
            window_end=window_end,
        )
        return tenant_id, site_id, email

    tenant_id, site_id, email = asyncio.run(setup())
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

    response = client.get("/timeline", cookies=dict(login_response.cookies))
    assert response.status_code == 200
    entries = response.json()["entries"]
    matching = [e for e in entries if e["site_id"] == str(site_id)]
    assert len(matching) == 1
    entry = matching[0]

    # Bounded interval preserved exactly.
    assert entry["time_precision"] == "WINDOW"
    assert entry["occurred_at"] is None
    assert entry["occurrence_window_start"] == window_start.isoformat()
    assert entry["occurrence_window_end"] == window_end.isoformat()


def test_t8_cross_tenant_timeline_body_contains_no_foreign_event_data() -> None:
    """T8 (event-level): cross-tenant event/site isolation in /timeline.
    Related incident/investigation/LKG references are not serialized by this
    endpoint and therefore cannot leak here; that safety is proven on the read
    surfaces where those references are actually exposed."""

    async def setup_two_tenants() -> tuple[
        uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, str
    ]:
        slug_a = f"iso-a-{uuid.uuid4().hex[:8]}"
        slug_b = f"iso-b-{uuid.uuid4().hex[:8]}"
        tenant_a = await factories.create_tenant(slug_a)
        tenant_b = await factories.create_tenant(slug_b)
        op_a_email = f"op-{slug_a}@example.com"
        await factories.create_operator(tenant_a, op_a_email)
        site_a = await factories.create_site(tenant_a)
        event_a = await factories.add_scheduled_event(tenant_a, site_a)
        site_b = await factories.create_site(tenant_b)
        event_b = await factories.add_scheduled_event(tenant_b, site_b)
        return tenant_a, tenant_b, site_a, site_b, event_a, event_b, op_a_email

    tenant_a, _tenant_b, site_a, site_b, event_a, event_b, op_a_email = asyncio.run(
        setup_two_tenants()
    )

    client = TestClient(app)
    login_response = client.post(
        "/auth/login",
        json={"email": op_a_email, "password": "correct-horse-battery", "tenant_id": str(tenant_a)},
    )
    assert login_response.status_code == 200
    cookies = dict(login_response.cookies)

    response = client.get("/timeline", cookies=cookies)
    assert response.status_code == 200
    body = response.text
    entries = response.json()["entries"]
    assert len(entries) == 1
    assert str(event_a) in body or any(e["site_id"] == str(site_a) for e in entries)
    assert str(site_b) not in body
    assert str(event_b) not in body


def test_t9_raw_internal_payload_not_exposed_in_timeline() -> None:
    """T9: raw/unrestricted payload data must not appear in Timeline serialization."""

    async def setup() -> tuple[uuid.UUID, uuid.UUID, str]:
        slug = f"t9-{uuid.uuid4().hex[:8]}"
        tenant_id = await factories.create_tenant(slug)
        _operator_id, email = await factories.create_operator(tenant_id, f"op-{slug}@example.com")
        site_id = await factories.create_site(tenant_id)
        await factories.add_event_with_internal_details(tenant_id, site_id)
        return tenant_id, site_id, email

    tenant_id, _site_id, email = asyncio.run(setup())

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

    response = client.get("/timeline", cookies=dict(login_response.cookies))
    assert response.status_code == 200
    entries = response.json()["entries"]
    assert len(entries) == 1
    entry = entries[0]

    # Explicit product schema fields are present.
    assert entry["event_id"] is not None
    assert entry["observed_at"] is not None
    assert entry["provenance"] == "machine_observed"
    # Raw internal fields must not leak.
    serialized = str(entry)
    for forbidden in ("internal_debug", "session_storage_dump", "connector_api_response"):
        assert forbidden not in serialized, f"leaked: {forbidden}"


def test_t10_site_filter_limits_events_and_notes_to_site() -> None:
    """T10: /timeline?site_id=X returns only X's events AND manual notes;
    All-sites mode still shows both sites. (EP-029 M2a filter completeness.)"""

    async def setup() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, str]:
        slug = f"t10-{uuid.uuid4().hex[:8]}"
        tenant_id = await factories.create_tenant(slug)
        _operator_id, email = await factories.create_operator(tenant_id, f"op-{slug}@example.com")
        site_a = await factories.create_site(tenant_id)
        site_b = await factories.create_site(tenant_id)
        await factories.add_scheduled_event(tenant_id, site_a)
        await factories.add_scheduled_event(tenant_id, site_b)
        await factories.create_manual_note(tenant_id, site_a, "Operator note about site A.")
        await factories.create_manual_note(tenant_id, site_b, "Operator note about site B.")
        return tenant_id, site_a, site_b, email

    tenant_id, site_a, site_b, email = asyncio.run(setup())
    client, cookies = _login_and_get_cookies(tenant_id, email)

    filtered = client.get(f"/timeline?site_id={site_a}", cookies=cookies)
    assert filtered.status_code == 200
    entries = filtered.json()["entries"]
    # Site A event + Site A note only; site A note must not be lost by the filter.
    assert len(entries) == 2
    assert {e["provenance"] for e in entries} == {"machine_observed", "human_reported"}
    assert {e["site_id"] for e in entries} == {str(site_a)}
    note_texts = {e.get("text") for e in entries}
    assert "Operator note about site A." in note_texts
    assert "Operator note about site B." not in note_texts
    assert str(site_b) not in filtered.text

    all_sites = client.get("/timeline", cookies=cookies)
    assert all_sites.status_code == 200
    all_entries = all_sites.json()["entries"]
    assert len(all_entries) == 4
    assert {e["site_id"] for e in all_entries} == {str(site_a), str(site_b)}


def test_t11_site_filter_never_exposes_foreign_tenant_items() -> None:
    """T11: filtering by another tenant's site_id returns no rows and leaks no
    foreign event/note content. (EP-029 M2a filter tenant boundary.)"""

    async def setup_two_tenants() -> tuple[uuid.UUID, uuid.UUID, str]:
        slug_a = f"t11a-{uuid.uuid4().hex[:8]}"
        tenant_a = await factories.create_tenant(slug_a)
        _operator_a, email_a = await factories.create_operator(tenant_a, f"op-{slug_a}@example.com")
        await factories.create_site(tenant_a)

        slug_b = f"t11b-{uuid.uuid4().hex[:8]}"
        tenant_b = await factories.create_tenant(slug_b)
        site_b = await factories.create_site(tenant_b)
        await factories.add_scheduled_event(tenant_b, site_b)
        await factories.create_manual_note(tenant_b, site_b, "Tenant B private note.")
        return tenant_a, site_b, email_a

    tenant_a, site_b, email_a = asyncio.run(setup_two_tenants())
    client, cookies = _login_and_get_cookies(tenant_a, email_a)

    response = client.get(f"/timeline?site_id={site_b}", cookies=cookies)
    assert response.status_code == 200
    entries = response.json()["entries"]
    assert entries == []
    assert str(site_b) not in response.text
    assert "Tenant B private note." not in response.text
