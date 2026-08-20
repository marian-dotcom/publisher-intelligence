import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EventDefinition(Base):
    __tablename__ = "event_definitions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    family: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    default_severity: Mapped[str] = mapped_column(String(20), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(nullable=False, default=True)
    metadata_schema: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint(
            "time_precision IN ('EXACT', 'WINDOW', 'DAY')", name="ck_events_time_precision"
        ),
        CheckConstraint(
            "severity IN ('INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL')", name="ck_events_severity"
        ),
        CheckConstraint(
            "observation_confidence IN ('LOW', 'MEDIUM', 'HIGH')",
            name="ck_events_observation_confidence",
        ),
        CheckConstraint(
            "status IN ('RECORDED', 'ACTIVE', 'RESOLVED', 'SUPERSEDED')",
            name="ck_events_status",
        ),
        CheckConstraint(
            "(status = 'RECORDED' AND condition_key IS NULL) OR "
            "(status IN ('ACTIVE', 'RESOLVED') AND condition_key IS NOT NULL) OR "
            "status = 'SUPERSEDED'",
            name="ck_events_condition_lifecycle",
        ),
        CheckConstraint(
            "status != 'ACTIVE' OR ended_at IS NULL", name="ck_events_active_has_no_end"
        ),
        CheckConstraint(
            "status != 'RESOLVED' OR ended_at IS NOT NULL", name="ck_events_resolved_has_end"
        ),
        CheckConstraint(
            "occurred_after_at IS NULL OR occurred_before_at IS NULL OR "
            "occurred_before_at >= occurred_after_at",
            name="ck_events_occurrence_bounds",
        ),
        Index("ix_events_tenant_site_detected", "tenant_id", "site_id", "detected_at"),
        Index("ix_events_tenant_site_started", "tenant_id", "site_id", "started_at"),
        Index(
            "ix_events_tenant_site_status_started",
            "tenant_id",
            "site_id",
            "status",
            "started_at",
        ),
        Index(
            "uq_events_active_condition",
            "tenant_id",
            "condition_key",
            unique=True,
            postgresql_where=text("status = 'ACTIVE' AND condition_key IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False
    )
    event_definition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event_definitions.id", ondelete="RESTRICT"), nullable=False
    )
    subject_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("domain_entities.id", ondelete="RESTRICT")
    )
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("templates.id", ondelete="RESTRICT")
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    occurred_after_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    occurred_before_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    time_precision: Mapped[str] = mapped_column(String(20), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    observation_confidence: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(50), nullable=False)
    source_version: Mapped[str | None] = mapped_column(String(50))
    condition_key: Mapped[str | None] = mapped_column(String(64))
    risk_score: Mapped[float | None] = mapped_column(Float)
    scope: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    superseded_by_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="RESTRICT")
    )


class EventEvidenceRef(Base):
    __tablename__ = "event_evidence_refs"
    __table_args__ = (
        UniqueConstraint(
            "event_id", "evidence_kind", "source_id", "relation", name="uq_event_evidence_ref"
        ),
        Index("ix_event_evidence_refs_tenant_event", "tenant_id", "event_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="RESTRICT"), nullable=False
    )
    evidence_kind: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    relation: Mapped[str] = mapped_column(String(30), nullable=False)
    summary: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
