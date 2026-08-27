"""EP-026 M4: append-only checkpoint cost-kind migration.

Extends the investigation budget ledger's resource-kind check constraint to
admit CHECKPOINT_RUN, the measured-cost unit for scheduled browser workload
(runs x bounded page set). No rows are added or changed.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0027_checkpoint_run_budget_kind"
down_revision: str | None = "0026_retention_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_CONSTRAINT = "resource_kind IN ('DRILLDOWN','LLM_PASS','DIAGNOSTIC_RUN')"
_NEW_CONSTRAINT = "resource_kind IN ('DRILLDOWN','LLM_PASS','DIAGNOSTIC_RUN','CHECKPOINT_RUN')"


def upgrade() -> None:
    op.drop_constraint(
        "ck_investigation_usage_resource_kind",
        "investigation_usage",
        type_="check",
    )
    op.create_check_constraint(
        "ck_investigation_usage_resource_kind",
        "investigation_usage",
        _NEW_CONSTRAINT,
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_investigation_usage_resource_kind",
        "investigation_usage",
        type_="check",
    )
    op.create_check_constraint(
        "ck_investigation_usage_resource_kind",
        "investigation_usage",
        _OLD_CONSTRAINT,
    )
