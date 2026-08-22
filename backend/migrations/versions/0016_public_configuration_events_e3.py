"""Add public configuration event definitions E3.

Revision ID: 0016_public_config_events_e3
Revises: 0015_public_configuration_e3
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.events.registry import RULES_BY_CODE, definition_id

revision: str = "0016_public_config_events_e3"
down_revision: str | None = "0015_public_configuration_e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PUBLIC_CONFIG_CODES = (
    "ROBOTS_TXT_CHANGED",
    "ROBOTS_BROAD_BLOCK_ADDED",
    "ROBOTS_BROAD_BLOCK_REMOVED",
    "ADS_TXT_CHANGED",
    "ADS_TXT_MISSING",
    "ADS_TXT_EMPTY_200",
    "ADS_TXT_INVALID",
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
            for code in PUBLIC_CONFIG_CODES
        ],
    )


def downgrade() -> None:
    ids = ",".join(f"'{definition_id(code)}'" for code in PUBLIC_CONFIG_CODES)
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM events WHERE event_definition_id IN ("
        + ids
        + ")) THEN RAISE EXCEPTION "
        "'cannot downgrade E3 with public configuration event history'; END IF; END $$"
    )
    op.execute(sa.text("DELETE FROM event_definitions WHERE id IN (" + ids + ")"))
