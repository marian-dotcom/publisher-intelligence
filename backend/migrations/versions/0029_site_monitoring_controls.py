"""EP-030 M1: per-site monitoring controls (data model + authenticated API).

Adds the per-site scheduled-monitoring authorization state, an append-only
transition audit, and the administrative SKIPPED checkpoint status value.

Revision ID: 0029_site_monitoring_controls
Revises: 0028_operator_ui_trigger_source
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0029_site_monitoring_controls"
down_revision: str | None = "0028_operator_ui_trigger_source"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_CHECKPOINT_STATUS = (
    "status IN ('PENDING', 'RUNNING', 'COMPLETE', 'PARTIAL', 'SITE_ERROR', "
    "'BROWSER_ERROR', 'TIMEOUT', 'BLOCKED')"
)
_NEW_CHECKPOINT_STATUS = (
    "status IN ('PENDING', 'RUNNING', 'COMPLETE', 'PARTIAL', 'SITE_ERROR', "
    "'BROWSER_ERROR', 'TIMEOUT', 'BLOCKED', 'SKIPPED')"
)


def upgrade() -> None:
    op.add_column(
        "sites",
        sa.Column(
            "monitoring_state",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'OFF'"),
        ),
    )
    op.add_column(
        "sites",
        sa.Column(
            "monitoring_state_updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_check_constraint(
        "ck_sites_monitoring_state",
        "sites",
        "monitoring_state IN ('ON', 'OFF')",
    )
    op.create_unique_constraint(
        "uq_sites_tenant_id",
        "sites",
        ["tenant_id", "id"],
    )

    op.create_table(
        "site_monitoring_state_changes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("from_state", sa.Text(), nullable=False),
        sa.Column("to_state", sa.Text(), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "from_state IN ('ON', 'OFF')",
            name="ck_site_monitoring_state_changes_from",
        ),
        sa.CheckConstraint(
            "to_state IN ('ON', 'OFF')",
            name="ck_site_monitoring_state_changes_to",
        ),
        sa.CheckConstraint(
            "from_state <> to_state",
            name="ck_site_monitoring_state_changes_clean_transition",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "site_id"],
            ["sites.tenant_id", "sites.id"],
            ondelete="RESTRICT",
            name="fk_site_monitoring_state_changes_site",
        ),
    )
    op.create_index(
        "ix_site_monitoring_state_changes_site_changed",
        "site_monitoring_state_changes",
        ["tenant_id", "site_id", "changed_at"],
        unique=False,
    )

    op.drop_constraint("ck_checkpoint_runs_status", "checkpoint_runs", type_="check")
    op.create_check_constraint(
        "ck_checkpoint_runs_status",
        "checkpoint_runs",
        _NEW_CHECKPOINT_STATUS,
    )


def downgrade() -> None:
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM site_monitoring_state_changes) THEN "
        "RAISE EXCEPTION 'cannot downgrade while site monitoring state changes exist'; "
        "END IF; END $$"
    )
    op.execute(
        "DO $$ BEGIN IF EXISTS "
        "(SELECT 1 FROM sites WHERE monitoring_state = 'ON') THEN "
        "RAISE EXCEPTION 'cannot downgrade while monitoring is enabled on a site'; "
        "END IF; END $$"
    )
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM checkpoint_runs WHERE status = 'SKIPPED') "
        "THEN RAISE EXCEPTION "
        "'cannot downgrade while skipped checkpoint runs exist'; END IF; END $$"
    )
    op.drop_constraint("ck_checkpoint_runs_status", "checkpoint_runs", type_="check")
    op.create_check_constraint(
        "ck_checkpoint_runs_status",
        "checkpoint_runs",
        _OLD_CHECKPOINT_STATUS,
    )
    op.drop_index(
        "ix_site_monitoring_state_changes_site_changed",
        table_name="site_monitoring_state_changes",
    )
    op.drop_table("site_monitoring_state_changes")
    op.drop_constraint("uq_sites_tenant_id", "sites", type_="unique")
    op.drop_constraint("ck_sites_monitoring_state", "sites", type_="check")
    op.drop_column("sites", "monitoring_state_updated_at")
    op.drop_column("sites", "monitoring_state")
