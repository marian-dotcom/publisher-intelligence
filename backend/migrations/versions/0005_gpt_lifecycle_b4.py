"""Add B4 template expectations and GPT lifecycle observations.

Revision ID: 0005_gpt_lifecycle_b4
Revises: 0004_template_evidence_b3
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_gpt_lifecycle_b4"
down_revision: str | None = "0004_template_evidence_b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "template_expected_entities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expectation_type", sa.String(length=50), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("confidence", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["entity_id"], ["domain_entities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["template_id"], ["templates.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to > valid_from",
            name="ck_template_expected_entity_validity",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "template_id",
            "entity_id",
            "expectation_type",
            "valid_from",
            name="uq_template_expected_entity_version",
        ),
    )
    op.create_index(
        "ix_template_expected_entities_tenant_template",
        "template_expected_entities",
        ["tenant_id", "template_id", "valid_from"],
        unique=False,
    )

    op.create_table(
        "gpt_slot_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("checkpoint_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slot_entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dom_element_id", sa.String(length=300), nullable=True),
        sa.Column("ad_unit_path", sa.String(length=500), nullable=True),
        sa.Column("sizes", postgresql.JSONB(), nullable=False),
        sa.Column("expected", sa.Boolean(), nullable=False),
        sa.Column("present", sa.Boolean(), nullable=False),
        sa.Column("defined_at_ms", sa.Integer(), nullable=True),
        sa.Column("requested_at_ms", sa.Integer(), nullable=True),
        sa.Column("response_at_ms", sa.Integer(), nullable=True),
        sa.Column("render_ended_at_ms", sa.Integer(), nullable=True),
        sa.Column("onload_at_ms", sa.Integer(), nullable=True),
        sa.Column("viewable_at_ms", sa.Integer(), nullable=True),
        sa.Column("is_empty", sa.Boolean(), nullable=True),
        sa.Column("creative_id", sa.String(length=300), nullable=True),
        sa.Column("line_item_id", sa.String(length=300), nullable=True),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("collector_version", sa.String(length=50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("request_count >= 0", name="ck_gpt_slot_request_count"),
        sa.ForeignKeyConstraint(["checkpoint_run_id"], ["checkpoint_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["slot_entity_id"], ["domain_entities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "checkpoint_run_id", "slot_entity_id", name="uq_gpt_slot_observation_run"
        ),
    )
    op.create_index(
        "ix_gpt_slot_observations_tenant_checkpoint",
        "gpt_slot_observations",
        ["tenant_id", "checkpoint_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_gpt_slot_observations_site_created",
        "gpt_slot_observations",
        ["site_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_gpt_slot_observations_site_created", table_name="gpt_slot_observations")
    op.drop_index("ix_gpt_slot_observations_tenant_checkpoint", table_name="gpt_slot_observations")
    op.drop_table("gpt_slot_observations")
    op.drop_index(
        "ix_template_expected_entities_tenant_template",
        table_name="template_expected_entities",
    )
    op.drop_table("template_expected_entities")
