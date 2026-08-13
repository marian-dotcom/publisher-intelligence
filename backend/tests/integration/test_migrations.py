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
            "domain_entities",
            "entity_observations",
            "gpt_slot_observations",
            "jobs",
            "js_error_observations",
            "monitored_urls",
            "publishers",
            "sites",
            "templates",
            "template_expected_entities",
            "tenants",
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
