import json
import uuid
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.browser.models import (
    CheckpointRun,
    CheckpointWindow,
    DomainEntity,
    EntityObservation,
    GPTSlotObservation,
    JavaScriptErrorObservation,
    SeoObservation,
)
from app.events.contracts import EvaluationInput, EventCandidate, EvidencePointer
from app.events.lifecycle import condition_key, higher_severity, normalized_scope
from app.events.models import Event, EventEvidenceRef
from app.events.registry import RULES_BY_CODE, definition_id

EVENT_NAMESPACE = uuid.UUID("17e07874-cc3f-4bdd-9385-0ab662fb8fb2")
EVIDENCE_NAMESPACE = uuid.UUID("b50e65ed-ad60-46c1-8e5e-96cf1714b9c5")
VALID_RELATIONS = {
    "BEFORE",
    "AFTER",
    "TRIGGER_BEFORE",
    "TRIGGER_AFTER",
    "SUPPORTING",
    "RECOVERY",
}


class EventStateError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class EventRunResult:
    candidate_count: int
    persisted_count: int
    unsupported_count: int
    skip_reasons: tuple[str, ...]
    updated_count: int = 0
    resolved_count: int = 0


@dataclass(frozen=True, slots=True)
class PersistenceResult:
    created_count: int = 0
    updated_count: int = 0
    resolved_count: int = 0


class EventRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def load_input(
        self, *, tenant_id: uuid.UUID, checkpoint_run_id: uuid.UUID
    ) -> EvaluationInput | None:
        async with self._session_factory() as session:
            current = await session.scalar(
                select(CheckpointRun).where(
                    CheckpointRun.id == checkpoint_run_id,
                    CheckpointRun.tenant_id == tenant_id,
                )
            )
            if current is None:
                raise EventStateError("checkpoint ownership mismatch")
            return await self._build_input(session, current)

    async def load_window_inputs(
        self, *, tenant_id: uuid.UUID, checkpoint_run_id: uuid.UUID
    ) -> tuple[EvaluationInput, ...]:
        async with self._session_factory() as session:
            current = await session.scalar(
                select(CheckpointRun).where(
                    CheckpointRun.id == checkpoint_run_id,
                    CheckpointRun.tenant_id == tenant_id,
                )
            )
            if current is None:
                raise EventStateError("checkpoint ownership mismatch")
            window = await session.scalar(
                select(CheckpointWindow).where(
                    CheckpointWindow.id == current.checkpoint_window_id,
                    CheckpointWindow.tenant_id == tenant_id,
                    CheckpointWindow.site_id == current.site_id,
                )
            )
            if window is None or window.status != "COMPLETE":
                return ()
            runs = list(
                (
                    await session.scalars(
                        select(CheckpointRun)
                        .where(
                            CheckpointRun.tenant_id == tenant_id,
                            CheckpointRun.site_id == current.site_id,
                            CheckpointRun.checkpoint_window_id == current.checkpoint_window_id,
                            CheckpointRun.status.in_(("COMPLETE", "PARTIAL")),
                        )
                        .order_by(CheckpointRun.id)
                    )
                ).all()
            )
            values: list[EvaluationInput] = []
            for run in runs:
                value = await self._build_input(session, run)
                if value is not None:
                    values.append(value)
            return tuple(values)

    async def _build_input(
        self, session: AsyncSession, current: CheckpointRun
    ) -> EvaluationInput | None:
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
                CheckpointRun.tenant_id == current.tenant_id,
                CheckpointRun.site_id == current.site_id,
                CheckpointRun.scenario_id == current.scenario_id,
                CheckpointRun.monitored_url_id == current.monitored_url_id,
            )
        )
        if previous is None or previous.completed_at is None or current.completed_at is None:
            raise EventStateError("invalid predecessor ownership or time")

        prior: CheckpointRun | None = None
        previous_lineage = previous.manifest.get("comparison_lineage")
        if (
            isinstance(previous_lineage, dict)
            and previous_lineage.get("selection_scope") == "EXACT_MONITORED_URL"
            and previous_lineage.get("previous_checkpoint_run_id")
        ):
            try:
                prior_id = uuid.UUID(str(previous_lineage["previous_checkpoint_run_id"]))
            except ValueError as error:
                raise EventStateError("invalid prior comparison lineage") from error
            prior = await session.scalar(
                select(CheckpointRun).where(
                    CheckpointRun.id == prior_id,
                    CheckpointRun.tenant_id == current.tenant_id,
                    CheckpointRun.site_id == current.site_id,
                    CheckpointRun.scenario_id == current.scenario_id,
                    CheckpointRun.monitored_url_id == current.monitored_url_id,
                )
            )
            if prior is not None and prior.completed_at is None:
                prior = None

        window = await session.scalar(
            select(CheckpointWindow).where(
                CheckpointWindow.id == current.checkpoint_window_id,
                CheckpointWindow.tenant_id == current.tenant_id,
                CheckpointWindow.site_id == current.site_id,
            )
        )
        if window is None:
            raise EventStateError("checkpoint window ownership mismatch")

        return EvaluationInput(
            tenant_id=current.tenant_id,
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
            prior_checkpoint_run_id=prior.id if prior is not None else None,
            prior_observed_at=prior.completed_at if prior is not None else None,
            prior_status=prior.status if prior is not None else None,
            prior_state=(
                _mapping(prior.manifest.get("normalized_state")) if prior is not None else {}
            ),
            prior_gpt=_mapping(prior.manifest.get("gpt")) if prior is not None else {},
            checkpoint_window_id=window.id,
            checkpoint_window_status=window.status,
        )

    async def persist(
        self, value: EvaluationInput, candidates: tuple[EventCandidate, ...]
    ) -> PersistenceResult:
        created = updated = resolved = 0
        async with self._session_factory() as session, session.begin():
            for candidate in candidates:
                rule = RULES_BY_CODE[candidate.code]
                if candidate.action == "PENDING":
                    continue
                if candidate.action == "RECORD":
                    if rule.kind != "POINT":
                        raise EventStateError("condition candidate cannot use point persistence")
                    was_created = await self._persist_point(session, value, candidate)
                    created += int(was_created)
                    continue
                if rule.kind != "CONDITION":
                    raise EventStateError("point candidate cannot use condition lifecycle")
                if candidate.action == "RESOLVE_CONDITION":
                    was_resolved = await self._resolve_condition(session, value, candidate)
                    resolved += int(was_resolved)
                    continue
                result = await self._persist_condition(session, value, candidate)
                created += int(result == "CREATED")
                updated += int(result == "UPDATED")
        return PersistenceResult(created, updated, resolved)

    async def _persist_point(
        self, session: AsyncSession, value: EvaluationInput, candidate: EventCandidate
    ) -> bool:
        rule = RULES_BY_CODE[candidate.code]
        scope = normalized_scope(candidate.scope or _exact_scope(value))
        event_id = _point_event_id(value, candidate, scope)
        detected_at = candidate.detected_at or value.current_observed_at
        occurred_before_at = candidate.occurred_before_at or value.current_observed_at
        result = await session.execute(
            insert(Event)
            .values(
                id=event_id,
                tenant_id=value.tenant_id,
                site_id=value.site_id,
                event_definition_id=definition_id(candidate.code),
                template_id=_scope_uuid(candidate.scope, "template_id"),
                started_at=occurred_before_at,
                occurred_after_at=candidate.occurred_after_at or value.previous_observed_at,
                occurred_before_at=occurred_before_at,
                time_precision="WINDOW",
                detected_at=detected_at,
                severity=candidate.severity or rule.default_severity,
                observation_confidence="HIGH",
                status="RECORDED",
                source_kind="BROWSER_CHECKPOINT",
                source_version=rule.rule_version,
                condition_key=None,
                scope=scope,
                summary=candidate.summary[:500],
                details={
                    "subject": candidate.subject,
                    "before": candidate.before,
                    "after": candidate.after,
                    "affected_url_count": candidate.affected_url_count,
                    "valid_url_count": candidate.valid_url_count,
                },
            )
            .on_conflict_do_nothing()
            .returning(Event.id)
        )
        created = result.scalar_one_or_none() is not None
        await self._insert_candidate_evidence(session, value, event_id, candidate.evidence)
        return created

    async def _persist_condition(
        self, session: AsyncSession, value: EvaluationInput, candidate: EventCandidate
    ) -> str:
        rule = RULES_BY_CODE[candidate.code]
        scope = normalized_scope(candidate.scope)
        key = condition_key(
            tenant_id=value.tenant_id,
            site_id=value.site_id,
            event_code=candidate.code,
            subject=candidate.subject,
            scope=scope,
        )
        active = await self._active_condition(session, value, key)
        if active is None and candidate.action == "SUPPORT_CONDITION":
            return "IGNORED"
        if active is None:
            detected_at = candidate.detected_at or value.current_observed_at
            occurred_before_at = candidate.occurred_before_at or detected_at
            event_id = _condition_event_id(key, candidate)
            lifecycle = {
                "latest_observed_at": detected_at.isoformat(),
                "supporting_count": len(
                    {
                        pointer.checkpoint_run_id
                        for pointer in candidate.evidence
                        if pointer.relation in {"TRIGGER_AFTER", "SUPPORTING"}
                    }
                ),
                "affected_url_count": candidate.affected_url_count,
                "valid_url_count": candidate.valid_url_count,
                "blast_radius": _blast_radius(candidate),
            }
            result = await session.execute(
                insert(Event)
                .values(
                    id=event_id,
                    tenant_id=value.tenant_id,
                    site_id=value.site_id,
                    event_definition_id=definition_id(candidate.code),
                    template_id=_scope_uuid(candidate.scope, "template_id"),
                    started_at=occurred_before_at,
                    occurred_after_at=candidate.occurred_after_at,
                    occurred_before_at=occurred_before_at,
                    time_precision="WINDOW",
                    detected_at=detected_at,
                    severity=candidate.severity or rule.default_severity,
                    observation_confidence="HIGH",
                    status="ACTIVE",
                    source_kind="BROWSER_CHECKPOINT",
                    source_version=rule.rule_version,
                    condition_key=key,
                    scope=scope,
                    summary=candidate.summary[:500],
                    details={
                        "subject": candidate.subject,
                        "before": candidate.before,
                        "after": candidate.after,
                        "lifecycle": lifecycle,
                    },
                )
                .on_conflict_do_nothing()
                .returning(Event.id)
            )
            if result.scalar_one_or_none() is not None:
                await self._insert_candidate_evidence(session, value, event_id, candidate.evidence)
                return "CREATED"
            active = await self._active_condition(session, value, key)
            if active is None:
                raise EventStateError("active condition conflict without owned row")

        pointers = tuple(
            EvidencePointer(pointer.checkpoint_run_id, "SUPPORTING")
            for pointer in candidate.evidence
            if pointer.relation in {"TRIGGER_AFTER", "SUPPORTING"}
        )
        inserted = await self._insert_candidate_evidence(
            session,
            value,
            active.id,
            pointers,
            skip_linked_checkpoints=True,
        )
        if inserted == 0:
            return "IGNORED"
        lifecycle = _lifecycle_details(active.details)
        latest = candidate.detected_at or value.current_observed_at
        lifecycle["latest_observed_at"] = max(
            str(lifecycle.get("latest_observed_at") or ""), latest.isoformat()
        )
        lifecycle["supporting_count"] = _metadata_int(lifecycle, "supporting_count") + inserted
        lifecycle["affected_url_count"] = max(
            _metadata_int(lifecycle, "affected_url_count"), candidate.affected_url_count
        )
        lifecycle["valid_url_count"] = max(
            _metadata_int(lifecycle, "valid_url_count"), candidate.valid_url_count
        )
        lifecycle["blast_radius"] = max(
            _metadata_int(lifecycle, "blast_radius"), _blast_radius(candidate)
        )
        active.details = {**active.details, "lifecycle": lifecycle}
        active.severity = higher_severity(
            active.severity, candidate.severity or rule.default_severity
        )
        return "UPDATED"

    async def _resolve_condition(
        self, session: AsyncSession, value: EvaluationInput, candidate: EventCandidate
    ) -> bool:
        scope = normalized_scope(candidate.scope)
        key = condition_key(
            tenant_id=value.tenant_id,
            site_id=value.site_id,
            event_code=candidate.code,
            subject=candidate.subject,
            scope=scope,
        )
        active = await self._active_condition(session, value, key)
        if active is None:
            return False
        detected_at = candidate.detected_at or value.current_observed_at
        if detected_at < active.detected_at:
            return False
        inserted = await self._insert_candidate_evidence(
            session,
            value,
            active.id,
            candidate.evidence,
            skip_linked_checkpoints=True,
        )
        if inserted == 0:
            return False
        lifecycle = _lifecycle_details(active.details)
        lifecycle["latest_observed_at"] = detected_at.isoformat()
        lifecycle["resolved_after_at"] = (
            candidate.occurred_after_at.isoformat()
            if candidate.occurred_after_at is not None
            else None
        )
        lifecycle["resolved_before_at"] = (
            candidate.occurred_before_at.isoformat()
            if candidate.occurred_before_at is not None
            else detected_at.isoformat()
        )
        active.details = {**active.details, "lifecycle": lifecycle}
        active.ended_at = detected_at
        active.status = "RESOLVED"
        return True

    @staticmethod
    async def _active_condition(
        session: AsyncSession, value: EvaluationInput, key: str
    ) -> Event | None:
        return cast(
            Event | None,
            await session.scalar(
                select(Event)
                .where(
                    Event.tenant_id == value.tenant_id,
                    Event.site_id == value.site_id,
                    Event.condition_key == key,
                    Event.status == "ACTIVE",
                )
                .with_for_update()
            ),
        )

    async def _insert_candidate_evidence(
        self,
        session: AsyncSession,
        value: EvaluationInput,
        event_id: uuid.UUID,
        pointers: tuple[EvidencePointer, ...],
        *,
        skip_linked_checkpoints: bool = False,
    ) -> int:
        inserted_checkpoints = 0
        seen: set[tuple[uuid.UUID, str]] = set()
        event = await session.scalar(
            select(Event).where(
                Event.id == event_id,
                Event.tenant_id == value.tenant_id,
                Event.site_id == value.site_id,
            )
        )
        if event is None:
            raise EventStateError("event ownership mismatch")
        candidate_event_scope = event.scope
        for pointer in pointers:
            if pointer.relation not in VALID_RELATIONS:
                raise EventStateError("unsupported evidence relation")
            pair = (pointer.checkpoint_run_id, pointer.relation)
            if pair in seen:
                continue
            seen.add(pair)
            run = await session.scalar(
                select(CheckpointRun).where(
                    CheckpointRun.id == pointer.checkpoint_run_id,
                    CheckpointRun.tenant_id == value.tenant_id,
                    CheckpointRun.site_id == value.site_id,
                )
            )
            if run is None:
                raise EventStateError("evidence checkpoint ownership mismatch")
            _validate_scope_against_run(candidate_scope=candidate_event_scope, run=run)
            if skip_linked_checkpoints and await _has_checkpoint_source(
                session, event_id, pointer.checkpoint_run_id
            ):
                continue
            inserted = await _insert_ref(
                session,
                value.tenant_id,
                event_id,
                "CHECKPOINT_RUN",
                pointer.checkpoint_run_id,
                pointer.relation,
            )
            inserted_checkpoints += int(inserted)
            await _insert_specific_ref(
                session,
                value,
                event_id,
                pointer,
                run,
            )
        return inserted_checkpoints


def _mapping(value: object) -> dict[str, Any]:
    return {str(key): item for key, item in value.items()} if isinstance(value, dict) else {}


def _exact_scope(value: EvaluationInput) -> dict[str, object]:
    return {
        "monitored_url_id": str(value.monitored_url_id),
        "scenario_id": str(value.scenario_id),
        "template_id": str(value.template_id),
    }


def _scope_uuid(scope: dict[str, object], key: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(scope[key]))
    except (KeyError, ValueError) as error:
        raise EventStateError(f"invalid event scope {key}") from error


def _validate_scope_against_run(*, candidate_scope: dict[str, object], run: CheckpointRun) -> None:
    if _scope_uuid(candidate_scope, "template_id") != run.template_id:
        raise EventStateError("event evidence template mismatch")
    if _scope_uuid(candidate_scope, "scenario_id") != run.scenario_id:
        raise EventStateError("event evidence scenario mismatch")
    monitored_url = candidate_scope.get("monitored_url_id")
    if monitored_url is not None:
        try:
            monitored_url_id = uuid.UUID(str(monitored_url))
        except ValueError as error:
            raise EventStateError("invalid event scope monitored_url_id") from error
        if monitored_url_id != run.monitored_url_id:
            raise EventStateError("event evidence monitored URL mismatch")


def _point_event_id(
    value: EvaluationInput, candidate: EventCandidate, scope: dict[str, object]
) -> uuid.UUID:
    rule = RULES_BY_CODE[candidate.code]
    before = next(
        (
            pointer.checkpoint_run_id
            for pointer in candidate.evidence
            if pointer.relation == "BEFORE"
        ),
        value.previous_checkpoint_run_id,
    )
    after = next(
        (
            pointer.checkpoint_run_id
            for pointer in candidate.evidence
            if pointer.relation == "AFTER"
        ),
        value.current_checkpoint_run_id,
    )
    if rule.rule_version == "e1-v1" and len(candidate.evidence) == 2:
        key = "|".join(
            (
                str(value.tenant_id),
                rule.rule_version,
                str(before),
                str(after),
                candidate.code,
                candidate.subject,
                json.dumps(scope, sort_keys=True),
            )
        )
    else:
        evidence = "|".join(
            sorted(
                f"{pointer.checkpoint_run_id}:{pointer.relation}" for pointer in candidate.evidence
            )
        )
        key = "|".join(
            (
                str(value.tenant_id),
                rule.rule_version,
                candidate.code,
                candidate.subject,
                json.dumps(scope, sort_keys=True),
                evidence,
            )
        )
    return uuid.uuid5(EVENT_NAMESPACE, key)


def _condition_event_id(key: str, candidate: EventCandidate) -> uuid.UUID:
    trigger = "|".join(
        sorted(
            str(pointer.checkpoint_run_id)
            for pointer in candidate.evidence
            if pointer.relation == "TRIGGER_AFTER"
        )
    )
    return uuid.uuid5(EVENT_NAMESPACE, f"{key}|{trigger}|{candidate.occurred_before_at}")


def _blast_radius(candidate: EventCandidate) -> int:
    if candidate.affected_url_count >= 2:
        return 2
    return 1


def _lifecycle_details(details: dict[str, Any]) -> dict[str, Any]:
    value = details.get("lifecycle")
    return dict(value) if isinstance(value, dict) else {}


def _metadata_int(value: dict[str, Any], key: str) -> int:
    item = value.get(key)
    return item if isinstance(item, int) and not isinstance(item, bool) else 0


async def _has_checkpoint_source(
    session: AsyncSession, event_id: uuid.UUID, source_id: uuid.UUID
) -> bool:
    return (
        await session.scalar(
            select(EventEvidenceRef.id).where(
                EventEvidenceRef.event_id == event_id,
                EventEvidenceRef.evidence_kind == "CHECKPOINT_RUN",
                EventEvidenceRef.source_id == source_id,
            )
        )
        is not None
    )


async def _insert_specific_ref(
    session: AsyncSession,
    value: EvaluationInput,
    event_id: uuid.UUID,
    pointer: EvidencePointer,
    run: CheckpointRun,
) -> None:
    candidate_event = await session.scalar(
        select(Event).where(
            Event.id == event_id,
            Event.tenant_id == value.tenant_id,
            Event.site_id == value.site_id,
        )
    )
    if candidate_event is None:
        raise EventStateError("event ownership mismatch")
    definition_code = await session.scalar(
        select(Event.event_definition_id).where(Event.id == event_id)
    )
    code = next(
        (rule_code for rule_code in RULES_BY_CODE if definition_id(rule_code) == definition_code),
        None,
    )
    if code is None:
        raise EventStateError("unknown event definition")
    subject = str(candidate_event.details.get("subject") or "")

    kind: str | None = None
    source_id: uuid.UUID | None = None
    if code == "JS_ERROR_STARTED":
        source_id = await session.scalar(
            select(JavaScriptErrorObservation.id).where(
                JavaScriptErrorObservation.tenant_id == value.tenant_id,
                JavaScriptErrorObservation.site_id == value.site_id,
                JavaScriptErrorObservation.checkpoint_run_id == run.id,
                JavaScriptErrorObservation.fingerprint == subject,
            )
        )
        kind = "JS_ERROR_OBSERVATION"
        if source_id is None and pointer.relation not in {"TRIGGER_BEFORE", "RECOVERY"}:
            raise EventStateError("missing JavaScript error evidence")
    elif code == "GPT_EXPECTED_SLOT_MISSING":
        source_id = await session.scalar(
            select(GPTSlotObservation.id)
            .join(DomainEntity, DomainEntity.id == GPTSlotObservation.slot_entity_id)
            .where(
                GPTSlotObservation.tenant_id == value.tenant_id,
                GPTSlotObservation.site_id == value.site_id,
                GPTSlotObservation.checkpoint_run_id == run.id,
                DomainEntity.tenant_id == value.tenant_id,
                DomainEntity.site_id == value.site_id,
                DomainEntity.stable_key == subject,
            )
        )
        kind = "GPT_SLOT_OBSERVATION"
        if source_id is None:
            raise EventStateError("missing GPT slot evidence")
    elif code in {"NOINDEX_ADDED", "CANONICAL_CHANGED"}:
        source_id = await session.scalar(
            select(SeoObservation.id).where(
                SeoObservation.tenant_id == value.tenant_id,
                SeoObservation.site_id == value.site_id,
                SeoObservation.checkpoint_run_id == run.id,
            )
        )
        kind = "SEO_OBSERVATION"
        if source_id is None:
            raise EventStateError("missing SEO evidence")
    elif code.startswith("THIRD_PARTY_DEPENDENCY_"):
        entity_id = await session.scalar(
            select(DomainEntity.id).where(
                DomainEntity.tenant_id == value.tenant_id,
                DomainEntity.site_id == value.site_id,
                DomainEntity.stable_key == subject,
            )
        )
        if entity_id is not None:
            source_id = await session.scalar(
                select(EntityObservation.id).where(
                    EntityObservation.tenant_id == value.tenant_id,
                    EntityObservation.checkpoint_run_id == run.id,
                    EntityObservation.entity_id == entity_id,
                )
            )
        kind = "ENTITY_OBSERVATION"
    if kind is not None and source_id is not None:
        await _insert_ref(
            session,
            value.tenant_id,
            event_id,
            kind,
            source_id,
            pointer.relation,
        )


async def _insert_ref(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    event_id: uuid.UUID,
    kind: str,
    source_id: uuid.UUID,
    relation: str,
) -> bool:
    ref_id = uuid.uuid5(EVIDENCE_NAMESPACE, f"{event_id}|{kind}|{source_id}|{relation}")
    result = await session.execute(
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
        .returning(EventEvidenceRef.id)
    )
    return result.scalar_one_or_none() is not None
