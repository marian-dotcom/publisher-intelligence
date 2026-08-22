import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.events.models import Event
from app.evidence.contracts import (
    validate_confidence,
    validate_note_type,
    validate_relation_type,
)
from app.evidence.models import (
    EventRelation,
    EvidencePack,
    ManualNote,
)
from app.incidents.contracts import InvestigationStateError


class EvidenceRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    # -- typed relations ---------------------------------------------------

    async def add_relation(
        self,
        *,
        tenant_id: uuid.UUID,
        site_id: uuid.UUID,
        from_event_id: uuid.UUID,
        to_event_id: uuid.UUID,
        relation_type: str,
        engine_version: str,
        derived_at: datetime | None = None,
        confidence: str | None = None,
        reason: str | None = None,
    ) -> EventRelation:
        if from_event_id == to_event_id:
            raise InvestigationStateError("event relations require distinct endpoints")
        validate_relation_type(relation_type)
        validate_confidence(confidence)
        await self._assert_event_ownership(tenant_id, site_id, from_event_id)
        await self._assert_event_ownership(tenant_id, site_id, to_event_id)
        async with self._session_factory() as session, session.begin():
            existing = await session.scalar(
                select(EventRelation).where(
                    EventRelation.tenant_id == tenant_id,
                    EventRelation.from_event_id == from_event_id,
                    EventRelation.to_event_id == to_event_id,
                    EventRelation.relation_type == relation_type,
                    EventRelation.engine_version == engine_version,
                )
            )
            if existing is not None:
                return existing
            relation = EventRelation(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                site_id=site_id,
                from_event_id=from_event_id,
                to_event_id=to_event_id,
                relation_type=relation_type,
                confidence=confidence,
                reason=reason,
                derived_at=derived_at or datetime.now(UTC),
                engine_version=engine_version,
            )
            session.add(relation)
            await session.flush()
            return relation

    async def relations_for_events(
        self, *, tenant_id: uuid.UUID, event_ids: tuple[uuid.UUID, ...]
    ) -> tuple[EventRelation, ...]:
        if not event_ids:
            return ()
        async with self._session_factory() as session:
            relations = list(
                (
                    await session.scalars(
                        select(EventRelation).where(
                            EventRelation.tenant_id == tenant_id,
                            EventRelation.from_event_id.in_(event_ids)
                            | EventRelation.to_event_id.in_(event_ids),
                        )
                    )
                ).all()
            )
        return tuple(relations)

    async def _assert_event_ownership(
        self, tenant_id: uuid.UUID, site_id: uuid.UUID, event_id: uuid.UUID
    ) -> None:
        async with self._session_factory() as session:
            owned = await session.scalar(
                select(Event.id).where(
                    Event.id == event_id,
                    Event.tenant_id == tenant_id,
                    Event.site_id == site_id,
                )
            )
        if owned is None:
            raise InvestigationStateError("event does not belong to tenant/site")

    # -- manual notes ------------------------------------------------------

    async def add_manual_note(
        self,
        *,
        tenant_id: uuid.UUID,
        site_id: uuid.UUID,
        note_type: str,
        note_text: str,
        created_by: uuid.UUID | None = None,
        incident_id: uuid.UUID | None = None,
        occurred_at: datetime | None = None,
        source: str = "operator",
    ) -> ManualNote:
        validate_note_type(note_type)
        if not note_text.strip():
            raise InvestigationStateError("manual note text is required")
        if len(note_text) > 5_000:
            raise InvestigationStateError("manual note text exceeds its bound")
        async with self._session_factory() as session, session.begin():
            note = ManualNote(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                site_id=site_id,
                incident_id=incident_id,
                note_type=note_type,
                note_text=note_text,
                occurred_at=occurred_at,
                created_by=created_by,
                source=source,
            )
            session.add(note)
            await session.flush()
            return note

    async def manual_notes_for_site(
        self, *, tenant_id: uuid.UUID, site_id: uuid.UUID
    ) -> tuple[ManualNote, ...]:
        async with self._session_factory() as session:
            notes = list(
                (
                    await session.scalars(
                        select(ManualNote)
                        .where(
                            ManualNote.tenant_id == tenant_id,
                            ManualNote.site_id == site_id,
                        )
                        .order_by(ManualNote.created_at)
                    )
                ).all()
            )
        return tuple(notes)

    # -- evidence packs ----------------------------------------------------

    async def persist_pack(
        self,
        *,
        tenant_id: uuid.UUID,
        site_id: uuid.UUID,
        content: dict[str, Any],
        fingerprints: dict[str, str],
        window_start: datetime,
        window_end: datetime,
        incident_id: uuid.UUID | None = None,
        content_hash_value: str | None = None,
        engine_version: str,
    ) -> tuple[EvidencePack, bool]:
        from app.evidence.contracts import (
            EVIDENCE_PACK_TOO_LARGE,
            MAX_PACK_BYTES,
            canonical_pack_bytes,
        )
        from app.evidence.contracts import (
            content_hash as compute_hash,
        )

        encoded = canonical_pack_bytes(content)
        if len(encoded) > MAX_PACK_BYTES:
            raise InvestigationStateError(EVIDENCE_PACK_TOO_LARGE)
        digest = content_hash_value or compute_hash(content)
        async with self._session_factory() as session, session.begin():
            existing = await session.scalar(
                select(EvidencePack).where(
                    EvidencePack.tenant_id == tenant_id,
                    EvidencePack.incident_id == incident_id,
                    EvidencePack.window_start == window_start,
                    EvidencePack.window_end == window_end,
                    EvidencePack.content_hash == digest,
                )
            )
            if existing is not None:
                return existing, False
            pack = EvidencePack(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                site_id=site_id,
                incident_id=incident_id,
                window_start=window_start,
                window_end=window_end,
                fingerprints=dict(fingerprints),
                content=dict(content),
                content_hash=digest,
                engine_version=engine_version,
            )
            session.add(pack)
            await session.flush()
            return pack, True
