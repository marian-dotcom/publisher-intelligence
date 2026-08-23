"""EP-025a product backend auth: operators, memberships, sessions.

Revision ID: 0023_product_backend_auth
Revises: 0022_monetization_capability
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023_product_backend_auth"
down_revision: str | None = "0022_monetization_capability"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "operators",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("actor_subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default=sa.text("'OPERATOR'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint("role IN ('ADMIN','OPERATOR')", name="ck_operators_role"),
        sa.UniqueConstraint("email", name="uq_operators_email"),
        sa.UniqueConstraint("actor_subject_id", name="uq_operators_actor_subject"),
    )

    op.create_table(
        "operator_tenants",
        sa.Column(
            "operator_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("operators.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
    )

    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "operator_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("operators.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("csrf_token_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("token_hash", name="uq_sessions_token_hash"),
    )
    op.create_index(
        "ix_sessions_operator_active",
        "sessions",
        ["operator_id"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )


def downgrade() -> None:
    for table in ("sessions", "operator_tenants", "operators"):
        op.execute(
            f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM {table}) THEN RAISE EXCEPTION "
            f"'cannot downgrade while {table} contains rows'; END IF; END $$"
        )
    op.drop_index("ix_sessions_operator_active", table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("operator_tenants")
    op.drop_table("operators")
