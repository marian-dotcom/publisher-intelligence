"""Add semantic browser events E1.

Revision ID: 0013_semantic_browser_events_e1
Revises: 0012_cross_source_metrics_c5
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.events.registry import RULES, definition_id

revision: str = "0013_semantic_browser_events_e1"
down_revision: str | None = "0012_cross_source_metrics_c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "seo_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "site_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sites.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "checkpoint_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("checkpoint_runs.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("final_url", sa.Text()),
        sa.Column("http_status", sa.Integer()),
        sa.Column("title_hash", sa.String(64)),
        sa.Column("meta_robots", sa.String(1000)),
        sa.Column("canonical_url", sa.Text()),
        sa.Column("important_content_present", sa.Boolean()),
        sa.Column("redirect_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mobile_render_ok", sa.Boolean()),
        sa.Column("collector_version", sa.String(50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.CheckConstraint("redirect_count >= 0", name="ck_seo_observations_redirect_count"),
    )
    op.create_index(
        "ix_seo_observations_tenant_checkpoint",
        "seo_observations",
        ["tenant_id", "checkpoint_run_id"],
    )
    op.create_table(
        "event_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(100), nullable=False, unique=True),
        sa.Column("family", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("default_severity", sa.String(20), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("metadata_schema", postgresql.JSONB()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
    )
    definitions = sa.table(
        "event_definitions",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("code", sa.String()),
        sa.column("family", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("default_severity", sa.String()),
        sa.column("schema_version", sa.Integer()),
        sa.column("active", sa.Boolean()),
        sa.column("metadata_schema", postgresql.JSONB()),
    )
    op.bulk_insert(
        definitions,
        [
            {
                "id": definition_id(r.code),
                "code": r.code,
                "family": r.family,
                "description": r.description,
                "default_severity": r.default_severity,
                "schema_version": r.schema_version,
                "active": True,
                "metadata_schema": None,
            }
            for r in RULES
        ],
    )
    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "site_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sites.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "event_definition_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("event_definitions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "subject_entity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("domain_entities.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("templates.id", ondelete="RESTRICT"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("occurred_after_at", sa.DateTime(timezone=True)),
        sa.Column("occurred_before_at", sa.DateTime(timezone=True)),
        sa.Column("time_precision", sa.String(20), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("observation_confidence", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("source_kind", sa.String(50), nullable=False),
        sa.Column("source_version", sa.String(50)),
        sa.Column("risk_score", sa.Float()),
        sa.Column("scope", postgresql.JSONB(), nullable=False),
        sa.Column("summary", sa.String(500), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "superseded_by_event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("events.id", ondelete="RESTRICT"),
        ),
        sa.CheckConstraint(
            "time_precision IN ('EXACT','WINDOW','DAY')", name="ck_events_time_precision"
        ),
        sa.CheckConstraint(
            "severity IN ('INFO','LOW','MEDIUM','HIGH','CRITICAL')", name="ck_events_severity"
        ),
        sa.CheckConstraint(
            "observation_confidence IN ('LOW','MEDIUM','HIGH')",
            name="ck_events_observation_confidence",
        ),
        sa.CheckConstraint("status IN ('OBSERVED','SUPERSEDED')", name="ck_events_status"),
        sa.CheckConstraint(
            "occurred_after_at IS NULL OR occurred_before_at IS NULL OR "
            "occurred_before_at >= occurred_after_at",
            name="ck_events_occurrence_bounds",
        ),
    )
    op.create_index(
        "ix_events_tenant_site_detected", "events", ["tenant_id", "site_id", "detected_at"]
    )
    op.create_table(
        "event_evidence_refs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("events.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("evidence_kind", sa.String(50), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("relation", sa.String(30), nullable=False),
        sa.Column("summary", sa.String(500)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "event_id", "evidence_kind", "source_id", "relation", name="uq_event_evidence_ref"
        ),
    )
    op.create_index(
        "ix_event_evidence_refs_tenant_event", "event_evidence_refs", ["tenant_id", "event_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_event_evidence_refs_tenant_event", table_name="event_evidence_refs")
    op.drop_table("event_evidence_refs")
    op.drop_index("ix_events_tenant_site_detected", table_name="events")
    op.drop_table("events")
    op.drop_table("event_definitions")
    op.drop_index("ix_seo_observations_tenant_checkpoint", table_name="seo_observations")
    op.drop_table("seo_observations")
