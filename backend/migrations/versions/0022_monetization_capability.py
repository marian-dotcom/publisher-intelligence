"""EP-024: monetization capability semantics on data connections.

Revision ID: 0022_monetization_capability
Revises: 0021_hypotheses_ranking
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_monetization_capability"
down_revision: str | None = "0021_hypotheses_ranking"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "data_connections",
        sa.Column(
            "monetization_capability",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'UNKNOWN'"),
        ),
    )
    op.create_check_constraint(
        "ck_data_connections_monetization_capability",
        "data_connections",
        "monetization_capability IN ('ABSOLUTE','RELATIVE_ONLY','UNKNOWN')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_data_connections_monetization_capability",
        "data_connections",
        type_="check",
    )
    op.drop_column("data_connections", "monetization_capability")
