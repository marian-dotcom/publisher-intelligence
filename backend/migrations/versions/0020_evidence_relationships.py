"""Add evidence relationships, manual notes, and evidence packs (EP-021).

Revision ID: 0020_evidence_relationships
Revises: 0019_incident_trigger_source
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020_evidence_relationships"
down_revision: str | None = "0019_incident_trigger_source"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RELATION_TYPES = (
    "'PRECEDES','COINCIDES_WITH','SAME_SEGMENT_AS','MECHANISTICALLY_CAN_AFFECT',"
    "'METRIC_PARENT_OF','METRIC_DESCENDANT_OF','SUPPORTS','CONTRADICTS',"
    "'INTRODUCED_BY','RESOLVED_AFTER','PERSISTED_AFTER_REMOVAL',"
    "'EXTERNAL_CONTEXT_FOR','UNKNOWN_RELATION'"
)
NOTE_TYPES = (
    "'DEPLOY','ROLLBACK','CONFIG_CHANGE','OPERATOR_INTERVENTION','EXTERNAL_COMMUNICATION','OTHER'"
)


def upgrade() -> None:
    op.create_table(
        "event_relations",
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
            "from_event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("events.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "to_event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("events.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("relation_type", sa.String(40), nullable=False),
        sa.Column("confidence", sa.String(20)),
        sa.Column("reason", sa.Text()),
        sa.Column("derived_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("engine_version", sa.String(50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            f"relation_type IN ({RELATION_TYPES})",
            name="ck_event_relations_type",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR confidence IN ('LOW','MEDIUM','HIGH')",
            name="ck_event_relations_confidence",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "from_event_id",
            "to_event_id",
            "relation_type",
            "engine_version",
            name="uq_event_relations_edge",
        ),
    )
    op.create_index("ix_event_relations_tenant_site", "event_relations", ["tenant_id", "site_id"])

    op.create_table(
        "manual_notes",
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
            sa.ForeignKey("incidents.id", ondelete="RESTRICT"),
        ),
        sa.Column("note_type", sa.String(40), nullable=False),
        sa.Column("note_text", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.Column("source", sa.String(50), nullable=False, server_default=sa.text("'operator'")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            f"note_type IN ({NOTE_TYPES})",
            name="ck_manual_notes_type",
        ),
    )
    op.create_index(
        "ix_manual_notes_tenant_site_created",
        "manual_notes",
        ["tenant_id", "site_id", "created_at"],
    )

    op.create_table(
        "evidence_packs",
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
            sa.ForeignKey("incidents.id", ondelete="RESTRICT"),
        ),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fingerprints", postgresql.JSONB(), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("engine_version", sa.String(50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "incident_id",
            "window_start",
            "window_end",
            "content_hash",
            name="uq_evidence_packs_generation",
        ),
    )
    op.create_index(
        "ix_evidence_packs_tenant_site_window",
        "evidence_packs",
        ["tenant_id", "site_id", "window_start"],
    )


def downgrade() -> None:
    for table in ("evidence_packs", "manual_notes", "event_relations"):
        op.execute(
            f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM {table}) THEN RAISE EXCEPTION "
            f"'cannot downgrade while {table} contains rows'; END IF; END $$"
        )
    op.drop_index("ix_evidence_packs_tenant_site_window", table_name="evidence_packs")
    op.drop_constraint("uq_evidence_packs_generation", "evidence_packs", type_="unique")
    op.drop_table("evidence_packs")
    op.drop_index("ix_manual_notes_tenant_site_created", table_name="manual_notes")
    op.drop_constraint("ck_manual_notes_type", "manual_notes", type_="check")
    op.drop_table("manual_notes")
    op.drop_index("ix_event_relations_tenant_site", table_name="event_relations")
    op.drop_constraint("ck_event_relations_confidence", "event_relations", type_="check")
    op.drop_constraint("ck_event_relations_type", "event_relations", type_="check")
    op.drop_constraint("uq_event_relations_edge", "event_relations", type_="unique")
    op.drop_table("event_relations")
