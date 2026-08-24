"""Smoke test: minimum Timeline seed state can be constructed reliably."""

import uuid

import pytest
from sqlalchemy import select

from app.db.session import get_session_factory
from app.events.models import Event
from tests.integration.product import factories

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_seed_helpers_construct_minimum_timeline_state() -> None:
    factory = get_session_factory()
    slug = f"seed-{uuid.uuid4().hex[:8]}"
    tenant_id = await factories.create_tenant(slug)
    operator_id, email = await factories.create_operator(tenant_id, f"{slug}@example.com")
    site_id = await factories.create_site(tenant_id)
    event_id = await factories.add_scheduled_event(tenant_id, site_id)

    assert operator_id is not None and email == f"{slug}@example.com"
    async with factory() as session:
        event = await session.scalar(select(Event).where(Event.id == event_id))
        assert event is not None
        assert str(event.site_id) == str(site_id)
        assert str(event.tenant_id) == str(tenant_id)
        assert event.status == "RECORDED"
