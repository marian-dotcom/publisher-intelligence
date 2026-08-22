import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

RELATION_TYPES = frozenset(
    {
        "PRECEDES",
        "COINCIDES_WITH",
        "SAME_SEGMENT_AS",
        "MECHANISTICALLY_CAN_AFFECT",
        "METRIC_PARENT_OF",
        "METRIC_DESCENDANT_OF",
        "SUPPORTS",
        "CONTRADICTS",
        "INTRODUCED_BY",
        "RESOLVED_AFTER",
        "PERSISTED_AFTER_REMOVAL",
        "EXTERNAL_CONTEXT_FOR",
        "UNKNOWN_RELATION",
    }
)
NOTE_TYPES = frozenset(
    {
        "DEPLOY",
        "ROLLBACK",
        "CONFIG_CHANGE",
        "OPERATOR_INTERVENTION",
        "EXTERNAL_COMMUNICATION",
        "OTHER",
    }
)


class EventRelation(Base):
    __tablename__ = "event_relations"
    __table_args__ = (
        CheckConstraint(
            f"relation_type IN ({','.join(repr(t) for t in sorted(RELATION_TYPES))})",
            name="ck_event_relations_type",
        ),
        CheckConstraint(
            "confidence IS NULL OR confidence IN ('LOW','MEDIUM','HIGH')",
            name="ck_event_relations_confidence",
        ),
        UniqueConstraint(
            "tenant_id",
            "from_event_id",
            "to_event_id",
            "relation_type",
            "engine_version",
            name="uq_event_relations_edge",
        ),
        Index("ix_event_relations_tenant_site", "tenant_id", "site_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False
    )
    from_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="RESTRICT"), nullable=False
    )
    to_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="RESTRICT"), nullable=False
    )
    relation_type: Mapped[str] = mapped_column(String(40), nullable=False)
    confidence: Mapped[str | None] = mapped_column(String(20))
    reason: Mapped[str | None] = mapped_column(Text)
    derived_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


# DATA_MODEL §64: relations are derived facts recorded once. Any ORM update is
# a provenance violation; there is no repository update path.
@event.listens_for(EventRelation, "before_update")
def _event_relation_frozen(mapper: Any, connection: Any, target: Any) -> None:
    raise RuntimeError("event relations are immutable after creation")


class ManualNote(Base):
    __tablename__ = "manual_notes"
    __table_args__ = (
        CheckConstraint(
            f"note_type IN ({','.join(repr(t) for t in sorted(NOTE_TYPES))})",
            name="ck_manual_notes_type",
        ),
        Index(
            "ix_manual_notes_tenant_site_created",
            "tenant_id",
            "site_id",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False
    )
    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="RESTRICT")
    )
    note_type: Mapped[str] = mapped_column(String(40), nullable=False)
    note_text: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default=text("'operator'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class EvidencePack(Base):
    __tablename__ = "evidence_packs"
    __table_args__ = (
        UniqueConstraint(
            "incident_id",
            "window_start",
            "window_end",
            "content_hash",
            name="uq_evidence_packs_generation",
        ),
        Index(
            "ix_evidence_packs_tenant_site_window",
            "tenant_id",
            "site_id",
            "window_start",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False
    )
    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="RESTRICT")
    )
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fingerprints: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
