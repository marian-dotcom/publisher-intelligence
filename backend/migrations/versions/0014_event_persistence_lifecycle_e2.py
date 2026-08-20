"""Add event persistence and lifecycle E2.

Revision ID: 0014_event_lifecycle_e2
Revises: 0013_semantic_browser_events_e1
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_event_lifecycle_e2"
down_revision: str | None = "0013_semantic_browser_events_e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_events_status", "events", type_="check")
    op.add_column("events", sa.Column("condition_key", sa.String(length=64), nullable=True))
    op.execute("UPDATE events SET status = 'RECORDED' WHERE status = 'OBSERVED'")
    op.create_check_constraint(
        "ck_events_status",
        "events",
        "status IN ('RECORDED','ACTIVE','RESOLVED','SUPERSEDED')",
    )
    op.create_check_constraint(
        "ck_events_condition_lifecycle",
        "events",
        "(status = 'RECORDED' AND condition_key IS NULL) OR "
        "(status IN ('ACTIVE','RESOLVED') AND condition_key IS NOT NULL) OR "
        "status = 'SUPERSEDED'",
    )
    op.create_check_constraint(
        "ck_events_active_has_no_end", "events", "status != 'ACTIVE' OR ended_at IS NULL"
    )
    op.create_check_constraint(
        "ck_events_resolved_has_end", "events", "status != 'RESOLVED' OR ended_at IS NOT NULL"
    )
    op.create_index(
        "ix_events_tenant_site_started", "events", ["tenant_id", "site_id", "started_at"]
    )
    op.create_index(
        "ix_events_tenant_site_status_started",
        "events",
        ["tenant_id", "site_id", "status", "started_at"],
    )
    op.create_index(
        "uq_events_active_condition",
        "events",
        ["tenant_id", "condition_key"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE' AND condition_key IS NOT NULL"),
    )
    op.execute("UPDATE event_definitions SET schema_version = 2")
    op.execute(
        "UPDATE event_definitions SET default_severity = 'MEDIUM' WHERE code = 'NOINDEX_ADDED'"
    )
    op.execute(
        "UPDATE event_definitions SET family = 'GPT', "
        "description = 'An expected GPT slot was not observed across representative URLs.' "
        "WHERE code = 'GPT_EXPECTED_SLOT_MISSING'"
    )
    op.execute(
        "UPDATE event_definitions "
        "SET description = 'A JavaScript error fingerprint appeared and persisted.' "
        "WHERE code = 'JS_ERROR_STARTED'"
    )


def downgrade() -> None:
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM events WHERE status IN ('ACTIVE','RESOLVED')) "
        "THEN RAISE EXCEPTION 'cannot downgrade E2 with condition event history'; END IF; END $$"
    )
    op.execute(
        "UPDATE event_definitions SET family = 'MONETIZATION', "
        "description = 'An expected GPT slot was not observed.' "
        "WHERE code = 'GPT_EXPECTED_SLOT_MISSING'"
    )
    op.execute(
        "UPDATE event_definitions "
        "SET description = 'A JavaScript error fingerprint appeared.' "
        "WHERE code = 'JS_ERROR_STARTED'"
    )
    op.execute(
        "UPDATE event_definitions SET default_severity = 'HIGH' WHERE code = 'NOINDEX_ADDED'"
    )
    op.execute("UPDATE event_definitions SET schema_version = 1")
    op.drop_index("uq_events_active_condition", table_name="events")
    op.drop_index("ix_events_tenant_site_status_started", table_name="events")
    op.drop_index("ix_events_tenant_site_started", table_name="events")
    op.drop_constraint("ck_events_resolved_has_end", "events", type_="check")
    op.drop_constraint("ck_events_active_has_no_end", "events", type_="check")
    op.drop_constraint("ck_events_condition_lifecycle", "events", type_="check")
    op.drop_constraint("ck_events_status", "events", type_="check")
    op.execute("UPDATE events SET status = 'OBSERVED' WHERE status = 'RECORDED'")
    op.drop_column("events", "condition_key")
    op.create_check_constraint("ck_events_status", "events", "status IN ('OBSERVED','SUPERSEDED')")
