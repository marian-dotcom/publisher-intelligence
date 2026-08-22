"""EP-020 incident intake, localization, and bounded initial diagnostics.

Deterministic workflow on top of the EP-019 foundations: capture the symptom
report verbatim, localise the affected window against real scheduled evidence,
freeze Last Known Good references for the investigation, and grant a bounded
number of incident-diagnostic checkpoints through the budget ledger.

Load-bearing invariant: observation failure is not evidence of publisher
failure. Absence or degradation of scheduled evidence narrows what we know; it
never asserts that the publisher system failed.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.browser.contracts import TRIGGER_SOURCES
from app.browser.models import BrowserScenario, CheckpointRun
from app.browser.service import CheckpointService
from app.incidents.contracts import (
    InvestigationStateError,
    validate_incident_fields,
    validate_symptom_segment,
)
from app.incidents.models import Incident
from app.incidents.persistence import InvestigationRepository

INVESTIGATION_KEY_PREFIX = "inc"


def investigation_key_for(incident_id: uuid.UUID) -> str:
    return f"{INVESTIGATION_KEY_PREFIX}-{incident_id}"


@dataclass(frozen=True, slots=True)
class LocalizationResult:
    incident_id: uuid.UUID
    investigation_key: str
    last_healthy_run_id: uuid.UUID | None
    last_healthy_at: datetime | None
    first_anomaly_run_id: uuid.UUID | None
    first_anomaly_at: datetime | None
    affected_scope_dimensions: tuple[str, ...]
    lkg_frozen: bool


@dataclass(frozen=True, slots=True)
class DiagnosticGrant:
    scenario_id: uuid.UUID
    checkpoint_run_id: uuid.UUID
    job_id: uuid.UUID


def _require_trigger_source(source: str) -> str:
    if source not in TRIGGER_SOURCES:
        raise InvestigationStateError("unknown checkpoint run trigger source")
    return source


class IncidentIntakeService:
    def __init__(
        self,
        *,
        repository: InvestigationRepository,
        checkpoint_service: CheckpointService,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._repository = repository
        self._checkpoints = checkpoint_service
        self._session_factory = session_factory

    async def open_investigation(
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
    ) -> tuple[Incident, str]:
        """Capture the symptom report verbatim and open an investigation."""
        validate_incident_fields(
            title=title,
            symptom_family=symptom_family,
            description=description,
            severity=severity,
        )
        if (
            reported_start_at is not None
            and reported_end_at is not None
            and reported_end_at < reported_start_at
        ):
            raise InvestigationStateError("reported window end precedes start")
        for segment in segments:
            validate_symptom_segment(
                dimension=str(segment.get("dimension", "")),
                operator=str(segment.get("operator", "")),
                value=str(segment.get("value", "")),
                source=str(segment.get("source", "")),
            )
        incident = await self._repository.create_incident(
            tenant_id=tenant_id,
            publisher_id=publisher_id,
            site_id=site_id,
            title=title,
            symptom_family=symptom_family,
            description=description,
            reported_start_at=reported_start_at,
            reported_end_at=reported_end_at,
            severity=severity,
            created_by=created_by,
            segments=segments,
        )
        return incident, investigation_key_for(incident.id)

    async def localize(
        self,
        *,
        tenant_id: uuid.UUID,
        incident_id: uuid.UUID,
        expected_fingerprints: dict[str, str],
    ) -> LocalizationResult:
        """Localize in time/scope against real scheduled evidence.

        Deterministic analysis only: anchor on the latest healthy scheduled
        observation at/before the reported onset, find the earliest non-healthy
        scheduled observation after it (when present), freeze LKG references for
        the affected site/template/scenario scope. Absence of evidence is
        reported as such — never as publisher failure.
        """
        incident = await self._repository.get_incident(tenant_id=tenant_id, incident_id=incident_id)
        onset = incident.reported_start_at
        async with self._session_factory() as session:
            runs = list(
                (
                    await session.scalars(
                        select(CheckpointRun).where(
                            CheckpointRun.tenant_id == tenant_id,
                            CheckpointRun.site_id == incident.site_id,
                            CheckpointRun.observation_kind == "SCHEDULED",
                        )
                    )
                ).all()
            )
        healthy_before = [
            run
            for run in runs
            if run.status == "COMPLETE"
            and run.completed_at is not None
            and (onset is None or run.completed_at <= onset)
        ]
        anomalies_after = [
            run
            for run in runs
            if run.status != "COMPLETE"
            and run.scheduled_for is not None
            and (onset is None or run.scheduled_for >= onset)
        ]
        healthy_before.sort(key=lambda run: cast(datetime, run.completed_at), reverse=True)
        anomalies_after.sort(key=lambda run: run.scheduled_for)

        last_healthy = healthy_before[0] if healthy_before else None
        first_anomaly = anomalies_after[0] if anomalies_after else None

        lkg_frozen = False
        if last_healthy is not None:
            await self._repository.freeze_lkg_selection(
                tenant_id=tenant_id,
                site_id=incident.site_id,
                scope_key=f"{incident.site_id}:{last_healthy.scenario_id}",
                checkpoint_run_id=last_healthy.id,
                fingerprints=expected_fingerprints,
                selection_method="LATEST_HEALTHY_SCHEDULED_BEFORE_ONSET",
                reason="localization baseline for open investigation",
                valid_for_incident_id=incident.id,
                template_id=last_healthy.template_id,
                scenario_id=last_healthy.scenario_id,
                selected_at=last_healthy.completed_at,
            )
            lkg_frozen = True

        scope_dimensions = tuple(
            dict.fromkeys(
                segment.dimension
                for segment in await self._symptom_segments(incident_id=incident.id)
            )
        )
        return LocalizationResult(
            incident_id=incident.id,
            investigation_key=investigation_key_for(incident.id),
            last_healthy_run_id=last_healthy.id if last_healthy else None,
            last_healthy_at=(last_healthy.completed_at if last_healthy is not None else None),
            first_anomaly_run_id=first_anomaly.id if first_anomaly else None,
            first_anomaly_at=first_anomaly.scheduled_for if first_anomaly else None,
            affected_scope_dimensions=scope_dimensions,
            lkg_frozen=lkg_frozen,
        )

    async def _symptom_segments(self, *, incident_id: uuid.UUID) -> list[Any]:
        from app.incidents.models import IncidentSymptomSegment

        async with self._session_factory() as session:
            return list(
                (
                    await session.scalars(
                        select(IncidentSymptomSegment).where(
                            IncidentSymptomSegment.incident_id == incident_id
                        )
                    )
                ).all()
            )

    async def request_initial_diagnostics(
        self,
        *,
        tenant_id: uuid.UUID,
        incident_id: uuid.UUID,
        max_scenarios: int = 2,
    ) -> tuple[DiagnosticGrant, ...]:
        """Grant up to ``max_scenarios`` bounded incident diagnostics.

        Consumption is enforced through the persistent budget ledger before any
        run is created; refused requests create nothing.
        """
        if max_scenarios < 1:
            raise InvestigationStateError("diagnostic request must target at least one scenario")
        incident = await self._repository.get_incident(tenant_id=tenant_id, incident_id=incident_id)
        used = await self._repository.current_usage(
            tenant_id=tenant_id,
            investigation_key=investigation_key_for(incident_id),
            resource_kind="DIAGNOSTIC_RUN",
        )
        limit = self._repository.default_limit("DIAGNOSTIC_RUN")
        if not self._repository.within_limit(resource_kind="DIAGNOSTIC_RUN", used=used):
            raise InvestigationStateError("investigation budget exhausted for DIAGNOSTIC_RUN")
        remaining = min(max_scenarios, limit - used)

        async with self._session_factory() as session:
            scenarios = list(
                (
                    await session.scalars(
                        select(BrowserScenario)
                        .where(
                            BrowserScenario.tenant_id == tenant_id,
                            BrowserScenario.site_id == incident.site_id,
                            BrowserScenario.status == "ACTIVE",
                        )
                        .order_by(BrowserScenario.code)
                        .limit(remaining)
                    )
                ).all()
            )
        if not scenarios:
            raise InvestigationStateError("no active scenarios available for diagnostics")

        grants: list[DiagnosticGrant] = []
        for scenario in scenarios:
            entry_count = await self._repository.current_usage(
                tenant_id=tenant_id,
                investigation_key=investigation_key_for(incident_id),
                resource_kind="DIAGNOSTIC_RUN",
            )
            if not self._repository.within_limit(resource_kind="DIAGNOSTIC_RUN", used=entry_count):
                break
            usage_key_sequence = entry_count + len(grants) + 1
            await self._repository.consume_budget(
                tenant_id=tenant_id,
                investigation_key=investigation_key_for(incident_id),
                resource_kind="DIAGNOSTIC_RUN",
                correlation_id=f"{scenario.code}:{usage_key_sequence}",
                incident_id=incident_id,
            )
            monitored_url = await self._first_active_monitored_url(
                tenant_id=tenant_id, site_id=incident.site_id
            )
            enqueued = await self._checkpoints.enqueue_incident_diagnostic(
                tenant_id=tenant_id,
                site_id=incident.site_id,
                incident_id=incident_id,
                monitored_url_id=monitored_url,
                scenario_id=scenario.id,
            )
            _require_trigger_source("INCIDENT")
            grants.append(
                DiagnosticGrant(
                    scenario_id=scenario.id,
                    checkpoint_run_id=enqueued.checkpoint_run_id,
                    job_id=enqueued.job_id,
                )
            )
        if not grants:
            raise InvestigationStateError("investigation budget exhausted for DIAGNOSTIC_RUN")
        return tuple(grants)

    async def _first_active_monitored_url(
        self, *, tenant_id: uuid.UUID, site_id: uuid.UUID
    ) -> uuid.UUID:
        from app.browser.models import MonitoredUrl

        async with self._session_factory() as session:
            monitored_url = await session.scalar(
                select(MonitoredUrl.id)
                .where(
                    MonitoredUrl.tenant_id == tenant_id,
                    MonitoredUrl.site_id == site_id,
                    MonitoredUrl.status == "ACTIVE",
                )
                .order_by(MonitoredUrl.priority, MonitoredUrl.url)
                .limit(1)
            )
        if monitored_url is None:
            raise InvestigationStateError("site has no active monitored urls")
        return monitored_url
