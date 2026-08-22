import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        CheckConstraint(
            "symptom_family IN ('GAM_ADSERVING','SEARCH_DISCOVER','CONSENT_CMP',"
            "'PREBID_HEADER_BIDDING','VIDEO','BROWSER_PERFORMANCE',"
            "'ANALYTICS_MEASUREMENT','EXTERNAL_INFRASTRUCTURE','REPORTING_DISCREPANCY',"
            "'POLICY_COMPLIANCE','PROGRAMMATIC_MARKET','OTHER')",
            name="ck_incidents_symptom_family",
        ),
        CheckConstraint(
            "status IN ('OPEN','INVESTIGATING','RESOLVED','CLOSED_UNRESOLVED')",
            name="ck_incidents_status",
        ),
        CheckConstraint(
            "severity IS NULL OR severity IN ('LOW','MEDIUM','HIGH','CRITICAL')",
            name="ck_incidents_severity",
        ),
        Index("ix_incidents_tenant_site_status", "tenant_id", "site_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    publisher_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("publishers.id", ondelete="RESTRICT"), nullable=False
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    symptom_family: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    reported_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reported_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'OPEN'"))
    severity: Mapped[str | None] = mapped_column(String(20))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class IncidentSymptomSegment(Base):
    __tablename__ = "incident_symptom_segments"
    __table_args__ = (
        Index(
            "ix_incident_symptom_segments_tenant_incident",
            "tenant_id",
            "incident_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    dimension: Mapped[str] = mapped_column(Text, nullable=False)
    operator: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class LastKnownGoodRef(Base):
    __tablename__ = "last_known_good_refs"
    __table_args__ = (
        UniqueConstraint(
            "scope_key",
            "valid_for_incident_id",
            "checkpoint_run_id",
            name="uq_last_known_good_refs_selection",
        ),
        Index(
            "ix_last_known_good_refs_tenant_site_scope",
            "tenant_id",
            "site_id",
            "scope_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False
    )
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("templates.id", ondelete="RESTRICT")
    )
    scenario_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("browser_scenarios.id", ondelete="RESTRICT")
    )
    scope_key: Mapped[str] = mapped_column(Text, nullable=False)
    checkpoint_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("checkpoint_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    valid_for_incident_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="RESTRICT")
    )
    selected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    selection_method: Mapped[str] = mapped_column(Text, nullable=False)
    selection_version: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    fingerprints: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


# ADR-060/061 + INCIDENT.md §88: a Last Known Good reference is frozen at
# creation. Selection is append-only — later version drift must never alter an
# open investigation's baseline. The mapper-level guard rejects ANY ORM update;
# there is deliberately no update path in the repository.


@event.listens_for(LastKnownGoodRef, "before_update")
def _lkg_ref_frozen(mapper: Any, connection: Any, target: Any) -> None:
    raise RuntimeError("last known good references are immutable after selection")


class InvestigationUsageEntry(Base):
    __tablename__ = "investigation_usage"
    __table_args__ = (
        CheckConstraint(
            "resource_kind IN ('DRILLDOWN','LLM_PASS','DIAGNOSTIC_RUN')",
            name="ck_investigation_usage_resource_kind",
        ),
        CheckConstraint("amount > 0", name="ck_investigation_usage_amount_positive"),
        UniqueConstraint("usage_key", name="uq_investigation_usage_key"),
        Index(
            "ix_investigation_usage_tenant_incident_kind",
            "tenant_id",
            "incident_id",
            "resource_kind",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="RESTRICT")
    )
    investigation_key: Mapped[str] = mapped_column(Text, nullable=False)
    resource_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    usage_key: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class RetentionHold(Base):
    __tablename__ = "retention_holds"
    __table_args__ = (
        Index(
            "ix_retention_holds_tenant_active",
            "tenant_id",
            postgresql_where=text("released_at IS NULL"),
        ),
        Index(
            "uq_retention_holds_active_target",
            "tenant_id",
            "reason",
            text("COALESCE(incident_id::text, '')"),
            text("COALESCE(artifact_id::text, '')"),
            text("COALESCE(source_extract_id::text, '')"),
            unique=True,
            postgresql_where=text("released_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="RESTRICT")
    )
    artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("artifacts.id", ondelete="RESTRICT")
    )
    source_extract_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("source_extracts.id", ondelete="RESTRICT"),
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_by: Mapped[str | None] = mapped_column(Text)
