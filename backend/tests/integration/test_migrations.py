import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.db.session import get_engine

pytestmark = pytest.mark.integration


def test_migrations_upgrade_downgrade_upgrade() -> None:
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")


async def test_schema_is_minimal_and_rejects_cancelled_status() -> None:
    engine = get_engine()
    async with engine.connect() as connection:
        tables = set(
            (
                await connection.execute(
                    text(
                        "SELECT tablename FROM pg_tables "
                        "WHERE schemaname = 'public' ORDER BY tablename"
                    )
                )
            ).scalars()
        )
        assert tables == {
            "ads_txt_records",
            "incidents",
            "incident_symptom_segments",
            "investigation_usage",
            "last_known_good_refs",
            "retention_holds",
            "alembic_version",
            "artifacts",
            "browser_scenarios",
            "interaction_profiles",
            "checkpoint_attempts",
            "checkpoint_runs",
            "checkpoint_windows",
            "cmp_observations",
            "consent_phase_dependency_observations",
            "collector_runs",
            "data_connections",
            "domain_entities",
            "entity_observations",
            "event_definitions",
            "event_evidence_refs",
            "events",
            "gpt_slot_observations",
            "jobs",
            "js_error_observations",
            "metric_points",
            "metric_derivation_inputs",
            "metric_derivations",
            "metric_series",
            "monitored_urls",
            "publishers",
            "seo_observations",
            "prebid_auction_observations",
            "prebid_bidder_observations",
            "public_config_snapshots",
            "sites",
            "source_extracts",
            "synthetic_performance_observations",
            "templates",
            "template_expected_entities",
            "tenants",
            "video_player_observations",
        }
        constraints = (
            (
                await connection.execute(
                    text(
                        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                        "WHERE conname = 'ck_jobs_status'"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(constraints) == 1
        assert "CANCELLED" not in constraints[0]
        assert "job_attempts" not in tables
        event_status = (
            (
                await connection.execute(
                    text(
                        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                        "WHERE conname = 'ck_events_status'"
                    )
                )
            )
            .scalars()
            .one()
        )
        assert "RECORDED" in event_status
        assert "ACTIVE" in event_status
        assert "RESOLVED" in event_status
        assert "OBSERVED" not in event_status
        active_index = (
            await connection.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE schemaname = 'public' "
                    "AND indexname = 'uq_events_active_condition'"
                )
            )
        ).scalar_one()
        assert "UNIQUE INDEX" in active_index
        assert "ACTIVE" in active_index
        assert "condition_key IS NOT NULL" in active_index
