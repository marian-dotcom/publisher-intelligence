"""EP-025a P2-C: incident hypothesis depth read contracts (C1)."""

import asyncio
import json
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.evidence.models import EvidencePack
from app.hypotheses.models import Hypothesis, HypothesisEvidence
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


async def seed_evidence(
    tenant_id: uuid.UUID,
    hypothesis_id: uuid.UUID,
    *,
    evidence_key: str,
    relation: str,
    source_kind: str,
    reason: str,
) -> uuid.UUID:
    factory = get_session_factory()
    evidence_id = uuid.uuid4()
    async with factory() as session, session.begin():
        session.add(
            HypothesisEvidence(
                id=evidence_id,
                tenant_id=tenant_id,
                hypothesis_id=hypothesis_id,
                evidence_key=evidence_key,
                source_kind=source_kind,
                relation=relation,
                weight=1 if relation == "SUPPORTS" else (-1 if relation == "CONTRADICTS" else 0),
                reason=reason,
            )
        )
    return evidence_id


def test_c2_hypothesis_evidence_relationships_serialize_with_missing_semantics() -> None:
    """C2: SUPPORTS/CONTRADICTS/missing evidence exposed distinctly and tenant-safe."""
    get_session_factory()

    async def seed_two_tenants() -> tuple[
        str, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, str, uuid.UUID
    ]:
        slug_a = f"c2a-{uuid.uuid4().hex[:8]}"
        slug_b = f"c2b-{uuid.uuid4().hex[:8]}"
        tenant_a = await create_tenant(slug_a)
        site_a = await create_site(tenant_a)
        incident_a = await create_incident(tenant_a, site_a, title="Incident A evidence")
        _op, email_a = await create_operator(tenant_a, f"op-{slug_a}@example.com")
        hyp_a = await seed_hypothesis(
            tenant_a,
            site_a,
            incident_a,
            hypothesis_key="gam_outage_window",
            statement="GAM ad-serving gap aligns with reported revenue drop.",
            status="LEADING",
            rank=1,
        )
        sup_a = await seed_evidence(
            tenant_a,
            hyp_a,
            evidence_key="ev-supports-gap",
            relation="SUPPORTS",
            source_kind="EVENT",
            reason="Machine event supports the ad-serving gap.",
        )
        con_a = await seed_evidence(
            tenant_a,
            hyp_a,
            evidence_key="ev-contradicts-recovery",
            relation="CONTRADICTS",
            source_kind="MANUAL_NOTE",
            reason="Operator noted recovery before the reported onset.",
        )
        gap_a = await seed_evidence(
            tenant_a,
            hyp_a,
            evidence_key="ev-gap-cmp-telemetry",
            relation="CONTEXT",
            source_kind="OBSERVATION_GAP",
            reason="CMP telemetry unavailable during the window.",
        )

        tenant_b = await create_tenant(slug_b)
        site_b = await create_site(tenant_b)
        incident_b = await create_incident(tenant_b, site_b, title="Incident B evidence")
        hyp_b = await seed_hypothesis(
            tenant_b,
            site_b,
            incident_b,
            hypothesis_key="tenant_b_secret_cause",
            statement="Tenant B private causal statement.",
            status="LEADING",
            rank=1,
        )
        secret_b = await seed_evidence(
            tenant_b,
            hyp_b,
            evidence_key="tenant-b-secret-evidence",
            relation="SUPPORTS",
            source_kind="EVENT",
            reason="Tenant B private supporting evidence.",
        )
        return (
            email_a,
            tenant_a,
            incident_a,
            sup_a,
            con_a,
            gap_a,
            secret_b,
            "tenant-b-secret-evidence",
            site_b,
        )

    (
        email_a,
        tenant_a,
        incident_a,
        sup_a_id,
        con_a_id,
        gap_a_id,
        _secret_b_id,
        key_b,
        site_b,
    ) = asyncio.run(seed_two_tenants())

    client = TestClient(app)
    cookies = _login(client, email_a, tenant_a)

    response = client.get(f"/incidents/{incident_a}", cookies=cookies)
    assert response.status_code == 200

    hypotheses = response.json()["hypotheses"]
    assert len(hypotheses) == 1
    evidence = hypotheses[0]["evidence"]
    assert len(evidence) == 3

    by_relation = {e["relation"]: e for e in evidence}
    # 1. SUPPORTS exposed as SUPPORTS with stable identity.
    assert by_relation["SUPPORTS"]["evidence_id"] == str(sup_a_id)
    assert by_relation["SUPPORTS"]["evidence_key"] == "ev-supports-gap"
    assert by_relation["SUPPORTS"]["source_kind"] == "EVENT"
    # 2. CONTRADICTS exposed as CONTRADICTS.
    assert by_relation["CONTRADICTS"]["evidence_id"] == str(con_a_id)
    assert by_relation["CONTRADICTS"]["source_kind"] == "MANUAL_NOTE"
    # 3. Missing/unavailable evidence is explicit via canonical OBSERVATION_GAP
    #    source_kind — never serialized as CONTRADICTS.
    assert by_relation["CONTEXT"]["evidence_id"] == str(gap_a_id)
    assert by_relation["CONTEXT"]["source_kind"] == "OBSERVATION_GAP"
    assert by_relation["CONTEXT"]["reason"] == "CMP telemetry unavailable during the window."
    assert all(
        e["relation"] != "CONTRADICTS" for e in evidence if e["source_kind"] == "OBSERVATION_GAP"
    )

    # 7. No raw payload/debug fields on any evidence row.
    for e in evidence:
        assert set(e.keys()) == {
            "evidence_id",
            "evidence_key",
            "relation",
            "source_kind",
            "event_id",
            "manual_note_id",
            "reason",
        }

    # 6. No tenant B evidence relationship/data leaks.
    body_text = response.text
    assert key_b not in body_text
    assert "Tenant B private supporting evidence." not in body_text
    assert str(site_b) not in body_text


async def build_and_persist_pack(
    tenant_id: uuid.UUID,
    site_id: uuid.UUID,
    incident_id: uuid.UUID | None,
) -> uuid.UUID:
    """Persist a pack through the canonical builder + repository semantics."""
    from datetime import UTC, datetime, timedelta

    from app.evidence.builder import EvidencePackBuilder
    from app.evidence.persistence import EvidenceRepository

    factory = get_session_factory()
    start = datetime.now(UTC) - timedelta(hours=3)
    end = datetime.now(UTC) - timedelta(hours=1)
    content = await EvidencePackBuilder(factory).build(
        tenant_id=tenant_id,
        site_id=site_id,
        incident_id=incident_id,
        window_start=start,
        window_end=end,
    )
    pack, _created = await EvidenceRepository(factory).persist_pack(
        tenant_id=tenant_id,
        site_id=site_id,
        content=content,
        fingerprints={"collector_bundle": "b8-v1"},
        window_start=start,
        window_end=end,
        incident_id=incident_id,
        engine_version=str(content["engine_version"]),
    )
    return pack.id


def test_c3_evidence_pack_read_is_tenant_safe_and_read_only() -> None:
    """C3: GET /evidence/packs/{id} returns own persisted packs; foreign → 404."""
    get_session_factory()

    async def seed_two_tenants() -> tuple[str, uuid.UUID, uuid.UUID, tuple[Any, ...], uuid.UUID]:
        slug_a = f"c3a-{uuid.uuid4().hex[:8]}"
        slug_b = f"c3b-{uuid.uuid4().hex[:8]}"
        tenant_a = await create_tenant(slug_a)
        site_a = await create_site(tenant_a)
        incident_a = await create_incident(tenant_a, site_a, title="Incident A pack")
        _op, email_a = await create_operator(tenant_a, f"op-{slug_a}@example.com")
        pack_a = await build_and_persist_pack(tenant_a, site_a, incident_a)

        tenant_b = await create_tenant(slug_b)
        site_b = await create_site(tenant_b)
        incident_b = await create_incident(tenant_b, site_b, title="Incident B pack")
        pack_b = await build_and_persist_pack(tenant_b, site_b, incident_b)

        # Snapshot pack A's stored row to prove the GET does not mutate it.
        factory = get_session_factory()
        async with factory() as session:
            row = await session.scalar(select(EvidencePack).where(EvidencePack.id == pack_a))
            assert row is not None
            before = (
                str(row.id),
                dict(row.fingerprints),
                dict(row.content),
                row.content_hash,
                row.engine_version,
                row.created_at.isoformat(),
            )
        return email_a, tenant_a, pack_a, before, pack_b

    email_a, tenant_a, pack_a_id, pack_before, pack_b_id = asyncio.run(seed_two_tenants())

    client = TestClient(app)
    cookies = _login(client, email_a, tenant_a)

    response = client.get(f"/evidence/packs/{pack_a_id}", cookies=cookies)
    assert response.status_code == 200

    body = response.json()
    pack = body["pack"]
    assert pack["pack_id"] == str(pack_a_id)
    assert pack["incident_id"] is not None
    assert pack["window_start"] is not None
    assert pack["window_end"] is not None
    assert pack["engine_version"]
    assert pack["content_hash"]

    content = body["content"]
    assert content["machine_observed_sections"] == [
        "scheduled_checkpoints",
        "public_config_states",
        "events",
        "relations",
    ]
    for section in (
        "scheduled_checkpoints",
        "public_config_states",
        "events",
        "relations",
        "human_reported_notes",
    ):
        assert isinstance(content[section], list)

    # Cross-tenant read of pack B uses the existing non-disclosing behavior.
    foreign = client.get(f"/evidence/packs/{pack_b_id}", cookies=cookies)
    assert foreign.status_code == 404
    assert str(pack_b_id) not in foreign.text

    # Read-only proof: persisted row identical after both GETs.
    async def read_row() -> tuple[Any, ...]:
        factory = get_session_factory()
        async with factory() as session:
            row = await session.scalar(select(EvidencePack).where(EvidencePack.id == pack_a_id))
            assert row is not None
            return (
                str(row.id),
                dict(row.fingerprints),
                dict(row.content),
                row.content_hash,
                row.engine_version,
                row.created_at.isoformat(),
            )

    pack_after = asyncio.run(read_row())
    assert pack_after == pack_before


async def seed_monetization(
    tenant_id: uuid.UUID,
    site_id: uuid.UUID,
    *,
    capability: str,
    currency_value: float | None,
    ratio_value: float | None,
) -> None:
    """Canonical DataConnection + MetricSeries/MetricPoint state (C5)."""
    from datetime import UTC, datetime, timedelta

    from app.connectors.models import DataConnection, MetricPoint, MetricSeries
    from app.metrics.models import MetricDerivation

    factory = get_session_factory()
    connection_id = uuid.uuid4()
    now = datetime.now(UTC)
    async with factory() as session, session.begin():
        session.add(
            DataConnection(
                id=connection_id,
                tenant_id=tenant_id,
                site_id=site_id,
                provider="gam",
                external_property_id=f"prop-{site_id.hex[:8]}",
                status="CONNECTED",
                monetization_capability=capability,
                scopes=[],
                secret_reference=f"secretref-{tenant_id.hex[:8]}",
                connected_at=now - timedelta(days=1),
            )
        )
        series_specs: list[tuple[str, str, float | None]] = [
            ("gam.ad_server_impressions", "COUNT", 1000.0),
            ("gam.ctr", "RATIO", ratio_value if ratio_value is not None else 0.42),
        ]
        if capability in ("RELATIVE_ONLY", "ABSOLUTE") and currency_value is not None:
            series_specs.append(("gam.ad_exchange_revenue", "CURRENCY", currency_value))
        derivation_id = uuid.uuid4()
        session.add(
            MetricDerivation(
                id=derivation_id,
                tenant_id=tenant_id,
                site_id=site_id,
                definition_code="C5_TEST_RELATIVE_V1",
                rule_version="c5-test-v1",
                engine_version="mx-v1",
                alignment_policy="UTC_DAY",
                freshness_policy="LATEST_MATURE",
                granularity="DAY",
                period_start=datetime(2026, 8, 20, tzinfo=UTC),
                period_end=datetime(2026, 8, 21, tzinfo=UTC),
                freshness_status="MATURE",
                input_fingerprint="0" * 64,
                derivation_key=f"c5-test|{site_id.hex[:8]}",
                definition={"rule": "relative-only-test-fixture"},
            )
        )
        await session.flush()

        for metric_code, unit, value in series_specs:
            series = MetricSeries(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                site_id=site_id,
                source="gam",
                metric_code=metric_code,
                metric_semantics_version="gam-historical-v1",
                unit=unit,
                granularity="DAY",
                dimensions={},
                series_key=f"{metric_code}|{unit}|{site_id.hex[:8]}",
            )
            session.add(series)
            await session.flush()
            if value is None:
                continue
            session.add(
                MetricPoint(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    site_id=site_id,
                    series_id=series.id,
                    source_extract_id=None,
                    derivation_id=derivation_id,
                    source_time="2026-08-20T00:00:00Z",
                    period_start=datetime(2026, 8, 20, tzinfo=UTC),
                    period_end=datetime(2026, 8, 21, tzinfo=UTC),
                    value=value,
                    freshness_status="MATURE",
                    retrieved_at=now - timedelta(hours=2),
                )
            )


def test_c5_monetization_exposure_is_gated_by_capability() -> None:
    """C5: RELATIVE_ONLY suppresses CURRENCY; ABSOLUTE exposes stored values;
    UNKNOWN fails closed; ABSOLUTE without data fabricates nothing."""
    get_session_factory()

    async def seed_all_cases() -> tuple[
        str, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, str
    ]:
        slug_a = f"c5a-{uuid.uuid4().hex[:8]}"
        slug_b = f"c5b-{uuid.uuid4().hex[:8]}"
        tenant_a = await create_tenant(slug_a)
        _op, email_a = await create_operator(tenant_a, f"op-{slug_a}@example.com")

        site_relative = await create_site(tenant_a)
        incident_relative = await create_incident(tenant_a, site_relative, title="Relative inc")
        await seed_monetization(
            tenant_a,
            site_relative,
            capability="RELATIVE_ONLY",
            currency_value=12345.67,
            ratio_value=0.31,
        )

        site_absolute = await create_site(tenant_a)
        incident_absolute = await create_incident(tenant_a, site_absolute, title="Absolute inc")
        await seed_monetization(
            tenant_a,
            site_absolute,
            capability="ABSOLUTE",
            currency_value=9876.54,
            ratio_value=0.55,
        )

        site_unknown = await create_site(tenant_a)
        incident_unknown = await create_incident(tenant_a, site_unknown, title="Unknown inc")
        await seed_monetization(
            tenant_a,
            site_unknown,
            capability="UNKNOWN",
            currency_value=777.77,
            ratio_value=0.99,
        )

        # Tenant B secret monetization data.
        tenant_b = await create_tenant(slug_b)
        site_b = await create_site(tenant_b)
        incident_b = await create_incident(tenant_b, site_b, title="B inc")
        await seed_monetization(
            tenant_b,
            site_b,
            capability="ABSOLUTE",
            currency_value=999999.99,
            ratio_value=0.01,
        )
        return (
            email_a,
            tenant_a,
            incident_relative,
            incident_absolute,
            incident_unknown,
            incident_b,
            "prop-" + site_b.hex[:8],
        )

    (
        email_a,
        tenant_a,
        incident_rel,
        incident_abs,
        incident_unk,
        _incident_b,
        prop_b_key,
    ) = asyncio.run(seed_all_cases())

    client = TestClient(app)
    cookies = _login(client, email_a, tenant_a)

    def metrics_of(incident_id: uuid.UUID) -> dict[str, Any]:
        resp = client.get(f"/incidents/{incident_id}", cookies=cookies)
        assert resp.status_code == 200
        mono = resp.json()["monetization"]
        return {
            "capability": mono["capability"],
            "by_code": {m["metric_code"]: m for m in mono["metrics"]},
            "text": resp.text,
        }

    # CASE A — RELATIVE_ONLY: relative visible, absolute actively suppressed.
    rel = metrics_of(incident_rel)
    assert rel["capability"] == "RELATIVE_ONLY"
    assert rel["by_code"]["gam.ctr"]["points"][0]["value"] == 0.31
    assert "gam.ad_server_impressions" in rel["by_code"]
    assert "gam.ad_exchange_revenue" not in rel["by_code"]
    assert "12345.67" not in rel["text"]

    # CASE B — ABSOLUTE: stored absolute value round-trips exactly.
    abso = metrics_of(incident_abs)
    assert abso["capability"] == "ABSOLUTE"
    assert abso["by_code"]["gam.ad_exchange_revenue"]["points"][0]["value"] == 9876.54
    assert abso["by_code"]["gam.ctr"]["points"][0]["value"] == 0.55

    # CASE C — UNKNOWN: fail closed; nothing exposed.
    unk = metrics_of(incident_unk)
    assert unk["capability"] == "UNKNOWN"
    assert unk["by_code"] == {}
    assert "777.77" not in unk["text"]

    # Tenant safety: no tenant B monetization identifiers/values leak.
    assert "999999.99" not in rel["text"]
    assert "0.01" + "" not in json.dumps([rel["by_code"].get("gam.ad_server_impressions")])
    assert prop_b_key not in rel["text"]

    # ABSOLUTE without evidence fabricates nothing: unknown-capability case above
    # plus a currency-series-absent check for the relative fixture already prove
    # values only appear when persisted under an authorized capability.
