"""Add observation run kind and trigger provenance (ADR-130).

Revision ID: 0017_observation_run_kind
Revises: 0016_public_config_events_e3
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017_observation_run_kind"
down_revision: str | None = "0016_public_config_events_e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "checkpoint_runs",
        sa.Column(
            "observation_kind",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'SCHEDULED'"),
        ),
    )
    op.add_column("checkpoint_runs", sa.Column("trigger_source", sa.String(30)))
    op.add_column(
        "checkpoint_runs",
        sa.Column("trigger_correlation_id", postgresql.UUID(as_uuid=True)),
    )
    op.create_check_constraint(
        "ck_checkpoint_runs_observation_kind",
        "checkpoint_runs",
        "observation_kind IN ('SCHEDULED','DIAGNOSTIC','INCIDENT_DIAGNOSTIC')",
    )
    op.create_check_constraint(
        "ck_checkpoint_runs_trigger_source",
        "checkpoint_runs",
        "trigger_source IS NULL OR trigger_source IN ('OPERATOR_CLI','LEGACY_CLI')",
    )
    # ADR-130: SCHEDULED observations carry no provenance; every non-scheduled
    # observation records both a controlled trigger source and a concrete,
    # non-null correlation identity for the specific invocation that produced it.
    op.create_check_constraint(
        "ck_checkpoint_runs_observation_provenance",
        "checkpoint_runs",
        "(observation_kind = 'SCHEDULED' AND trigger_source IS NULL "
        "AND trigger_correlation_id IS NULL) OR "
        "(observation_kind IN ('DIAGNOSTIC','INCIDENT_DIAGNOSTIC') "
        "AND trigger_source IS NOT NULL AND trigger_correlation_id IS NOT NULL)",
    )


def downgrade() -> None:
    op.execute(
        "DO $$ BEGIN IF EXISTS ("
        "SELECT 1 FROM checkpoint_runs WHERE observation_kind <> 'SCHEDULED'"
        ") THEN RAISE EXCEPTION "
        "'cannot downgrade while non-scheduled checkpoint runs exist'; END IF; END $$"
    )
    op.drop_constraint(
        "ck_checkpoint_runs_observation_provenance", "checkpoint_runs", type_="check"
    )
    op.drop_constraint("ck_checkpoint_runs_trigger_source", "checkpoint_runs", type_="check")
    op.drop_constraint("ck_checkpoint_runs_observation_kind", "checkpoint_runs", type_="check")
    op.drop_column("checkpoint_runs", "trigger_correlation_id")
    op.drop_column("checkpoint_runs", "trigger_source")
    op.drop_column("checkpoint_runs", "observation_kind")
