"""Add C1 persistence for the GA4 C2 connector.

Revision ID: 0010_ga4_connector_c2
Revises: 0009_synthetic_perf_b8
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_ga4_connector_c2"
down_revision: str | None = "0009_synthetic_perf_b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "data_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("external_account_id", sa.String(length=200), nullable=True),
        sa.Column("external_property_id", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("scopes", postgresql.JSONB(), nullable=False),
        sa.Column("secret_reference", sa.Text(), nullable=False),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_class", sa.String(length=100), nullable=True),
        sa.Column("last_error_code", sa.String(length=100), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('PENDING', 'CONNECTED', 'DEGRADED', 'AUTH_EXPIRED', "
            "'PERMISSION_ERROR', 'DISCONNECTED')",
            name="ck_data_connections_status",
        ),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "site_id",
            "provider",
            "external_property_id",
            name="uq_data_connections_property",
        ),
    )
    op.create_index(
        "ix_data_connections_tenant_provider",
        "data_connections",
        ["tenant_id", "provider", "status"],
    )

    op.create_table(
        "source_extracts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("extract_type", sa.String(length=100), nullable=False),
        sa.Column("scheduled_run_key", sa.String(length=255), nullable=False),
        sa.Column("query_definition", postgresql.JSONB(), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_timezone", sa.String(length=100), nullable=True),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("freshness_status", sa.String(length=20), nullable=False),
        sa.Column("response_metadata", postgresql.JSONB(), nullable=False),
        sa.Column("raw_artifact_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("connector_version", sa.String(length=50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'COMPLETE', 'PARTIAL', 'FAILED')",
            name="ck_source_extracts_status",
        ),
        sa.CheckConstraint(
            "freshness_status IN ('PRELIMINARY', 'MATURE', 'STALE', 'UNKNOWN')",
            name="ck_source_extracts_freshness",
        ),
        sa.ForeignKeyConstraint(["connection_id"], ["data_connections.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "connection_id", "scheduled_run_key", name="uq_source_extracts_logical_run"
        ),
    )
    op.create_index(
        "ix_source_extracts_connection_type",
        "source_extracts",
        ["connection_id", "extract_type"],
    )
    op.create_index(
        "ix_source_extracts_tenant_site_period",
        "source_extracts",
        ["tenant_id", "site_id", "period_start"],
    )

    op.create_table(
        "metric_series",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("metric_code", sa.String(length=100), nullable=False),
        sa.Column("metric_semantics_version", sa.String(length=50), nullable=False),
        sa.Column("unit", sa.String(length=30), nullable=False),
        sa.Column("granularity", sa.String(length=30), nullable=False),
        sa.Column("dimensions", postgresql.JSONB(), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("series_key", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("series_key", name="uq_metric_series_key"),
    )
    op.create_index(
        "ix_metric_series_site_source_metric",
        "metric_series",
        ["site_id", "source", "metric_code"],
    )

    op.create_table(
        "metric_points",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("series_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_extract_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_time", sa.String(length=20), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("numerator", sa.Float(), nullable=True),
        sa.Column("denominator", sa.Float(), nullable=True),
        sa.Column("sample_status", sa.String(length=30), nullable=True),
        sa.Column("freshness_status", sa.String(length=20), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("period_end > period_start", name="ck_metric_points_period"),
        sa.ForeignKeyConstraint(["series_id"], ["metric_series.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_extract_id"], ["source_extracts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "series_id",
            "period_start",
            "source_extract_id",
            name="uq_metric_points_extract_period",
        ),
    )
    op.create_index(
        "ix_metric_points_series_period", "metric_points", ["series_id", "period_start"]
    )
    op.create_index(
        "ix_metric_points_tenant_site_period",
        "metric_points",
        ["tenant_id", "site_id", "period_start"],
    )


def downgrade() -> None:
    op.drop_index("ix_metric_points_tenant_site_period", table_name="metric_points")
    op.drop_index("ix_metric_points_series_period", table_name="metric_points")
    op.drop_table("metric_points")
    op.drop_index("ix_metric_series_site_source_metric", table_name="metric_series")
    op.drop_table("metric_series")
    op.drop_index("ix_source_extracts_tenant_site_period", table_name="source_extracts")
    op.drop_index("ix_source_extracts_connection_type", table_name="source_extracts")
    op.drop_table("source_extracts")
    op.drop_index("ix_data_connections_tenant_provider", table_name="data_connections")
    op.drop_table("data_connections")
