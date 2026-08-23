import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Hypothesis(Base):
    __tablename__ = "hypotheses"
    __table_args__ = (
        CheckConstraint(
            "status IN ('LEADING','CONTENDER','WEAKENED','UNRESOLVED')",
            name="ck_hypotheses_status",
        ),
        CheckConstraint(
            "confidence IN ('LOW','MEDIUM','HIGH')",
            name="ck_hypotheses_confidence",
        ),
        UniqueConstraint("incident_id", "hypothesis_key", name="uq_hypotheses_incident_key"),
        Index("ix_hypotheses_tenant_site", "tenant_id", "site_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    hypothesis_key: Mapped[str] = mapped_column(Text, nullable=False)
    family: Mapped[str] = mapped_column(String(50), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'UNRESOLVED'")
    )
    confidence: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'LOW'")
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    supporting_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    contradicting_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    engine_version: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        server_onupdate=text("CURRENT_TIMESTAMP"),
    )


class HypothesisEvidence(Base):
    __tablename__ = "hypothesis_evidence"
    __table_args__ = (
        CheckConstraint(
            "source_kind IN ('EVENT','MANUAL_NOTE','OBSERVATION_GAP')",
            name="ck_hypothesis_evidence_source",
        ),
        CheckConstraint(
            "relation IN ('SUPPORTS','CONTRADICTS','CONTEXT')",
            name="ck_hypothesis_evidence_relation",
        ),
        UniqueConstraint("hypothesis_id", "evidence_key", name="uq_hypothesis_evidence_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    hypothesis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hypotheses.id", ondelete="CASCADE"), nullable=False
    )
    evidence_key: Mapped[str] = mapped_column(Text, nullable=False)
    source_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="RESTRICT")
    )
    manual_note_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("manual_notes.id", ondelete="RESTRICT")
    )
    relation: Mapped[str] = mapped_column(String(20), nullable=False)
    weight: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
