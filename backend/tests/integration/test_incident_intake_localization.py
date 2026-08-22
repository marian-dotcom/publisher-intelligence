import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select

from app.browser.models import (
    BrowserScenario,
    CheckpointRun,
    CheckpointWindow,
    MonitoredUrl,
    Publisher,
    Site,
    Template,
)
from app.browser.service import CheckpointService
from app.common.comparability import evidence_fingerprints
from app.config.settings import get_settings
from app.db.models import Job, Tenant
from app.db.session import get_session_factory
from app.incidents.intake import IncidentIntakeService, investigation_key_for
from app.incidents.models import (
    InvestigationUsageEntry,
    LastKnownGoodRef,
)
from app.incidents.persistence import InvestigationRepository
from app.jobs.queue import JobQueue

pytestmark = pytest.mark.integration


async def _seed_site() -> tuple[uuid.UUID, uuid.UUID]:
    factory = get_session_factory()
    tenant_id, publisher_id = uuid.uuid4(), uuid.uuid4()
    site_id, template_id = uuid.uuid4(), uuid.uuid4()
    monitored_url_id, scenario_id = uuid.uuid4(), uuid.uuid4()
    async with factory() as session, session.begin():
        session.add(Tenant(id=tenant_id, slug=f"intk-{tenant_id.hex[:10]}", name="Intake Tenant"))
        await session.flush()
        session.add(
            Publisher(
                id=publisher_id,
                tenant_id=tenant_id,
                name="Intake Publisher",
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
                name="Intake Site",
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
        await session.execute(
            delete(InvestigationUsageEntry).where(InvestigationUsageEntry.tenant_id == tenant_id)
        )
        from app.incidents.models import LastKnownGoodRef, RetentionHold

        await session.execute(
            delete(LastKnownGoodRef).where(LastKnownGoodRef.tenant_id == tenant_id)
        )
        await session.execute(delete(RetentionHold).where(RetentionHold.tenant_id == tenant_id))
        await session.execute(delete(CheckpointRun).where(CheckpointRun.tenant_id == tenant_id))
        await session.execute(
            delete(CheckpointWindow).where(CheckpointWindow.tenant_id == tenant_id)
        )
        from app.incidents.models import (
            Incident as IncidentModel,
        )
        from app.incidents.models import (
            IncidentSymptomSegment as SegmentModel,
        )
        from app.incidents.models import (
            InvestigationUsageEntry as UsageModel,
        )
        from app.incidents.models import (
            LastKnownGoodRef as LkgModel,
        )
        from app.incidents.models import (
            RetentionHold as HoldModel,
        )

        await session.execute(delete(UsageModel).where(UsageModel.tenant_id == tenant_id))
        await session.execute(delete(LkgModel).where(LkgModel.tenant_id == tenant_id))
        await session.execute(delete(HoldModel).where(HoldModel.tenant_id == tenant_id))
        await session.execute(delete(SegmentModel).where(SegmentModel.tenant_id == tenant_id))
        await session.execute(delete(IncidentModel).where(IncidentModel.tenant_id == tenant_id))
        await session.execute(delete(BrowserScenario).where(BrowserScenario.tenant_id == tenant_id))
        await session.execute(delete(MonitoredUrl).where(MonitoredUrl.tenant_id == tenant_id))
        await session.execute(delete(Template).where(Template.tenant_id == tenant_id))
        await session.execute(delete(Site).where(Site.tenant_id == tenant_id))
        await session.execute(delete(Publisher).where(Publisher.tenant_id == tenant_id))
        await session.execute(delete(Tenant).where(Tenant.id == tenant_id))


def _service() -> tuple[IncidentIntakeService, InvestigationRepository]:
    settings = get_settings()
    factory = get_session_factory()
    repository = InvestigationRepository(factory)
    checkpoints = CheckpointService(factory, JobQueue(factory), settings)
    return (
        IncidentIntakeService(
            repository=repository,
            checkpoint_service=checkpoints,
            session_factory=factory,
        ),
        repository,
    )


@pytest.mark.asyncio
async def test_open_investigation_persists_incident_segments_and_key() -> None:
    tenant_id, site_id = await _seed_site()
    intake, repository = _service()
    try:
        async with get_session_factory()() as session, session.begin():
            site = await session.scalar(select(Site).where(Site.id == site_id))
            assert site is not None
        incident, key = await intake.open_investigation(
            tenant_id=tenant_id,
            publisher_id=site.publisher_id,
            site_id=site_id,
            title="Ads stopped serving on mobile",
            symptom_family="GAM_ADSERVING",
            description="GAM requests fell to zero on mobile templates.",
            reported_start_at=datetime(2026, 8, 20, 6, tzinfo=UTC),
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
        assert key == investigation_key_for(incident.id)
        loaded = await repository.get_incident(tenant_id=tenant_id, incident_id=incident.id)
        assert loaded.description.startswith("GAM requests")
        assert loaded.status == "OPEN"

        with pytest.raises(Exception, match="end precedes start"):
            await intake.open_investigation(
                tenant_id=tenant_id,
                publisher_id=site.publisher_id,
                site_id=site_id,
                title="Bad window",
                symptom_family="OTHER",
                description="x",
                reported_start_at=datetime(2026, 8, 21, tzinfo=UTC),
                reported_end_at=datetime(2026, 8, 20, tzinfo=UTC),
            )

        other_tenant = uuid.uuid4()
        with pytest.raises(Exception, match="tenant"):
            await repository.get_incident(tenant_id=other_tenant, incident_id=incident.id)
    finally:
        await _cleanup(tenant_id)


@pytest.mark.asyncio
async def test_localization_anchors_on_last_healthy_and_freezes_lkg() -> None:
    tenant_id, site_id = await _seed_site()
    intake, _repository = _service()
    try:
        factory = get_session_factory()
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
            onset = datetime(2026, 8, 21, 12, tzinfo=UTC)

            async def add_run(run_id: uuid.UUID, when: datetime, *, status: str) -> None:
                window_id = uuid.uuid4()
                session.add(
                    CheckpointWindow(
                        id=window_id,
                        tenant_id=tenant_id,
                        site_id=site.id,
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
                        site_id=site.id,
                        checkpoint_window_id=window_id,
                        monitored_url_id=monitored_url.id,
                        template_id=template.id,
                        scenario_id=scenario.id,
                        observation_kind="SCHEDULED",
                        scheduled_for=when,
                        started_at=when,
                        completed_at=when + timedelta(minutes=5),
                        status=status,
                        attempt_count=1,
                        collector_bundle_version="b8-v1",
                        environment={"is_mobile": False},
                        limitations=[],
                        manifest={},
                    )
                )

            healthy_id = uuid.uuid4()
            await add_run(healthy_id, onset - timedelta(hours=6), status="COMPLETE")
            await add_run(uuid.uuid4(), onset + timedelta(minutes=30), status="SITE_ERROR")

        incident, key = await intake.open_investigation(
            tenant_id=tenant_id,
            publisher_id=site.publisher_id,
            site_id=site_id,
            title="Search visibility dropped",
            symptom_family="SEARCH_DISCOVER",
            description="Impressions collapsed.",
            reported_start_at=onset,
        )
        result = await intake.localize(
            tenant_id=tenant_id,
            incident_id=incident.id,
            expected_fingerprints=evidence_fingerprints({"collector_bundle": "b8-v1"}),
        )
        assert result.last_healthy_run_id == healthy_id
        assert result.first_anomaly_at is not None
        assert result.lkg_frozen is True
        assert key == result.investigation_key

        async with factory() as session:
            refs = list(
                (
                    await session.scalars(
                        select(LastKnownGoodRef).where(LastKnownGoodRef.tenant_id == tenant_id)
                    )
                ).all()
            )
        assert len(refs) == 1
        assert refs[0].valid_for_incident_id == incident.id
        assert refs[0].checkpoint_run_id == healthy_id
    finally:
        await _cleanup(tenant_id)


@pytest.mark.asyncio
async def test_initial_diagnostics_are_bounded_provenanced_and_isolated() -> None:
    tenant_id, site_id = await _seed_site()
    intake, repository = _service()
    try:
        factory = get_session_factory()
        async with factory() as session, session.begin():
            site = await session.scalar(select(Site).where(Site.id == site_id))
            assert site is not None
        incident, key = await intake.open_investigation(
            tenant_id=tenant_id,
            publisher_id=site.publisher_id,
            site_id=site_id,
            title="Mobile ads missing",
            symptom_family="GAM_ADSERVING",
            description="No GAM requests on mobile.",
        )

        grants = await intake.request_initial_diagnostics(
            tenant_id=tenant_id,
            incident_id=incident.id,
            max_scenarios=2,
        )
        assert len(grants) >= 1

        async with factory() as session:
            runs = list(
                (
                    await session.scalars(
                        select(CheckpointRun).where(CheckpointRun.tenant_id == tenant_id)
                    )
                ).all()
            )
            jobs = list(
                (await session.scalars(select(Job).where(Job.tenant_id == tenant_id))).all()
            )
        assert {run.observation_kind for run in runs} == {"INCIDENT_DIAGNOSTIC"}
        assert {run.trigger_source for run in runs} == {"INCIDENT"}
        assert {run.trigger_correlation_id for run in runs} == {incident.id}
        assert {job.job_type for job in jobs} == {"BROWSER_CHECKPOINT"}

        used = await repository.current_usage(
            tenant_id=tenant_id,
            investigation_key=key,
            resource_kind="DIAGNOSTIC_RUN",
        )
        assert used == len(grants)

        # Exhaust the remaining budget; the next request must be refused and
        # must create no further runs or jobs.
        while repository.within_limit(resource_kind="DIAGNOSTIC_RUN", used=used):
            used += 1
        overflow_entries = [{"usage_key": f"filler-{index}"} for index in range(len(grants), used)]
        async with factory() as session, session.begin():
            site_row = await session.scalar(select(Site).where(Site.id == site_id))
            assert site_row is not None
            for entry in overflow_entries:
                session.add(
                    InvestigationUsageEntry(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        incident_id=incident.id,
                        investigation_key=key,
                        resource_kind="DIAGNOSTIC_RUN",
                        amount=1,
                        usage_key=entry["usage_key"],
                        occurred_at=datetime.now(UTC),
                    )
                )

        with pytest.raises(Exception, match="budget exhausted"):
            await intake.request_initial_diagnostics(
                tenant_id=tenant_id,
                incident_id=incident.id,
                max_scenarios=2,
            )
        async with factory() as session:
            run_count = len(
                (
                    await session.scalars(
                        select(CheckpointRun).where(CheckpointRun.tenant_id == tenant_id)
                    )
                ).all()
            )
            job_count = len(
                (await session.scalars(select(Job).where(Job.tenant_id == tenant_id))).all()
            )
        assert run_count == len(runs)
        assert job_count == len(jobs)
    finally:
        await _cleanup(tenant_id)
