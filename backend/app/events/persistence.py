import json
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.browser.models import CheckpointRun, DomainEntity, EntityObservation, SeoObservation
from app.events.contracts import EvaluationInput, EventCandidate
from app.events.models import Event, EventEvidenceRef
from app.events.registry import EVENT_RULE_BUNDLE_VERSION, RULES_BY_CODE, definition_id

EVENT_NAMESPACE = uuid.UUID("17e07874-cc3f-4bdd-9385-0ab662fb8fb2")
EVIDENCE_NAMESPACE = uuid.UUID("b50e65ed-ad60-46c1-8e5e-96cf1714b9c5")


class EventStateError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class EventRunResult:
    candidate_count: int
    persisted_count: int
    unsupported_count: int
    skip_reasons: tuple[str, ...]


class EventRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def load_input(
        self, *, tenant_id: uuid.UUID, checkpoint_run_id: uuid.UUID
    ) -> EvaluationInput | None:
        async with self._session_factory() as session:
            current = await session.scalar(
                select(CheckpointRun).where(
                    CheckpointRun.id == checkpoint_run_id, CheckpointRun.tenant_id == tenant_id
                )
            )
            if current is None:
                raise EventStateError("checkpoint ownership mismatch")
            lineage = current.manifest.get("comparison_lineage")
            if not isinstance(lineage, dict) or not lineage.get("previous_checkpoint_run_id"):
                return None
            try:
                previous_id = uuid.UUID(str(lineage["previous_checkpoint_run_id"]))
            except ValueError as error:
                raise EventStateError("invalid comparison lineage") from error
            previous = await session.scalar(
                select(CheckpointRun).where(
                    CheckpointRun.id == previous_id,
                    CheckpointRun.tenant_id == tenant_id,
                    CheckpointRun.site_id == current.site_id,
                )
            )
            if previous is None or previous.completed_at is None or current.completed_at is None:
                raise EventStateError("invalid predecessor ownership or time")
            return EvaluationInput(
                tenant_id=tenant_id,
                site_id=current.site_id,
                monitored_url_id=current.monitored_url_id,
                template_id=current.template_id,
                scenario_id=current.scenario_id,
                previous_checkpoint_run_id=previous.id,
                current_checkpoint_run_id=current.id,
                previous_observed_at=previous.completed_at,
                current_observed_at=current.completed_at,
                previous_status=previous.status,
                current_status=current.status,
                selection_scope=str(lineage.get("selection_scope") or ""),
                previous_state=_mapping(previous.manifest.get("normalized_state")),
                current_state=_mapping(current.manifest.get("normalized_state")),
                previous_gpt=_mapping(previous.manifest.get("gpt")),
                current_gpt=_mapping(current.manifest.get("gpt")),
            )

    async def persist(self, value: EvaluationInput, candidates: tuple[EventCandidate, ...]) -> int:
        confirmed = [
            candidate
            for candidate in candidates
            if candidate.confirmation == "SINGLE_STRONG_OBSERVATION"
        ]
        persisted = 0
        async with self._session_factory() as session, session.begin():
            for candidate in confirmed:
                rule = RULES_BY_CODE[candidate.code]
                scope = {
                    "monitored_url_id": str(value.monitored_url_id),
                    "scenario_id": str(value.scenario_id),
                    "template_id": str(value.template_id),
                }
                key = "|".join(
                    (
                        str(value.tenant_id),
                        EVENT_RULE_BUNDLE_VERSION,
                        str(value.previous_checkpoint_run_id),
                        str(value.current_checkpoint_run_id),
                        candidate.code,
                        candidate.subject,
                        json.dumps(scope, sort_keys=True),
                    )
                )
                event_id = uuid.uuid5(EVENT_NAMESPACE, key)
                result = await session.execute(
                    insert(Event)
                    .values(
                        id=event_id,
                        tenant_id=value.tenant_id,
                        site_id=value.site_id,
                        event_definition_id=definition_id(candidate.code),
                        template_id=value.template_id,
                        started_at=value.current_observed_at,
                        occurred_after_at=value.previous_observed_at,
                        occurred_before_at=value.current_observed_at,
                        time_precision="WINDOW",
                        detected_at=value.current_observed_at,
                        severity=rule.default_severity,
                        observation_confidence="HIGH",
                        status="OBSERVED",
                        source_kind="BROWSER_CHECKPOINT",
                        source_version=EVENT_RULE_BUNDLE_VERSION,
                        scope=scope,
                        summary=candidate.summary[:500],
                        details={
                            "subject": candidate.subject,
                            "before": candidate.before,
                            "after": candidate.after,
                        },
                    )
                    .on_conflict_do_nothing()
                    .returning(Event.id)
                )
                if result.scalar_one_or_none() is not None:
                    persisted += 1
                for source_id, relation in (
                    (value.previous_checkpoint_run_id, "BEFORE"),
                    (value.current_checkpoint_run_id, "AFTER"),
                ):
                    await _insert_ref(
                        session, value.tenant_id, event_id, "CHECKPOINT_RUN", source_id, relation
                    )
                if candidate.code == "CANONICAL_CHANGED":
                    for run_id, relation in (
                        (value.previous_checkpoint_run_id, "BEFORE"),
                        (value.current_checkpoint_run_id, "AFTER"),
                    ):
                        seo_id = await session.scalar(
                            select(SeoObservation.id).where(
                                SeoObservation.tenant_id == value.tenant_id,
                                SeoObservation.checkpoint_run_id == run_id,
                            )
                        )
                        if seo_id is not None:
                            await _insert_ref(
                                session,
                                value.tenant_id,
                                event_id,
                                "SEO_OBSERVATION",
                                seo_id,
                                relation,
                            )
                else:
                    entity = await session.scalar(
                        select(DomainEntity).where(
                            DomainEntity.tenant_id == value.tenant_id,
                            DomainEntity.site_id == value.site_id,
                            DomainEntity.stable_key == candidate.subject,
                        )
                    )
                    if entity is not None:
                        for run_id, relation in (
                            (value.previous_checkpoint_run_id, "BEFORE"),
                            (value.current_checkpoint_run_id, "AFTER"),
                        ):
                            observation_id = await session.scalar(
                                select(EntityObservation.id).where(
                                    EntityObservation.tenant_id == value.tenant_id,
                                    EntityObservation.checkpoint_run_id == run_id,
                                    EntityObservation.entity_id == entity.id,
                                )
                            )
                            if observation_id is not None:
                                await _insert_ref(
                                    session,
                                    value.tenant_id,
                                    event_id,
                                    "ENTITY_OBSERVATION",
                                    observation_id,
                                    relation,
                                )
        return persisted


def _mapping(value: object) -> dict[str, Any]:
    return {str(key): item for key, item in value.items()} if isinstance(value, dict) else {}


async def _insert_ref(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    event_id: uuid.UUID,
    kind: str,
    source_id: uuid.UUID,
    relation: str,
) -> None:
    ref_id = uuid.uuid5(EVIDENCE_NAMESPACE, f"{event_id}|{kind}|{source_id}|{relation}")
    await session.execute(
        insert(EventEvidenceRef)
        .values(
            id=ref_id,
            tenant_id=tenant_id,
            event_id=event_id,
            evidence_kind=kind,
            source_id=source_id,
            relation=relation,
        )
        .on_conflict_do_nothing()
    )
