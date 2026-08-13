"""Add versioned B2 interaction profiles and scenario lifecycle.

Revision ID: 0003_repeatable_browser_runs_b2
Revises: 0002_browser_checkpoint_b1
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_repeatable_browser_runs_b2"
down_revision: str | None = "0002_browser_checkpoint_b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "interaction_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("steps", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "site_id", "code", "version"),
    )
    op.create_index(
        "ix_interaction_profiles_site_status",
        "interaction_profiles",
        ["site_id", "status"],
        unique=False,
    )
    op.add_column(
        "browser_scenarios",
        sa.Column("interaction_profile_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "browser_scenarios",
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_browser_scenarios_interaction_profile_id",
        "browser_scenarios",
        "interaction_profiles",
        ["interaction_profile_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_browser_scenarios_interaction_profile_id",
        "browser_scenarios",
        type_="foreignkey",
    )
    op.drop_column("browser_scenarios", "retired_at")
    op.drop_column("browser_scenarios", "interaction_profile_id")
    op.drop_index("ix_interaction_profiles_site_status", table_name="interaction_profiles")
    op.drop_table("interaction_profiles")
