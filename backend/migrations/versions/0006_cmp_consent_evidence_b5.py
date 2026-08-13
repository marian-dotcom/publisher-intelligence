"""Add B5 consent scenarios and CMP phase evidence.

Revision ID: 0006_cmp_consent_b5
Revises: 0005_gpt_lifecycle_b4
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_cmp_consent_b5"
down_revision: str | None = "0005_gpt_lifecycle_b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "browser_scenarios",
        sa.Column("consent_path", sa.String(length=20), server_default="PRIMARY", nullable=False),
    )
    op.execute("UPDATE browser_scenarios SET consent_path = 'NONE' WHERE code = 'core_desktop_v1'")
    op.create_check_constraint(
        "ck_browser_scenarios_consent_path",
        "browser_scenarios",
        "consent_path IN ('PRIMARY', 'REJECT', 'NONE')",
    )

    op.create_table(
        "cmp_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("checkpoint_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cmp_entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("cmp_detected", sa.Boolean(), nullable=False),
        sa.Column("tcf_api_detected", sa.Boolean(), nullable=False),
        sa.Column("ui_detected_at_ms", sa.Integer(), nullable=True),
        sa.Column("api_ready_at_ms", sa.Integer(), nullable=True),
        sa.Column("consent_action", sa.String(length=30), nullable=False),
        sa.Column("consent_action_status", sa.String(length=30), nullable=False),
        sa.Column("action_started_at_ms", sa.Integer(), nullable=True),
        sa.Column("action_completed_at_ms", sa.Integer(), nullable=True),
        sa.Column("tc_state_available_at_ms", sa.Integer(), nullable=True),
        sa.Column("gdpr_applies", sa.Boolean(), nullable=True),
        sa.Column("tc_string_hash", sa.String(length=64), nullable=True),
        sa.Column("tcf_error_codes", postgresql.JSONB(), nullable=False),
        sa.Column("collector_version", sa.String(length=50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(["checkpoint_run_id"], ["checkpoint_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["cmp_entity_id"], ["domain_entities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("checkpoint_run_id"),
        sa.CheckConstraint(
            "consent_action IN ('PRIMARY', 'REJECT', 'NONE')",
            name="ck_cmp_observations_consent_action",
        ),
        sa.CheckConstraint(
            "consent_action_status IN "
            "('NOT_REQUESTED', 'NOT_PRESENT', 'UNAVAILABLE', 'COMPLETED', 'TIMEOUT', 'ERROR')",
            name="ck_cmp_observations_action_status",
        ),
    )
    op.create_index(
        "ix_cmp_observations_tenant_checkpoint",
        "cmp_observations",
        ["tenant_id", "checkpoint_run_id"],
        unique=False,
    )

    op.create_table(
        "consent_phase_dependency_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("checkpoint_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("phase", sa.String(length=30), nullable=False),
        sa.Column("dependency_entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("first_request_at_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["checkpoint_run_id"], ["checkpoint_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["dependency_entity_id"], ["domain_entities.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "checkpoint_run_id",
            "phase",
            "dependency_entity_id",
            name="uq_consent_phase_dependency_run",
        ),
        sa.CheckConstraint(
            "phase IN ('PRE_CONSENT', 'POST_ACCEPT', 'POST_REJECT')",
            name="ck_consent_phase_dependencies_phase",
        ),
        sa.CheckConstraint(
            "request_count >= 0 AND error_count >= 0",
            name="ck_consent_phase_dependencies_counts",
        ),
    )
    op.create_index(
        "ix_consent_phase_dependencies_tenant_checkpoint",
        "consent_phase_dependency_observations",
        ["tenant_id", "checkpoint_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_consent_phase_dependencies_tenant_checkpoint",
        table_name="consent_phase_dependency_observations",
    )
    op.drop_table("consent_phase_dependency_observations")
    op.drop_index("ix_cmp_observations_tenant_checkpoint", table_name="cmp_observations")
    op.drop_table("cmp_observations")
    op.drop_constraint(
        "ck_browser_scenarios_consent_path",
        "browser_scenarios",
        type_="check",
    )
    op.drop_column("browser_scenarios", "consent_path")
