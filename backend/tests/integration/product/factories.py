"""Minimal product seed helpers for P2-B validation (one responsibility each)."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.auth.models import Operator, OperatorTenant
from app.auth.security import hash_password
from app.browser.models import (
    BrowserScenario,
    CheckpointRun,
    CheckpointWindow,
    MonitoredUrl,
    Publisher,
    Site,
    Template,
)
from app.db.models import Tenant
from app.db.session import get_session_factory
from app.events.models import Event
from app.events.registry import definition_id
from app.evidence.models import ManualNote
from app.incidents.models import Incident


async def create_tenant(slug: str) -> uuid.UUID:
    factory = get_session_factory()
    tenant_id = uuid.uuid4()
    async with factory() as session, session.begin():
        session.add(Tenant(id=tenant_id, slug=slug, name=slug))
    return tenant_id


async def create_operator(tenant_id: uuid.UUID, email: str) -> tuple[uuid.UUID, str]:
    factory = get_session_factory()
    operator_id = uuid.uuid4()
    async with factory() as session, session.begin():
        session.add(
            Operator(
                id=operator_id,
                actor_subject_id=uuid.uuid4(),
                email=email,
                password_hash=hash_password("correct-horse-battery"),
                role="OPERATOR",
                is_active=True,
            )
        )
        await session.flush()
        session.add(OperatorTenant(operator_id=operator_id, tenant_id=tenant_id))
    return operator_id, email


async def create_site(tenant_id: uuid.UUID) -> uuid.UUID:
    factory = get_session_factory()
    publisher_id, site_id = uuid.uuid4(), uuid.uuid4()
    async with factory() as session, session.begin():
        session.add(
            Publisher(
                id=publisher_id,
                tenant_id=tenant_id,
                name=f"pub-{publisher_id.hex[:8]}",
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
                name=f"site-{site_id.hex[:8]}",
                canonical_domain=f"{site_id.hex}.example.com",
                canonical_scheme="https",
                timezone="UTC",
                status="ACTIVE",
            )
        )
    return site_id


async def add_scheduled_event(tenant_id: uuid.UUID, site_id: uuid.UUID) -> uuid.UUID:
    """Minimum canonical chain: window/run prerequisites + deterministic event."""
    factory = get_session_factory()
    async with factory() as session, session.begin():
        site = await session.scalar(select(Site).where(Site.id == site_id))
        assert site is not None
        monitored_url_id, scenario_id, template_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
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
        when = datetime.now(UTC) - timedelta(hours=1)
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
        run_id = uuid.uuid4()
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
        await session.flush()
        event_id = uuid.uuid4()
        session.add(
            Event(
                id=event_id,
                tenant_id=tenant_id,
                site_id=site_id,
                event_definition_id=definition_id("NOINDEX_ADDED"),
                template_id=None,
                started_at=when,
                occurred_after_at=None,
                occurred_before_at=when,
                time_precision="WINDOW",
                detected_at=when + timedelta(minutes=5),
                severity="MEDIUM",
                observation_confidence="HIGH",
                status="RECORDED",
                source_kind="BROWSER_CHECKPOINT",
                source_version="e3-v1",
                condition_key=None,
                scope={"config_type": "ROBOTS_TXT"},
                summary="P2-B seed event",
                details={},
            )
        )
    return event_id


async def create_manual_note(tenant_id: uuid.UUID, site_id: uuid.UUID, note_text: str) -> uuid.UUID:
    factory = get_session_factory()
    note_id = uuid.uuid4()
    async with factory() as session, session.begin():
        session.add(
            ManualNote(
                id=note_id,
                tenant_id=tenant_id,
                site_id=site_id,
                incident_id=None,
                note_type="OTHER",
                note_text=note_text,
                source="operator",
            )
        )
    return note_id


async def add_exact_event(tenant_id: uuid.UUID, site_id: uuid.UUID) -> uuid.UUID:
    """Event with canonical exact occurrence time (time_precision=EXACT)."""
    factory = get_session_factory()
    event_id = uuid.uuid4()
    occurred_at = datetime(2026, 8, 21, 14, 30, tzinfo=UTC)
    async with factory() as session, session.begin():
        site = await session.scalar(select(Site).where(Site.id == site_id))
        assert site is not None
        monitored_url_id = uuid.uuid4()
        template_id = uuid.uuid4()
        _scenario_id_unused = uuid.uuid4()
        session.add(
            Template(
                id=template_id,
                tenant_id=tenant_id,
                site_id=site_id,
                code="exact",
                display_name="Exact",
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
                url=f"https://{site_id.hex}.example.com/exact",
                status="ACTIVE",
            )
        )
        scenario_id2 = uuid.uuid4()
        session.add(
            BrowserScenario(
                id=scenario_id2,
                tenant_id=tenant_id,
                site_id=site_id,
                code=f"core_desktop_{scenario_id2.hex[:6]}",
                version=1,
                status="ACTIVE",
            )
        )
        window_id = uuid.uuid4()
        when = datetime.now(UTC) - timedelta(hours=1)
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
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                site_id=site_id,
                checkpoint_window_id=window_id,
                monitored_url_id=monitored_url_id,
                template_id=template_id,
                scenario_id=scenario_id2,
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
        await session.flush()
        session.add(
            Event(
                id=event_id,
                tenant_id=tenant_id,
                site_id=site_id,
                event_definition_id=definition_id("NOINDEX_ADDED"),
                template_id=None,
                started_at=occurred_at,
                occurred_after_at=None,
                occurred_before_at=occurred_at,
                time_precision="EXACT",
                detected_at=occurred_at + timedelta(minutes=5),
                severity="MEDIUM",
                observation_confidence="HIGH",
                status="RECORDED",
                source_kind="BROWSER_CHECKPOINT",
                source_version="e3-v1",
                condition_key=None,
                scope={"config_type": "ROBOTS_TXT"},
                summary="P2-B exact-occurrence fixture event",
                details={},
            )
        )
    return event_id


async def add_bounded_event(
    tenant_id: uuid.UUID,
    site_id: uuid.UUID,
    *,
    window_start: datetime,
    window_end: datetime,
) -> uuid.UUID:
    """Event with bounded occurrence interval (both after/before set, WINDOW precision)."""
    factory = get_session_factory()
    event_id = uuid.uuid4()
    async with factory() as session, session.begin():
        monitored_url_id = uuid.uuid4()
        template_id = uuid.uuid4()
        scenario_id = uuid.uuid4()
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
        window_id = uuid.uuid4()
        when = datetime.now(UTC) - timedelta(hours=1)
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
            Event(
                id=event_id,
                tenant_id=tenant_id,
                site_id=site_id,
                event_definition_id=definition_id("NOINDEX_ADDED"),
                template_id=None,
                started_at=when,
                occurred_after_at=window_start,
                occurred_before_at=window_end,
                time_precision="WINDOW",
                detected_at=when + timedelta(minutes=5),
                severity="MEDIUM",
                observation_confidence="HIGH",
                status="RECORDED",
                source_kind="BROWSER_CHECKPOINT",
                source_version="e3-v1",
                condition_key=None,
                scope={"config_type": "ROBOTS_TXT"},
                summary="P2-B bounded-window fixture event",
                details={},
            )
        )
    return event_id


async def add_event_with_internal_details(tenant_id: uuid.UUID, site_id: uuid.UUID) -> uuid.UUID:
    """Event with populated internal details/metadata for leakage testing."""
    factory = get_session_factory()
    event_id = uuid.uuid4()
    when = datetime(2026, 8, 22, 12, tzinfo=UTC)
    monitored_url_id, template_id = uuid.uuid4(), uuid.uuid4()
    async with factory() as session, session.begin():
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
            Event(
                id=event_id,
                tenant_id=tenant_id,
                site_id=site_id,
                event_definition_id=definition_id("NOINDEX_ADDED"),
                template_id=None,
                started_at=when,
                occurred_after_at=None,
                occurred_before_at=when,
                time_precision="WINDOW",
                detected_at=when + timedelta(minutes=5),
                severity="MEDIUM",
                observation_confidence="HIGH",
                status="RECORDED",
                source_kind="BROWSER_CHECKPOINT",
                source_version="e3-v1",
                condition_key=None,
                scope={"config_type": "ROBOTS_TXT"},
                summary="T9 raw-payload fixture event",
                details={
                    "internal_debug": "raw_dom_snapshot_data_here",
                    "session_storage_dump": {"key": "value"},
                    "connector_api_response": {"rows": [1, 2, 3]},
                    "absolute_revenue_eur": 12345.67,
                },
            )
        )
    return event_id


async def create_incident(
    tenant_id: uuid.UUID,
    site_id: uuid.UUID,
    *,
    title: str = "Test incident",
    status: str = "OPEN",
) -> uuid.UUID:
    factory = get_session_factory()
    async with factory() as session, session.begin():
        site = await session.scalar(select(Site).where(Site.id == site_id))
        assert site is not None
        incident_id = uuid.uuid4()
        session.add(
            Incident(
                id=incident_id,
                tenant_id=tenant_id,
                publisher_id=site.publisher_id,
                site_id=site_id,
                title=title,
                symptom_family="GAM_ADSERVING",
                description=f"Description for {title}",
                opened_at=datetime.now(UTC),
                status=status,
            )
        )
    return incident_id


async def seed_diagnostic_event_chain(*, slug: str | None = None) -> dict[str, object]:
    """EP-026 M2b: minimal canonical chain for diagnostic-run → event persistence.

    Creates tenant, publisher/site, template, monitored URL, scenario,
    checkpoint window, and a COMPLETED scheduled baseline run plus a DIAGNOSTIC
    run (trigger_source=INCIDENT, correlation = window-scoped UUID), returning
    the identifiers needed to derive/persist browser-source reliability events.
    """
    from datetime import UTC, datetime, timedelta

    tenant_id, publisher_id, site_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    template_id, monitored_url_id, scenario_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    baseline_window_id, diagnostic_window_id = uuid.uuid4(), uuid.uuid4()
    baseline_run_id, diagnostic_run_id = uuid.uuid4(), uuid.uuid4()
    correlation_id = uuid.uuid4()
    slug = slug or f"m2b-{tenant_id.hex[:8]}"
    when = datetime.now(UTC) - timedelta(hours=2)
    factory = get_session_factory()
    async with factory() as session, session.begin():
        session.add(Tenant(id=tenant_id, slug=slug, name=slug.title()))
        await session.flush()
        session.add(
            Publisher(
                id=publisher_id,
                tenant_id=tenant_id,
                name=f"P {slug}",
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
                name=f"Site {slug}",
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
        session.add(
            CheckpointWindow(
                id=baseline_window_id,
                tenant_id=tenant_id,
                site_id=site_id,
                scheduled_for=when,
                window_start=when,
                window_end=when + timedelta(minutes=30),
            )
        )
        session.add(
            CheckpointWindow(
                id=diagnostic_window_id,
                tenant_id=tenant_id,
                site_id=site_id,
                scheduled_for=when + timedelta(minutes=40),
                window_start=when + timedelta(minutes=40),
                window_end=when + timedelta(hours=1),
            )
        )
        await session.flush()
        common = dict(
            tenant_id=tenant_id,
            site_id=site_id,
            monitored_url_id=monitored_url_id,
            template_id=template_id,
            scenario_id=scenario_id,
            attempt_count=1,
            environment={},
            limitations=[],
            manifest={},
        )
        # Healthy scheduled baseline (the LKG-comparable observation).
        session.add(
            CheckpointRun(
                id=baseline_run_id,
                checkpoint_window_id=baseline_window_id,
                observation_kind="SCHEDULED",
                scheduled_for=when,
                started_at=when,
                completed_at=when + timedelta(minutes=5),
                status="RUNNING",
                collector_bundle_version="b8-v1",
                **common,
            )
        )
        # Degraded diagnostic observation of our own access path.
        session.add(
            CheckpointRun(
                id=diagnostic_run_id,
                checkpoint_window_id=diagnostic_window_id,
                observation_kind="DIAGNOSTIC",
                trigger_source="INCIDENT",
                trigger_correlation_id=correlation_id,
                scheduled_for=when + timedelta(minutes=40),
                started_at=when + timedelta(minutes=41),
                completed_at=when + timedelta(minutes=46),
                status="RUNNING",
                http_status=403,
                final_url=f"https://{site_id.hex}.example.com/a",
                collector_bundle_version="b8-v1",
                **common,
            )
        )
    return {
        "tenant_id": tenant_id,
        "site_id": site_id,
        "baseline_run_id": baseline_run_id,
        "diagnostic_run_id": diagnostic_run_id,
        "correlation_id": correlation_id,
    }
