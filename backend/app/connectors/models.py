import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

CONNECTION_STATUSES = (
    "PENDING",
    "CONNECTED",
    "DEGRADED",
    "AUTH_EXPIRED",
    "PERMISSION_ERROR",
    "DISCONNECTED",
)
EXTRACT_STATUSES = ("PENDING", "COMPLETE", "PARTIAL", "FAILED")
FRESHNESS_STATUSES = ("PRELIMINARY", "MATURE", "STALE", "UNKNOWN")


class DataConnection(Base):
    __tablename__ = "data_connections"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'CONNECTED', 'DEGRADED', 'AUTH_EXPIRED', "
            "'PERMISSION_ERROR', 'DISCONNECTED')",
            name="ck_data_connections_status",
        ),
        UniqueConstraint(
            "tenant_id",
            "site_id",
            "provider",
            "external_property_id",
            name="uq_data_connections_property",
        ),
        Index("ix_data_connections_tenant_provider", "tenant_id", "provider", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    external_account_id: Mapped[str | None] = mapped_column(String(200))
    external_property_id: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING")
    scopes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    secret_reference: Mapped[str] = mapped_column(Text, nullable=False)
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_class: Mapped[str | None] = mapped_column(String(100))
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    connection_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SourceExtract(Base):
    __tablename__ = "source_extracts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'COMPLETE', 'PARTIAL', 'FAILED')",
            name="ck_source_extracts_status",
        ),
        CheckConstraint(
            "freshness_status IN ('PRELIMINARY', 'MATURE', 'STALE', 'UNKNOWN')",
            name="ck_source_extracts_freshness",
        ),
        UniqueConstraint(
            "connection_id", "scheduled_run_key", name="uq_source_extracts_logical_run"
        ),
        Index("ix_source_extracts_tenant_site_period", "tenant_id", "site_id", "period_start"),
        Index("ix_source_extracts_connection_type", "connection_id", "extract_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_connections.id", ondelete="RESTRICT"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    extract_type: Mapped[str] = mapped_column(String(100), nullable=False)
    scheduled_run_key: Mapped[str] = mapped_column(String(255), nullable=False)
    query_definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_timezone: Mapped[str | None] = mapped_column(String(100))
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    freshness_status: Mapped[str] = mapped_column(String(20), nullable=False)
    response_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    raw_artifact_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    connector_version: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class MetricSeries(Base):
    __tablename__ = "metric_series"
    __table_args__ = (
        UniqueConstraint("series_key", name="uq_metric_series_key"),
        Index("ix_metric_series_site_source_metric", "site_id", "source", "metric_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    metric_code: Mapped[str] = mapped_column(String(100), nullable=False)
    metric_semantics_version: Mapped[str] = mapped_column(String(50), nullable=False)
    unit: Mapped[str] = mapped_column(String(30), nullable=False)
    granularity: Mapped[str] = mapped_column(String(30), nullable=False)
    dimensions: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    series_key: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MetricPoint(Base):
    __tablename__ = "metric_points"
    __table_args__ = (
        CheckConstraint("period_end > period_start", name="ck_metric_points_period"),
        UniqueConstraint(
            "series_id",
            "period_start",
            "source_extract_id",
            name="uq_metric_points_extract_period",
        ),
        Index("ix_metric_points_tenant_site_period", "tenant_id", "site_id", "period_start"),
        Index("ix_metric_points_series_period", "series_id", "period_start"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False
    )
    series_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("metric_series.id", ondelete="RESTRICT"), nullable=False
    )
    source_extract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_extracts.id", ondelete="RESTRICT"), nullable=False
    )
    source_time: Mapped[str] = mapped_column(String(20), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    numerator: Mapped[float | None] = mapped_column(Float)
    denominator: Mapped[float | None] = mapped_column(Float)
    sample_status: Mapped[str | None] = mapped_column(String(30))
    freshness_status: Mapped[str] = mapped_column(String(20), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
