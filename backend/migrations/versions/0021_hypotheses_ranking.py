"""Add deterministic hypotheses and evidence links (EP-023).

Revision ID: 0021_hypotheses_ranking
Revises: 0020_evidence_relationships
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021_hypotheses_ranking"
down_revision: str | None = "0020_evidence_relationships"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "hypotheses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "site_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sites.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "incident_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("incidents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("hypothesis_key", sa.Text(), nullable=False),
        sa.Column("family", sa.String(50), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'UNRESOLVED'")),
        sa.Column("confidence", sa.String(20), nullable=False, server_default=sa.text("'LOW'")),
        sa.Column("rank", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("supporting_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("contradicting_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("engine_version", sa.String(50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "status IN ('LEADING','CONTENDER','WEAKENED','UNRESOLVED')",
            name="ck_hypotheses_status",
        ),
        sa.CheckConstraint(
            "confidence IN ('LOW','MEDIUM','HIGH')", name="ck_hypotheses_confidence"
        ),
        sa.UniqueConstraint("incident_id", "hypothesis_key", name="uq_hypotheses_incident_key"),
    )
    op.create_index("ix_hypotheses_tenant_site", "hypotheses", ["tenant_id", "site_id"])

    op.create_table(
        "hypothesis_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "hypothesis_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("hypotheses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("evidence_key", sa.Text(), nullable=False),
        sa.Column("source_kind", sa.String(30), nullable=False),
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("events.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "manual_note_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("manual_notes.id", ondelete="RESTRICT"),
        ),
        sa.Column("relation", sa.String(20), nullable=False),
        sa.Column("weight", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("reason", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "source_kind IN ('EVENT','MANUAL_NOTE','OBSERVATION_GAP')",
            name="ck_hypothesis_evidence_source",
        ),
        sa.CheckConstraint(
            "relation IN ('SUPPORTS','CONTRADICTS','CONTEXT')",
            name="ck_hypothesis_evidence_relation",
        ),
        sa.UniqueConstraint("hypothesis_id", "evidence_key", name="uq_hypothesis_evidence_key"),
    )


def downgrade() -> None:
    for table in ("hypothesis_evidence", "hypotheses"):
        op.execute(
            f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM {table}) THEN RAISE EXCEPTION "
            f"'cannot downgrade while {table} contains rows'; END IF; END $$"
        )
    op.drop_constraint("uq_hypothesis_evidence_key", "hypothesis_evidence", type_="unique")
    op.drop_table("hypothesis_evidence")
    op.drop_index("ix_hypotheses_tenant_site", table_name="hypotheses")
    op.drop_table("hypotheses")
