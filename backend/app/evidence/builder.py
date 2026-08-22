"""Deterministic evidence-pack assembly over stored evidence.

Identical repository state within the requested window produces byte-identical
pack content. Manual notes are included only as clearly-tagged human_reported
entries and never feed event derivation.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.browser.models import CheckpointRun
from app.events.models import Event
from app.evidence.contracts import (
    NOTE_SOURCE_HUMAN,
    PACK_ENGINE_VERSION,
)
from app.evidence.models import EventRelation, ManualNote
from app.incidents.models import Incident, IncidentSymptomSegment
from app.public_config.models import PublicConfigSnapshot

PACK_MAX_RUNS = 200
PACK_MAX_SNAPSHOTS = 100
PACK_MAX_EVENTS = 200


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


class EvidencePackBuilder:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def build(
        self,
        *,
        tenant_id: uuid.UUID,
        site_id: uuid.UUID,
        incident_id: uuid.UUID | None,
        window_start: datetime,
        window_end: datetime,
    ) -> dict[str, Any]:
        if window_end <= window_start:
            raise ValueError("evidence pack window end must be after start")
        async with self._session_factory() as session:
            incident = None
            segments: list[IncidentSymptomSegment] = []
            if incident_id is not None:
                incident = await session.scalar(
                    select(Incident).where(
                        Incident.id == incident_id,
                        Incident.tenant_id == tenant_id,
                        Incident.site_id == site_id,
                    )
                )
                if incident is None:
                    raise ValueError("incident does not belong to tenant/site")
                segments = list(
                    (
                        await session.scalars(
                            select(IncidentSymptomSegment).where(
                                IncidentSymptomSegment.incident_id == incident_id,
                                IncidentSymptomSegment.tenant_id == tenant_id,
                            )
                        )
                    ).all()
                )

            runs = list(
                (
                    await session.scalars(
                        select(CheckpointRun)
                        .where(
                            CheckpointRun.tenant_id == tenant_id,
                            CheckpointRun.site_id == site_id,
                            CheckpointRun.observation_kind == "SCHEDULED",
                            CheckpointRun.scheduled_for >= window_start,
                            CheckpointRun.scheduled_for <= window_end,
                        )
                        .order_by(CheckpointRun.scheduled_for)
                        .limit(PACK_MAX_RUNS)
                    )
                ).all()
            )
            snapshots = list(
                (
                    await session.scalars(
                        select(PublicConfigSnapshot)
                        .where(
                            PublicConfigSnapshot.tenant_id == tenant_id,
                            PublicConfigSnapshot.site_id == site_id,
                            PublicConfigSnapshot.observed_at >= window_start,
                            PublicConfigSnapshot.observed_at <= window_end,
                        )
                        .order_by(PublicConfigSnapshot.observed_at)
                        .limit(PACK_MAX_SNAPSHOTS)
                    )
                ).all()
            )
            events = list(
                (
                    await session.scalars(
                        select(Event)
                        .where(
                            Event.tenant_id == tenant_id,
                            Event.site_id == site_id,
                            Event.detected_at >= window_start,
                            Event.detected_at <= window_end,
                        )
                        .order_by(Event.detected_at)
                        .limit(PACK_MAX_EVENTS)
                    )
                ).all()
            )
            relations = list(
                (
                    await session.scalars(
                        select(EventRelation).where(
                            EventRelation.tenant_id == tenant_id,
                            EventRelation.site_id == site_id,
                            EventRelation.derived_at >= window_start,
                            EventRelation.derived_at <= window_end,
                        )
                    )
                ).all()
            )
            notes = list(
                (
                    await session.scalars(
                        select(ManualNote)
                        .where(
                            ManualNote.tenant_id == tenant_id,
                            ManualNote.site_id == site_id,
                            ManualNote.created_at <= window_end,
                        )
                        .order_by(ManualNote.created_at)
                    )
                ).all()
            )

        content: dict[str, Any] = {
            "engine_version": PACK_ENGINE_VERSION,
            "window": {
                "start": window_start.isoformat(),
                "end": window_end.isoformat(),
            },
            "incident": (
                {
                    "id": str(incident.id),
                    "title": incident.title,
                    "symptom_family": incident.symptom_family,
                    "description": incident.description,
                    "reported_start_at": _iso(incident.reported_start_at),
                    "reported_end_at": _iso(incident.reported_end_at),
                    "status": incident.status,
                    "symptom_segments": [
                        {
                            "dimension": segment.dimension,
                            "operator": segment.operator,
                            "value": segment.value,
                            "source": segment.source,
                        }
                        for segment in sorted(segments, key=lambda item: item.id)
                    ],
                }
                if incident is not None
                else None
            ),
            "scheduled_checkpoints": [
                {
                    "run_id": str(run.id),
                    "scenario_id": str(run.scenario_id),
                    "observation_kind": run.observation_kind,
                    "status": run.status,
                    "scheduled_for": _iso(run.scheduled_for),
                    "collector_bundle_version": run.collector_bundle_version,
                    "limitations": list(run.limitations),
                }
                for run in sorted(runs, key=lambda item: item.scheduled_for)
            ],
            "public_config_states": [
                {
                    "snapshot_id": str(snapshot.id),
                    "config_type": snapshot.config_type,
                    "parse_status": snapshot.parse_status,
                    "observed_at": _iso(snapshot.observed_at),
                    "fetch_kind": snapshot.fetch_kind,
                    "normalizer_version": snapshot.normalizer_version,
                }
                for snapshot in sorted(snapshots, key=lambda item: item.observed_at)
            ],
            "events": [
                {
                    "event_id": str(item.id),
                    "definition_id": str(item.event_definition_id),
                    "status": item.status,
                    "severity": item.severity,
                    "detected_at": _iso(item.detected_at),
                    "occurred_before_at": _iso(item.occurred_before_at),
                    "summary": item.summary,
                }
                for item in sorted(events, key=lambda item: (item.detected_at, item.id))
            ],
            "relations": [
                {
                    "from_event_id": str(relation.from_event_id),
                    "to_event_id": str(relation.to_event_id),
                    "relation_type": relation.relation_type,
                    "confidence": relation.confidence,
                    "engine_version": relation.engine_version,
                }
                for relation in sorted(relations, key=lambda item: (item.derived_at, item.id))
            ],
            # Human-reported context: explicitly tagged, never merged into the
            # machine_observed sections above.
            "human_reported_notes": [
                {
                    "note_id": str(note.id),
                    "note_type": note.note_type,
                    "text": note.note_text,
                    "occurred_at": _iso(note.occurred_at),
                    "source": note.source,
                    "created_at": _iso(note.created_at),
                }
                for note in sorted(notes, key=lambda item: item.created_at)
            ],
        }
        for note_entry in content["human_reported_notes"]:
            note_entry["evidence_source"] = NOTE_SOURCE_HUMAN
        content["human_reported_notes_count"] = len(content["human_reported_notes"])
        content["machine_observed_sections"] = [
            "scheduled_checkpoints",
            "public_config_states",
            "events",
            "relations",
        ]
        return content

    @staticmethod
    def pack_hash(content: dict[str, Any]) -> str:
        from app.evidence.contracts import content_hash as compute_hash

        return compute_hash(content)
