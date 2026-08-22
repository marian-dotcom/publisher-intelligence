import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.browser.models import (
    BrowserScenario,
    CheckpointRun,
    CheckpointWindow,
    MonitoredUrl,
    Publisher,
    Site,
    Template,
)
from app.common.comparability import evidence_fingerprints
from app.db.models import Tenant
from app.db.session import get_session_factory
from app.events.models import Event
from app.evidence.builder import EvidencePackBuilder
from app.evidence.fixtures import (
    INVENTORY,
    load_all_connector_fixtures,
    load_fixture,
)
from app.evidence.models import EventRelation
from app.evidence.persistence import EvidenceRepository

pytestmark = pytest.mark.integration


@pytest.fixture
async def evidence_pack_fixture() -> AsyncGenerator[tuple[uuid.UUID, uuid.UUID], None]:
    factory = get_session_factory()
    tenant_id, publisher_id = uuid.uuid4(), uuid.uuid4()
    site_id, template_id = uuid.uuid4(), uuid.uuid4()
    monitored_url_id, scenario_id = uuid.uuid4(), uuid.uuid4()
    async with factory() as session, session.begin():
        session.add(Tenant(id=tenant_id, slug=f"evp-{tenant_id.hex[:10]}", name="EVP Tenant"))
        await session.flush()
        session.add(
            Publisher(
                id=publisher_id,
                tenant_id=tenant_id,
                name="EVP Publisher",
                slug=f"publisher-{publisher_id.hex[:10]}",
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
                name="EVP Site",
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
        base_time = datetime(2026, 8, 21, 6, tzinfo=UTC)

        async def add_scheduled_run(run_id: uuid.UUID, when: datetime) -> None:
            window_id = uuid.uuid4()
            session.add(
                CheckpointWindow(
                    id=window_id,
                    tenant_id=tenant_id,
                    site_id=site_id,
                    scheduled_for=when,
                    window_start=when,
                    window_end=when + timedelta(minutes=30),
                )
            )
            await session.flush()
            session.add(
                CheckpointRun(
                    id=run_id,
                    tenant_id=tenant_id,
                    site_id=site_id,
                    checkpoint_window_id=window_id,
                    monitored_url_id=monitored_url_id,
                    template_id=template_id,
                    scenario_id=scenario_id,
                    observation_kind="SCHEDULED",
                    scheduled_for=when,
                    started_at=when,
                    completed_at=when + timedelta(minutes=5),
                    status="COMPLETE",
                    attempt_count=1,
                    collector_bundle_version="b8-v1",
                    environment={"is_mobile": False},
                    limitations=[],
                    manifest={},
                )
            )

        await add_scheduled_run(uuid.uuid4(), base_time)
        await add_scheduled_run(uuid.uuid4(), base_time + timedelta(hours=6))

        from app.events.registry import definition_id as event_definition_id

        definition_id = event_definition_id("NOINDEX_ADDED")
        event_a = Event(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            site_id=site_id,
            event_definition_id=definition_id,
            template_id=None,
            started_at=base_time,
            occurred_after_at=None,
            occurred_before_at=base_time,
            time_precision="WINDOW",
            detected_at=base_time,
            severity="MEDIUM",
            observation_confidence="HIGH",
            status="RECORDED",
            source_kind="BROWSER_CHECKPOINT",
            source_version="e3-v1",
            condition_key=None,
            scope={"config_type": "ROBOTS_TXT"},
            summary="fixture event A",
            details={},
        )
        event_b = Event(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            site_id=site_id,
            event_definition_id=definition_id,
            template_id=None,
            started_at=base_time + timedelta(hours=6),
            occurred_after_at=None,
            occurred_before_at=base_time + timedelta(hours=6),
            time_precision="WINDOW",
            detected_at=base_time + timedelta(hours=6),
            severity="LOW",
            observation_confidence="HIGH",
            status="RECORDED",
            source_kind="BROWSER_CHECKPOINT",
            source_version="e3-v1",
            condition_key=None,
            scope={"config_type": "ROBOTS_TXT"},
            summary="fixture event B",
            details={},
        )
        session.add_all([event_a, event_b])

    yield tenant_id, site_id

    from tests.integration.purge import make_purge

    purge = make_purge(get_session_factory)
    await purge()


def test_sanitized_connector_fixture_inventory_is_available() -> None:
    fixtures = load_all_connector_fixtures()
    assert set(fixtures) == {"ga4", "gsc", "gam"}
    for provider, payloads in fixtures.items():
        assert payloads, provider
        for name, payload in payloads.items():
            assert isinstance(payload, dict), f"{provider}/{name}"
            serialized = str(payload).lower()
            assert "password" not in serialized
            assert "refresh_token" not in serialized


def test_fixture_paths_exist_on_disk() -> None:
    root = Path(__file__).resolve().parents[1] / "fixtures" / "connectors"
    for provider, names in INVENTORY.items():
        for name in names:
            assert (root / provider / name).exists(), f"{provider}/{name}"


def test_load_fixture_rejects_missing_files() -> None:
    with pytest.raises(FileNotFoundError):
        load_fixture("ga4", "does_not_exist.json")


def test_fingerprints_flow_into_packs() -> None:
    fingerprints = evidence_fingerprints({"collector_bundle": "b8-v1"})
    assert fingerprints == {"collector_bundle": "b8-v1"}


@pytest.mark.asyncio
async def test_evidence_pack_is_deterministic_and_tenant_scoped(
    evidence_pack_fixture: tuple[uuid.UUID, uuid.UUID],
) -> None:
    tenant_id, site_id = evidence_pack_fixture
    builder = EvidencePackBuilder(get_session_factory())
    window_start = datetime(2026, 8, 20, tzinfo=UTC)
    window_end = datetime(2026, 8, 23, tzinfo=UTC)

    pack_one = await builder.build(
        tenant_id=tenant_id,
        site_id=site_id,
        incident_id=None,
        window_start=window_start,
        window_end=window_end,
    )
    pack_two = await builder.build(
        tenant_id=tenant_id,
        site_id=site_id,
        incident_id=None,
        window_start=window_start,
        window_end=window_end,
    )
    assert EvidencePackBuilder.pack_hash(pack_one) == EvidencePackBuilder.pack_hash(pack_two)
    assert len(pack_one["scheduled_checkpoints"]) == 2

    empty_pack = await builder.build(
        tenant_id=uuid.uuid4(),
        site_id=site_id,
        incident_id=None,
        window_start=window_start,
        window_end=window_end,
    )
    assert empty_pack["scheduled_checkpoints"] == []
    assert empty_pack["human_reported_notes_count"] == 0


@pytest.mark.asyncio
async def test_relations_and_manual_notes_are_append_only_and_scoped(
    evidence_pack_fixture: tuple[uuid.UUID, uuid.UUID],
) -> None:
    tenant_id, site_id = evidence_pack_fixture
    factory = get_session_factory()
    repository = EvidenceRepository(factory)
    async with factory() as session:
        events = list(
            (await session.scalars(select(Event).where(Event.tenant_id == tenant_id))).all()
        )
    assert len(events) >= 2
    event_a, event_b = events[0], events[1]

    relation = await repository.add_relation(
        tenant_id=tenant_id,
        site_id=site_id,
        from_event_id=event_a.id,
        to_event_id=event_b.id,
        relation_type="PRECEDES",
        engine_version="test-v1",
        confidence="HIGH",
        reason="ordering fixture",
    )
    duplicate = await repository.add_relation(
        tenant_id=tenant_id,
        site_id=site_id,
        from_event_id=event_a.id,
        to_event_id=event_b.id,
        relation_type="PRECEDES",
        engine_version="test-v1",
    )
    assert duplicate.id == relation.id

    relations = await repository.relations_for_events(tenant_id=tenant_id, event_ids=(event_a.id,))
    assert len(relations) == 1

    async with factory() as session:
        loaded = await session.get(EventRelation, relation.id)
        assert loaded is not None
        loaded.reason = "tampered"
        with pytest.raises(RuntimeError, match="immutable"):
            await session.commit()
        await session.rollback()

    note = await repository.add_manual_note(
        tenant_id=tenant_id,
        site_id=site_id,
        note_type="ROLLBACK",
        note_text="Operator rolled back the CMP change.",
    )
    notes = await repository.manual_notes_for_site(tenant_id=tenant_id, site_id=site_id)
    assert [item.id for item in notes] == [note.id]
    assert notes[0].source == "operator"

    assert await repository.manual_notes_for_site(tenant_id=uuid.uuid4(), site_id=site_id) == ()

    with pytest.raises(Exception, match="tenant"):
        await repository._assert_event_ownership(uuid.uuid4(), site_id, event_a.id)
