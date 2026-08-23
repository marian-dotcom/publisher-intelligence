"""Tenant-scoped Timeline and Incidents read contracts (EP-025a P2-B).

Provenance and time semantics are preserved exactly: observed_at is never
substituted for occurred_at; unknown occurrence is returned as null; bounded
windows are exposed as bounds. Manual/human evidence remains structurally
distinct from machine-observed evidence.
"""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.auth.dependencies import ActorContext, get_current_actor
from app.db.session import get_session_factory
from app.events.models import Event
from app.evidence.models import ManualNote
from app.hypotheses.persistence import HypothesisRepository
from app.incidents.models import (
    Incident,
    IncidentSymptomSegment,
    LastKnownGoodRef,
)

router = APIRouter(tags=["memory"])


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


@router.get("/timeline")
async def timeline(
    actor: ActorContext = Depends(get_current_actor),  # noqa: B008
    site_id: uuid.UUID | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    factory = get_session_factory()
    async with factory() as session:
        conditions: list[Any] = [Event.tenant_id == actor.tenant_id]
        if site_id is not None:
            conditions.append(Event.site_id == site_id)
        events = list(
            (
                await session.scalars(
                    select(Event)
                    .where(*conditions)
                    .order_by(Event.detected_at.desc())
                    .limit(min(max(limit, 1), 200))
                )
            ).all()
        )
        notes = list(
            (
                await session.scalars(
                    select(ManualNote)
                    .where(ManualNote.tenant_id == actor.tenant_id)
                    .order_by(ManualNote.created_at.desc())
                    .limit(min(max(limit, 1), 200))
                )
            ).all()
        )
    entries = []
    for item in events:
        exact_occurred = (
            _iso(item.occurred_before_at)
            if item.time_precision == "EXACT" and item.occurred_before_at
            else None
        )
        entries.append(
            {
                "event_id": str(item.id),
                "event_type": str(item.event_definition_id),
                "source": item.source_kind,
                "provenance": "machine_observed",
                "severity": item.severity,
                "status": item.status,
                "time_precision": item.time_precision,
                "observed_at": _iso(item.detected_at),
                "occurred_at": exact_occurred,
                "occurrence_window_start": _iso(item.occurred_after_at),
                "occurrence_window_end": _iso(item.occurred_before_at),
                "site_id": str(item.site_id),
            }
        )
    entries.extend(
        {
            "note_id": str(note.id),
            "note_type": note.note_type,
            "provenance": "human_reported",
            "source": note.source,
            "observed_at": _iso(note.created_at),
            "occurred_at": _iso(note.occurred_at),
            "text": note.note_text,
            "site_id": str(note.site_id),
        }
        for note in notes
    )
    return {"entries": entries}


@router.get("/incidents")
async def incidents_list(
    actor: ActorContext = Depends(get_current_actor),  # noqa: B008
) -> dict[str, Any]:
    factory = get_session_factory()
    async with factory() as session:
        rows = list(
            (
                await session.scalars(
                    select(Incident)
                    .where(Incident.tenant_id == actor.tenant_id)
                    .order_by(Incident.opened_at.desc())
                )
            ).all()
        )
    return {
        "incidents": [
            {
                "incident_id": str(row.id),
                "title": row.title,
                "symptom_family": row.symptom_family,
                "status": row.status,
                "severity": row.severity,
                "reported_start_at": _iso(row.reported_start_at),
                "reported_end_at": _iso(row.reported_end_at),
                "opened_at": _iso(row.opened_at),
                "site_id": str(row.site_id),
            }
            for row in rows
        ]
    }


@router.get("/incidents/{incident_id}")
async def incident_detail(
    incident_id: uuid.UUID,
    actor: ActorContext = Depends(get_current_actor),  # noqa: B008
) -> dict[str, Any]:
    factory = get_session_factory()
    async with factory() as session:
        incident = await session.scalar(
            select(Incident).where(
                Incident.id == incident_id,
                Incident.tenant_id == actor.tenant_id,
            )
        )
        if incident is None:
            raise HTTPException(status_code=404, detail="resource not found")
        segments = list(
            (
                await session.scalars(
                    select(IncidentSymptomSegment).where(
                        IncidentSymptomSegment.incident_id == incident_id
                    )
                )
            ).all()
        )
        lkg_refs = list(
            (
                await session.scalars(
                    select(LastKnownGoodRef).where(
                        LastKnownGoodRef.valid_for_incident_id == incident_id,
                        LastKnownGoodRef.tenant_id == actor.tenant_id,
                    )
                )
            ).all()
        )
    # Canonical deterministic hypothesis state (EP-023): tenant+incident scoped,
    # ordered by rank. The LLM never decides this state; it is read-only here.
    hypotheses = await HypothesisRepository(factory).list_for_incident(
        tenant_id=actor.tenant_id, incident_id=incident_id
    )
    return {
        "incident": {
            "incident_id": str(incident.id),
            "title": incident.title,
            "symptom_family": incident.symptom_family,
            "description": incident.description,
            "status": incident.status,
            "severity": incident.severity,
            "reported_start_at": _iso(incident.reported_start_at),
            "reported_end_at": _iso(incident.reported_end_at),
            "opened_at": _iso(incident.opened_at),
            "resolved_at": _iso(incident.resolved_at),
            "resolution_summary": incident.resolution_summary,
            "site_id": str(incident.site_id),
        },
        "symptom_segments": [
            {
                "dimension": segment.dimension,
                "operator": segment.operator,
                "value": segment.value,
                "source": segment.source,
            }
            for segment in segments
        ],
        "last_known_good_references": [
            {
                "reference_id": str(ref.id),
                "checkpoint_run_id": str(ref.checkpoint_run_id),
                "scope_key": ref.scope_key,
                "selection_method": ref.selection_method,
                "selection_version": ref.selection_version,
                "selected_at": _iso(ref.selected_at),
                "reason": ref.reason,
                "fingerprints": ref.fingerprints,
            }
            for ref in lkg_refs
        ],
        "hypotheses": [
            {
                "hypothesis_id": str(h.id),
                "hypothesis_key": h.hypothesis_key,
                "family": h.family,
                "statement": h.statement,
                "status": h.status,
                "confidence": h.confidence,
                "rank": h.rank,
                "supporting_count": h.supporting_count,
                "contradicting_count": h.contradicting_count,
                "rationale": h.rationale,
                "engine_version": h.engine_version,
            }
            for h in hypotheses
        ],
    }
