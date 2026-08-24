"""EP-025a P2-D D1: authenticated Investigate intake happy path.

The route delegates to the canonical EP-020 IncidentIntakeService; this file
proves the authenticated HTTP boundary wires actor provenance, tenant
ownership, and temporal uncertainty through to persisted domain state.
"""

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.browser.models import Site
from app.incidents.intake import investigation_key_for
from app.incidents.models import Incident
from app.main import app
from tests.integration.product.factories import (
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


def test_d1_authenticated_intake_persists_incident_with_actor_provenance() -> None:
    get_session_factory()

    async def seed() -> tuple[uuid.UUID, str, uuid.UUID]:
        slug = f"d1-{uuid.uuid4().hex[:8]}"
        tenant_id = await create_tenant(slug)
        site_id = await create_site(tenant_id)
        _operator_id, email = await create_operator(tenant_id, f"op-{slug}@example.com")
        return tenant_id, email, site_id

    tenant_id, email, site_id = asyncio.run(seed())
    factory = get_session_factory()

    async def actor_subject_of(email_address: str) -> uuid.UUID:
        from app.auth.models import Operator

        async with factory() as session:
            operator = await session.scalar(select(Operator).where(Operator.email == email_address))
            assert operator is not None
            return operator.actor_subject_id

    subject_id = asyncio.run(actor_subject_of(email))

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
    csrf_token = login_response.json()["csrf_token"]
    cookies = dict(login_response.cookies)

    reported_start = "2026-08-20T06:30:00+00:00"
    response = client.post(
        "/investigations",
        headers={"X-CSRF-Token": csrf_token},
        cookies=cookies,
        json={
            "site_id": str(site_id),
            "title": "Revenue dropped on mobile web",
            "symptom_family": "GAM_ADSERVING",
            "description": "Operator noticed ad slots emptying after deploy.",
            "reported_start_at": reported_start,
        },
    )
    assert response.status_code == 200

    # Approved product fields only.
    body = response.json()
    assert set(body.keys()) == {"incident_id", "investigation_key", "status"}
    assert body["status"] == "OPEN"

    incident_id = uuid.UUID(body["incident_id"])
    assert body["investigation_key"] == str(investigation_key_for(incident_id))

    async def read_persisted() -> tuple[Any, ...]:
        async with factory() as session:
            incident = await session.scalar(select(Incident).where(Incident.id == incident_id))
            site = await session.scalar(select(Site).where(Site.id == site_id))
            assert incident is not None and site is not None
            return (
                incident.tenant_id,
                incident.site_id,
                site.publisher_id,
                incident.created_by,
                incident.title,
                incident.description,
                incident.symptom_family,
                incident.status,
                incident.reported_start_at,
                incident.reported_end_at,
            )

    (
        persisted_tenant,
        persisted_site,
        persisted_publisher,
        created_by,
        title,
        description,
        family,
        status,
        start_at,
        end_at,
    ) = asyncio.run(read_persisted())

    # Tenant ownership derived server-side; requested site belongs to it.
    assert persisted_tenant == tenant_id
    assert persisted_site == site_id
    assert persisted_publisher is not None
    # Actor provenance equals the authenticated operator's actor_subject_id —
    # never client-supplied.
    assert created_by == subject_id
    # WHAT round-trips verbatim (EP-020 symptom capture).
    assert title == "Revenue dropped on mobile web"
    assert description == "Operator noticed ad slots emptying after deploy."
    assert family == "GAM_ADSERVING"
    assert status == "OPEN"
    # WHEN keeps canonical temporal uncertainty: known bound preserved exactly;
    # unknown end remains unknown (never fabricated).
    assert start_at == datetime.fromisoformat(reported_start)
    assert start_at.tzinfo is not None and start_at.utcoffset() == UTC.utcoffset(start_at)
    assert end_at is None
