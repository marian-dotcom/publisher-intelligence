"""Add immutable public configuration evidence E3.

Revision ID: 0015_public_configuration_e3
Revises: 0014_event_lifecycle_e2
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_public_configuration_e3"
down_revision: str | None = "0014_event_lifecycle_e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "public_config_snapshots",
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
        sa.Column("config_type", sa.String(30), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("http_status", sa.Integer()),
        sa.Column("content_hash", sa.String(64)),
        sa.Column("parse_status", sa.String(30), nullable=False),
        sa.Column(
            "artifact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("artifacts.id", ondelete="RESTRICT"),
        ),
        sa.Column("normalizer_version", sa.String(50), nullable=False),
        sa.Column(
            "summary", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("fetch_kind", sa.String(20), nullable=False),
        sa.Column("validation_of_snapshot_id", postgresql.UUID(as_uuid=True)),
        sa.Column("observation_key", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "config_type IN ('ROBOTS_TXT','ADS_TXT')",
            name="ck_public_config_snapshots_type",
        ),
        sa.CheckConstraint(
            "parse_status IN ('VALID','VALID_WITH_WARNINGS','EMPTY','INVALID','MISSING',"
            "'HTTP_ERROR','UNREACHABLE','TOO_LARGE','BLOCKED')",
            name="ck_public_config_snapshots_parse_status",
        ),
        sa.CheckConstraint(
            "http_status IS NULL OR (http_status >= 100 AND http_status <= 599)",
            name="ck_public_config_snapshots_http_status",
        ),
        sa.CheckConstraint(
            "(fetch_kind = 'SCHEDULED' AND validation_of_snapshot_id IS NULL) OR "
            "(fetch_kind = 'VALIDATION' AND validation_of_snapshot_id IS NOT NULL)",
            name="ck_public_config_snapshots_fetch_kind",
        ),
        sa.CheckConstraint(
            "validation_of_snapshot_id IS NULL OR validation_of_snapshot_id <> id",
            name="ck_public_config_snapshots_not_self_validation",
        ),
        sa.ForeignKeyConstraint(
            ["validation_of_snapshot_id"],
            ["public_config_snapshots.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("observation_key", name="uq_public_config_snapshot_observation_key"),
    )
    op.create_index(
        "ix_public_config_snapshots_tenant_site_type_observed",
        "public_config_snapshots",
        ["tenant_id", "site_id", "config_type", "observed_at"],
    )
    op.create_index(
        "ix_public_config_snapshots_validation_primary",
        "public_config_snapshots",
        ["validation_of_snapshot_id"],
    )

    op.create_table(
        "ads_txt_records",
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
            "snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("public_config_snapshots.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("advertising_system_domain", sa.String(253), nullable=False),
        sa.Column("publisher_account_id", sa.String(500), nullable=False),
        sa.Column("relationship", sa.String(20), nullable=False),
        sa.Column("cert_authority_id", sa.String(255)),
        sa.Column("record_hash", sa.String(64), nullable=False),
        sa.Column("is_valid", sa.Boolean(), nullable=False),
        sa.Column(
            "validation_errors",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "relationship IN ('DIRECT','RESELLER')", name="ck_ads_txt_records_relationship"
        ),
        sa.UniqueConstraint("snapshot_id", "record_hash", name="uq_ads_txt_records_snapshot_hash"),
    )
    op.create_index(
        "ix_ads_txt_records_tenant_site_snapshot",
        "ads_txt_records",
        ["tenant_id", "site_id", "snapshot_id"],
    )


def downgrade() -> None:
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM public_config_snapshots) "
        "THEN RAISE EXCEPTION 'cannot downgrade E3 with public configuration evidence'; "
        "END IF; END $$"
    )
    op.drop_index("ix_ads_txt_records_tenant_site_snapshot", table_name="ads_txt_records")
    op.drop_table("ads_txt_records")
    op.drop_index(
        "ix_public_config_snapshots_validation_primary", table_name="public_config_snapshots"
    )
    op.drop_index(
        "ix_public_config_snapshots_tenant_site_type_observed",
        table_name="public_config_snapshots",
    )
    op.drop_table("public_config_snapshots")
