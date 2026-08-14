"""Add B8 synthetic performance evidence.

Revision ID: 0009_synthetic_perf_b8
Revises: 0008_video_player_b7
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_synthetic_perf_b8"
down_revision: str | None = "0008_video_player_b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "synthetic_performance_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("checkpoint_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lcp_ms", sa.Float(), nullable=True),
        sa.Column("cls", sa.Float(), nullable=True),
        sa.Column("inp_ms", sa.Float(), nullable=True),
        sa.Column("inp_method", sa.String(length=100), nullable=True),
        sa.Column("ttfb_ms", sa.Float(), nullable=True),
        sa.Column("dom_content_loaded_ms", sa.Float(), nullable=True),
        sa.Column("load_event_ms", sa.Float(), nullable=True),
        sa.Column("long_task_count", sa.Integer(), nullable=True),
        sa.Column("long_task_total_ms", sa.Float(), nullable=True),
        sa.Column("collector_version", sa.String(length=50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint(
            "(lcp_ms IS NULL OR lcp_ms >= 0) AND "
            "(cls IS NULL OR cls >= 0) AND "
            "(inp_ms IS NULL OR inp_ms >= 0) AND "
            "(ttfb_ms IS NULL OR ttfb_ms >= 0) AND "
            "(dom_content_loaded_ms IS NULL OR dom_content_loaded_ms >= 0) AND "
            "(load_event_ms IS NULL OR load_event_ms >= 0)",
            name="ck_synthetic_performance_timings",
        ),
        sa.CheckConstraint(
            "(long_task_count IS NULL OR long_task_count >= 0) AND "
            "(long_task_total_ms IS NULL OR long_task_total_ms >= 0)",
            name="ck_synthetic_performance_long_tasks",
        ),
        sa.ForeignKeyConstraint(["checkpoint_run_id"], ["checkpoint_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("checkpoint_run_id", name="uq_synthetic_performance_checkpoint"),
    )
    op.create_index(
        "ix_synthetic_performance_tenant_checkpoint",
        "synthetic_performance_observations",
        ["tenant_id", "checkpoint_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_synthetic_performance_tenant_checkpoint",
        table_name="synthetic_performance_observations",
    )
    op.drop_table("synthetic_performance_observations")
