"""Widen source time labels for GSC offset-hour provenance.

Revision ID: 0011_gsc_connector_c3
Revises: 0010_ga4_connector_c2
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_gsc_connector_c3"
down_revision: str | None = "0010_ga4_connector_c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "metric_points",
        "source_time",
        existing_type=sa.String(length=20),
        type_=sa.String(length=64),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "metric_points",
        "source_time",
        existing_type=sa.String(length=64),
        type_=sa.String(length=20),
        existing_nullable=False,
    )
