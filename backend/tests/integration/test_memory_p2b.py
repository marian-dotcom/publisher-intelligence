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


def _login_and_get_cookies(tenant_id, email):

    client = TestClient(app)
    response = client.post(
        "/auth/login",
        json={"email": email, "password": "correct-horse-battery", "tenant_id": str(tenant_id)},
    )
    assert response.status_code == 200
    return client, dict(response.cookies)


def test_t1_authenticated_tenant_can_read_own_timeline() -> None:
    factory = get_session_factory()

    async def setup():
        slug = f"t1-{uuid.uuid4().hex[:8]}"
        tenant_id = await factories.create_tenant(slug)
        operator_id, email = await factories.create_operator(tenant_id, f"op-{slug}@example.com")
        site_id = await factories.create_site(tenant_id)
        event_id = await factories.add_scheduled_event(tenant_id, site_id)
        return tenant_id, site_id, event_id, email

    tenant_id, site_id, event_id, email = asyncio.run(setup())

    async def verify_event() -> None:
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
