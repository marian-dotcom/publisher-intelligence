import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PublicConfigSnapshot(Base):
    __tablename__ = "public_config_snapshots"
    __table_args__ = (
        CheckConstraint(
            "config_type IN ('ROBOTS_TXT','ADS_TXT')",
            name="ck_public_config_snapshots_type",
        ),
        CheckConstraint(
            "parse_status IN ('VALID','VALID_WITH_WARNINGS','EMPTY','INVALID','MISSING',"
            "'HTTP_ERROR','UNREACHABLE','TOO_LARGE','BLOCKED')",
            name="ck_public_config_snapshots_parse_status",
        ),
        CheckConstraint(
            "http_status IS NULL OR (http_status >= 100 AND http_status <= 599)",
            name="ck_public_config_snapshots_http_status",
        ),
        CheckConstraint(
            "(fetch_kind = 'SCHEDULED' AND validation_of_snapshot_id IS NULL) OR "
            "(fetch_kind = 'VALIDATION' AND validation_of_snapshot_id IS NOT NULL)",
            name="ck_public_config_snapshots_fetch_kind",
        ),
        CheckConstraint(
            "validation_of_snapshot_id IS NULL OR validation_of_snapshot_id <> id",
            name="ck_public_config_snapshots_not_self_validation",
        ),
        UniqueConstraint("observation_key", name="uq_public_config_snapshot_observation_key"),
        Index(
            "ix_public_config_snapshots_tenant_site_type_observed",
            "tenant_id",
            "site_id",
            "config_type",
            "observed_at",
        ),
        Index("ix_public_config_snapshots_validation_primary", "validation_of_snapshot_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False
    )
    config_type: Mapped[str] = mapped_column(String(30), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    parse_status: Mapped[str] = mapped_column(String(30), nullable=False)
    artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("artifacts.id", ondelete="RESTRICT")
    )
    normalizer_version: Mapped[str] = mapped_column(String(50), nullable=False)
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    fetch_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    validation_of_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public_config_snapshots.id", ondelete="RESTRICT"),
    )
    observation_key: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class AdsTxtRecord(Base):
    __tablename__ = "ads_txt_records"
    __table_args__ = (
        CheckConstraint(
            "relationship IN ('DIRECT','RESELLER')", name="ck_ads_txt_records_relationship"
        ),
        UniqueConstraint("snapshot_id", "record_hash", name="uq_ads_txt_records_snapshot_hash"),
        Index("ix_ads_txt_records_tenant_site_snapshot", "tenant_id", "site_id", "snapshot_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False
    )
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public_config_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    advertising_system_domain: Mapped[str] = mapped_column(String(253), nullable=False)
    publisher_account_id: Mapped[str] = mapped_column(String(500), nullable=False)
    relationship: Mapped[str] = mapped_column(String(20), nullable=False)
    cert_authority_id: Mapped[str | None] = mapped_column(String(255))
    record_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_valid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    validation_errors: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
