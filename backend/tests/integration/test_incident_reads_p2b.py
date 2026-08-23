"""EP-025a P2-B Incidents: I1 — authenticated tenant can list own incidents."""
import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient

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
    purge = make_purge(get_session_factory)
    asyncio.run(purge())


from app.db.session import get_session_factory  # noqa: E402


def test_i1_authenticated_tenant_can_list_own_incidents() -> None:
    """I1: authenticated tenant can list its own incidents."""
    slug = f"i1-{uuid.uuid4().hex[:8]}"

    async def seed():
        tenant_id = await create_tenant(slug)
        site_id = await create_site(tenant_id)
        incident_id = await create_incident(
            tenant_id, site_id, title="Revenue dropped on mobile"
        )
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
