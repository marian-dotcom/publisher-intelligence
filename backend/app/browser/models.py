import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
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

FINAL_CHECKPOINT_STATUSES = (
    "COMPLETE",
    "PARTIAL",
    "SITE_ERROR",
    "BROWSER_ERROR",
    "TIMEOUT",
    "BLOCKED",
)


class Publisher(Base):
    __tablename__ = "publishers"
    __table_args__ = (UniqueConstraint("tenant_id", "slug"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    default_timezone: Mapped[str] = mapped_column(String(100), nullable=False, default="UTC")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class Site(Base):
    __tablename__ = "sites"
    __table_args__ = (UniqueConstraint("tenant_id", "canonical_domain"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    publisher_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("publishers.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    canonical_domain: Mapped[str] = mapped_column(String(253), nullable=False)
    canonical_scheme: Mapped[str] = mapped_column(String(10), nullable=False, default="https")
    timezone: Mapped[str] = mapped_column(String(100), nullable=False, default="UTC")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class Template(Base):
    __tablename__ = "templates"
    __table_args__ = (UniqueConstraint("site_id", "code"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    template_family: Mapped[str] = mapped_column(String(100), nullable=False, default="CUSTOM")
    fingerprint_version: Mapped[str | None] = mapped_column(String(50))
    expected_features: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MonitoredUrl(Base):
    __tablename__ = "monitored_urls"
    __table_args__ = (Index("ix_monitored_urls_site_status", "site_id", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("templates.id", ondelete="RESTRICT"), nullable=False
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_canary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class InteractionProfile(Base):
    __tablename__ = "interaction_profiles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "site_id", "code", "version"),
        Index("ix_interaction_profiles_site_status", "site_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="RESTRICT")
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BrowserScenario(Base):
    __tablename__ = "browser_scenarios"
    __table_args__ = (
        UniqueConstraint("tenant_id", "site_id", "code", "version"),
        CheckConstraint(
            "consent_path IN ('PRIMARY', 'REJECT', 'NONE')",
            name="ck_browser_scenarios_consent_path",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False
    )
    interaction_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interaction_profiles.id", ondelete="RESTRICT")
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    device_class: Mapped[str] = mapped_column(String(20), nullable=False, default="DESKTOP")
    device_profile: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    locale: Mapped[str] = mapped_column(String(50), nullable=False, default="en-US")
    timezone: Mapped[str] = mapped_column(String(100), nullable=False, default="UTC")
    cache_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="CLEAN")
    consent_path: Mapped[str] = mapped_column(String(20), nullable=False, default="PRIMARY")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CheckpointWindow(Base):
    __tablename__ = "checkpoint_windows"
    __table_args__ = (UniqueConstraint("site_id", "scheduled_for"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False
    )
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="SCHEDULED")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CheckpointRun(Base):
    __tablename__ = "checkpoint_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'COMPLETE', 'PARTIAL', 'SITE_ERROR', "
            "'BROWSER_ERROR', 'TIMEOUT', 'BLOCKED')",
            name="ck_checkpoint_runs_status",
        ),
        UniqueConstraint("checkpoint_window_id", "monitored_url_id", "scenario_id"),
        Index("ix_checkpoint_runs_tenant_started", "tenant_id", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False
    )
    checkpoint_window_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("checkpoint_windows.id", ondelete="RESTRICT"),
        nullable=False,
    )
    monitored_url_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("monitored_urls.id", ondelete="RESTRICT"), nullable=False
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("templates.id", ondelete="RESTRICT"), nullable=False
    )
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("browser_scenarios.id", ondelete="RESTRICT"), nullable=False
    )
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    final_url: Mapped[str | None] = mapped_column(Text)
    http_status: Mapped[int | None] = mapped_column(Integer)
    playwright_version: Mapped[str | None] = mapped_column(String(50))
    chromium_version: Mapped[str | None] = mapped_column(String(100))
    collector_bundle_version: Mapped[str] = mapped_column(
        String(50), nullable=False, default="b7-v1"
    )
    environment: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    limitations: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class CheckpointAttempt(Base):
    __tablename__ = "checkpoint_attempts"
    __table_args__ = (UniqueConstraint("checkpoint_run_id", "attempt_number"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    checkpoint_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("checkpoint_runs.id", ondelete="RESTRICT"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="RUNNING")
    failure_class: Mapped[str | None] = mapped_column(String(100))
    failure_message: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )


class CollectorRun(Base):
    __tablename__ = "collector_runs"
    __table_args__ = (UniqueConstraint("checkpoint_run_id", "collector_type"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    checkpoint_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("checkpoint_runs.id", ondelete="RESTRICT"), nullable=False
    )
    collector_type: Mapped[str] = mapped_column(String(100), nullable=False)
    collector_version: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class Artifact(Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        UniqueConstraint("checkpoint_run_id", "artifact_type"),
        Index("ix_artifacts_tenant_checkpoint", "tenant_id", "checkpoint_run_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False
    )
    checkpoint_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("checkpoint_runs.id", ondelete="RESTRICT"), nullable=False
    )
    artifact_type: Mapped[str] = mapped_column(String(100), nullable=False)
    storage_provider: Mapped[str] = mapped_column(
        String(50), nullable=False, default="S3_COMPATIBLE"
    )
    object_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(String(200), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    retention_class: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )


class DomainEntity(Base):
    __tablename__ = "domain_entities"
    __table_args__ = (
        UniqueConstraint("site_id", "entity_kind", "stable_key"),
        Index("ix_domain_entities_tenant_site_kind", "tenant_id", "site_id", "entity_kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False
    )
    entity_kind: Mapped[str] = mapped_column(String(100), nullable=False)
    stable_key: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(300))
    source_system: Mapped[str | None] = mapped_column(String(100))
    native_id: Mapped[str | None] = mapped_column(String(300))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    identity_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class EntityObservation(Base):
    __tablename__ = "entity_observations"
    __table_args__ = (
        UniqueConstraint(
            "checkpoint_run_id", "entity_id", "observation_type", name="uq_entity_observation_run"
        ),
        Index("ix_entity_observations_tenant_checkpoint", "tenant_id", "checkpoint_run_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False
    )
    checkpoint_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("checkpoint_runs.id", ondelete="RESTRICT"), nullable=False
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("domain_entities.id", ondelete="RESTRICT"), nullable=False
    )
    observation_type: Mapped[str] = mapped_column(String(100), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    state_hash: Mapped[str | None] = mapped_column(String(64))
    state: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    collector_version: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class TemplateExpectedEntity(Base):
    __tablename__ = "template_expected_entities"
    __table_args__ = (
        UniqueConstraint(
            "template_id",
            "entity_id",
            "expectation_type",
            "valid_from",
            name="uq_template_expected_entity_version",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_to > valid_from",
            name="ck_template_expected_entity_validity",
        ),
        Index(
            "ix_template_expected_entities_tenant_template",
            "tenant_id",
            "template_id",
            "valid_from",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("templates.id", ondelete="RESTRICT"), nullable=False
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("domain_entities.id", ondelete="RESTRICT"), nullable=False
    )
    expectation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class GPTSlotObservation(Base):
    __tablename__ = "gpt_slot_observations"
    __table_args__ = (
        UniqueConstraint("checkpoint_run_id", "slot_entity_id", name="uq_gpt_slot_observation_run"),
        CheckConstraint("request_count >= 0", name="ck_gpt_slot_request_count"),
        Index("ix_gpt_slot_observations_tenant_checkpoint", "tenant_id", "checkpoint_run_id"),
        Index("ix_gpt_slot_observations_site_created", "site_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False
    )
    checkpoint_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("checkpoint_runs.id", ondelete="RESTRICT"), nullable=False
    )
    slot_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("domain_entities.id", ondelete="RESTRICT"), nullable=False
    )
    dom_element_id: Mapped[str | None] = mapped_column(String(300))
    ad_unit_path: Mapped[str | None] = mapped_column(String(500))
    sizes: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    expected: Mapped[bool] = mapped_column(Boolean, nullable=False)
    present: Mapped[bool] = mapped_column(Boolean, nullable=False)
    defined_at_ms: Mapped[int | None] = mapped_column(Integer)
    requested_at_ms: Mapped[int | None] = mapped_column(Integer)
    response_at_ms: Mapped[int | None] = mapped_column(Integer)
    render_ended_at_ms: Mapped[int | None] = mapped_column(Integer)
    onload_at_ms: Mapped[int | None] = mapped_column(Integer)
    viewable_at_ms: Mapped[int | None] = mapped_column(Integer)
    is_empty: Mapped[bool | None] = mapped_column(Boolean)
    creative_id: Mapped[str | None] = mapped_column(String(300))
    line_item_id: Mapped[str | None] = mapped_column(String(300))
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    collector_version: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class CMPObservation(Base):
    __tablename__ = "cmp_observations"
    __table_args__ = (
        UniqueConstraint("checkpoint_run_id"),
        Index("ix_cmp_observations_tenant_checkpoint", "tenant_id", "checkpoint_run_id"),
        CheckConstraint(
            "consent_action IN ('PRIMARY', 'REJECT', 'NONE')",
            name="ck_cmp_observations_consent_action",
        ),
        CheckConstraint(
            "consent_action_status IN "
            "('NOT_REQUESTED', 'NOT_PRESENT', 'UNAVAILABLE', 'COMPLETED', 'TIMEOUT', 'ERROR')",
            name="ck_cmp_observations_action_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False
    )
    checkpoint_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("checkpoint_runs.id", ondelete="RESTRICT"), nullable=False
    )
    cmp_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("domain_entities.id", ondelete="RESTRICT")
    )
    cmp_detected: Mapped[bool] = mapped_column(Boolean, nullable=False)
    tcf_api_detected: Mapped[bool] = mapped_column(Boolean, nullable=False)
    ui_detected_at_ms: Mapped[int | None] = mapped_column(Integer)
    api_ready_at_ms: Mapped[int | None] = mapped_column(Integer)
    consent_action: Mapped[str] = mapped_column(String(30), nullable=False)
    consent_action_status: Mapped[str] = mapped_column(String(30), nullable=False)
    action_started_at_ms: Mapped[int | None] = mapped_column(Integer)
    action_completed_at_ms: Mapped[int | None] = mapped_column(Integer)
    tc_state_available_at_ms: Mapped[int | None] = mapped_column(Integer)
    gdpr_applies: Mapped[bool | None] = mapped_column(Boolean)
    tc_string_hash: Mapped[str | None] = mapped_column(String(64))
    tcf_error_codes: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    collector_version: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )


class ConsentPhaseDependencyObservation(Base):
    __tablename__ = "consent_phase_dependency_observations"
    __table_args__ = (
        UniqueConstraint(
            "checkpoint_run_id",
            "phase",
            "dependency_entity_id",
            name="uq_consent_phase_dependency_run",
        ),
        Index(
            "ix_consent_phase_dependencies_tenant_checkpoint",
            "tenant_id",
            "checkpoint_run_id",
        ),
        CheckConstraint(
            "phase IN ('PRE_CONSENT', 'POST_ACCEPT', 'POST_REJECT')",
            name="ck_consent_phase_dependencies_phase",
        ),
        CheckConstraint(
            "request_count >= 0 AND error_count >= 0",
            name="ck_consent_phase_dependencies_counts",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    checkpoint_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("checkpoint_runs.id", ondelete="RESTRICT"), nullable=False
    )
    phase: Mapped[str] = mapped_column(String(30), nullable=False)
    dependency_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("domain_entities.id", ondelete="RESTRICT"), nullable=False
    )
    request_count: Mapped[int] = mapped_column(Integer, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False)
    first_request_at_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class PrebidAuctionObservation(Base):
    __tablename__ = "prebid_auction_observations"
    __table_args__ = (
        UniqueConstraint("checkpoint_run_id", "auction_key", name="uq_prebid_auction_run_key"),
        CheckConstraint(
            "bidder_request_count >= 0 AND bid_response_count >= 0 AND "
            "no_bid_count >= 0 AND timeout_count >= 0",
            name="ck_prebid_auction_counts",
        ),
        Index("ix_prebid_auctions_tenant_checkpoint", "tenant_id", "checkpoint_run_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False
    )
    checkpoint_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("checkpoint_runs.id", ondelete="RESTRICT"), nullable=False
    )
    auction_key: Mapped[str] = mapped_column(String(50), nullable=False)
    started_at_ms: Mapped[float | None] = mapped_column(Float)
    ended_at_ms: Mapped[float | None] = mapped_column(Float)
    configured_timeout_ms: Mapped[int | None] = mapped_column(Integer)
    ad_unit_count: Mapped[int | None] = mapped_column(Integer)
    bidder_request_count: Mapped[int] = mapped_column(Integer, nullable=False)
    bid_response_count: Mapped[int] = mapped_column(Integer, nullable=False)
    no_bid_count: Mapped[int] = mapped_column(Integer, nullable=False)
    timeout_count: Mapped[int] = mapped_column(Integer, nullable=False)
    collector_version: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )


class PrebidBidderObservation(Base):
    __tablename__ = "prebid_bidder_observations"
    __table_args__ = (
        UniqueConstraint(
            "auction_observation_id", "bidder_code", name="uq_prebid_bidder_auction_code"
        ),
        CheckConstraint(
            "request_count >= 0 AND response_count >= 0 AND no_bid_count >= 0 AND "
            "timeout_count >= 0 AND winning_bid_count >= 0",
            name="ck_prebid_bidder_counts",
        ),
        Index("ix_prebid_bidders_tenant_checkpoint", "tenant_id", "checkpoint_run_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False
    )
    checkpoint_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("checkpoint_runs.id", ondelete="RESTRICT"), nullable=False
    )
    auction_observation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prebid_auction_observations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    bidder_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("domain_entities.id", ondelete="RESTRICT")
    )
    bidder_code: Mapped[str] = mapped_column(String(100), nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False)
    response_count: Mapped[int] = mapped_column(Integer, nullable=False)
    no_bid_count: Mapped[int] = mapped_column(Integer, nullable=False)
    timeout_count: Mapped[int] = mapped_column(Integer, nullable=False)
    response_time_ms_min: Mapped[float | None] = mapped_column(Float)
    response_time_ms_max: Mapped[float | None] = mapped_column(Float)
    response_time_ms_avg: Mapped[float | None] = mapped_column(Float)
    winning_bid_count: Mapped[int] = mapped_column(Integer, nullable=False)
    collector_version: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )


class VideoPlayerObservation(Base):
    __tablename__ = "video_player_observations"
    __table_args__ = (
        UniqueConstraint(
            "checkpoint_run_id", "player_entity_id", name="uq_video_player_run_entity"
        ),
        CheckConstraint(
            "vast_request_count >= 0 AND vast_error_count >= 0 AND media_request_count >= 0",
            name="ck_video_player_counts",
        ),
        CheckConstraint(
            "(width_px IS NULL OR width_px >= 0) AND (height_px IS NULL OR height_px >= 0)",
            name="ck_video_player_dimensions",
        ),
        Index("ix_video_players_tenant_checkpoint", "tenant_id", "checkpoint_run_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False
    )
    checkpoint_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("checkpoint_runs.id", ondelete="RESTRICT"), nullable=False
    )
    player_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("domain_entities.id", ondelete="RESTRICT"), nullable=False
    )
    present: Mapped[bool] = mapped_column(Boolean, nullable=False)
    visible: Mapped[bool | None] = mapped_column(Boolean)
    sticky: Mapped[bool | None] = mapped_column(Boolean)
    fixed: Mapped[bool | None] = mapped_column(Boolean)
    autoplay: Mapped[bool | None] = mapped_column(Boolean)
    muted: Mapped[bool | None] = mapped_column(Boolean)
    controls_present: Mapped[bool | None] = mapped_column(Boolean)
    dismiss_control_present: Mapped[bool | None] = mapped_column(Boolean)
    width_px: Mapped[float | None] = mapped_column(Float)
    height_px: Mapped[float | None] = mapped_column(Float)
    vast_request_count: Mapped[int] = mapped_column(Integer, nullable=False)
    vast_error_count: Mapped[int] = mapped_column(Integer, nullable=False)
    media_request_count: Mapped[int] = mapped_column(Integer, nullable=False)
    playback_started: Mapped[bool | None] = mapped_column(Boolean)
    collector_version: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )


class JavaScriptErrorObservation(Base):
    __tablename__ = "js_error_observations"
    __table_args__ = (
        UniqueConstraint("checkpoint_run_id", "fingerprint"),
        Index("ix_js_error_observations_site_fingerprint", "site_id", "fingerprint", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False
    )
    checkpoint_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("checkpoint_runs.id", ondelete="RESTRICT"), nullable=False
    )
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    error_type: Mapped[str | None] = mapped_column(String(100))
    normalized_message: Mapped[str] = mapped_column(Text, nullable=False)
    source_host: Mapped[str | None] = mapped_column(String(253))
    source_path: Mapped[str | None] = mapped_column(Text)
    top_frame: Mapped[str | None] = mapped_column(Text)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
    first_seen_in_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stack_sample: Mapped[str | None] = mapped_column(Text)
    collector_version: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
