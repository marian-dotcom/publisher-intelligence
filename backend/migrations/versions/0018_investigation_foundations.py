"""Add investigation foundations (incidents, LKG refs, usage, holds).

Revision ID: 0018_investigation_foundations
Revises: 0017_observation_run_kind
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018_investigation_foundations"
down_revision: str | None = "0017_observation_run_kind"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "incidents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "publisher_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("publishers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "site_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sites.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("symptom_family", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("reported_start_at", sa.DateTime(timezone=True)),
        sa.Column("reported_end_at", sa.DateTime(timezone=True)),
        sa.Column(
            "opened_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("status", sa.String(30), nullable=False, server_default=sa.text("'OPEN'")),
        sa.Column("severity", sa.String(20)),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolution_summary", sa.Text()),
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
            "symptom_family IN ('GAM_ADSERVING','SEARCH_DISCOVER','CONSENT_CMP',"
            "'PREBID_HEADER_BIDDING','VIDEO','BROWSER_PERFORMANCE',"
            "'ANALYTICS_MEASUREMENT','EXTERNAL_INFRASTRUCTURE','REPORTING_DISCREPANCY',"
            "'POLICY_COMPLIANCE','PROGRAMMATIC_MARKET','OTHER')",
            name="ck_incidents_symptom_family",
        ),
        sa.CheckConstraint(
            "status IN ('OPEN','INVESTIGATING','RESOLVED','CLOSED_UNRESOLVED')",
            name="ck_incidents_status",
        ),
        sa.CheckConstraint(
            "severity IS NULL OR severity IN ('LOW','MEDIUM','HIGH','CRITICAL')",
            name="ck_incidents_severity",
        ),
    )
    op.create_index(
        "ix_incidents_tenant_site_status", "incidents", ["tenant_id", "site_id", "status"]
    )

    op.create_table(
        "incident_symptom_segments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "incident_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("incidents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("dimension", sa.Text(), nullable=False),
        sa.Column("operator", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(
        "ix_incident_symptom_segments_tenant_incident",
        "incident_symptom_segments",
        ["tenant_id", "incident_id"],
    )

    op.create_table(
        "last_known_good_refs",
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
            "template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("templates.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "scenario_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("browser_scenarios.id", ondelete="RESTRICT"),
        ),
        sa.Column("scope_key", sa.Text(), nullable=False),
        sa.Column(
            "checkpoint_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("checkpoint_runs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "valid_for_incident_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("incidents.id", ondelete="RESTRICT"),
        ),
        sa.Column("selected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("selection_method", sa.Text(), nullable=False),
        sa.Column("selection_version", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("fingerprints", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "scope_key",
            "valid_for_incident_id",
            "checkpoint_run_id",
            name="uq_last_known_good_refs_selection",
        ),
    )
    op.create_index(
        "ix_last_known_good_refs_tenant_site_scope",
        "last_known_good_refs",
        ["tenant_id", "site_id", "scope_key"],
    )

    op.create_table(
        "investigation_usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "incident_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("incidents.id", ondelete="RESTRICT"),
        ),
        sa.Column("investigation_key", sa.Text(), nullable=False),
        sa.Column("resource_kind", sa.String(40), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("usage_key", sa.Text(), nullable=False),
        sa.Column("detail", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "resource_kind IN ('DRILLDOWN','LLM_PASS','DIAGNOSTIC_RUN')",
            name="ck_investigation_usage_resource_kind",
        ),
        sa.CheckConstraint("amount > 0", name="ck_investigation_usage_amount_positive"),
        sa.UniqueConstraint("usage_key", name="uq_investigation_usage_key"),
    )
    op.create_index(
        "ix_investigation_usage_tenant_incident_kind",
        "investigation_usage",
        ["tenant_id", "incident_id", "resource_kind"],
    )

    op.create_table(
        "retention_holds",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "incident_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("incidents.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "artifact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("artifacts.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "source_extract_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("source_extracts.id", ondelete="RESTRICT"),
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("released_at", sa.DateTime(timezone=True)),
        sa.Column("released_by", sa.Text()),
    )
    op.create_index(
        "ix_retention_holds_tenant_active",
        "retention_holds",
        ["tenant_id"],
        postgresql_where=sa.text("released_at IS NULL"),
    )


def downgrade() -> None:
    for table in (
        "retention_holds",
        "investigation_usage",
        "last_known_good_refs",
        "incident_symptom_segments",
        "incidents",
    ):
        op.execute(
            f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM {table}) THEN RAISE EXCEPTION "
            f"'cannot downgrade while {table} contains rows'; END IF; END $$"
        )
    op.drop_index("ix_retention_holds_tenant_active", table_name="retention_holds")
    op.drop_table("retention_holds")
    op.drop_constraint("uq_investigation_usage_key", "investigation_usage", type_="unique")
    op.drop_index("ix_investigation_usage_tenant_incident_kind", table_name="investigation_usage")
    op.drop_table("investigation_usage")
    op.drop_index("ix_last_known_good_refs_tenant_site_scope", table_name="last_known_good_refs")
    op.drop_table("last_known_good_refs")
    op.drop_index(
        "ix_incident_symptom_segments_tenant_incident",
        table_name="incident_symptom_segments",
    )
    op.drop_table("incident_symptom_segments")
    op.drop_index("ix_incidents_tenant_site_status", table_name="incidents")
    op.drop_table("incidents")
