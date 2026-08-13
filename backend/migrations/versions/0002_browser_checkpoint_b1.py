"""Add minimal real-browser checkpoint evidence schema.

Revision ID: 0002_browser_checkpoint_b1
Revises: 0001_repository_foundation
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_browser_checkpoint_b1"
down_revision: str | None = "0001_repository_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _identity_columns() -> list[sa.Column]:
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
    ]


def _created_at() -> sa.Column:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("CURRENT_TIMESTAMP"),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "publishers",
        *_identity_columns(),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("default_timezone", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "slug"),
    )
    op.create_table(
        "sites",
        *_identity_columns(),
        sa.Column("publisher_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("canonical_domain", sa.String(length=253), nullable=False),
        sa.Column("canonical_scheme", sa.String(length=10), nullable=False),
        sa.Column("timezone", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(["publisher_id"], ["publishers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "canonical_domain"),
    )
    op.create_table(
        "templates",
        *_identity_columns(),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("site_id", "code"),
    )
    op.create_table(
        "browser_scenarios",
        *_identity_columns(),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("device_class", sa.String(length=20), nullable=False),
        sa.Column("device_profile", postgresql.JSONB(), nullable=False),
        sa.Column("locale", sa.String(length=50), nullable=False),
        sa.Column("timezone", sa.String(length=100), nullable=False),
        sa.Column("cache_mode", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "site_id", "code", "version"),
    )
    op.create_table(
        "checkpoint_windows",
        *_identity_columns(),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        _created_at(),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("site_id", "scheduled_for"),
    )
    op.create_table(
        "monitored_urls",
        *_identity_columns(),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("is_canary", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "valid_from",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["template_id"], ["templates.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_monitored_urls_site_status", "monitored_urls", ["site_id", "status"], unique=False
    )
    op.create_table(
        "checkpoint_runs",
        *_identity_columns(),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("checkpoint_window_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("monitored_url_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scenario_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("final_url", sa.Text(), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("playwright_version", sa.String(length=50), nullable=True),
        sa.Column("chromium_version", sa.String(length=100), nullable=True),
        sa.Column("collector_bundle_version", sa.String(length=50), nullable=False),
        sa.Column("environment", postgresql.JSONB(), nullable=False),
        sa.Column("limitations", postgresql.JSONB(), nullable=False),
        sa.Column("manifest", postgresql.JSONB(), nullable=False),
        _created_at(),
        sa.CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'COMPLETE', 'PARTIAL', 'SITE_ERROR', "
            "'BROWSER_ERROR', 'TIMEOUT', 'BLOCKED')",
            name="ck_checkpoint_runs_status",
        ),
        sa.ForeignKeyConstraint(
            ["checkpoint_window_id"], ["checkpoint_windows.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["monitored_url_id"], ["monitored_urls.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["scenario_id"], ["browser_scenarios.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["template_id"], ["templates.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("checkpoint_window_id", "monitored_url_id", "scenario_id"),
    )
    op.create_index(
        "ix_checkpoint_runs_tenant_started",
        "checkpoint_runs",
        ["tenant_id", "started_at"],
        unique=False,
    )
    op.create_table(
        "checkpoint_attempts",
        *_identity_columns(),
        sa.Column("checkpoint_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("failure_class", sa.String(length=100), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(["checkpoint_run_id"], ["checkpoint_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("checkpoint_run_id", "attempt_number"),
    )
    op.create_table(
        "collector_runs",
        *_identity_columns(),
        sa.Column("checkpoint_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("collector_type", sa.String(length=100), nullable=False),
        sa.Column("collector_version", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("summary", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(["checkpoint_run_id"], ["checkpoint_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("checkpoint_run_id", "collector_type"),
    )
    op.create_table(
        "artifacts",
        *_identity_columns(),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("checkpoint_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("artifact_type", sa.String(length=100), nullable=False),
        sa.Column("storage_provider", sa.String(length=50), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(length=200), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("retention_class", sa.String(length=50), nullable=False),
        _created_at(),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(["checkpoint_run_id"], ["checkpoint_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("checkpoint_run_id", "artifact_type"),
        sa.UniqueConstraint("object_key"),
    )
    op.create_index(
        "ix_artifacts_tenant_checkpoint",
        "artifacts",
        ["tenant_id", "checkpoint_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_artifacts_tenant_checkpoint", table_name="artifacts")
    op.drop_table("artifacts")
    op.drop_table("collector_runs")
    op.drop_table("checkpoint_attempts")
    op.drop_index("ix_checkpoint_runs_tenant_started", table_name="checkpoint_runs")
    op.drop_table("checkpoint_runs")
    op.drop_index("ix_monitored_urls_site_status", table_name="monitored_urls")
    op.drop_table("monitored_urls")
    op.drop_table("checkpoint_windows")
    op.drop_table("browser_scenarios")
    op.drop_table("templates")
    op.drop_table("sites")
    op.drop_table("publishers")
