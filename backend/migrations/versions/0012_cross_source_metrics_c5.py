"""Add auditable cross-source derived metric provenance.

Revision ID: 0012_cross_source_metrics_c5
Revises: 0011_gsc_connector_c3
Create Date: 2026-08-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_cross_source_metrics_c5"
down_revision: str | None = "0011_gsc_connector_c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "metric_derivations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("definition_code", sa.String(length=100), nullable=False),
        sa.Column("rule_version", sa.String(length=50), nullable=False),
        sa.Column("engine_version", sa.String(length=50), nullable=False),
        sa.Column("alignment_policy", sa.String(length=50), nullable=False),
        sa.Column("freshness_policy", sa.String(length=50), nullable=False),
        sa.Column("granularity", sa.String(length=30), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("freshness_status", sa.String(length=20), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("derivation_key", sa.String(length=64), nullable=False),
        sa.Column("limitations", postgresql.JSONB(), nullable=False),
        sa.Column("definition", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("period_end > period_start", name="ck_metric_derivations_period"),
        sa.CheckConstraint(
            "freshness_status IN ('PRELIMINARY', 'MATURE')",
            name="ck_metric_derivations_freshness",
        ),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("derivation_key", name="uq_metric_derivations_key"),
    )
    op.create_index(
        "ix_metric_derivations_tenant_site_period",
        "metric_derivations",
        ["tenant_id", "site_id", "period_start"],
    )

    op.alter_column(
        "metric_points", "source_extract_id", existing_type=postgresql.UUID(), nullable=True
    )
    op.add_column(
        "metric_points",
        sa.Column("derivation_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_metric_points_derivation_id",
        "metric_points",
        "metric_derivations",
        ["derivation_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_metric_points_derivation_period",
        "metric_points",
        ["series_id", "period_start", "derivation_id"],
    )
    op.create_check_constraint(
        "ck_metric_points_exactly_one_provenance",
        "metric_points",
        "(source_extract_id IS NOT NULL AND derivation_id IS NULL) OR "
        "(source_extract_id IS NULL AND derivation_id IS NOT NULL)",
    )

    op.create_table(
        "metric_derivation_inputs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("derivation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_metric_point_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('NUMERATOR', 'DENOMINATOR')",
            name="ck_metric_derivation_inputs_role",
        ),
        sa.ForeignKeyConstraint(["derivation_id"], ["metric_derivations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["source_metric_point_id"], ["metric_points.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "derivation_id",
            "source_metric_point_id",
            "role",
            name="uq_metric_derivation_inputs_source_role",
        ),
    )
    op.create_index(
        "ix_metric_derivation_inputs_source",
        "metric_derivation_inputs",
        ["source_metric_point_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_metric_derivation_inputs_source", table_name="metric_derivation_inputs")
    op.drop_table("metric_derivation_inputs")
    op.execute("DELETE FROM metric_points WHERE derivation_id IS NOT NULL")
    op.drop_constraint("ck_metric_points_exactly_one_provenance", "metric_points", type_="check")
    op.drop_constraint("uq_metric_points_derivation_period", "metric_points", type_="unique")
    op.drop_constraint("fk_metric_points_derivation_id", "metric_points", type_="foreignkey")
    op.drop_column("metric_points", "derivation_id")
    op.alter_column(
        "metric_points", "source_extract_id", existing_type=postgresql.UUID(), nullable=False
    )
    op.execute("DELETE FROM metric_series WHERE source = 'DERIVED'")
    op.drop_index("ix_metric_derivations_tenant_site_period", table_name="metric_derivations")
    op.drop_table("metric_derivations")
