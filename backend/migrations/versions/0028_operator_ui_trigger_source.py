"""Allow OPERATOR_UI as a checkpoint trigger source (EP-028 / ADR-130).

Revision ID: 0028_operator_ui_trigger_source
Revises: 0027_checkpoint_run_budget_kind
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0028_operator_ui_trigger_source"
down_revision: str | None = "0027_checkpoint_run_budget_kind"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_CHECK = "trigger_source IS NULL OR trigger_source IN ('OPERATOR_CLI','LEGACY_CLI','INCIDENT')"
NEW_CHECK = (
    "trigger_source IS NULL OR "
    "trigger_source IN ('OPERATOR_CLI','LEGACY_CLI','OPERATOR_UI','INCIDENT')"
)


def upgrade() -> None:
    op.drop_constraint("ck_checkpoint_runs_trigger_source", "checkpoint_runs", type_="check")
    op.create_check_constraint("ck_checkpoint_runs_trigger_source", "checkpoint_runs", NEW_CHECK)


def downgrade() -> None:
    op.execute(
        "DO $$ BEGIN IF EXISTS ("
        "SELECT 1 FROM checkpoint_runs WHERE trigger_source = 'OPERATOR_UI'"
        ") THEN RAISE EXCEPTION "
        "'cannot downgrade while operator-ui checkpoint runs exist'; END IF; END $$"
    )
    op.drop_constraint("ck_checkpoint_runs_trigger_source", "checkpoint_runs", type_="check")
    op.create_check_constraint("ck_checkpoint_runs_trigger_source", "checkpoint_runs", OLD_CHECK)
