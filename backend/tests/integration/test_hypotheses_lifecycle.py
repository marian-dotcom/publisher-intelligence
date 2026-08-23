import uuid
from datetime import UTC, datetime

import pytest

from app.browser.models import Publisher, Site
from app.db.models import Tenant
from app.db.session import get_session_factory
from app.hypotheses.persistence import HypothesisRepository
from app.incidents.contracts import InvestigationStateError
from app.incidents.models import (
    Incident,
)
from tests.integration.purge import PURGE_ORDER


@pytest.mark.asyncio
async def test_ranked_set_replacement_is_atomic_and_tenant_scoped() -> None:
    factory = get_session_factory()
    repository = HypothesisRepository(factory)
    tenant_id, other_tenant = uuid.uuid4(), uuid.uuid4()
    publisher_id, site_id = uuid.uuid4(), uuid.uuid4()
    incident_id = uuid.uuid4()
    async with factory() as session, session.begin():
        session.add(Tenant(id=tenant_id, slug=f"hyp-{tenant_id.hex[:8]}", name="Hyp Tenant"))
        await session.flush()
        session.add(
            Publisher(
                id=publisher_id,
                tenant_id=tenant_id,
                name="Hyp Publisher",
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
                name="Hyp Site",
                canonical_domain=f"{site_id.hex}.example.com",
                canonical_scheme="https",
                timezone="UTC",
                status="ACTIVE",
            )
        )
        await session.flush()
        from app.events.models import Event
        from app.events.registry import definition_id

        definition_id_value = definition_id("NOINDEX_ADDED")
        event_a_id, event_b_id = uuid.uuid4(), uuid.uuid4()
        for eid in (event_a_id, event_b_id):
            session.add(
                Event(
                    id=eid,
                    tenant_id=tenant_id,
                    site_id=site_id,
                    event_definition_id=definition_id_value,
                    template_id=None,
                    started_at=datetime.now(UTC),
                    occurred_after_at=None,
                    occurred_before_at=datetime.now(UTC),
                    time_precision="WINDOW",
                    detected_at=datetime.now(UTC),
                    severity="LOW",
                    observation_confidence="HIGH",
                    status="RECORDED",
                    source_kind="BROWSER_CHECKPOINT",
                    source_version="e3-v1",
                    condition_key=None,
                    scope={"config_type": "ROBOTS_TXT"},
                    summary="lifecycle fixture event",
                    details={},
                )
            )
        await session.flush()
        session.add(
            Incident(
                id=incident_id,
                tenant_id=tenant_id,
                publisher_id=publisher_id,
                site_id=site_id,
                title="Ranked incident",
                symptom_family="GAM_ADSERVING",
                description="d",
                opened_at=datetime.now(UTC),
                status="OPEN",
            )
        )

    ranked = [
        {
            "hypothesis_key": "GAM_ADSERVING:degradation",
            "family": "GAM_ADSERVING",
            "statement": "GAM degradation explains symptom",
            "status": "LEADING",
            "confidence": "HIGH",
            "rank": 1,
            "supporting_count": 2,
            "contradicting_count": 0,
            "rationale": "rank 1: 2 supporting typed evidence items (score 4)",
        },
        {
            "hypothesis_key": "SEARCH_DISCOVER:degradation",
            "family": "SEARCH_DISCOVER",
            "statement": "Search degradation candidate",
            "status": "WEAKENED",
            "confidence": "LOW",
            "rank": 2,
            "supporting_count": 0,
            "contradicting_count": 1,
            "rationale": "rank 2: contradicted by unaffected segment",
        },
    ]
    links = {
        "GAM_ADSERVING:degradation": [
            {
                "evidence_key": "ev-1|SUPPORTS",
                "source_kind": "EVENT",
                "event_id": event_a_id,
                "manual_note_id": None,
                "relation": "SUPPORTS",
                "weight": 2,
                "reason": "typed relation",
            }
        ],
        "SEARCH_DISCOVER:degradation": [
            {
                "evidence_key": "ev-2|CONTRADICTS",
                "source_kind": "EVENT",
                "event_id": event_b_id,
                "manual_note_id": None,
                "relation": "CONTRADICTS",
                "weight": 1,
                "reason": "unaffected segment",
            }
        ],
    }
    stored = await repository.replace_ranked_set(
        tenant_id=tenant_id,
        incident_id=incident_id,
        ranked=ranked,
        evidence_links=links,
    )
    assert stored == 2

    rows = await repository.list_for_incident(tenant_id=tenant_id, incident_id=incident_id)
    assert [row.status for row in rows] == ["LEADING", "WEAKENED"]

    from tests.integration.purge import make_purge

    await make_purge(get_session_factory)()

    with pytest.raises(InvestigationStateError):
        await repository.replace_ranked_set(
            tenant_id=other_tenant,
            incident_id=incident_id,
            ranked=ranked,
            evidence_links=links,
        )


def test_purge_order_covers_foundation_tables() -> None:

    for table in ("hypotheses", "hypothesis_evidence", "incidents", "tenants"):
        assert table in PURGE_ORDER
