"""Add B6 Prebid auction and bidder evidence.

Revision ID: 0007_prebid_auction_b6
Revises: 0006_cmp_consent_b5
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_prebid_auction_b6"
down_revision: str | None = "0006_cmp_consent_b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "prebid_auction_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("checkpoint_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("auction_key", sa.String(length=50), nullable=False),
        sa.Column("started_at_ms", sa.Float(), nullable=True),
        sa.Column("ended_at_ms", sa.Float(), nullable=True),
        sa.Column("configured_timeout_ms", sa.Integer(), nullable=True),
        sa.Column("ad_unit_count", sa.Integer(), nullable=True),
        sa.Column("bidder_request_count", sa.Integer(), nullable=False),
        sa.Column("bid_response_count", sa.Integer(), nullable=False),
        sa.Column("no_bid_count", sa.Integer(), nullable=False),
        sa.Column("timeout_count", sa.Integer(), nullable=False),
        sa.Column("collector_version", sa.String(length=50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(["checkpoint_run_id"], ["checkpoint_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("checkpoint_run_id", "auction_key", name="uq_prebid_auction_run_key"),
        sa.CheckConstraint(
            "bidder_request_count >= 0 AND bid_response_count >= 0 AND "
            "no_bid_count >= 0 AND timeout_count >= 0",
            name="ck_prebid_auction_counts",
        ),
    )
    op.create_index(
        "ix_prebid_auctions_tenant_checkpoint",
        "prebid_auction_observations",
        ["tenant_id", "checkpoint_run_id"],
        unique=False,
    )
    op.create_table(
        "prebid_bidder_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("checkpoint_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("auction_observation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bidder_entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("bidder_code", sa.String(length=100), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("response_count", sa.Integer(), nullable=False),
        sa.Column("no_bid_count", sa.Integer(), nullable=False),
        sa.Column("timeout_count", sa.Integer(), nullable=False),
        sa.Column("response_time_ms_min", sa.Float(), nullable=True),
        sa.Column("response_time_ms_max", sa.Float(), nullable=True),
        sa.Column("response_time_ms_avg", sa.Float(), nullable=True),
        sa.Column("winning_bid_count", sa.Integer(), nullable=False),
        sa.Column("collector_version", sa.String(length=50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(
            ["auction_observation_id"],
            ["prebid_auction_observations.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["bidder_entity_id"], ["domain_entities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["checkpoint_run_id"], ["checkpoint_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "auction_observation_id", "bidder_code", name="uq_prebid_bidder_auction_code"
        ),
        sa.CheckConstraint(
            "request_count >= 0 AND response_count >= 0 AND no_bid_count >= 0 AND "
            "timeout_count >= 0 AND winning_bid_count >= 0",
            name="ck_prebid_bidder_counts",
        ),
    )
    op.create_index(
        "ix_prebid_bidders_tenant_checkpoint",
        "prebid_bidder_observations",
        ["tenant_id", "checkpoint_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_prebid_bidders_tenant_checkpoint", table_name="prebid_bidder_observations")
    op.drop_table("prebid_bidder_observations")
    op.drop_index("ix_prebid_auctions_tenant_checkpoint", table_name="prebid_auction_observations")
    op.drop_table("prebid_auction_observations")
