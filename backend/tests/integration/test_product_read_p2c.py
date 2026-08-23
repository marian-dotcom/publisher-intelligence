"""EP-025a P2-C: incident hypothesis depth read contracts (C1)."""

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient

from app.hypotheses.models import Hypothesis
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


def _login(client: TestClient, email: str, tenant_id: uuid.UUID) -> dict[str, str]:
    response = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "tenant_id": str(tenant_id),
        },
    )
    assert response.status_code == 200
    return dict(response.cookies)


async def seed_hypothesis(
    tenant_id: uuid.UUID,
    site_id: uuid.UUID,
    incident_id: uuid.UUID,
    *,
    hypothesis_key: str,
    statement: str,
    status: str,
    rank: int,
) -> uuid.UUID:
    """Smallest legitimate deterministic hypothesis state (EP-023 semantics)."""
    factory = get_session_factory()
    hypothesis_id = uuid.uuid4()
    async with factory() as session, session.begin():
        session.add(
            Hypothesis(
                id=hypothesis_id,
                tenant_id=tenant_id,
                site_id=site_id,
                incident_id=incident_id,
                hypothesis_key=hypothesis_key,
                family="GAM_ADSERVING",
                statement=statement,
                status=status,
                confidence="MEDIUM",
                rank=rank,
                supporting_count=2,
                contradicting_count=1,
                rationale=f"Deterministic rationale for {hypothesis_key}",
                engine_version="hy-v1",
            )
        )
    return hypothesis_id


def test_c1_incident_detail_exposes_ranked_hypothesis_state_with_leading() -> None:
    """C1: incident detail exposes canonical ranked hypotheses incl. LEADING."""
    get_session_factory()

    async def seed_two_tenants() -> tuple[
        str, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, str, uuid.UUID
    ]:
        slug_a = f"c1a-{uuid.uuid4().hex[:8]}"
        slug_b = f"c1b-{uuid.uuid4().hex[:8]}"
        tenant_a = await create_tenant(slug_a)
        site_a = await create_site(tenant_a)
        incident_a = await create_incident(tenant_a, site_a, title="Incident A hypotheses")
        _op, email_a = await create_operator(tenant_a, f"op-{slug_a}@example.com")
        leading_id = await seed_hypothesis(
            tenant_a,
            site_a,
            incident_a,
            hypothesis_key="gam_outage_window",
            statement="GAM ad-serving gap aligns with reported revenue drop.",
            status="LEADING",
            rank=1,
        )
        await seed_hypothesis(
            tenant_a,
            site_a,
            incident_a,
            hypothesis_key="cmp_consent_loss",
            statement="Consent-rate decline reduced bidable traffic.",
            status="CONTENDER",
            rank=2,
        )

        tenant_b = await create_tenant(slug_b)
        site_b = await create_site(tenant_b)
        incident_b = await create_incident(tenant_b, site_b, title="Incident B hypotheses")
        leading_b = await seed_hypothesis(
            tenant_b,
            site_b,
            incident_b,
            hypothesis_key="tenant_b_secret_cause",
            statement="Tenant B private causal statement.",
            status="LEADING",
            rank=1,
        )
        return email_a, tenant_a, incident_a, leading_id, leading_b, "tenant_b_secret_cause", site_b

    (
        email_a,
        tenant_a,
        incident_a,
        leading_a_id,
        leading_b_id,
        key_b,
        site_b,
    ) = asyncio.run(seed_two_tenants())

    client = TestClient(app)
    cookies = _login(client, email_a, tenant_a)

    response = client.get(f"/incidents/{incident_a}", cookies=cookies)
    assert response.status_code == 200

    hypotheses = response.json()["hypotheses"]
    assert len(hypotheses) == 2
    # Deterministic rank order preserved.
    assert [h["rank"] for h in hypotheses] == [1, 2]

    leading = hypotheses[0]
    assert leading["status"] == "LEADING"
    assert leading["confidence"] == "MEDIUM"
    # Stable hypothesis identity.
    assert leading["hypothesis_id"] == str(leading_a_id)
    assert leading["hypothesis_key"] == "gam_outage_window"
    # Canonical persisted fields exposed.
    assert leading["statement"] == "GAM ad-serving gap aligns with reported revenue drop."
    assert leading["rationale"] == "Deterministic rationale for gam_outage_window"
    assert leading["supporting_count"] == 2
    assert leading["contradicting_count"] == 1
    assert leading["engine_version"] == "hy-v1"

    contender = hypotheses[1]
    assert contender["status"] == "CONTENDER"
    assert contender["hypothesis_key"] == "cmp_consent_loss"

    # No tenant B hypothesis data may leak.
    body_text = response.text
    assert str(leading_b_id) not in body_text
    assert key_b not in body_text
    assert "Tenant B private causal statement." not in body_text
    assert str(site_b) not in body_text
