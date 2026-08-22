"""Allow INCIDENT as a checkpoint trigger source (EP-020 / ADR-130).

Revision ID: 0019_incident_trigger_source
Revises: 0018_investigation_foundations
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0019_incident_trigger_source"
down_revision: str | None = "0018_investigation_foundations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_CHECK = "trigger_source IS NULL OR trigger_source IN ('OPERATOR_CLI','LEGACY_CLI')"
NEW_CHECK = "trigger_source IS NULL OR trigger_source IN ('OPERATOR_CLI','LEGACY_CLI','INCIDENT')"


def upgrade() -> None:
    op.drop_constraint("ck_checkpoint_runs_trigger_source", "checkpoint_runs", type_="check")
    op.create_check_constraint("ck_checkpoint_runs_trigger_source", "checkpoint_runs", NEW_CHECK)


def downgrade() -> None:
    op.execute(
        "DO $$ BEGIN IF EXISTS ("
        "SELECT 1 FROM checkpoint_runs WHERE trigger_source = 'INCIDENT'"
        ") THEN RAISE EXCEPTION "
        "'cannot downgrade while incident-diagnostic checkpoint runs exist'; END IF; END $$"
    )
    op.drop_constraint("ck_checkpoint_runs_trigger_source", "checkpoint_runs", type_="check")
    op.create_check_constraint("ck_checkpoint_runs_trigger_source", "checkpoint_runs", OLD_CHECK)
