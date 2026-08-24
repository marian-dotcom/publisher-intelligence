"""Add browser-source reliability event definitions (EP-026 e26-v1).

Revision ID: 0025_browser_source_events_e26
Revises: 0024_browser_access_class
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.events.registry import RULES_BY_CODE, definition_id

revision: str = "0025_browser_source_events_e26"
down_revision: str | None = "0024_browser_access_class"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BROWSER_SOURCE_CODES = (
    "BROWSER_SOURCE_DEGRADED",
    "BROWSER_ACCESS_CHALLENGE_SUSPECTED",
    "BROWSER_SOURCE_RECOVERED",
)


def upgrade() -> None:
    definitions = sa.table(
        "event_definitions",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("code", sa.String()),
        sa.column("family", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("default_severity", sa.String()),
        sa.column("schema_version", sa.Integer()),
        sa.column("active", sa.Boolean()),
        sa.column("metadata_schema", postgresql.JSONB()),
    )
    op.bulk_insert(
        definitions,
        [
            {
                "id": definition_id(code),
                "code": code,
                "family": RULES_BY_CODE[code].family,
                "description": RULES_BY_CODE[code].description,
                "default_severity": RULES_BY_CODE[code].default_severity,
                "schema_version": RULES_BY_CODE[code].schema_version,
                "active": True,
                "metadata_schema": None,
            }
            for code in BROWSER_SOURCE_CODES
        ],
    )


def downgrade() -> None:
    ids = ",".join(f"'{definition_id(code)}'" for code in BROWSER_SOURCE_CODES)
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM events WHERE event_definition_id IN ("
        + ids
        + ")) THEN RAISE EXCEPTION "
        "'cannot downgrade EP-026 with browser-source event history'; END IF; END $$"
    )
    op.execute(sa.text("DELETE FROM event_definitions WHERE id IN (" + ids + ")"))
