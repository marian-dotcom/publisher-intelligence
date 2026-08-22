import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.browser.models import CheckpointRun
from app.incidents.contracts import (
    DEFAULT_RESOURCE_LIMITS,
    InvestigationStateError,
    usage_key_for,
    validate_incident_fields,
    validate_resource_kind,
    validate_symptom_segment,
)
from app.incidents.models import (
    Incident,
    IncidentSymptomSegment,
    InvestigationUsageEntry,
    LastKnownGoodRef,
    RetentionHold,
)

LKG_SELECTION_VERSION = "lkg-v1"
FINAL_HEALTHY_STATUSES = ("COMPLETE",)


class InvestigationRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    # -- incidents ---------------------------------------------------------

    async def create_incident(
        self,
        *,
        tenant_id: uuid.UUID,
        publisher_id: uuid.UUID,
        site_id: uuid.UUID,
        title: str,
        symptom_family: str,
        description: str,
        reported_start_at: datetime | None = None,
        reported_end_at: datetime | None = None,
        severity: str | None = None,
        created_by: uuid.UUID | None = None,
        segments: tuple[dict[str, str], ...] = (),
    ) -> Incident:
        validate_incident_fields(
            title=title,
            symptom_family=symptom_family,
            description=description,
            severity=severity,
        )
        for segment in segments:
            validate_symptom_segment(
                dimension=str(segment.get("dimension", "")),
                operator=str(segment.get("operator", "")),
                value=str(segment.get("value", "")),
                source=str(segment.get("source", "")),
            )
        async with self._session_factory() as session, session.begin():
            incident = Incident(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                publisher_id=publisher_id,
                site_id=site_id,
                title=title,
                symptom_family=symptom_family,
                description=description,
                reported_start_at=reported_start_at,
                reported_end_at=reported_end_at,
                opened_at=datetime.now(UTC),
                status="OPEN",
                severity=severity,
                created_by=created_by,
            )
            session.add(incident)
            await session.flush()
            for segment in segments:
                session.add(
                    IncidentSymptomSegment(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        incident_id=incident.id,
                        dimension=str(segment["dimension"]),
                        operator=str(segment["operator"]),
                        value=str(segment["value"]),
                        source=str(segment["source"]),
                    )
                )
            return incident

    async def get_incident(self, *, tenant_id: uuid.UUID, incident_id: uuid.UUID) -> Incident:
        async with self._session_factory() as session:
            incident = await session.scalar(
                select(Incident).where(
                    Incident.id == incident_id,
                    Incident.tenant_id == tenant_id,
                )
            )
        if incident is None:
            raise InvestigationStateError("incident does not belong to tenant")
        return incident

    # -- last known good ---------------------------------------------------

    async def select_eligible_lkg_run(
        self,
        *,
        tenant_id: uuid.UUID,
        site_id: uuid.UUID,
        scope_key: str,
        expected_fingerprints: dict[str, str],
        scenario_id: uuid.UUID | None = None,
        template_id: uuid.UUID | None = None,
    ) -> CheckpointRun | None:
        """Deterministic scheduled-only LKG eligibility lookup.

        Eligible candidates are COMPLETE scheduled runs (ADR-130) for the same
        site whose recorded collector bundle participates in an equal
        fingerprint snapshot. Ordering is recency-based; the first candidate is
        returned.
        """
        async with self._session_factory() as session:
            conditions: list[ColumnElement[bool]] = [
                CheckpointRun.tenant_id == tenant_id,
                CheckpointRun.site_id == site_id,
                # ADR-130 cohort purity: only routine scheduled evidence
                # may anchor a Last Known Good reference.
                CheckpointRun.observation_kind == "SCHEDULED",
                CheckpointRun.status.in_(("COMPLETE",)),
            ]
            if "collector_bundle_version" in expected_fingerprints:
                conditions.append(
                    CheckpointRun.collector_bundle_version
                    == expected_fingerprints["collector_bundle_version"]
                )
            if scenario_id is not None:
                conditions.append(CheckpointRun.scenario_id == scenario_id)
            if template_id is not None:
                conditions.append(CheckpointRun.template_id == template_id)
            run = await session.scalar(
                select(CheckpointRun)
                .where(*conditions)
                .order_by(
                    CheckpointRun.scheduled_for.desc(),
                    CheckpointRun.completed_at.desc(),
                    CheckpointRun.id.desc(),
                )
                .limit(1)
            )
            return run

    async def freeze_lkg_selection(
        self,
        *,
        tenant_id: uuid.UUID,
        site_id: uuid.UUID,
        scope_key: str,
        checkpoint_run_id: uuid.UUID,
        fingerprints: dict[str, str],
        selection_method: str,
        reason: str,
        valid_for_incident_id: uuid.UUID | None = None,
        template_id: uuid.UUID | None = None,
        scenario_id: uuid.UUID | None = None,
        selected_at: datetime | None = None,
    ) -> LastKnownGoodRef:
        if not scope_key.strip():
            raise InvestigationStateError("LKG scope key is required")
        if not selection_method.strip() or not reason.strip():
            raise InvestigationStateError("LKG selection method and reason are required")
        existing = await self.get_frozen_lkg_ref(
            tenant_id=tenant_id,
            site_id=site_id,
            scope_key=scope_key,
            checkpoint_run_id=checkpoint_run_id,
            valid_for_incident_id=valid_for_incident_id,
        )
        if existing is not None:
            return existing
        async with self._session_factory() as session, session.begin():
            ref = LastKnownGoodRef(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                site_id=site_id,
                template_id=template_id,
                scenario_id=scenario_id,
                scope_key=scope_key,
                checkpoint_run_id=checkpoint_run_id,
                valid_for_incident_id=valid_for_incident_id,
                selected_at=selected_at or datetime.now(UTC),
                selection_method=selection_method,
                selection_version=LKG_SELECTION_VERSION,
                reason=reason,
                fingerprints=dict(fingerprints),
            )
            session.add(ref)
            await session.flush()
            return ref

    async def get_frozen_lkg_ref(
        self,
        *,
        tenant_id: uuid.UUID,
        site_id: uuid.UUID,
        scope_key: str,
        checkpoint_run_id: uuid.UUID,
        valid_for_incident_id: uuid.UUID | None = None,
    ) -> LastKnownGoodRef | None:
        async with self._session_factory() as session:
            ref = await session.scalar(
                select(LastKnownGoodRef).where(
                    LastKnownGoodRef.tenant_id == tenant_id,
                    LastKnownGoodRef.site_id == site_id,
                    LastKnownGoodRef.scope_key == scope_key,
                    LastKnownGoodRef.checkpoint_run_id == checkpoint_run_id,
                    LastKnownGoodRef.valid_for_incident_id == valid_for_incident_id,
                )
            )
            return ref

    # -- investigation budget ledger ---------------------------------------

    async def consume_budget(
        self,
        *,
        tenant_id: uuid.UUID,
        investigation_key: str,
        resource_kind: str,
        correlation_id: uuid.UUID | str,
        incident_id: uuid.UUID | None = None,
        amount: int = 1,
        detail: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> InvestigationUsageEntry:
        validate_resource_kind(resource_kind)
        key = usage_key_for(
            investigation_key=investigation_key,
            resource_kind=resource_kind,
            correlation_id=correlation_id,
        )
        async with self._session_factory() as session, session.begin():
            entry = await session.scalar(
                select(InvestigationUsageEntry).where(
                    InvestigationUsageEntry.tenant_id == tenant_id,
                    InvestigationUsageEntry.usage_key == key,
                )
            )
            if entry is not None:
                return entry
            created = InvestigationUsageEntry(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                incident_id=incident_id,
                investigation_key=investigation_key.strip(),
                resource_kind=resource_kind,
                amount=amount,
                usage_key=key,
                detail=detail or {},
                occurred_at=occurred_at or datetime.now(UTC),
            )
            session.add(created)
            await session.flush()
            return created

    async def current_usage(
        self,
        *,
        tenant_id: uuid.UUID,
        investigation_key: str,
        resource_kind: str,
        incident_id: uuid.UUID | None = None,
    ) -> int:
        validate_resource_kind(resource_kind)
        async with self._session_factory() as session:
            total = await session.scalar(
                select(func.sum(InvestigationUsageEntry.amount)).where(
                    InvestigationUsageEntry.tenant_id == tenant_id,
                    InvestigationUsageEntry.investigation_key == investigation_key,
                    InvestigationUsageEntry.resource_kind == resource_kind,
                    *(
                        [InvestigationUsageEntry.incident_id == incident_id]
                        if incident_id is not None
                        else []
                    ),
                )
            )
        return int(total or 0)

    def default_limit(self, resource_kind: str) -> int:
        validate_resource_kind(resource_kind)
        return DEFAULT_RESOURCE_LIMITS[resource_kind]

    def within_limit(self, *, resource_kind: str, used: int) -> bool:
        return used < self.default_limit(resource_kind)

    # -- retention holds ---------------------------------------------------

    async def create_retention_hold(
        self,
        *,
        tenant_id: uuid.UUID,
        reason: str,
        incident_id: uuid.UUID | None = None,
        artifact_id: uuid.UUID | None = None,
        source_extract_id: uuid.UUID | None = None,
    ) -> RetentionHold:
        if not reason.strip():
            raise InvestigationStateError("retention hold reason is required")
        targets = (incident_id, artifact_id, source_extract_id)
        if all(item is None for item in targets):
            raise InvestigationStateError("retention hold requires at least one target")
        async with self._session_factory() as session, session.begin():
            conditions: list[ColumnElement[bool]] = [
                RetentionHold.tenant_id == tenant_id,
                RetentionHold.released_at.is_(None),
                RetentionHold.reason == reason,
            ]
            for column, value in (
                (RetentionHold.incident_id, incident_id),
                (RetentionHold.artifact_id, artifact_id),
                (RetentionHold.source_extract_id, source_extract_id),
            ):
                conditions.append(column.is_(None) if value is None else column == value)
            existing = await session.scalar(select(RetentionHold).where(*conditions))
            if existing is not None:
                return existing
            created = RetentionHold(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                incident_id=incident_id,
                artifact_id=artifact_id,
                source_extract_id=source_extract_id,
                reason=reason,
            )
            session.add(created)
            try:
                await session.flush()
            except IntegrityError:
                # Concurrent creation raced the active-hold match; the partial
                # unique index guarantees exactly one active hold survives.
                # Re-select it on a fresh transaction.
                winner = await self._active_hold(tenant_id=tenant_id, conditions=conditions)
                if winner is None:
                    raise InvestigationStateError(
                        "retention hold conflict left no surviving hold"
                    ) from None
                return winner
            return created

    async def _active_hold(
        self, *, tenant_id: uuid.UUID, conditions: list[ColumnElement[bool]]
    ) -> RetentionHold | None:
        async with self._session_factory() as session:
            query_conditions: list[ColumnElement[bool]] = [
                RetentionHold.tenant_id == tenant_id,
                *conditions[1:],
            ]
            result: RetentionHold | None = await session.scalar(
                select(RetentionHold).where(*query_conditions)
            )
            return result

    async def release_retention_hold(
        self,
        *,
        tenant_id: uuid.UUID,
        hold_id: uuid.UUID,
        released_by: str,
    ) -> RetentionHold:
        if not released_by.strip():
            raise InvestigationStateError("release actor reference is required")
        async with self._session_factory() as session, session.begin():
            hold = await session.scalar(
                select(RetentionHold)
                .where(
                    RetentionHold.id == hold_id,
                    RetentionHold.tenant_id == tenant_id,
                )
                .with_for_update()
            )
            if hold is None:
                raise InvestigationStateError("retention hold does not belong to tenant")
            if hold.released_at is not None:
                raise InvestigationStateError("retention hold was already released")
            hold.released_at = datetime.now(UTC)
            hold.released_by = released_by
            return hold

    async def active_holds_for_tenant(self, *, tenant_id: uuid.UUID) -> tuple[RetentionHold, ...]:
        async with self._session_factory() as session:
            holds = list(
                (
                    await session.scalars(
                        select(RetentionHold).where(
                            RetentionHold.tenant_id == tenant_id,
                            RetentionHold.released_at.is_(None),
                        )
                    )
                ).all()
            )
        return tuple(holds)
