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
        monitored_url = await session.scalar(
            select(MonitoredUrl).where(MonitoredUrl.tenant_id == tenant_id)
        )
        template = await session.scalar(select(Template).where(Template.tenant_id == tenant_id))
        scenario = await session.scalar(
            select(BrowserScenario).where(BrowserScenario.tenant_id == tenant_id)
        )
        assert monitored_url and template and scenario
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


async def add_bounded_event(
    tenant_id: uuid.UUID,
    site_id: uuid.UUID,
    *,
    window_start,
    window_end,
) -> uuid.UUID:
    """Event with bounded occurrence interval (WINDOW precision, both bounds set)."""
    factory = get_session_factory()
    event_id = uuid.uuid4()
    when = datetime.now(UTC) - timedelta(hours=1)
    async with factory() as session, session.begin():
        monitored_url_id, template_id, scenario_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
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
