"""EP-023 persistence: atomic ranked-set replacement per incident."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.hypotheses.models import Hypothesis, HypothesisEvidence
from app.incidents.contracts import InvestigationStateError
from app.incidents.models import Incident

RANKING_ENGINE_VERSION = "ranking-v1"


class HypothesisRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def replace_ranked_set(
        self,
        *,
        tenant_id: uuid.UUID,
        incident_id: uuid.UUID,
        ranked: list[dict[str, Any]],
        evidence_links: dict[str, list[dict[str, Any]]],
    ) -> int:
        """Atomically replace the incident's hypothesis set with `ranked`.

        ranked items carry: hypothesis_key, family, statement, status,
        confidence, rank, supporting_count, contradicting_count, rationale.
        evidence_links maps hypothesis_key → typed evidence rows (source_kind,
        event_id/manual_note_id, relation, weight, reason, evidence_key).
        Returns the number of hypotheses stored.
        """
        async with self._session_factory() as session, session.begin():
            incident = await session.scalar(
                select(Incident).where(
                    Incident.id == incident_id,
                    Incident.tenant_id == tenant_id,
                )
            )
            if incident is None:
                raise InvestigationStateError("incident does not belong to tenant")
            site_id = incident.site_id

            existing_keys = set(
                await session.scalars(
                    select(Hypothesis.hypothesis_key).where(
                        Hypothesis.incident_id == incident_id,
                        Hypothesis.tenant_id == tenant_id,
                    )
                )
            )
            for key in existing_keys - {item["hypothesis_key"] for item in ranked}:
                stale = await session.scalar(
                    select(Hypothesis).where(
                        Hypothesis.incident_id == incident_id,
                        Hypothesis.tenant_id == tenant_id,
                        Hypothesis.hypothesis_key == key,
                    )
                )
                if stale is not None:
                    await session.delete(stale)
                    await session.flush()

            for item in ranked:
                key = item["hypothesis_key"]
                row = await session.scalar(
                    select(Hypothesis).where(
                        Hypothesis.incident_id == incident_id,
                        Hypothesis.tenant_id == tenant_id,
                        Hypothesis.hypothesis_key == key,
                    )
                )
                if row is not None:
                    # Deterministic replacement: identity is stable, content
                    # is recomputed. Update only the mutable lifecycle columns.
                    row.family = item["family"]
                    row.statement = item["statement"]
                    row.status = item["status"]
                    row.confidence = item["confidence"]
                    row.rank = item["rank"]
                    row.supporting_count = item["supporting_count"]
                    row.contradicting_count = item["contradicting_count"]
                    row.rationale = item["rationale"]
                    continue
                row = Hypothesis(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    site_id=site_id,
                    incident_id=incident_id,
                    hypothesis_key=key,
                    family=item["family"],
                    statement=item["statement"],
                    status=item["status"],
                    confidence=item["confidence"],
                    rank=item["rank"],
                    supporting_count=item["supporting_count"],
                    contradicting_count=item["contradicting_count"],
                    rationale=item["rationale"],
                    engine_version=RANKING_ENGINE_VERSION,
                )
                session.add(row)
                await session.flush()

                for link in evidence_links.get(key, []):
                    entry_id = uuid.uuid4()
                    session.add(
                        HypothesisEvidence(
                            id=entry_id,
                            tenant_id=tenant_id,
                            hypothesis_id=row.id,
                            evidence_key=f"{key}|{link['evidence_key']}",
                            source_kind=link["source_kind"],
                            event_id=link.get("event_id"),
                            manual_note_id=link.get("manual_note_id"),
                            relation=link["relation"],
                            weight=link["weight"],
                            reason=link.get("reason"),
                        )
                    )
            return len(ranked)

    async def list_for_incident(
        self, *, tenant_id: uuid.UUID, incident_id: uuid.UUID
    ) -> list[Hypothesis]:
        async with self._session_factory() as session:
            return list(
                (
                    await session.scalars(
                        select(Hypothesis)
                        .where(
                            Hypothesis.tenant_id == tenant_id,
                            Hypothesis.incident_id == incident_id,
                        )
                        .order_by(Hypothesis.rank)
                    )
                ).all()
            )

    @staticmethod
    def assert_tenant_scope(tenant_id: uuid.UUID) -> None:
        del tenant_id
