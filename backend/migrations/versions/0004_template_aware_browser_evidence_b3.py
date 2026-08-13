"""Add B3 template metadata and normalized browser observations.

Revision ID: 0004_template_evidence_b3
Revises: 0003_repeatable_browser_runs_b2
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_template_evidence_b3"
down_revision: str | None = "0003_repeatable_browser_runs_b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "templates",
        sa.Column(
            "template_family",
            sa.String(length=100),
            server_default="CUSTOM",
            nullable=False,
        ),
    )
    op.add_column(
        "templates",
        sa.Column("fingerprint_version", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "templates",
        sa.Column(
            "expected_features",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "templates",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE templates SET template_family = 'ARTICLE', "
        "fingerprint_version = 'template-config-v1' WHERE code = 'pilot'"
    )

    op.create_table(
        "domain_entities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_kind", sa.String(length=100), nullable=False),
        sa.Column("stable_key", sa.Text(), nullable=False),
        sa.Column("display_name", sa.String(length=300), nullable=True),
        sa.Column("source_system", sa.String(length=100), nullable=True),
        sa.Column("native_id", sa.String(length=300), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("identity_metadata", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("site_id", "entity_kind", "stable_key"),
    )
    op.create_index(
        "ix_domain_entities_tenant_site_kind",
        "domain_entities",
        ["tenant_id", "site_id", "entity_kind"],
        unique=False,
    )

    op.create_table(
        "entity_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("checkpoint_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("observation_type", sa.String(length=100), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state_hash", sa.String(length=64), nullable=True),
        sa.Column("state", postgresql.JSONB(), nullable=False),
        sa.Column("collector_version", sa.String(length=50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["checkpoint_run_id"], ["checkpoint_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["entity_id"], ["domain_entities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "checkpoint_run_id",
            "entity_id",
            "observation_type",
            name="uq_entity_observation_run",
        ),
    )
    op.create_index(
        "ix_entity_observations_tenant_checkpoint",
        "entity_observations",
        ["tenant_id", "checkpoint_run_id"],
        unique=False,
    )

    op.create_table(
        "js_error_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("checkpoint_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("error_type", sa.String(length=100), nullable=True),
        sa.Column("normalized_message", sa.Text(), nullable=False),
        sa.Column("source_host", sa.String(length=253), nullable=True),
        sa.Column("source_path", sa.Text(), nullable=True),
        sa.Column("top_frame", sa.Text(), nullable=True),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("first_seen_in_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stack_sample", sa.Text(), nullable=True),
        sa.Column("collector_version", sa.String(length=50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["checkpoint_run_id"], ["checkpoint_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("checkpoint_run_id", "fingerprint"),
    )
    op.create_index(
        "ix_js_error_observations_site_fingerprint",
        "js_error_observations",
        ["site_id", "fingerprint", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_js_error_observations_site_fingerprint", table_name="js_error_observations")
    op.drop_table("js_error_observations")
    op.drop_index("ix_entity_observations_tenant_checkpoint", table_name="entity_observations")
    op.drop_table("entity_observations")
    op.drop_index("ix_domain_entities_tenant_site_kind", table_name="domain_entities")
    op.drop_table("domain_entities")
    op.drop_column("templates", "archived_at")
    op.drop_column("templates", "expected_features")
    op.drop_column("templates", "fingerprint_version")
    op.drop_column("templates", "template_family")
