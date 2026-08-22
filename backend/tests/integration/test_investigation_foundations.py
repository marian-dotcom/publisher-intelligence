import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.browser.models import (
    BrowserScenario,
    CheckpointRun,
    CheckpointWindow,
    MonitoredUrl,
    Publisher,
    Site,
    Template,
)
from app.common.comparability import evidence_fingerprints, fingerprints_comparable
from app.db.models import Job, Tenant
from app.db.session import get_session_factory
from app.events.models import Event, EventEvidenceRef
from app.incidents.contracts import InvestigationStateError
from app.incidents.models import (
    Incident,
    IncidentSymptomSegment,
    InvestigationUsageEntry,
    LastKnownGoodRef,
    RetentionHold,
)
from app.incidents.persistence import InvestigationRepository

pytestmark = pytest.mark.integration

FINGERPRINTS = evidence_fingerprints({"collector_bundle": "b8-v1", "robots": "robots-rfc9309-v1"})


async def _seed_site() -> tuple[uuid.UUID, uuid.UUID]:
    factory = get_session_factory()
    tenant_id, publisher_id = uuid.uuid4(), uuid.uuid4()
    site_id, template_id = uuid.uuid4(), uuid.uuid4()
    monitored_url_id, scenario_id = uuid.uuid4(), uuid.uuid4()
    async with factory() as session, session.begin():
        session.add(Tenant(id=tenant_id, slug=f"inv-{tenant_id.hex[:10]}", name="Inv Tenant"))
        await session.flush()
        session.add(
            Publisher(
                id=publisher_id,
                tenant_id=tenant_id,
                name="Inv Publisher",
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
                name="Inv Site",
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
    return tenant_id, site_id


async def _cleanup(tenant_id: uuid.UUID) -> None:
    factory = get_session_factory()
    async with factory() as session, session.begin():
        await session.execute(delete(Job).where(Job.tenant_id == tenant_id))
        await session.execute(delete(RetentionHold).where(RetentionHold.tenant_id == tenant_id))
        await session.execute(
            delete(InvestigationUsageEntry).where(InvestigationUsageEntry.tenant_id == tenant_id)
        )
        await session.execute(
            delete(LastKnownGoodRef).where(LastKnownGoodRef.tenant_id == tenant_id)
        )
        await session.execute(
            delete(IncidentSymptomSegment).where(IncidentSymptomSegment.tenant_id == tenant_id)
        )
        await session.execute(delete(Incident).where(Incident.tenant_id == tenant_id))
        await session.execute(
            delete(EventEvidenceRef).where(EventEvidenceRef.tenant_id == tenant_id)
        )
        await session.execute(delete(Event).where(Event.tenant_id == tenant_id))
        await session.execute(delete(CheckpointRun).where(CheckpointRun.tenant_id == tenant_id))
        await session.execute(
            delete(CheckpointWindow).where(CheckpointWindow.tenant_id == tenant_id)
        )
        await session.execute(delete(BrowserScenario).where(BrowserScenario.tenant_id == tenant_id))
        await session.execute(delete(MonitoredUrl).where(MonitoredUrl.tenant_id == tenant_id))
        await session.execute(delete(Template).where(Template.tenant_id == tenant_id))
        await session.execute(delete(Site).where(Site.tenant_id == tenant_id))
        await session.execute(delete(Publisher).where(Publisher.tenant_id == tenant_id))
        await session.execute(delete(Tenant).where(Tenant.id == tenant_id))


@pytest.mark.asyncio
async def test_incident_creation_with_segments_roundtrips() -> None:
    tenant_id, site_id = await _seed_site()
    try:
        factory = get_session_factory()
        async with factory() as session, session.begin():
            site = await session.scalar(select(Site).where(Site.id == site_id))
            assert site is not None
        repository = InvestigationRepository(factory)
        created = await repository.create_incident(
            tenant_id=tenant_id,
            publisher_id=site.publisher_id,
            site_id=site_id,
            title="Revenue dropped",
            symptom_family="GAM_ADSERVING",
            description="Ad revenue fell sharply since Tuesday.",
            reported_start_at=datetime(2026, 8, 19, tzinfo=UTC),
            severity="HIGH",
            segments=(
                {
                    "dimension": "device",
                    "operator": "=",
                    "value": "mobile",
                    "source": "operator",
                },
            ),
        )
        loaded = await repository.get_incident(tenant_id=tenant_id, incident_id=created.id)
        assert loaded.status == "OPEN"
        async with factory() as session:
            segments = list(
                (
                    await session.scalars(
                        select(IncidentSymptomSegment).where(
                            IncidentSymptomSegment.incident_id == created.id
                        )
                    )
                ).all()
            )
        assert len(segments) == 1
        assert segments[0].dimension == "device"

        other_tenant = uuid.uuid4()
        with pytest.raises(InvestigationStateError, match="tenant"):
            await repository.get_incident(tenant_id=other_tenant, incident_id=created.id)
    finally:
        await _cleanup(tenant_id)


@pytest.mark.asyncio
async def test_incident_vocabulary_violations_rejected_by_database() -> None:
    tenant_id, site_id = await _seed_site()
    try:
        factory = get_session_factory()
        async with factory() as session, session.begin():
            site = await session.scalar(select(Site).where(Site.id == site_id))
            assert site is not None

        bad_rows: list[dict[str, object]] = [
            {"symptom_family": "NOT_A_FAMILY"},
            {"status": "MAGIC_STATUS"},
            {"severity": "EXTREME"},
        ]
        for overrides in bad_rows:
            async with factory() as session, session.begin():
                site_row = await session.scalar(select(Site).where(Site.id == site_id))
                assert site_row is not None
                values: dict[str, object] = {
                    "id": uuid.uuid4(),
                    "tenant_id": tenant_id,
                    "publisher_id": site_row.publisher_id,
                    "site_id": site_id,
                    "title": "Bad row",
                    "symptom_family": "OTHER",
                    "description": "constraint probe",
                    "opened_at": datetime.now(UTC),
                    "status": "OPEN",
                }
                values.update(overrides)
                session.add(Incident(**values))
                with pytest.raises(IntegrityError):
                    await session.commit()
    finally:
        await _cleanup(tenant_id)


@pytest.mark.asyncio
async def test_budget_ledger_is_idempotent_and_scoped() -> None:
    tenant_id, _unused_site = await _seed_site()
    try:
        factory = get_session_factory()
        repository = InvestigationRepository(factory)

        first = await repository.consume_budget(
            tenant_id=tenant_id,
            investigation_key="inv-abc",
            resource_kind="DRILLDOWN",
            correlation_id="request-1",
        )
        duplicate = await repository.consume_budget(
            tenant_id=tenant_id,
            investigation_key="inv-abc",
            resource_kind="DRILLDOWN",
            correlation_id="request-1",
        )
        assert first.usage_key == duplicate.usage_key
        await repository.consume_budget(
            tenant_id=tenant_id,
            investigation_key="inv-abc",
            resource_kind="DRILLDOWN",
            correlation_id="request-2",
        )

        used = await repository.current_usage(
            tenant_id=tenant_id,
            investigation_key="inv-abc",
            resource_kind="DRILLDOWN",
        )
        assert used == 2

        other_tenant = uuid.uuid4()
        assert (
            await repository.current_usage(
                tenant_id=other_tenant,
                investigation_key="inv-abc",
                resource_kind="DRILLDOWN",
            )
            == 0
        )

        with pytest.raises(InvestigationStateError):
            await repository.consume_budget(
                tenant_id=tenant_id,
                investigation_key="inv-abc",
                resource_kind="MYSTERY",
                correlation_id="request-3",
            )

        assert repository.within_limit(resource_kind="DRILLDOWN", used=2)
        assert not repository.within_limit(resource_kind="DRILLDOWN", used=4)
    finally:
        await _cleanup(tenant_id)


@pytest.mark.asyncio
async def test_retention_hold_lifecycle_is_auditable_and_idempotent() -> None:
    tenant_id, site_id = await _seed_site()
    try:
        factory = get_session_factory()
        repository = InvestigationRepository(factory)
        async with factory() as session, session.begin():
            site_row = await session.scalar(select(Site).where(Site.id == site_id))
            assert site_row is not None
            incident_target = uuid.uuid4()
            session.add(
                Incident(
                    id=incident_target,
                    tenant_id=tenant_id,
                    publisher_id=site_row.publisher_id,
                    site_id=site_id,
                    title="Hold target",
                    symptom_family="OTHER",
                    description="pinned evidence source",
                    opened_at=datetime.now(UTC),
                    status="OPEN",
                )
            )
            await session.flush()

        hold = await repository.create_retention_hold(
            tenant_id=tenant_id,
            reason="incident evidence pinning",
            incident_id=incident_target,
        )
        duplicate = await repository.create_retention_hold(
            tenant_id=tenant_id,
            reason="incident evidence pinning",
            incident_id=incident_target,
        )
        assert hold.id == duplicate.id

        active = await repository.active_holds_for_tenant(tenant_id=tenant_id)
        assert [item.id for item in active] == [hold.id]

        with pytest.raises(InvestigationStateError, match="release actor"):
            await repository.release_retention_hold(
                tenant_id=tenant_id, hold_id=hold.id, released_by="  "
            )

        released = await repository.release_retention_hold(
            tenant_id=tenant_id, hold_id=hold.id, released_by="operator-1"
        )
        assert released.released_by == "operator-1"
        assert released.released_at is not None

        assert await repository.active_holds_for_tenant(tenant_id=tenant_id) == ()

        with pytest.raises(InvestigationStateError, match="already released"):
            await repository.release_retention_hold(
                tenant_id=tenant_id, hold_id=hold.id, released_by="operator-2"
            )

        with pytest.raises(InvestigationStateError, match="at least one target"):
            await repository.create_retention_hold(
                tenant_id=tenant_id, reason="no target", artifact_id=None
            )
    finally:
        await _cleanup(tenant_id)


@pytest.mark.asyncio
async def test_lkg_selection_honours_kinds_and_fingerprints_and_freezes() -> None:
    tenant_id, site_id = await _seed_site()
    try:
        factory = get_session_factory()
        repository = InvestigationRepository(factory)
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
            base_time = datetime(2026, 8, 22, 6, tzinfo=UTC)
            canonical_window = uuid.uuid4()
            diagnostic_window = uuid.uuid4()
            session.add_all(
                [
                    CheckpointWindow(
                        id=canonical_window,
                        tenant_id=tenant_id,
                        site_id=site.id,
                        scheduled_for=base_time,
                        window_start=base_time,
                        window_end=base_time + timedelta(minutes=30),
                    ),
                    CheckpointWindow(
                        id=diagnostic_window,
                        tenant_id=tenant_id,
                        site_id=site.id,
                        scheduled_for=base_time + timedelta(days=1),
                        window_start=base_time + timedelta(days=1),
                        window_end=base_time + timedelta(days=1, minutes=5),
                    ),
                ]
            )
            await session.flush()

            def add_run(
                run_id: uuid.UUID,
                window_id: uuid.UUID,
                kind: str,
                when: datetime,
                *,
                collector: str = "b8-v1",
                status: str = "COMPLETE",
            ) -> None:
                session.add(
                    CheckpointRun(
                        id=run_id,
                        tenant_id=tenant_id,
                        site_id=site.id,
                        checkpoint_window_id=window_id,
                        monitored_url_id=monitored_url.id,
                        template_id=template.id,
                        scenario_id=scenario.id,
                        observation_kind=kind,
                        trigger_source=None if kind == "SCHEDULED" else "OPERATOR_CLI",
                        trigger_correlation_id=(uuid.uuid4() if kind != "SCHEDULED" else None),
                        scheduled_for=when,
                        started_at=when,
                        completed_at=when + timedelta(minutes=5),
                        status=status,
                        attempt_count=1,
                        collector_bundle_version=collector,
                        environment={"is_mobile": False},
                        limitations=[],
                        manifest={},
                    )
                )

            eligible_a, diagnostic_run, wrong_collector = (
                uuid.uuid4(),
                uuid.uuid4(),
                uuid.uuid4(),
            )
            wrong_collector_window = uuid.uuid4()
            add_run(eligible_a, canonical_window, "SCHEDULED", base_time)
            add_run(
                diagnostic_run,
                diagnostic_window,
                "DIAGNOSTIC",
                base_time + timedelta(days=1),
            )
            session.add(
                CheckpointWindow(
                    id=wrong_collector_window,
                    tenant_id=tenant_id,
                    site_id=site.id,
                    scheduled_for=base_time - timedelta(days=1),
                    window_start=base_time - timedelta(days=1),
                    window_end=base_time - timedelta(days=1, minutes=-30),
                )
            )
            await session.flush()
            add_run(
                wrong_collector,
                wrong_collector_window,
                "SCHEDULED",
                base_time - timedelta(days=1),
                collector="b9-v1",
            )

        selected = await repository.select_eligible_lkg_run(
            tenant_id=tenant_id,
            site_id=site_id,
            scope_key=f"{site_id}:desktop",
            expected_fingerprints=FINGERPRINTS,
            scenario_id=scenario.id,
            template_id=template.id,
        )
        assert selected is not None
        assert selected.id == eligible_a

        frozen = await repository.freeze_lkg_selection(
            tenant_id=tenant_id,
            site_id=site_id,
            scope_key=f"{site_id}:desktop",
            checkpoint_run_id=selected.id,
            fingerprints=FINGERPRINTS,
            selection_method="LATEST_HEALTHY_SCHEDULED",
            reason="baseline before reported onset",
            template_id=template.id,
            scenario_id=scenario.id,
        )
        frozen_again = await repository.freeze_lkg_selection(
            tenant_id=tenant_id,
            site_id=site_id,
            scope_key=f"{site_id}:desktop",
            checkpoint_run_id=selected.id,
            fingerprints=FINGERPRINTS,
            selection_method="LATEST_HEALTHY_SCHEDULED",
            reason="baseline before reported onset",
            template_id=template.id,
            scenario_id=scenario.id,
        )
        assert frozen.id == frozen_again.id
        assert frozen.fingerprints["collector_bundle"] == "b8-v1"
        assert frozen.selection_version == "lkg-v1"

        async with factory() as session:
            loaded = await session.scalar(
                select(LastKnownGoodRef).where(LastKnownGoodRef.id == frozen.id)
            )
            assert loaded is not None
            loaded.reason = "tampered"
            with pytest.raises(RuntimeError, match="immutable"):
                await session.commit()
            await session.rollback()
    finally:
        await _cleanup(tenant_id)


@pytest.mark.asyncio
async def test_fingerprint_mismatch_and_status_exclude_candidates() -> None:
    tenant_id, site_id = await _seed_site()
    try:
        factory = get_session_factory()
        repository = InvestigationRepository(factory)
        async with factory() as session, session.begin():
            scenario = await session.scalar(
                select(BrowserScenario).where(BrowserScenario.tenant_id == tenant_id)
            )
            assert scenario is not None
            base_time = datetime(2026, 8, 22, 12, tzinfo=UTC)
            window_id = uuid.uuid4()
            session.add(
                CheckpointWindow(
                    id=window_id,
                    tenant_id=tenant_id,
                    site_id=site_id,
                    scheduled_for=base_time,
                    window_start=base_time,
                    window_end=base_time + timedelta(minutes=30),
                )
            )
            await session.flush()
            monitored_url = await session.scalar(
                select(MonitoredUrl).where(MonitoredUrl.tenant_id == tenant_id)
            )
            template = await session.scalar(select(Template).where(Template.tenant_id == tenant_id))
            assert monitored_url and template
            session.add(
                CheckpointRun(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    site_id=site_id,
                    checkpoint_window_id=window_id,
                    monitored_url_id=monitored_url.id,
                    template_id=template.id,
                    scenario_id=scenario.id,
                    observation_kind="SCHEDULED",
                    scheduled_for=base_time,
                    started_at=base_time,
                    completed_at=base_time + timedelta(minutes=5),
                    status="PENDING",
                    attempt_count=1,
                    collector_bundle_version="b8-v1",
                    environment={"is_mobile": False},
                    limitations=[],
                    manifest={},
                )
            )

        selected = await repository.select_eligible_lkg_run(
            tenant_id=tenant_id,
            site_id=site_id,
            scope_key=f"{site_id}:desktop",
            expected_fingerprints=FINGERPRINTS,
            scenario_id=scenario.id,
            template_id=template.id,
        )
        assert selected is None
    finally:
        await _cleanup(tenant_id)


def test_comparability_helper_remains_consistent() -> None:
    snapshot = evidence_fingerprints({"a": "1"})
    assert fingerprints_comparable(snapshot, {"a": "1"})
