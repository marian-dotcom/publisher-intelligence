"""EP-026 M2b-1a-2a: add checkpoint_runs.browser_access_classification."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0024_browser_access_class"
down_revision = "0023_product_backend_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "checkpoint_runs",
        sa.Column("browser_access_classification", JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("checkpoint_runs", "browser_access_classification")
