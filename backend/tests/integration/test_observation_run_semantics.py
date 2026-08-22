import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.browser.contracts import (
    BrowserEvidence,
    BrowserTarget,
    CheckpointStatus,
)
from app.browser.models import (
    BrowserScenario,
    CheckpointAttempt,
    CheckpointRun,
    CheckpointWindow,
    InteractionProfile,
    MonitoredUrl,
    Publisher,
    Site,
    Template,
)
from app.browser.persistence import CheckpointRepository
from app.browser.service import CheckpointService
from app.config.settings import get_settings
from app.db.models import Job, Tenant
from app.db.session import get_session_factory
from app.events.models import Event, EventEvidenceRef
from app.events.persistence import EventRepository, EventStateError
from app.jobs.queue import JobQueue

pytestmark = pytest.mark.integration


async def _seed_site() -> uuid.UUID:
    factory = get_session_factory()
    tenant_id, publisher_id = uuid.uuid4(), uuid.uuid4()
    site_id, template_id = uuid.uuid4(), uuid.uuid4()
    monitored_url_id, scenario_id = uuid.uuid4(), uuid.uuid4()
    async with factory() as session, session.begin():
        session.add(Tenant(id=tenant_id, slug=f"obs-{tenant_id.hex[:10]}", name="Obs Tenant"))
        await session.flush()
        session.add(
            Publisher(
                id=publisher_id,
                tenant_id=tenant_id,
                name="Obs Publisher",
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
                name="Obs Site",
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
    return tenant_id


async def _cleanup(tenant_id: uuid.UUID) -> None:
    factory = get_session_factory()
    async with factory() as session, session.begin():
        await session.execute(delete(Job).where(Job.tenant_id == tenant_id))
        await session.execute(
            delete(EventEvidenceRef).where(EventEvidenceRef.tenant_id == tenant_id)
        )
        await session.execute(delete(Event).where(Event.tenant_id == tenant_id))
        await session.execute(
            delete(CheckpointAttempt).where(CheckpointAttempt.tenant_id == tenant_id)
        )
        await session.execute(delete(CheckpointRun).where(CheckpointRun.tenant_id == tenant_id))
        await session.execute(
            delete(CheckpointWindow).where(CheckpointWindow.tenant_id == tenant_id)
        )
        await session.execute(delete(BrowserScenario).where(BrowserScenario.tenant_id == tenant_id))
        await session.execute(
            delete(InteractionProfile).where(InteractionProfile.tenant_id == tenant_id)
        )
        await session.execute(delete(MonitoredUrl).where(MonitoredUrl.tenant_id == tenant_id))
        await session.execute(delete(Template).where(Template.tenant_id == tenant_id))
        await session.execute(delete(Site).where(Site.tenant_id == tenant_id))
        await session.execute(delete(Publisher).where(Publisher.tenant_id == tenant_id))
        await session.execute(delete(Tenant).where(Tenant.id == tenant_id))


@pytest.mark.asyncio
async def test_provenance_constraints_enforced_at_database_level() -> None:
    tenant_id = await _seed_site()
    try:
        factory = get_session_factory()
        async with factory() as session, session.begin():
            site = await session.scalar(select(Site).where(Site.tenant_id == tenant_id))
            assert site is not None
            scenario = await session.scalar(
                select(BrowserScenario).where(BrowserScenario.tenant_id == tenant_id)
            )
            monitored_url = await session.scalar(
                select(MonitoredUrl).where(MonitoredUrl.tenant_id == tenant_id)
            )
            template = await session.scalar(select(Template).where(Template.tenant_id == tenant_id))
            assert site is not None and scenario is not None
            assert monitored_url is not None and template is not None
            window_id = uuid.uuid4()

            def run_row(**overrides: object) -> dict[str, Any]:
                values: dict[str, Any] = {
                    "id": uuid.uuid4(),
                    "tenant_id": tenant_id,
                    "site_id": site.id,
                    "checkpoint_window_id": window_id,
                    "monitored_url_id": monitored_url.id,
                    "template_id": template.id,
                    "scenario_id": scenario.id,
                    "scheduled_for": datetime.now(UTC),
                    "status": "PENDING",
                    "attempt_count": 0,
                    "collector_bundle_version": "b8-v1",
                    "environment": {},
                    "limitations": [],
                    "manifest": {},
                }
                values.update(overrides)
                return values

            valid_scheduled = run_row()
            diagnostic_window_id = uuid.uuid4()
            valid_diagnostic = run_row(
                checkpoint_window_id=diagnostic_window_id,
                observation_kind="DIAGNOSTIC",
                trigger_source="OPERATOR_CLI",
                trigger_correlation_id=uuid.uuid4(),
            )
            session.add_all(
                [
                    CheckpointWindow(
                        id=window_id,
                        tenant_id=tenant_id,
                        site_id=site.id,
                        scheduled_for=datetime.now(UTC),
                        window_start=datetime.now(UTC),
                        window_end=datetime.now(UTC) + timedelta(minutes=30),
                    ),
                    CheckpointWindow(
                        id=diagnostic_window_id,
                        tenant_id=tenant_id,
                        site_id=site.id,
                        scheduled_for=datetime.now(UTC) + timedelta(minutes=2),
                        window_start=datetime.now(UTC) + timedelta(minutes=2),
                        window_end=datetime.now(UTC) + timedelta(minutes=7),
                    ),
                ]
            )
            await session.flush()
            session.add_all(
                [
                    CheckpointRun(**valid_scheduled),
                    CheckpointRun(**valid_diagnostic),
                ]
            )

        violations: list[dict[str, Any]] = [
            {"observation_kind": "UNKNOWN_KIND"},
            {"observation_kind": "SCHEDULED", "trigger_source": "OPERATOR_CLI"},
            {"observation_kind": "SCHEDULED", "trigger_correlation_id": uuid.uuid4()},
            {"observation_kind": "DIAGNOSTIC"},
            {"observation_kind": "DIAGNOSTIC", "trigger_source": "OPERATOR_CLI"},
            {
                "observation_kind": "INCIDENT_DIAGNOSTIC",
                "trigger_source": "NOT_A_SOURCE",
                "trigger_correlation_id": uuid.uuid4(),
            },
        ]
        for overrides in violations:
            async with factory() as session, session.begin():
                site_row = await session.scalar(select(Site).where(Site.tenant_id == tenant_id))
                scenario_row = await session.scalar(
                    select(BrowserScenario).where(BrowserScenario.tenant_id == tenant_id)
                )
                url_row = await session.scalar(
                    select(MonitoredUrl).where(MonitoredUrl.tenant_id == tenant_id)
                )
                template_row = await session.scalar(
                    select(Template).where(Template.tenant_id == tenant_id)
                )
                assert site_row and scenario_row and url_row and template_row
                # Each violation gets its own window so the only potentially
                # violated constraint is the provenance rule under test.
                violation_window = CheckpointWindow(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    site_id=site_row.id,
                    scheduled_for=datetime.now(UTC),
                    window_start=datetime.now(UTC),
                    window_end=datetime.now(UTC) + timedelta(minutes=30),
                )
                session.add(violation_window)
                await session.flush()
                session.add(
                    CheckpointRun(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        site_id=site_row.id,
                        checkpoint_window_id=violation_window.id,
                        monitored_url_id=url_row.id,
                        template_id=template_row.id,
                        scenario_id=scenario_row.id,
                        scheduled_for=datetime.now(UTC),
                        attempt_count=0,
                        collector_bundle_version="b8-v1",
                        environment={},
                        limitations=[],
                        manifest={},
                        **overrides,
                    )
                )
                with pytest.raises(IntegrityError):
                    await session.commit()
    finally:
        await _cleanup(tenant_id)


def _evidence(status: CheckpointStatus) -> BrowserEvidence:
    now = datetime.now(UTC)
    return BrowserEvidence(
        status=status,
        started_at=now - timedelta(minutes=1),
        completed_at=now,
        final_url=None,
        http_status=None,
        playwright_version="1.0.0-test",
        chromium_version=None,
        environment={"is_mobile": False},
    )


@pytest.mark.asyncio
async def test_cli_registration_persists_distinct_concrete_identities() -> None:
    settings = get_settings()
    factory = get_session_factory()
    queue = JobQueue(factory)
    service = CheckpointService(factory, queue, settings)
    slug = f"obs-cli-{uuid.uuid4().hex[:10]}"
    first = await service.register_and_enqueue(
        tenant_slug=slug,
        tenant_name="Obs CLI Tenant",
        publisher_name="Obs CLI Publisher",
        site_name="Obs CLI Site",
        url="https://www.example.com/",
    )
    second = await service.register_and_enqueue(
        tenant_slug=slug,
        tenant_name="Obs CLI Tenant",
        publisher_name="Obs CLI Publisher",
        site_name="Obs CLI Site",
        url="https://www.example.com/second",
    )
    try:
        assert first.trigger_correlation_id != second.trigger_correlation_id
        async with factory() as session:
            runs = list(
                (
                    await session.scalars(
                        select(CheckpointRun).where(CheckpointRun.tenant_id == first.tenant_id)
                    )
                ).all()
            )
            windows = list(
                (
                    await session.scalars(
                        select(CheckpointWindow).where(
                            CheckpointWindow.tenant_id == first.tenant_id
                        )
                    )
                ).all()
            )
        assert {run.observation_kind for run in runs} == {"DIAGNOSTIC"}
        assert {run.trigger_source for run in runs} == {"OPERATOR_CLI"}
        assert {run.trigger_correlation_id for run in runs} == {
            first.trigger_correlation_id,
            second.trigger_correlation_id,
        }
        # Ad-hoc diagnostic windows are five-minute invocations, independent of
        # the canonical six-hour scheduled windows even when the target
        # URL/scenario overlap monitoring.
        for window in windows:
            assert window.window_end - window.window_start == timedelta(minutes=5)
    finally:
        await _cleanup(first.tenant_id)
        await _cleanup(second.tenant_id)


@pytest.mark.asyncio
async def test_diagnostic_run_is_excluded_from_cohorts_and_keeps_provenance() -> None:
    tenant_id = await _seed_site()
    try:
        factory = get_session_factory()
        repository = CheckpointRepository(factory)
        async with factory() as session, session.begin():
            site = await session.scalar(select(Site).where(Site.tenant_id == tenant_id))
            scenario = await session.scalar(
                select(BrowserScenario).where(BrowserScenario.tenant_id == tenant_id)
            )
            monitored_url = await session.scalar(
                select(MonitoredUrl).where(MonitoredUrl.tenant_id == tenant_id)
            )
            template = await session.scalar(select(Template).where(Template.tenant_id == tenant_id))
            assert site and scenario and monitored_url and template
            base_time = datetime(2026, 8, 22, 6, tzinfo=UTC)
            site_id_value = site.id
            monitored_url_id_value = monitored_url.id
            template_id_value = template.id
            scenario_code = scenario.code
            scenario_version_value = scenario.version
            scenario_locale = scenario.locale
            scenario_timezone = scenario.timezone

            async def add_window(window_id: uuid.UUID, start: datetime) -> None:
                session.add(
                    CheckpointWindow(
                        id=window_id,
                        tenant_id=tenant_id,
                        site_id=site.id,
                        scheduled_for=start,
                        window_start=start,
                        window_end=start + timedelta(minutes=30),
                    )
                )
                await session.flush()

            async def add_run(
                run_id: uuid.UUID,
                window_id: uuid.UUID,
                kind: str,
                when: datetime,
                *,
                status: str = "COMPLETE",
            ) -> CheckpointRun:
                correlation = uuid.uuid4() if kind != "SCHEDULED" else None
                run = CheckpointRun(
                    id=run_id,
                    tenant_id=tenant_id,
                    site_id=site.id,
                    checkpoint_window_id=window_id,
                    monitored_url_id=monitored_url.id,
                    template_id=template.id,
                    scenario_id=scenario.id,
                    observation_kind=kind,
                    trigger_source="OPERATOR_CLI" if kind != "SCHEDULED" else None,
                    trigger_correlation_id=correlation,
                    scheduled_for=when,
                    started_at=when,
                    completed_at=when + timedelta(minutes=5) if status == "COMPLETE" else None,
                    status=status,
                    attempt_count=1,
                    collector_bundle_version="b8-v1",
                    environment={"is_mobile": False},
                    limitations=[],
                    manifest={},
                )
                session.add(run)
                await session.flush()
                return run

            scheduled_a_id, diagnostic_id, scheduled_b_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
            window_a, window_d, window_b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
            await add_window(window_a, base_time)
            await add_window(window_d, base_time + timedelta(minutes=7))
            await add_window(window_b, base_time + timedelta(days=1))
            await add_run(scheduled_a_id, window_a, "SCHEDULED", base_time)
            await add_run(diagnostic_id, window_d, "DIAGNOSTIC", base_time + timedelta(minutes=7))
            await add_run(scheduled_b_id, window_b, "SCHEDULED", base_time + timedelta(days=1))
            # Put the diagnostic run into a realistic in-flight state with a
            # running attempt so repository lifecycle methods can act on it.
            diagnostic_run_row = await session.scalar(
                select(CheckpointRun).where(CheckpointRun.id == diagnostic_id)
            )
            assert diagnostic_run_row is not None
            diagnostic_run_row.status = "RUNNING"
            session.add(
                CheckpointAttempt(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    checkpoint_run_id=diagnostic_id,
                    attempt_number=1,
                    started_at=base_time + timedelta(minutes=7),
                    status="RUNNING",
                )
            )

        # Lineage predecessor selection skips the diagnostic observation.
        selected = await repository.previous_comparable(
            tenant_id=tenant_id, checkpoint_run_id=scheduled_b_id
        )
        assert selected is not None
        assert selected.id == scheduled_a_id
        selected_for_diagnostic = await repository.previous_comparable(
            tenant_id=tenant_id, checkpoint_run_id=diagnostic_id
        )
        assert selected_for_diagnostic is not None
        assert selected_for_diagnostic.id == scheduled_a_id

        # Capture creation-time provenance before any lifecycle action.
        async with factory() as session:
            seeded_run = await session.scalar(
                select(CheckpointRun).where(CheckpointRun.id == diagnostic_id)
            )
        assert seeded_run is not None
        assert seeded_run.observation_kind == "DIAGNOSTIC"
        original_correlation_seed = seeded_run.trigger_correlation_id
        assert original_correlation_seed is not None

        # Retrying the same run preserves the stored identity.
        await repository.record_retryable_failure(
            tenant_id=tenant_id,
            checkpoint_run_id=diagnostic_id,
            attempt_number=1,
            failure_class="BROWSER_ERROR",
            failure_message="test retry",
        )
        async with factory() as session:
            retried = await session.scalar(
                select(CheckpointRun).where(CheckpointRun.id == diagnostic_id)
            )
        assert retried is not None
        assert retried.trigger_correlation_id == original_correlation_seed
        assert retried.observation_kind == "DIAGNOSTIC"

        # A later successful attempt finalizes without changing provenance and
        # still enqueues no derivation job.
        async with factory() as session, session.begin():
            run_row = await session.scalar(
                select(CheckpointRun).where(CheckpointRun.id == diagnostic_id)
            )
            assert run_row is not None
            run_row.status = "RUNNING"
            session.add(
                CheckpointAttempt(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    checkpoint_run_id=diagnostic_id,
                    attempt_number=2,
                    started_at=datetime.now(UTC),
                    status="RUNNING",
                )
            )
        target = BrowserTarget(
            checkpoint_run_id=diagnostic_id,
            tenant_id=tenant_id,
            site_id=site_id_value,
            monitored_url_id=monitored_url_id_value,
            scenario_id=scenario.id,
            url="https://diagnostic.example/",
            canonical_domain="diagnostic.example",
            scenario_code=scenario_code,
            scenario_version=scenario_version_value,
            locale=scenario_locale,
            timezone=scenario_timezone,
            viewport_width=1280,
            viewport_height=720,
            template_id=template_id_value,
        )
        await repository.finalize(
            target=target,
            attempt_number=2,
            evidence=_evidence("COMPLETE"),
            artifacts=[],
            manifest={},
        )
        async with factory() as session:
            derive_jobs = list(
                (
                    await session.scalars(
                        select(Job).where(
                            Job.tenant_id == tenant_id,
                            Job.job_type == "DERIVE_BROWSER_EVENTS",
                        )
                    )
                ).all()
            )
            diagnostic_run = await session.scalar(
                select(CheckpointRun).where(CheckpointRun.id == diagnostic_id)
            )
        assert derive_jobs == []
        assert diagnostic_run is not None
        assert diagnostic_run.observation_kind == "DIAGNOSTIC"
        assert diagnostic_run.trigger_source == "OPERATOR_CLI"
        assert diagnostic_run.trigger_correlation_id == original_correlation_seed

        # Window aggregation cannot mix kinds: the (window, url, scenario)
        # uniqueness constraint already prevents a diagnostic run from sharing
        # a scheduled window for the same URL. Derivation must additionally
        # fail closed when recorded lineage points at non-scheduled evidence.
        event_repository = EventRepository(factory)
        lineage_run_id = uuid.uuid4()
        async with factory() as session, session.begin():
            lineage_window = uuid.uuid4()
            session.add(
                CheckpointWindow(
                    id=lineage_window,
                    tenant_id=tenant_id,
                    site_id=site.id,
                    scheduled_for=base_time + timedelta(days=2),
                    window_start=base_time + timedelta(days=2),
                    window_end=base_time + timedelta(days=2, minutes=30),
                )
            )
            await session.flush()
            session.add(
                CheckpointRun(
                    id=lineage_run_id,
                    tenant_id=tenant_id,
                    site_id=site.id,
                    checkpoint_window_id=lineage_window,
                    monitored_url_id=monitored_url.id,
                    template_id=template.id,
                    scenario_id=scenario.id,
                    observation_kind="SCHEDULED",
                    scheduled_for=base_time + timedelta(days=2),
                    started_at=base_time + timedelta(days=2),
                    completed_at=base_time + timedelta(days=2, minutes=5),
                    status="COMPLETE",
                    attempt_count=1,
                    collector_bundle_version="b8-v1",
                    environment={"is_mobile": False},
                    limitations=[],
                    manifest={
                        "comparison_lineage": {
                            "previous_checkpoint_run_id": str(diagnostic_id),
                            "selection_scope": "EXACT_MONITORED_URL",
                        }
                    },
                )
            )

        with pytest.raises(EventStateError):
            await event_repository.load_input(tenant_id=tenant_id, checkpoint_run_id=diagnostic_id)

        # A scheduled run whose recorded lineage points at non-scheduled
        # evidence fails closed instead of comparing incompatible cohorts.
        with pytest.raises(EventStateError):
            await event_repository.load_input(tenant_id=tenant_id, checkpoint_run_id=lineage_run_id)
    finally:
        await _cleanup(tenant_id)


@pytest.mark.asyncio
async def test_provenance_is_immutable_through_orm_updates() -> None:
    tenant_id = await _seed_site()
    try:
        factory = get_session_factory()
        async with factory() as session, session.begin():
            site = await session.scalar(select(Site).where(Site.tenant_id == tenant_id))
            scenario = await session.scalar(
                select(BrowserScenario).where(BrowserScenario.tenant_id == tenant_id)
            )
            monitored_url = await session.scalar(
                select(MonitoredUrl).where(MonitoredUrl.tenant_id == tenant_id)
            )
            template = await session.scalar(select(Template).where(Template.tenant_id == tenant_id))
            assert site and scenario and monitored_url and template
            window_id = uuid.uuid4()
            session.add(
                CheckpointWindow(
                    id=window_id,
                    tenant_id=tenant_id,
                    site_id=site.id,
                    scheduled_for=datetime.now(UTC),
                    window_start=datetime.now(UTC),
                    window_end=datetime.now(UTC) + timedelta(minutes=30),
                )
            )
            await session.flush()
            run = CheckpointRun(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                site_id=site.id,
                checkpoint_window_id=window_id,
                monitored_url_id=monitored_url.id,
                template_id=template.id,
                scenario_id=scenario.id,
                observation_kind="DIAGNOSTIC",
                trigger_source="OPERATOR_CLI",
                trigger_correlation_id=uuid.uuid4(),
                scheduled_for=datetime.now(UTC),
                status="PENDING",
                attempt_count=0,
                collector_bundle_version="b8-v1",
                environment={},
                limitations=[],
                manifest={},
            )
            session.add(run)

        correlation = run.trigger_correlation_id
        async with factory() as session:
            loaded = await session.scalar(select(CheckpointRun).where(CheckpointRun.id == run.id))
            assert loaded is not None
            loaded.status = "RUNNING"
            loaded.attempt_count = 1
            loaded.trigger_correlation_id = uuid.uuid4()
            with pytest.raises(RuntimeError, match="immutable"):
                await session.commit()
            await session.rollback()

        async with factory() as session:
            reloaded = await session.scalar(select(CheckpointRun).where(CheckpointRun.id == run.id))
            assert reloaded is not None
            assert reloaded.trigger_correlation_id == correlation
            assert reloaded.status == "PENDING"

        # Assigning an identical value remains harmless.
        async with factory() as session:
            loaded = await session.scalar(select(CheckpointRun).where(CheckpointRun.id == run.id))
            assert loaded is not None
            loaded.status = "RUNNING"
            loaded.trigger_correlation_id = correlation
            await session.commit()
    finally:
        await _cleanup(tenant_id)


def test_downgrade_refuses_while_non_scheduled_runs_exist() -> None:
    from alembic import command
    from alembic.config import Config

    factory = get_session_factory()

    async def seed() -> tuple[uuid.UUID, uuid.UUID]:
        tenant_id = await _seed_site()
        async with factory() as session, session.begin():
            site = await session.scalar(select(Site).where(Site.tenant_id == tenant_id))
            scenario = await session.scalar(
                select(BrowserScenario).where(BrowserScenario.tenant_id == tenant_id)
            )
            monitored_url = await session.scalar(
                select(MonitoredUrl).where(MonitoredUrl.tenant_id == tenant_id)
            )
            template = await session.scalar(select(Template).where(Template.tenant_id == tenant_id))
            assert site and scenario and monitored_url and template
            window_id = uuid.uuid4()
            session.add(
                CheckpointWindow(
                    id=window_id,
                    tenant_id=tenant_id,
                    site_id=site.id,
                    scheduled_for=datetime.now(UTC),
                    window_start=datetime.now(UTC),
                    window_end=datetime.now(UTC) + timedelta(minutes=5),
                )
            )
            await session.flush()
            session.add(
                CheckpointRun(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    site_id=site.id,
                    checkpoint_window_id=window_id,
                    monitored_url_id=monitored_url.id,
                    template_id=template.id,
                    scenario_id=scenario.id,
                    observation_kind="DIAGNOSTIC",
                    trigger_source="OPERATOR_CLI",
                    trigger_correlation_id=uuid.uuid4(),
                    scheduled_for=datetime.now(UTC),
                    status="PENDING",
                    attempt_count=0,
                    collector_bundle_version="b8-v1",
                    environment={},
                    limitations=[],
                    manifest={},
                )
            )
        return tenant_id, window_id

    import asyncio

    tenant_id, _ = asyncio.run(seed())
    try:
        config = Config("alembic.ini")
        # Target the exact revision: relative -1 breaks once newer
        # migrations stack above this one.
        with pytest.raises(Exception, match="non-scheduled checkpoint runs exist"):
            command.downgrade(config, "0016_public_config_events_e3")
    finally:
        # Remove the blocking evidence first, then restore the shared test
        # database to head for the remaining suite.
        config = Config("alembic.ini")
        asyncio.run(_cleanup(tenant_id))
        command.downgrade(config, "base")
        command.upgrade(config, "head")
