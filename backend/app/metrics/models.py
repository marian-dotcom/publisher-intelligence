import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MetricDerivation(Base):
    __tablename__ = "metric_derivations"
    __table_args__ = (
        CheckConstraint("period_end > period_start", name="ck_metric_derivations_period"),
        CheckConstraint(
            "freshness_status IN ('PRELIMINARY', 'MATURE')",
            name="ck_metric_derivations_freshness",
        ),
        UniqueConstraint("derivation_key", name="uq_metric_derivations_key"),
        Index(
            "ix_metric_derivations_tenant_site_period",
            "tenant_id",
            "site_id",
            "period_start",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False
    )
    definition_code: Mapped[str] = mapped_column(String(100), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(50), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(50), nullable=False)
    alignment_policy: Mapped[str] = mapped_column(String(50), nullable=False)
    freshness_policy: Mapped[str] = mapped_column(String(50), nullable=False)
    granularity: Mapped[str] = mapped_column(String(30), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    freshness_status: Mapped[str] = mapped_column(String(20), nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    derivation_key: Mapped[str] = mapped_column(String(64), nullable=False)
    limitations: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class MetricDerivationInput(Base):
    __tablename__ = "metric_derivation_inputs"
    __table_args__ = (
        CheckConstraint(
            "role IN ('NUMERATOR', 'DENOMINATOR')",
            name="ck_metric_derivation_inputs_role",
        ),
        UniqueConstraint(
            "derivation_id",
            "source_metric_point_id",
            "role",
            name="uq_metric_derivation_inputs_source_role",
        ),
        Index("ix_metric_derivation_inputs_source", "source_metric_point_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False
    )
    derivation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("metric_derivations.id", ondelete="RESTRICT"), nullable=False
    )
    source_metric_point_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("metric_points.id", ondelete="RESTRICT"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
