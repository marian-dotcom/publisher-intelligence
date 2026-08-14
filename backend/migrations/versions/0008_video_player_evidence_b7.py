"""Add B7 video player evidence.

Revision ID: 0008_video_player_b7
Revises: 0007_prebid_auction_b6
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_video_player_b7"
down_revision: str | None = "0007_prebid_auction_b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "video_player_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("checkpoint_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("player_entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("present", sa.Boolean(), nullable=False),
        sa.Column("visible", sa.Boolean(), nullable=True),
        sa.Column("sticky", sa.Boolean(), nullable=True),
        sa.Column("fixed", sa.Boolean(), nullable=True),
        sa.Column("autoplay", sa.Boolean(), nullable=True),
        sa.Column("muted", sa.Boolean(), nullable=True),
        sa.Column("controls_present", sa.Boolean(), nullable=True),
        sa.Column("dismiss_control_present", sa.Boolean(), nullable=True),
        sa.Column("width_px", sa.Float(), nullable=True),
        sa.Column("height_px", sa.Float(), nullable=True),
        sa.Column("vast_request_count", sa.Integer(), nullable=False),
        sa.Column("vast_error_count", sa.Integer(), nullable=False),
        sa.Column("media_request_count", sa.Integer(), nullable=False),
        sa.Column("playback_started", sa.Boolean(), nullable=True),
        sa.Column("collector_version", sa.String(length=50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint(
            "vast_request_count >= 0 AND vast_error_count >= 0 AND media_request_count >= 0",
            name="ck_video_player_counts",
        ),
        sa.CheckConstraint(
            "(width_px IS NULL OR width_px >= 0) AND (height_px IS NULL OR height_px >= 0)",
            name="ck_video_player_dimensions",
        ),
        sa.ForeignKeyConstraint(["checkpoint_run_id"], ["checkpoint_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["player_entity_id"], ["domain_entities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "checkpoint_run_id", "player_entity_id", name="uq_video_player_run_entity"
        ),
    )
    op.create_index(
        "ix_video_players_tenant_checkpoint",
        "video_player_observations",
        ["tenant_id", "checkpoint_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_video_players_tenant_checkpoint", table_name="video_player_observations")
    op.drop_table("video_player_observations")
