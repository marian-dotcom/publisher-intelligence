import json
import uuid
from dataclasses import replace
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.events.contracts import EventCandidate, EvidencePointer
from app.events.lifecycle import condition_key, higher_severity, normalized_scope
from app.events.models import Event, EventEvidenceRef
from app.events.persistence import (
    EVENT_NAMESPACE,
    EVIDENCE_NAMESPACE,
    VALID_RELATIONS,
    EventStateError,
    PersistenceResult,
)
from app.events.registry import RULES_BY_CODE, definition_id
from app.public_config.evaluator import (
    MUTUALLY_EXCLUSIVE_ADS_CODES,
    PublicConfigEvaluationInput,
)
from app.public_config.models import PublicConfigSnapshot

PUBLIC_CONFIG_RELATIONS = VALID_RELATIONS | {"VALIDATION"}


class PublicConfigEventRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def persist(
        self,
        value: PublicConfigEvaluationInput,
        candidates: tuple[EventCandidate, ...],
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
                    created += int(await self._persist_point(session, value, candidate))
                    continue
                if rule.kind != "CONDITION":
                    raise EventStateError("point candidate cannot use condition lifecycle")
                if candidate.action == "RESOLVE_CONDITION":
                    resolved += int(await self._resolve_condition(session, value, candidate))
                    continue
                if candidate.action == "UPSERT_CONDITION" and (
                    candidate.code in MUTUALLY_EXCLUSIVE_ADS_CODES
                ):
                    resolved += int(
                        await self._resolve_exclusive_siblings(session, value, candidate)
                    )
                outcome = await self._persist_condition(session, value, candidate)
                created += int(outcome == "CREATED")
                updated += int(outcome == "UPDATED")
        return PersistenceResult(created, updated, resolved)

    async def _persist_point(
        self,
        session: AsyncSession,
        value: PublicConfigEvaluationInput,
        candidate: EventCandidate,
    ) -> bool:
        rule = RULES_BY_CODE[candidate.code]
        scope = normalized_scope(candidate.scope)
        event_id = _point_event_id(value, candidate, scope)
        detected_at = candidate.detected_at or value.primary.observed_at
        occurred_before_at = candidate.occurred_before_at or value.primary.observed_at
        result = await session.execute(
            insert(Event)
            .values(
                id=event_id,
                tenant_id=value.primary.tenant_id,
                site_id=value.primary.site_id,
                event_definition_id=definition_id(candidate.code),
                template_id=None,
                started_at=occurred_before_at,
                occurred_after_at=candidate.occurred_after_at,
                occurred_before_at=occurred_before_at,
                time_precision="WINDOW",
                detected_at=detected_at,
                severity=candidate.severity or rule.default_severity,
                observation_confidence="HIGH",
                status="RECORDED",
                source_kind="PUBLIC_CONFIG",
                source_version=rule.rule_version,
                condition_key=None,
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
        created = result.scalar_one_or_none() is not None
        await self._insert_evidence(session, value, event_id, candidate.evidence)
        return created

    async def _persist_condition(
        self,
        session: AsyncSession,
        value: PublicConfigEvaluationInput,
        candidate: EventCandidate,
    ) -> str:
        rule = RULES_BY_CODE[candidate.code]
        scope = normalized_scope(candidate.scope)
        key = condition_key(
            tenant_id=value.primary.tenant_id,
            site_id=value.primary.site_id,
            event_code=candidate.code,
            subject=candidate.subject,
            scope=scope,
        )
        active = await self._active_condition(session, value, key)
        if active is None and candidate.action == "SUPPORT_CONDITION":
            return "IGNORED"
        if active is None:
            detected_at = candidate.detected_at or value.primary.observed_at
            occurred_before_at = candidate.occurred_before_at or value.primary.observed_at
            event_id = _condition_event_id(key, candidate)
            lifecycle = {
                "latest_observed_at": detected_at.isoformat(),
                "supporting_count": _scheduled_evidence_count(candidate.evidence),
            }
            result = await session.execute(
                insert(Event)
                .values(
                    id=event_id,
                    tenant_id=value.primary.tenant_id,
                    site_id=value.primary.site_id,
                    event_definition_id=definition_id(candidate.code),
                    template_id=None,
                    started_at=occurred_before_at,
                    occurred_after_at=candidate.occurred_after_at,
                    occurred_before_at=occurred_before_at,
                    time_precision="WINDOW",
                    detected_at=detected_at,
                    severity=candidate.severity or rule.default_severity,
                    observation_confidence="HIGH",
                    status="ACTIVE",
                    source_kind="PUBLIC_CONFIG",
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
                await self._insert_evidence(session, value, event_id, candidate.evidence)
                return "CREATED"
            active = await self._active_condition(session, value, key)
            if active is None:
                raise EventStateError("active public configuration condition conflict")

        inserted = await self._insert_evidence(
            session,
            value,
            active.id,
            candidate.evidence,
            skip_linked_sources=True,
        )
        if inserted == 0:
            return "IGNORED"
        lifecycle = _lifecycle_details(active.details)
        detected_at = candidate.detected_at or value.primary.observed_at
        lifecycle["latest_observed_at"] = max(
            str(lifecycle.get("latest_observed_at") or ""), detected_at.isoformat()
        )
        lifecycle["supporting_count"] = _metadata_int(lifecycle, "supporting_count") + inserted
        active.details = {**active.details, "lifecycle": lifecycle}
        active.severity = higher_severity(
            active.severity, candidate.severity or rule.default_severity
        )
        return "UPDATED"

    async def _resolve_exclusive_siblings(
        self,
        session: AsyncSession,
        value: PublicConfigEvaluationInput,
        candidate: EventCandidate,
    ) -> bool:
        resolved_any = False
        for code in sorted(MUTUALLY_EXCLUSIVE_ADS_CODES - {candidate.code}):
            resolved_any |= await self._resolve_condition(
                session, value, replace(candidate, code=code)
            )
        return resolved_any

    async def _resolve_condition(
        self,
        session: AsyncSession,
        value: PublicConfigEvaluationInput,
        candidate: EventCandidate,
    ) -> bool:
        key = condition_key(
            tenant_id=value.primary.tenant_id,
            site_id=value.primary.site_id,
            event_code=candidate.code,
            subject=candidate.subject,
            scope=normalized_scope(candidate.scope),
        )
        active = await self._active_condition(session, value, key)
        if active is None:
            return False
        detected_at = candidate.detected_at or value.primary.observed_at
        if detected_at < active.detected_at:
            return False
        inserted = await self._insert_evidence(
            session,
            value,
            active.id,
            candidate.evidence,
            skip_linked_sources=True,
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
        session: AsyncSession, value: PublicConfigEvaluationInput, key: str
    ) -> Event | None:
        return cast(
            Event | None,
            await session.scalar(
                select(Event)
                .where(
                    Event.tenant_id == value.primary.tenant_id,
                    Event.site_id == value.primary.site_id,
                    Event.condition_key == key,
                    Event.status == "ACTIVE",
                )
                .with_for_update()
            ),
        )

    async def _insert_evidence(
        self,
        session: AsyncSession,
        value: PublicConfigEvaluationInput,
        event_id: uuid.UUID,
        pointers: tuple[EvidencePointer, ...],
        *,
        skip_linked_sources: bool = False,
    ) -> int:
        event = await session.scalar(
            select(Event).where(
                Event.id == event_id,
                Event.tenant_id == value.primary.tenant_id,
                Event.site_id == value.primary.site_id,
            )
        )
        if event is None:
            raise EventStateError("event ownership mismatch")
        if event.scope != normalized_scope({"config_type": value.primary.config_type}):
            raise EventStateError("public configuration event scope mismatch")

        inserted_scheduled = 0
        seen: set[tuple[uuid.UUID, str]] = set()
        for pointer in pointers:
            if pointer.evidence_kind != "PUBLIC_CONFIG_SNAPSHOT":
                raise EventStateError("public configuration events require snapshot evidence")
            if pointer.relation not in PUBLIC_CONFIG_RELATIONS:
                raise EventStateError("unsupported evidence relation")
            pair = (pointer.source_id, pointer.relation)
            if pair in seen:
                continue
            seen.add(pair)
            snapshot = await session.scalar(
                select(PublicConfigSnapshot).where(
                    PublicConfigSnapshot.id == pointer.source_id,
                    PublicConfigSnapshot.tenant_id == value.primary.tenant_id,
                    PublicConfigSnapshot.site_id == value.primary.site_id,
                    PublicConfigSnapshot.config_type == value.primary.config_type,
                )
            )
            if snapshot is None:
                raise EventStateError("public configuration evidence ownership mismatch")
            _validate_relation(snapshot, pointer, value)
            if skip_linked_sources and await _has_source(session, event_id, pointer.source_id):
                continue
            inserted = await session.scalar(
                insert(EventEvidenceRef)
                .values(
                    id=uuid.uuid5(
                        EVIDENCE_NAMESPACE,
                        f"{event_id}|PUBLIC_CONFIG_SNAPSHOT|{pointer.source_id}|{pointer.relation}",
                    ),
                    tenant_id=value.primary.tenant_id,
                    event_id=event_id,
                    evidence_kind="PUBLIC_CONFIG_SNAPSHOT",
                    source_id=pointer.source_id,
                    relation=pointer.relation,
                    summary=None,
                )
                .on_conflict_do_nothing(constraint="uq_event_evidence_ref")
                .returning(EventEvidenceRef.id)
            )
            if inserted is not None and snapshot.fetch_kind == "SCHEDULED":
                inserted_scheduled += 1
        return inserted_scheduled


def _point_event_id(
    value: PublicConfigEvaluationInput,
    candidate: EventCandidate,
    scope: dict[str, object],
) -> uuid.UUID:
    key = "|".join(
        (
            str(value.primary.tenant_id),
            RULES_BY_CODE[candidate.code].rule_version,
            str(value.primary.id),
            candidate.code,
            candidate.subject,
            json.dumps(scope, sort_keys=True),
        )
    )
    return uuid.uuid5(EVENT_NAMESPACE, key)


def _condition_event_id(key: str, candidate: EventCandidate) -> uuid.UUID:
    trigger = "|".join(
        sorted(
            str(pointer.source_id)
            for pointer in candidate.evidence
            if pointer.relation == "TRIGGER_AFTER"
        )
    )
    return uuid.uuid5(EVENT_NAMESPACE, f"{key}|{trigger}|{candidate.occurred_before_at}")


def _validate_relation(
    snapshot: PublicConfigSnapshot,
    pointer: EvidencePointer,
    value: PublicConfigEvaluationInput,
) -> None:
    if pointer.relation == "VALIDATION":
        if (
            snapshot.fetch_kind != "VALIDATION"
            or snapshot.validation_of_snapshot_id != value.primary.id
        ):
            raise EventStateError("invalid public configuration validation evidence")
    elif snapshot.fetch_kind != "SCHEDULED":
        raise EventStateError("validation snapshot requires VALIDATION relation")
    elif pointer.relation in {"AFTER", "TRIGGER_AFTER", "SUPPORTING", "RECOVERY"}:
        if snapshot.id != value.primary.id:
            raise EventStateError("public configuration primary evidence relation mismatch")
    elif pointer.relation in {"BEFORE", "TRIGGER_BEFORE"} and (
        snapshot.id == value.primary.id or snapshot.observed_at >= value.primary.observed_at
    ):
        raise EventStateError("public configuration predecessor evidence relation mismatch")


async def _has_source(session: AsyncSession, event_id: uuid.UUID, source_id: uuid.UUID) -> bool:
    return (
        await session.scalar(
            select(EventEvidenceRef.id).where(
                EventEvidenceRef.event_id == event_id,
                EventEvidenceRef.evidence_kind == "PUBLIC_CONFIG_SNAPSHOT",
                EventEvidenceRef.source_id == source_id,
            )
        )
        is not None
    )


def _scheduled_evidence_count(pointers: tuple[EvidencePointer, ...]) -> int:
    return len(
        {
            pointer.source_id
            for pointer in pointers
            if pointer.relation in {"TRIGGER_AFTER", "SUPPORTING"}
        }
    )


def _lifecycle_details(details: dict[str, Any]) -> dict[str, Any]:
    value = details.get("lifecycle")
    return dict(value) if isinstance(value, dict) else {}


def _metadata_int(value: dict[str, Any], key: str) -> int:
    item = value.get(key)
    return item if isinstance(item, int) and not isinstance(item, bool) else 0
