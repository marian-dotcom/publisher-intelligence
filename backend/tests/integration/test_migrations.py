from datetime import UTC, datetime

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text

from app.browser.models import (
    BrowserScenario,
    CheckpointRun,
    MonitoredUrl,
    Publisher,
    Site,
    SiteMonitoringStateChange,
    Template,
)
from app.config.settings import get_settings
from app.db.models import Tenant
from app.db.session import get_engine, get_session_factory
from app.events.models import Event
from app.events.registry import definition_id
from app.evidence.models import EventRelation, EvidencePack, ManualNote
from app.incidents.models import Incident
from app.jobs.queue import JobQueue
from tests.integration.purge import make_purge

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
            "retention_runs",
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
            "event_relations",
            "evidence_packs",
            "hypotheses",
            "hypothesis_evidence",
            "manual_notes",
            "operators",
            "operator_tenants",
            "sessions",
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
            "site_monitoring_state_changes",
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


def test_guarded_downgrades_refuse_while_evidence_exists() -> None:
    """One ordered descent exercises every guarded downgrade exactly once."""
    import asyncio
    import uuid

    from alembic import command
    from alembic.config import Config
    from sqlalchemy.exc import ProgrammingError

    from app.browser.service import CheckpointService

    factory = get_session_factory()

    async def seed() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
        tenant_id = uuid.uuid4()
        publisher_id, site_id = uuid.uuid4(), uuid.uuid4()
        template_id = uuid.uuid4()
        monitored_url_id, scenario_id = uuid.uuid4(), uuid.uuid4()
        async with factory() as session, session.begin():
            session.add(Tenant(id=tenant_id, slug=f"guard-{tenant_id.hex[:8]}", name="Guard"))
            await session.flush()
            session.add(
                Publisher(
                    id=publisher_id,
                    tenant_id=tenant_id,
                    name="Guard Publisher",
                    slug=f"pub-{publisher_id.hex[:8]}",
                    default_timezone="UTC",
                    status="ACTIVE",
                )
            )
            await session.flush()
            session.add(
                Site(
                    id=site_id,
                    tenant_id=tenant_id,
                    publisher_id=publisher_id,
                    name="Guard Site",
                    canonical_domain=f"{site_id.hex}.example.com",
                    canonical_scheme="https",
                    timezone="UTC",
                    status="ACTIVE",
                )
            )
            await session.flush()
            session.add(
                Template(
                    id=template_id,
                    tenant_id=tenant_id,
                    site_id=site_id,
                    code="article",
                    display_name="Article",
                    status="ACTIVE",
                )
            )
            await session.flush()
            session.add(
                MonitoredUrl(
                    id=monitored_url_id,
                    tenant_id=tenant_id,
                    site_id=site_id,
                    template_id=template_id,
                    url=f"https://{site_id.hex}.example.com/a",
                    status="ACTIVE",
                )
            )
            session.add(
                BrowserScenario(
                    id=scenario_id,
                    tenant_id=tenant_id,
                    site_id=site_id,
                    code=f"core_desktop_{scenario_id.hex[:6]}",
                    version=1,
                    status="ACTIVE",
                )
            )

        settings = get_settings()
        checkpoints = CheckpointService(factory, JobQueue(factory), settings)
        registered = await checkpoints.register_and_enqueue(
            tenant_slug=f"guard-cli-{tenant_id.hex[:8]}",
            tenant_name="Guard CLI Tenant",
            publisher_name="Guard CLI Publisher",
            site_name="Guard CLI Site",
            url="https://www.example.com/",
            observation_kind="DIAGNOSTIC",
        )
        async with factory() as session, session.begin():
            site = await session.scalar(select(Site).where(Site.id == site_id))
            scenario = await session.scalar(
                select(BrowserScenario).where(BrowserScenario.tenant_id == tenant_id)
            )
            monitored_url = await session.scalar(
                select(MonitoredUrl).where(MonitoredUrl.tenant_id == tenant_id)
            )
            template = await session.scalar(select(Template).where(Template.tenant_id == tenant_id))
            assert site and scenario and monitored_url and template

            incident_id = uuid.uuid4()
            session.add(
                Incident(
                    id=incident_id,
                    tenant_id=tenant_id,
                    publisher_id=site.publisher_id,
                    site_id=site_id,
                    title="Guard incident",
                    symptom_family="OTHER",
                    description="blocks downgrade",
                    opened_at=datetime.now(UTC),
                    status="OPEN",
                )
            )
            await session.flush()
            event_a = Event(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                site_id=site_id,
                event_definition_id=definition_id("NOINDEX_ADDED"),
                template_id=None,
                started_at=datetime.now(UTC),
                occurred_after_at=None,
                occurred_before_at=datetime.now(UTC),
                time_precision="WINDOW",
                detected_at=datetime.now(UTC),
                severity="LOW",
                observation_confidence="HIGH",
                status="RECORDED",
                source_kind="BROWSER_CHECKPOINT",
                source_version="e3-v1",
                condition_key=None,
                scope={"config_type": "ROBOTS_TXT"},
                summary="guard event A",
                details={},
            )
            event_b = Event(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                site_id=site_id,
                event_definition_id=definition_id("NOINDEX_ADDED"),
                template_id=None,
                started_at=datetime.now(UTC),
                occurred_after_at=None,
                occurred_before_at=datetime.now(UTC),
                time_precision="WINDOW",
                detected_at=datetime.now(UTC),
                severity="LOW",
                observation_confidence="HIGH",
                status="RECORDED",
                source_kind="BROWSER_CHECKPOINT",
                source_version="e3-v1",
                condition_key=None,
                scope={"config_type": "ROBOTS_TXT"},
                summary="guard event B",
                details={},
            )
            session.add_all([event_a, event_b])
            await session.flush()
            session.add(
                EventRelation(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    site_id=site_id,
                    from_event_id=event_a.id,
                    to_event_id=event_b.id,
                    relation_type="PRECEDES",
                    derived_at=datetime.now(UTC),
                    engine_version="test-v1",
                )
            )
            session.add(
                ManualNote(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    site_id=site_id,
                    incident_id=incident_id,
                    note_type="ROLLBACK",
                    note_text="operator rollback blocks the descent",
                )
            )
            session.add(
                EvidencePack(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    site_id=site_id,
                    incident_id=incident_id,
                    window_start=datetime.now(UTC),
                    window_end=datetime.now(UTC),
                    fingerprints={"collector_bundle": "b8-v1"},
                    content={"engine_version": "pack-v1"},
                    content_hash="a" * 64,
                    engine_version="pack-v1",
                )
            )
            diagnostic_run_id = registered.checkpoint_run_id
            return (
                tenant_id,
                site_id,
                diagnostic_run_id,
            )

        del diagnostic_run_id

    config = Config("alembic.ini")
    seeded = asyncio.run(seed())
    _tenant_id, _site_id, _diagnostic_run_id = seeded

    def expect_refusal(pattern: str) -> None:
        try:
            command.downgrade(config, "base")
        except ProgrammingError as error:
            assert pattern in str(error), str(error)
            return
        raise AssertionError(f"expected downgrade refusal matching {pattern!r}")

    purge = make_purge(get_session_factory)

    try:
        expect_refusal("evidence_packs contains rows")

        # Whichever guarded table is encountered first, the descent must
        # refuse while any foundation/evidence row exists.
        with pytest.raises(ProgrammingError, match="cannot downgrade while"):
            command.downgrade(config, "base")
    finally:
        asyncio.run(purge())
        command.downgrade(config, "base")
        command.upgrade(config, "head")


def test_ep030_populated_site_upgrade_backfills_off() -> None:
    """EP-030 migration: a site that exists BEFORE revision 0029 is upgraded with an
    OFF monitoring_state and a non-null backfill timestamp, and it leaves the audit
    table empty and the site's unrelated data unchanged."""
    import asyncio
    import uuid

    from alembic import command
    from alembic.config import Config

    from app.db.session import get_session_factory

    factory = get_session_factory()
    config = Config("alembic.ini")
    purge = make_purge(get_session_factory)

    async def seed_at_0028() -> dict[str, uuid.UUID]:
        """Insert a minimal tenant/publisher/site hierarchy using raw SQL while
        still at revision 0028 (where sites has no monitoring columns yet)."""
        ids = {
            "tenant_id": uuid.uuid4(),
            "publisher_id": uuid.uuid4(),
            "site_id": uuid.uuid4(),
        }
        slug = ids["tenant_id"].hex[:8]
        async with factory() as session, session.begin():
            await session.execute(
                text("INSERT INTO tenants (id, slug, name) VALUES (:id, :slug, :name)"),
                {"id": ids["tenant_id"], "slug": f"pop-{slug}", "name": "Populated"},
            )
            await session.execute(
                text(
                    "INSERT INTO publishers (id, tenant_id, name, slug, "
                    "default_timezone, status) VALUES "
                    "(:id, :tenant_id, :name, :slug, 'UTC', 'ACTIVE')"
                ),
                {
                    "id": ids["publisher_id"],
                    "tenant_id": ids["tenant_id"],
                    "name": "Populated Publisher",
                    "slug": f"pop-pub-{ids['publisher_id'].hex[:8]}",
                },
            )
            await session.execute(
                text(
                    "INSERT INTO sites (id, tenant_id, publisher_id, name, "
                    "canonical_domain, canonical_scheme, timezone, status) VALUES "
                    "(:id, :tenant_id, :publisher_id, :name, :canonical_domain, "
                    "'https', 'UTC', 'ACTIVE')"
                ),
                {
                    "id": ids["site_id"],
                    "tenant_id": ids["tenant_id"],
                    "publisher_id": ids["publisher_id"],
                    "name": "Populated Site",
                    "canonical_domain": f"{ids['site_id'].hex}.example.com",
                },
            )
        return ids

    async def read_site(site_id: uuid.UUID) -> tuple[str, datetime | None]:
        async with factory() as session:
            row = (
                await session.execute(
                    text(
                        "SELECT monitoring_state::text, monitoring_state_updated_at "
                        "FROM sites WHERE id = :site_id"
                    ),
                    {"site_id": site_id},
                )
            ).first()
        assert row is not None
        state, updated_at = str(row[0]), row[1]
        return state, updated_at if isinstance(updated_at, datetime) else None

    async def audit_count() -> int:
        async with factory() as session:
            value = (
                await session.execute(text("SELECT count(*) FROM site_monitoring_state_changes"))
            ).scalar_one()
        return int(value)

    async def publisher_domain_snapshot(site_id: uuid.UUID) -> tuple[str, str]:
        async with factory() as session:
            row = (
                await session.execute(
                    text(
                        "SELECT s.canonical_domain, s.canonical_scheme "
                        "FROM sites s WHERE s.id = :site_id"
                    ),
                    {"site_id": site_id},
                )
            ).first()
        assert row is not None
        return row[0], row[1]

    try:
        command.upgrade(config, "0028_operator_ui_trigger_source")
        ids = asyncio.run(seed_at_0028())
        site_id = ids["site_id"]
        domain_before, scheme_before = asyncio.run(publisher_domain_snapshot(site_id))

        command.upgrade(config, "head")

        state, updated_at = asyncio.run(read_site(site_id))
        domain_after, scheme_after = asyncio.run(publisher_domain_snapshot(site_id))
        assert state == "OFF"
        assert updated_at is not None
        # The exact backfill instant is a timezone-aware wall clock value.
        assert updated_at.tzinfo is not None
        assert (domain_after, scheme_after) == (domain_before, scheme_before)
        assert asyncio.run(audit_count()) == 0
    finally:
        asyncio.run(purge())
        command.downgrade(config, "base")
        command.upgrade(config, "head")


def test_ep030_monitoring_downgrade_guards_and_off_default() -> None:
    """EP-030 migration: sites default OFF, and the guarded downgrade refuses while a
    monitoring audit row exists, a site is ON, or a SKIPPED run exists."""
    import asyncio
    import uuid
    from unittest.mock import patch

    from alembic import command
    from alembic.config import Config
    from sqlalchemy.exc import ProgrammingError

    from app.browser.security import BrowserNetworkGuard
    from app.browser.service import CheckpointService

    factory = get_session_factory()

    async def seed() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
        tenant_id = uuid.uuid4()
        publisher_id, site_id = uuid.uuid4(), uuid.uuid4()
        actor_id = uuid.uuid4()
        async with factory() as session, session.begin():
            session.add(Tenant(id=tenant_id, slug=f"ep030-{tenant_id.hex[:8]}", name="EP-030"))
            await session.flush()
            session.add(
                Publisher(
                    id=publisher_id,
                    tenant_id=tenant_id,
                    name="EP-030 Publisher",
                    slug=f"ep030-pub-{publisher_id.hex[:8]}",
                    default_timezone="UTC",
                    status="ACTIVE",
                )
            )
            await session.flush()
            session.add(
                Site(
                    id=site_id,
                    tenant_id=tenant_id,
                    publisher_id=publisher_id,
                    name="EP-030 Site",
                    canonical_domain=f"{site_id.hex}.example.com",
                    canonical_scheme="https",
                    timezone="UTC",
                    status="ACTIVE",
                )
            )
        return tenant_id, site_id, actor_id

    async def assert_default_off(site_id: uuid.UUID) -> None:
        async with factory() as session:
            state = await session.scalar(select(Site.monitoring_state).where(Site.id == site_id))
            audit = list((await session.scalars(select(SiteMonitoringStateChange))).all())
        assert state == "OFF"
        assert audit == []

    async def enable(site_id: uuid.UUID) -> None:
        async with factory() as session, session.begin():
            site = await session.scalar(select(Site).where(Site.id == site_id))
            assert site is not None
            site.monitoring_state = "ON"
            site.monitoring_state_updated_at = datetime.now(UTC)

    async def add_audit_row(tenant_id: uuid.UUID, site_id: uuid.UUID, actor_id: uuid.UUID) -> None:
        async with factory() as session, session.begin():
            session.add(
                SiteMonitoringStateChange(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    site_id=site_id,
                    from_state="OFF",
                    to_state="ON",
                    actor_id=actor_id,
                )
            )

    async def set_skipped(checkpoint_run_id: uuid.UUID) -> None:
        async with factory() as session, session.begin():
            run = await session.scalar(
                select(CheckpointRun).where(CheckpointRun.id == checkpoint_run_id)
            )
            assert run is not None
            run.status = "SKIPPED"

    async def _allow_url(_self: object, url: str) -> str:
        return url

    config = Config("alembic.ini")

    def expect_refusal(pattern: str) -> None:
        try:
            command.downgrade(config, "base")
        except ProgrammingError as error:
            assert pattern in str(error), str(error)
            return
        raise AssertionError(f"expected downgrade refusal matching {pattern!r}")

    purge = make_purge(get_session_factory)

    try:
        tenant_id, site_id, actor_id = asyncio.run(seed())
        asyncio.run(assert_default_off(site_id))

        # Guard 1: an audit row blocks the descent (and no audit row exists yet).
        asyncio.run(add_audit_row(tenant_id, site_id, actor_id))
        expect_refusal("cannot downgrade while site monitoring state changes exist")

        # Guard 2: a site with monitoring ON blocks the descent.
        asyncio.run(purge())
        _t, site2, _a = asyncio.run(seed())
        asyncio.run(enable(site2))
        expect_refusal("cannot downgrade while monitoring is enabled on a site")

        # Guard 3: a SKIPPED checkpoint run blocks the descent.
        asyncio.run(purge())
        settings = get_settings()
        checkpoint_service = CheckpointService(factory, JobQueue(factory), settings)
        with patch.object(BrowserNetworkGuard, "validate_initial", _allow_url):
            registered = asyncio.run(
                checkpoint_service.register_and_enqueue(
                    tenant_slug=f"ep030-skip-{uuid.uuid4().hex[:8]}",
                    tenant_name="EP-030 Skip Tenant",
                    publisher_name="EP-030 Skip Publisher",
                    site_name="EP-030 Skip Site",
                    url=f"https://{uuid.uuid4().hex}.example.com/",
                    observation_kind="DIAGNOSTIC",
                )
            )
        asyncio.run(set_skipped(registered.checkpoint_run_id))
        expect_refusal("cannot downgrade while skipped checkpoint runs exist")
    finally:
        asyncio.run(purge())
        command.downgrade(config, "base")
        command.upgrade(config, "head")
