import asyncio
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select

from app.browser.models import (
    BrowserScenario,
    CheckpointRun,
    CheckpointWindow,
    DomainEntity,
    GPTSlotObservation,
    JavaScriptErrorObservation,
    MonitoredUrl,
    Publisher,
    SeoObservation,
    Site,
    Template,
)
from app.db.models import Tenant
from app.db.session import get_session_factory
from app.events.models import Event, EventEvidenceRef
from app.events.persistence import EventRepository, EventStateError
from app.events.registry import definition_id
from app.events.service import EventService

pytestmark = pytest.mark.integration


@dataclass(frozen=True, slots=True)
class EventFixture:
    tenant_id: uuid.UUID
    other_tenant_id: uuid.UUID
    site_id: uuid.UUID
    template_id: uuid.UUID
    scenario_id: uuid.UUID
    monitored_url_ids: tuple[uuid.UUID, uuid.UUID]


@pytest.fixture
async def event_fixture() -> AsyncIterator[EventFixture]:
    tenant_id, other_tenant_id = uuid.uuid4(), uuid.uuid4()
    publisher_id, site_id, template_id, scenario_id = (uuid.uuid4() for _ in range(4))
    monitored_url_ids = (uuid.uuid4(), uuid.uuid4())
    factory = get_session_factory()
    async with factory() as session, session.begin():
        session.add_all(
            [
                Tenant(id=tenant_id, slug=f"events-{tenant_id.hex[:10]}", name="Events Tenant"),
                Tenant(
                    id=other_tenant_id,
                    slug=f"events-other-{other_tenant_id.hex[:10]}",
                    name="Other Events Tenant",
                ),
            ]
        )
        await session.flush()
        session.add(
            Publisher(
                id=publisher_id,
                tenant_id=tenant_id,
                name="Events Publisher",
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
                name="Events Site",
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
                template_family="ARTICLE",
                expected_features={},
                status="ACTIVE",
            )
        )
        await session.flush()
        session.add_all(
            [
                MonitoredUrl(
                    id=monitored_url_id,
                    tenant_id=tenant_id,
                    site_id=site_id,
                    template_id=template_id,
                    url=f"https://{site_id.hex}.example.com/article-{index}",
                    priority=index,
                    is_canary=False,
                    status="ACTIVE",
                )
                for index, monitored_url_id in enumerate(monitored_url_ids)
            ]
        )
        session.add(
            BrowserScenario(
                id=scenario_id,
                tenant_id=tenant_id,
                site_id=site_id,
                code="desktop-primary",
                version=1,
                device_class="DESKTOP",
                device_profile={},
                locale="en-US",
                timezone="UTC",
                cache_mode="CLEAN",
                consent_path="PRIMARY",
                status="ACTIVE",
            )
        )

    yield EventFixture(
        tenant_id,
        other_tenant_id,
        site_id,
        template_id,
        scenario_id,
        monitored_url_ids,
    )

    async with factory() as session, session.begin():
        for model in (
            EventEvidenceRef,
            Event,
            GPTSlotObservation,
            JavaScriptErrorObservation,
            SeoObservation,
            CheckpointRun,
            CheckpointWindow,
            DomainEntity,
            MonitoredUrl,
            BrowserScenario,
            Template,
            Site,
            Publisher,
        ):
            await session.execute(delete(model).where(model.tenant_id == tenant_id))
        await session.execute(delete(Tenant).where(Tenant.id.in_([tenant_id, other_tenant_id])))


async def test_js_condition_deduplicates_resolves_and_reopens(
    event_fixture: EventFixture,
) -> None:
    fixture = event_fixture
    factory = get_session_factory()
    observed = datetime(2026, 8, 21, tzinfo=UTC)
    previous_id: uuid.UUID | None = None
    runs: list[uuid.UUID] = []
    affected_states = [False, True, True, True, False, True, True]
    async with factory() as session, session.begin():
        for index, affected in enumerate(affected_states):
            run = _checkpoint(
                fixture,
                monitored_url_id=fixture.monitored_url_ids[0],
                observed_at=observed + timedelta(hours=6 * index),
                previous_id=previous_id,
                errors=("js-fingerprint",) if affected else (),
            )
            session.add(run.window)
            await session.flush()
            session.add(run.run)
            if affected:
                session.add(
                    JavaScriptErrorObservation(
                        id=uuid.uuid4(),
                        tenant_id=fixture.tenant_id,
                        site_id=fixture.site_id,
                        checkpoint_run_id=run.run.id,
                        fingerprint="js-fingerprint",
                        normalized_message="bounded normalized error",
                        count=1,
                        collector_version="b3-v1",
                    )
                )
            runs.append(run.run.id)
            previous_id = run.run.id

    service = EventService(EventRepository(factory))
    created, repeated = await asyncio.gather(
        service.derive(tenant_id=fixture.tenant_id, checkpoint_run_id=runs[2]),
        service.derive(tenant_id=fixture.tenant_id, checkpoint_run_id=runs[2]),
    )
    supported = await service.derive(tenant_id=fixture.tenant_id, checkpoint_run_id=runs[3])
    resolved = await service.derive(tenant_id=fixture.tenant_id, checkpoint_run_id=runs[4])
    pending = await service.derive(tenant_id=fixture.tenant_id, checkpoint_run_id=runs[5])
    reopened = await service.derive(tenant_id=fixture.tenant_id, checkpoint_run_id=runs[6])

    assert created.persisted_count + repeated.persisted_count == 1
    assert created.updated_count + repeated.updated_count == 0
    assert supported.updated_count == 1
    assert resolved.resolved_count == 1
    assert pending.persisted_count == 0 and pending.unsupported_count == 1
    assert reopened.persisted_count == 1

    async with factory() as session:
        events = list(
            (
                await session.scalars(
                    select(Event)
                    .where(
                        Event.tenant_id == fixture.tenant_id,
                        Event.event_definition_id == definition_id("JS_ERROR_STARTED"),
                    )
                    .order_by(Event.started_at)
                )
            ).all()
        )
        assert [event.status for event in events] == ["RESOLVED", "ACTIVE"]
        assert events[0].ended_at == observed + timedelta(hours=24)
        assert events[0].occurred_after_at == observed
        assert events[0].occurred_before_at == observed + timedelta(hours=6)
        assert events[0].detected_at == observed + timedelta(hours=12)
        assert events[0].details["lifecycle"]["supporting_count"] == 3
        refs = list(
            (
                await session.scalars(
                    select(EventEvidenceRef).where(
                        EventEvidenceRef.tenant_id == fixture.tenant_id,
                        EventEvidenceRef.event_id == events[0].id,
                    )
                )
            ).all()
        )
        assert {"TRIGGER_BEFORE", "TRIGGER_AFTER", "SUPPORTING", "RECOVERY"} <= {
            ref.relation for ref in refs
        }

    repository = EventRepository(factory)
    with pytest.raises(EventStateError, match="ownership"):
        await repository.load_input(
            tenant_id=fixture.other_tenant_id,
            checkpoint_run_id=runs[2],
        )


async def test_gpt_multi_url_condition_aggregates_and_requires_corroborated_recovery(
    event_fixture: EventFixture,
) -> None:
    fixture = event_fixture
    factory = get_session_factory()
    observed = datetime(2026, 8, 21, tzinfo=UTC)
    slot_id = uuid.uuid4()
    async with factory() as session, session.begin():
        session.add(
            DomainEntity(
                id=slot_id,
                tenant_id=fixture.tenant_id,
                site_id=fixture.site_id,
                entity_kind="GPT_SLOT",
                stable_key="slot-article-mid",
                first_seen_at=observed,
                last_seen_at=observed,
                identity_metadata={},
            )
        )
        previous_runs: list[uuid.UUID] = []
        current_runs: list[uuid.UUID] = []
        recovery_runs: list[uuid.UUID] = []
        previous_window_id: uuid.UUID | None = None
        current_window_id: uuid.UUID | None = None
        recovery_window_id: uuid.UUID | None = None
        for index, monitored_url_id in enumerate(fixture.monitored_url_ids):
            previous = _checkpoint(
                fixture,
                monitored_url_id=monitored_url_id,
                observed_at=observed,
                gpt_present=True,
            )
            current = _checkpoint(
                fixture,
                monitored_url_id=monitored_url_id,
                observed_at=observed + timedelta(hours=6),
                previous_id=previous.run.id,
                gpt_present=False,
            )
            recovery = _checkpoint(
                fixture,
                monitored_url_id=monitored_url_id,
                observed_at=observed + timedelta(hours=12),
                previous_id=current.run.id,
                gpt_present=True,
            )
            if index == 0:
                previous_window_id = previous.window.id
                current_window_id = current.window.id
                recovery_window_id = recovery.window.id
                session.add_all([previous.window, current.window, recovery.window])
                await session.flush()
            else:
                assert (
                    previous_window_id is not None
                    and current_window_id is not None
                    and recovery_window_id is not None
                )
                previous.run.checkpoint_window_id = previous_window_id
                current.run.checkpoint_window_id = current_window_id
                recovery.run.checkpoint_window_id = recovery_window_id
            session.add(previous.run)
            session.add_all([current.run, recovery.run])
            for checkpoint, present in (
                (previous.run, True),
                (current.run, False),
                (recovery.run, True),
            ):
                session.add(
                    GPTSlotObservation(
                        id=uuid.uuid4(),
                        tenant_id=fixture.tenant_id,
                        site_id=fixture.site_id,
                        checkpoint_run_id=checkpoint.id,
                        slot_entity_id=slot_id,
                        sizes=[],
                        expected=True,
                        present=present,
                        request_count=1 if present else 0,
                        collector_version="b4-v1",
                    )
                )
            previous_runs.append(previous.run.id)
            current_runs.append(current.run.id)
            recovery_runs.append(recovery.run.id)

    service = EventService(EventRepository(factory))
    created = await service.derive(tenant_id=fixture.tenant_id, checkpoint_run_id=current_runs[0])
    replayed = await service.derive(tenant_id=fixture.tenant_id, checkpoint_run_id=current_runs[1])
    resolved = await service.derive(tenant_id=fixture.tenant_id, checkpoint_run_id=recovery_runs[0])
    assert created.persisted_count == 1
    assert replayed.persisted_count == replayed.updated_count == 0
    assert resolved.resolved_count == 1

    async with factory() as session:
        event = await session.scalar(
            select(Event).where(
                Event.tenant_id == fixture.tenant_id,
                Event.event_definition_id == definition_id("GPT_EXPECTED_SLOT_MISSING"),
            )
        )
        assert event is not None
        assert event.status == "RESOLVED"
        assert event.severity == "HIGH"
        assert event.scope == {
            "scenario_id": str(fixture.scenario_id),
            "template_id": str(fixture.template_id),
        }
        assert event.details["lifecycle"]["affected_url_count"] == 2
        refs = list(
            (
                await session.scalars(
                    select(EventEvidenceRef).where(EventEvidenceRef.event_id == event.id)
                )
            ).all()
        )
        assert len([ref for ref in refs if ref.evidence_kind == "GPT_SLOT_OBSERVATION"]) == 6


async def test_noindex_uses_one_aggregated_recorded_point(
    event_fixture: EventFixture,
) -> None:
    fixture = event_fixture
    factory = get_session_factory()
    observed = datetime(2026, 8, 21, tzinfo=UTC)
    async with factory() as session, session.begin():
        current_runs: list[uuid.UUID] = []
        previous_window_id: uuid.UUID | None = None
        current_window_id: uuid.UUID | None = None
        for index, monitored_url_id in enumerate(fixture.monitored_url_ids):
            previous = _checkpoint(
                fixture,
                monitored_url_id=monitored_url_id,
                observed_at=observed,
            )
            current = _checkpoint(
                fixture,
                monitored_url_id=monitored_url_id,
                observed_at=observed + timedelta(hours=6),
                previous_id=previous.run.id,
                noindex=True,
            )
            if index == 0:
                previous_window_id = previous.window.id
                current_window_id = current.window.id
                session.add_all([previous.window, current.window])
                await session.flush()
            else:
                assert previous_window_id is not None and current_window_id is not None
                previous.run.checkpoint_window_id = previous_window_id
                current.run.checkpoint_window_id = current_window_id
            session.add(previous.run)
            session.add(current.run)
            for checkpoint, noindex in ((previous.run, False), (current.run, True)):
                session.add(
                    SeoObservation(
                        id=uuid.uuid4(),
                        tenant_id=fixture.tenant_id,
                        site_id=fixture.site_id,
                        checkpoint_run_id=checkpoint.id,
                        final_url="https://example.com/article",
                        http_status=200,
                        meta_robots="noindex" if noindex else None,
                        redirect_count=0,
                        collector_version="seo-e1-v1",
                        metadata_json={},
                    )
                )
            current_runs.append(current.run.id)

    service = EventService(EventRepository(factory))
    result = await service.derive(tenant_id=fixture.tenant_id, checkpoint_run_id=current_runs[0])
    assert result.persisted_count == 1
    async with factory() as session:
        events = list(
            (
                await session.scalars(
                    select(Event).where(
                        Event.tenant_id == fixture.tenant_id,
                        Event.event_definition_id == definition_id("NOINDEX_ADDED"),
                    )
                )
            ).all()
        )
        assert len(events) == 1
        assert events[0].status == "RECORDED"
        assert events[0].severity == "CRITICAL"
        assert "monitored_url_id" not in events[0].scope


@dataclass(slots=True)
class CheckpointFixture:
    window: CheckpointWindow
    run: CheckpointRun


def _checkpoint(
    fixture: EventFixture,
    *,
    monitored_url_id: uuid.UUID,
    observed_at: datetime,
    previous_id: uuid.UUID | None = None,
    errors: tuple[str, ...] = (),
    gpt_present: bool | None = None,
    noindex: bool = False,
) -> CheckpointFixture:
    window_id, run_id = uuid.uuid4(), uuid.uuid4()
    window = CheckpointWindow(
        id=window_id,
        tenant_id=fixture.tenant_id,
        site_id=fixture.site_id,
        scheduled_for=observed_at,
        window_start=observed_at,
        window_end=observed_at + timedelta(hours=6),
        status="COMPLETE",
        completed_at=observed_at,
    )
    gpt_slots = (
        [
            {
                "stable_key": "slot-article-mid",
                "expected": True,
                "present": gpt_present,
            }
        ]
        if gpt_present is not None
        else []
    )
    run = CheckpointRun(
        id=run_id,
        tenant_id=fixture.tenant_id,
        site_id=fixture.site_id,
        checkpoint_window_id=window_id,
        monitored_url_id=monitored_url_id,
        template_id=fixture.template_id,
        scenario_id=fixture.scenario_id,
        scheduled_for=observed_at,
        started_at=observed_at - timedelta(minutes=1),
        completed_at=observed_at,
        status="COMPLETE",
        attempt_count=1,
        collector_bundle_version="b8-v1",
        environment={},
        limitations=[],
        manifest={
            "comparison_lineage": {
                "previous_checkpoint_run_id": str(previous_id) if previous_id else None,
                "selection_scope": "EXACT_MONITORED_URL" if previous_id else None,
            },
            "normalized_state": _state(errors=errors, noindex=noindex),
            "gpt": {"slots": gpt_slots},
        },
    )
    return CheckpointFixture(window, run)


def _state(*, errors: tuple[str, ...] = (), noindex: bool = False) -> dict[str, object]:
    return {
        "scripts": {"normalizer_version": "v1", "identities": [], "truncated": False},
        "network": {"normalizer_version": "v1", "dependencies": [], "truncated": False},
        "javascript_errors": {
            "normalizer_version": "v1",
            "errors": [{"fingerprint": error} for error in errors],
        },
        "seo": {
            "normalizer_version": "seo-e1-v1",
            "meta_robots": "noindex" if noindex else None,
            "canonical_url": "https://example.com/article",
        },
    }
