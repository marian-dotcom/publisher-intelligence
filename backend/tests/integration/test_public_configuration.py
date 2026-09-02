import asyncio
import hashlib
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from sqlalchemy import delete, func, select

from app.browser.models import Publisher, Site, SiteMonitoringStateChange
from app.db.models import Job, Tenant
from app.db.session import get_session_factory
from app.events.models import Event, EventEvidenceRef
from app.events.registry import definition_id
from app.jobs.queue import JobQueue
from app.public_config.client import PublicConfigFetchResult
from app.public_config.contracts import (
    PUBLIC_CONFIG_RULE_VERSION,
    AdsTxtRecordInput,
    PublicConfigRunResult,
    PublicConfigSnapshotInput,
    ads_txt_record_hash,
    public_config_observation_key,
)
from app.public_config.event_persistence import PublicConfigEventRepository
from app.public_config.event_service import PublicConfigEventService
from app.public_config.models import AdsTxtRecord, PublicConfigSnapshot
from app.public_config.persistence import PublicConfigRepository, PublicConfigStateError
from app.public_config.scheduling import (
    PublicConfigSchedulingService,
    resolve_public_config_slot,
)
from app.public_config.service import PublicConfigMonitoringSkippedError, PublicConfigService

pytestmark = pytest.mark.integration


@dataclass(frozen=True, slots=True)
class PublicConfigFixture:
    tenant_id: uuid.UUID
    other_tenant_id: uuid.UUID
    site_id: uuid.UUID


@pytest.fixture
async def public_config_fixture() -> AsyncIterator[PublicConfigFixture]:
    tenant_id, other_tenant_id = uuid.uuid4(), uuid.uuid4()
    publisher_id, site_id = uuid.uuid4(), uuid.uuid4()
    factory = get_session_factory()
    async with factory() as session, session.begin():
        session.add_all(
            [
                Tenant(id=tenant_id, slug=f"public-{tenant_id.hex[:10]}", name="Public Tenant"),
                Tenant(
                    id=other_tenant_id,
                    slug=f"public-other-{other_tenant_id.hex[:10]}",
                    name="Other Public Tenant",
                ),
            ]
        )
        await session.flush()
        session.add(
            Publisher(
                id=publisher_id,
                tenant_id=tenant_id,
                name="Public Publisher",
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
                name="Public Site",
                canonical_domain=f"{site_id.hex}.example.com",
                canonical_scheme="https",
                timezone="UTC",
                status="ACTIVE",
                # EP-030 M2: scheduled public-config fetch/validation is fail-closed
                # by default and PC-GATE-3 pre-flight requires ON. Authorize the
                # fixture site with a deep-past watermark so the fixture's fixed
                # 2026-08-21 due instants are strictly after the enable watermark.
                monitoring_state="ON",
                monitoring_state_updated_at=datetime(2020, 1, 1, tzinfo=UTC),
            )
        )

    yield PublicConfigFixture(tenant_id, other_tenant_id, site_id)

    async with factory() as session, session.begin():
        await session.execute(
            delete(SiteMonitoringStateChange).where(
                SiteMonitoringStateChange.tenant_id == tenant_id
            )
        )
        await session.execute(delete(Job).where(Job.tenant_id == tenant_id))
        await session.execute(
            delete(EventEvidenceRef).where(EventEvidenceRef.tenant_id == tenant_id)
        )
        await session.execute(delete(Event).where(Event.tenant_id == tenant_id))
        await session.execute(delete(AdsTxtRecord).where(AdsTxtRecord.tenant_id == tenant_id))
        await session.execute(
            delete(PublicConfigSnapshot).where(PublicConfigSnapshot.tenant_id == tenant_id)
        )
        await session.execute(delete(Site).where(Site.tenant_id == tenant_id))
        await session.execute(delete(Publisher).where(Publisher.tenant_id == tenant_id))
        await session.execute(delete(Tenant).where(Tenant.id.in_([tenant_id, other_tenant_id])))


async def test_persistence_is_idempotent_and_keeps_immutable_records(
    public_config_fixture: PublicConfigFixture,
) -> None:
    fixture = public_config_fixture
    observed_at = datetime(2026, 8, 21, 12, tzinfo=UTC)
    key = public_config_observation_key(
        tenant_id=fixture.tenant_id,
        site_id=fixture.site_id,
        config_type="ADS_TXT",
        fetch_kind="SCHEDULED",
        source_key=observed_at.isoformat(),
    )
    record = AdsTxtRecordInput(
        advertising_system_domain="example.com",
        publisher_account_id="account-1",
        relationship="DIRECT",
        cert_authority_id=None,
        record_hash=ads_txt_record_hash(
            advertising_system_domain="example.com",
            publisher_account_id="account-1",
            relationship="DIRECT",
            cert_authority_id=None,
        ),
    )
    snapshot = PublicConfigSnapshotInput(
        observation_key=key,
        config_type="ADS_TXT",
        observed_at=observed_at,
        http_status=200,
        content_hash="a" * 64,
        parse_status="VALID",
        normalizer_version="ads-txt-v1",
        summary={"valid_record_count": 1},
    )
    repository = PublicConfigRepository(get_session_factory())

    first, repeated = await asyncio.gather(
        repository.persist_snapshot(
            tenant_id=fixture.tenant_id,
            site_id=fixture.site_id,
            snapshot=snapshot,
            records=(record,),
        ),
        repository.persist_snapshot(
            tenant_id=fixture.tenant_id,
            site_id=fixture.site_id,
            snapshot=snapshot,
            records=(record,),
        ),
    )

    assert first.snapshot_id == repeated.snapshot_id
    assert first.created != repeated.created
    loaded = await repository.load_snapshot(
        tenant_id=fixture.tenant_id,
        site_id=fixture.site_id,
        snapshot_id=first.snapshot_id,
    )
    assert loaded.parse_status == "VALID"
    assert loaded.summary == {"valid_record_count": 1}
    async with get_session_factory()() as session:
        snapshot_count = await session.scalar(
            select(func.count())
            .select_from(PublicConfigSnapshot)
            .where(PublicConfigSnapshot.observation_key == key)
        )
        record_count = await session.scalar(
            select(func.count())
            .select_from(AdsTxtRecord)
            .where(AdsTxtRecord.snapshot_id == first.snapshot_id)
        )
    assert snapshot_count == 1
    assert record_count == 1


async def test_persistence_enforces_ownership_and_validation_lineage(
    public_config_fixture: PublicConfigFixture,
) -> None:
    fixture = public_config_fixture
    repository = PublicConfigRepository(get_session_factory())
    observed_at = datetime(2026, 8, 21, 12, tzinfo=UTC)
    primary = PublicConfigSnapshotInput(
        observation_key=public_config_observation_key(
            tenant_id=fixture.tenant_id,
            site_id=fixture.site_id,
            config_type="ROBOTS_TXT",
            fetch_kind="SCHEDULED",
            source_key=observed_at.isoformat(),
        ),
        config_type="ROBOTS_TXT",
        observed_at=observed_at,
        http_status=200,
        content_hash="b" * 64,
        parse_status="VALID",
        normalizer_version="robots-v1",
        summary={"group_count": 1},
    )
    with pytest.raises(PublicConfigStateError, match="does not belong"):
        await repository.persist_snapshot(
            tenant_id=fixture.other_tenant_id,
            site_id=fixture.site_id,
            snapshot=primary,
        )

    persisted_primary = await repository.persist_snapshot(
        tenant_id=fixture.tenant_id,
        site_id=fixture.site_id,
        snapshot=primary,
    )
    validation = PublicConfigSnapshotInput(
        observation_key=public_config_observation_key(
            tenant_id=fixture.tenant_id,
            site_id=fixture.site_id,
            config_type="ROBOTS_TXT",
            fetch_kind="VALIDATION",
            source_key=str(persisted_primary.snapshot_id),
        ),
        config_type="ROBOTS_TXT",
        observed_at=observed_at + timedelta(seconds=30),
        http_status=200,
        content_hash="b" * 64,
        parse_status="VALID",
        normalizer_version="robots-v1",
        summary={"group_count": 1},
        fetch_kind="VALIDATION",
        validation_of_snapshot_id=persisted_primary.snapshot_id,
    )
    persisted_validation = await repository.persist_snapshot(
        tenant_id=fixture.tenant_id,
        site_id=fixture.site_id,
        snapshot=validation,
    )
    loaded = await repository.load_snapshot(
        tenant_id=fixture.tenant_id,
        site_id=fixture.site_id,
        snapshot_id=persisted_validation.snapshot_id,
    )

    assert loaded.fetch_kind == "VALIDATION"
    assert loaded.validation_of_snapshot_id == persisted_primary.snapshot_id


async def test_previous_snapshot_ignores_validation_and_incompatible_versions(
    public_config_fixture: PublicConfigFixture,
) -> None:
    fixture = public_config_fixture
    repository = PublicConfigRepository(get_session_factory())
    observed_at = datetime(2026, 8, 21, 12, tzinfo=UTC)
    scheduled_ids: list[uuid.UUID] = []
    for index, version in enumerate(("robots-v1", "robots-v2", "robots-v1")):
        timestamp = observed_at + timedelta(hours=index)
        snapshot = PublicConfigSnapshotInput(
            observation_key=public_config_observation_key(
                tenant_id=fixture.tenant_id,
                site_id=fixture.site_id,
                config_type="ROBOTS_TXT",
                fetch_kind="SCHEDULED",
                source_key=timestamp.isoformat(),
            ),
            config_type="ROBOTS_TXT",
            observed_at=timestamp,
            http_status=200,
            content_hash=f"{index + 1}" * 64,
            parse_status="VALID",
            normalizer_version=version,
            summary={"group_count": index + 1},
        )
        result = await repository.persist_snapshot(
            tenant_id=fixture.tenant_id,
            site_id=fixture.site_id,
            snapshot=snapshot,
        )
        scheduled_ids.append(result.snapshot_id)

    previous = await repository.previous_scheduled_snapshot(
        tenant_id=fixture.tenant_id,
        site_id=fixture.site_id,
        config_type="ROBOTS_TXT",
        observed_before=observed_at + timedelta(hours=3),
        normalizer_version="robots-v1",
    )

    assert previous is not None
    assert previous.id == scheduled_ids[2]


class _SequenceClient:
    def __init__(self, contents: list[bytes]) -> None:
        self._contents = contents

    async def fetch(self, **_kwargs: object) -> PublicConfigFetchResult:
        content = self._contents.pop(0)
        return PublicConfigFetchResult(
            url="https://example.com/robots.txt",
            http_status=200,
            content=content,
            content_hash=hashlib.sha256(content).hexdigest(),
            content_type="text/plain",
            redirect_count=0,
        )


class _ResponseSequenceClient:
    def __init__(self, responses: list[tuple[int, bytes]]) -> None:
        self._responses = responses

    async def fetch(self, **_kwargs: object) -> PublicConfigFetchResult:
        status, content = self._responses.pop(0)
        return PublicConfigFetchResult(
            url="https://example.com/ads.txt",
            http_status=status,
            content=content,
            content_hash=hashlib.sha256(content).hexdigest(),
            content_type="text/plain",
            redirect_count=0,
        )


class _MinuteClock:
    def __init__(self) -> None:
        self._current = datetime(2026, 8, 21, tzinfo=UTC)

    def __call__(self) -> datetime:
        current = self._current
        self._current += timedelta(minutes=1)
        return current


async def test_high_risk_transition_queues_and_links_one_validation(
    public_config_fixture: PublicConfigFixture,
) -> None:
    fixture = public_config_fixture
    factory = get_session_factory()
    repository = PublicConfigRepository(factory)
    queue = JobQueue(factory)
    service = PublicConfigService(
        repository,
        queue,
        _SequenceClient(
            [
                b"User-agent: *\nDisallow: /private\n",
                b"User-agent: *\nDisallow: /\n",
                b"User-agent: *\nDisallow: /\n",
            ]
        ),  # type: ignore[arg-type]
        clock=_MinuteClock(),
    )
    await service.run_scheduled(
        tenant_id=fixture.tenant_id,
        site_id=fixture.site_id,
        config_type="ROBOTS_TXT",
        scheduled_for=datetime(2026, 8, 21, tzinfo=UTC),
        attempt=1,
        rule_version=PUBLIC_CONFIG_RULE_VERSION,
    )
    primary = await service.run_scheduled(
        tenant_id=fixture.tenant_id,
        site_id=fixture.site_id,
        config_type="ROBOTS_TXT",
        scheduled_for=datetime(2026, 8, 21, 6, tzinfo=UTC),
        attempt=1,
        rule_version=PUBLIC_CONFIG_RULE_VERSION,
    )

    assert primary.validation_requested is True
    async with factory() as session:
        validation_jobs = list(
            (
                await session.scalars(
                    select(Job).where(
                        Job.tenant_id == fixture.tenant_id,
                        Job.job_type == "VALIDATE_PUBLIC_CONFIG",
                    )
                )
            ).all()
        )
    assert len(validation_jobs) == 1
    assert validation_jobs[0].payload["primary_snapshot_id"] == str(primary.snapshot_id)

    validation = await service.run_validation(
        tenant_id=fixture.tenant_id,
        site_id=fixture.site_id,
        config_type="ROBOTS_TXT",
        primary_snapshot_id=primary.snapshot_id,
        attempt=1,
        rule_version=PUBLIC_CONFIG_RULE_VERSION,
    )
    stored = await repository.load_snapshot(
        tenant_id=fixture.tenant_id,
        site_id=fixture.site_id,
        snapshot_id=validation.snapshot_id,
    )

    assert stored.fetch_kind == "VALIDATION"
    assert stored.validation_of_snapshot_id == primary.snapshot_id


async def test_event_broad_block_is_persisted_only_after_matching_validation(
    public_config_fixture: PublicConfigFixture,
) -> None:
    fixture = public_config_fixture
    factory = get_session_factory()
    repository = PublicConfigRepository(factory)
    service = PublicConfigService(
        repository,
        JobQueue(factory),
        _SequenceClient(
            [
                b"User-agent: *\nDisallow: /private\n",
                b"User-agent: *\nDisallow: /\n",
                b"User-agent: *\nDisallow: /\n",
                b"User-agent: *\nDisallow: /\n",
            ]
        ),  # type: ignore[arg-type]
        clock=_MinuteClock(),
        event_service=PublicConfigEventService(repository, PublicConfigEventRepository(factory)),
    )
    await service.run_scheduled(
        tenant_id=fixture.tenant_id,
        site_id=fixture.site_id,
        config_type="ROBOTS_TXT",
        scheduled_for=datetime(2026, 8, 21, tzinfo=UTC),
        attempt=1,
        rule_version=PUBLIC_CONFIG_RULE_VERSION,
    )
    primary = await service.run_scheduled(
        tenant_id=fixture.tenant_id,
        site_id=fixture.site_id,
        config_type="ROBOTS_TXT",
        scheduled_for=datetime(2026, 8, 21, 6, tzinfo=UTC),
        attempt=1,
        rule_version=PUBLIC_CONFIG_RULE_VERSION,
    )
    async with factory() as session:
        before_validation = await session.scalar(
            select(func.count()).select_from(Event).where(Event.tenant_id == fixture.tenant_id)
        )
    assert before_validation == 0

    validation = await service.run_validation(
        tenant_id=fixture.tenant_id,
        site_id=fixture.site_id,
        config_type="ROBOTS_TXT",
        primary_snapshot_id=primary.snapshot_id,
        attempt=1,
        rule_version=PUBLIC_CONFIG_RULE_VERSION,
    )
    repeated_validation = await service.run_validation(
        tenant_id=fixture.tenant_id,
        site_id=fixture.site_id,
        config_type="ROBOTS_TXT",
        primary_snapshot_id=primary.snapshot_id,
        attempt=2,
        rule_version=PUBLIC_CONFIG_RULE_VERSION,
    )

    async with factory() as session:
        events = list(
            (
                await session.scalars(
                    select(Event).where(
                        Event.tenant_id == fixture.tenant_id,
                        Event.event_definition_id == definition_id("ROBOTS_BROAD_BLOCK_ADDED"),
                    )
                )
            ).all()
        )
        assert len(events) == 1
        assert events[0].severity == "CRITICAL"
        assert events[0].scope == {"config_type": "ROBOTS_TXT"}
        assert "index" not in events[0].summary.lower()
        refs = list(
            (
                await session.scalars(
                    select(EventEvidenceRef).where(EventEvidenceRef.event_id == events[0].id)
                )
            ).all()
        )
    assert {ref.relation for ref in refs} == {"BEFORE", "AFTER", "VALIDATION"}
    assert {ref.evidence_kind for ref in refs} == {"PUBLIC_CONFIG_SNAPSHOT"}
    assert validation.snapshot_id in {ref.source_id for ref in refs}
    assert repeated_validation.snapshot_id in {ref.source_id for ref in refs}


async def test_event_ads_condition_supports_resolves_and_recurs(
    public_config_fixture: PublicConfigFixture,
) -> None:
    fixture = public_config_fixture
    factory = get_session_factory()
    repository = PublicConfigRepository(factory)
    valid = b"example.net, account-1, DIRECT\n"
    service = PublicConfigService(
        repository,
        JobQueue(factory),
        _ResponseSequenceClient(
            [
                (200, valid),
                (404, b""),
                (404, b""),
                (404, b""),
                (404, b""),
                (200, valid),
                (200, valid),
                (404, b""),
                (404, b""),
            ]
        ),  # type: ignore[arg-type]
        clock=_MinuteClock(),
        event_service=PublicConfigEventService(repository, PublicConfigEventRepository(factory)),
    )

    async def scheduled(hour: int) -> PublicConfigRunResult:
        return await service.run_scheduled(
            tenant_id=fixture.tenant_id,
            site_id=fixture.site_id,
            config_type="ADS_TXT",
            scheduled_for=datetime(2026, 8, 21, hour, tzinfo=UTC),
            attempt=1,
            rule_version=PUBLIC_CONFIG_RULE_VERSION,
        )

    async def validate(primary_snapshot_id: uuid.UUID) -> None:
        await service.run_validation(
            tenant_id=fixture.tenant_id,
            site_id=fixture.site_id,
            config_type="ADS_TXT",
            primary_snapshot_id=primary_snapshot_id,
            attempt=1,
            rule_version=PUBLIC_CONFIG_RULE_VERSION,
        )

    await scheduled(0)
    first_missing = await scheduled(1)
    await validate(first_missing.snapshot_id)
    repeated_missing = await scheduled(2)
    await validate(repeated_missing.snapshot_id)
    recovery = await scheduled(3)
    assert recovery.validation_requested is True
    await validate(recovery.snapshot_id)
    recurrence = await scheduled(4)
    await validate(recurrence.snapshot_id)

    async with factory() as session:
        events = list(
            (
                await session.scalars(
                    select(Event)
                    .where(
                        Event.tenant_id == fixture.tenant_id,
                        Event.event_definition_id == definition_id("ADS_TXT_MISSING"),
                    )
                    .order_by(Event.started_at)
                )
            ).all()
        )
        refs = list(
            (
                await session.scalars(
                    select(EventEvidenceRef).where(EventEvidenceRef.event_id == events[0].id)
                )
            ).all()
        )

    assert [event.status for event in events] == ["RESOLVED", "ACTIVE"]
    assert events[0].details["lifecycle"]["supporting_count"] == 2
    assert {ref.relation for ref in refs} >= {
        "TRIGGER_BEFORE",
        "TRIGGER_AFTER",
        "SUPPORTING",
        "RECOVERY",
        "VALIDATION",
    }


async def test_ads_state_transitions_resolve_mutually_exclusive_conditions(
    public_config_fixture: PublicConfigFixture,
) -> None:
    fixture = public_config_fixture
    factory = get_session_factory()
    repository = PublicConfigRepository(factory)
    valid = b"example.net, account-1, DIRECT\n"
    service = PublicConfigService(
        repository,
        JobQueue(factory),
        _ResponseSequenceClient(
            [
                (200, valid),
                (404, b""),
                (404, b""),
                (200, b""),
                (200, b""),
                (200, b""),
                (200, b"garbage-line-without-valid-record\n"),
                (200, b"garbage-line-without-valid-record\n"),
                (200, valid),
                (200, valid),
            ]
        ),  # type: ignore[arg-type]
        clock=_MinuteClock(),
        event_service=PublicConfigEventService(repository, PublicConfigEventRepository(factory)),
    )

    async def scheduled(hour: int) -> PublicConfigRunResult:
        return await service.run_scheduled(
            tenant_id=fixture.tenant_id,
            site_id=fixture.site_id,
            config_type="ADS_TXT",
            scheduled_for=datetime(2026, 8, 21, hour, tzinfo=UTC),
            attempt=1,
            rule_version=PUBLIC_CONFIG_RULE_VERSION,
        )

    async def validate(
        primary_snapshot_id: uuid.UUID, *, attempt: int = 1
    ) -> PublicConfigRunResult:
        return await service.run_validation(
            tenant_id=fixture.tenant_id,
            site_id=fixture.site_id,
            config_type="ADS_TXT",
            primary_snapshot_id=primary_snapshot_id,
            attempt=attempt,
            rule_version=PUBLIC_CONFIG_RULE_VERSION,
        )

    async def condition_status(code: str) -> list[str]:
        async with factory() as session:
            events = list(
                (
                    await session.scalars(
                        select(Event)
                        .where(
                            Event.tenant_id == fixture.tenant_id,
                            Event.event_definition_id == definition_id(code),
                        )
                        .order_by(Event.started_at)
                    )
                ).all()
            )
        return [event.status for event in events]

    await scheduled(0)
    missing = await scheduled(1)
    await validate(missing.snapshot_id)
    assert await condition_status("ADS_TXT_MISSING") == ["ACTIVE"]

    unrelated_id = uuid.uuid4()
    detected_at = datetime(2026, 8, 20, tzinfo=UTC)
    async with factory() as session, session.begin():
        session.add(
            Event(
                id=unrelated_id,
                tenant_id=fixture.tenant_id,
                site_id=fixture.site_id,
                event_definition_id=definition_id("JS_ERROR_STARTED"),
                template_id=None,
                started_at=detected_at,
                occurred_after_at=None,
                occurred_before_at=detected_at,
                time_precision="WINDOW",
                detected_at=detected_at,
                severity="MEDIUM",
                observation_confidence="HIGH",
                status="ACTIVE",
                source_kind="BROWSER_CHECKPOINT",
                source_version="e2-v1",
                condition_key=f"unrelated-js-error-{unrelated_id.hex}",
                scope={"scenario": "core_desktop_v2"},
                summary="unrelated active browser condition",
                details={},
            )
        )

    empty = await scheduled(2)
    await validate(empty.snapshot_id)
    assert await condition_status("ADS_TXT_MISSING") == ["RESOLVED"]
    assert await condition_status("ADS_TXT_EMPTY_200") == ["ACTIVE"]
    assert await condition_status("ADS_TXT_INVALID") == []
    assert await condition_status("JS_ERROR_STARTED") == ["ACTIVE"]

    repeated_empty = await validate(empty.snapshot_id, attempt=2)
    assert await condition_status("ADS_TXT_EMPTY_200") == ["ACTIVE"]
    assert await condition_status("ADS_TXT_MISSING") == ["RESOLVED"]

    invalid = await scheduled(3)
    await validate(invalid.snapshot_id)
    assert await condition_status("ADS_TXT_EMPTY_200") == ["RESOLVED"]
    assert await condition_status("ADS_TXT_INVALID") == ["ACTIVE"]
    assert await condition_status("JS_ERROR_STARTED") == ["ACTIVE"]

    recovery = await scheduled(4)
    assert recovery.validation_requested is True
    await validate(recovery.snapshot_id)
    assert await condition_status("ADS_TXT_INVALID") == ["RESOLVED"]
    assert await condition_status("ADS_TXT_MISSING") == ["RESOLVED"]
    assert await condition_status("ADS_TXT_EMPTY_200") == ["RESOLVED"]
    assert await condition_status("JS_ERROR_STARTED") == ["ACTIVE"]

    async with factory() as session:
        empty_events = list(
            (
                await session.scalars(
                    select(Event).where(
                        Event.tenant_id == fixture.tenant_id,
                        Event.event_definition_id == definition_id("ADS_TXT_EMPTY_200"),
                    )
                )
            ).all()
        )
        empty_refs = list(
            (
                await session.scalars(
                    select(EventEvidenceRef).where(
                        EventEvidenceRef.event_id.in_([event.id for event in empty_events])
                    )
                )
            ).all()
        )
        unrelated_refs = list(
            (
                await session.scalars(
                    select(EventEvidenceRef).where(EventEvidenceRef.event_id == unrelated_id)
                )
            ).all()
        )
    assert len(empty_events) == 1
    assert empty_events[0].status == "RESOLVED"
    assert repeated_empty.snapshot_id in {ref.source_id for ref in empty_refs}
    assert unrelated_refs == []


class _ProbeClient:
    """Raises if any fetch is attempted; proves PC-GATE-3 skips without contact."""

    def __init__(self) -> None:
        self.called = False

    async def fetch(self, **_kwargs: object) -> PublicConfigFetchResult:
        self.called = True
        raise AssertionError("publisher contact must not occur after an M2 skip")


class _PublicConfigSnapshotClient(_SequenceClient):
    """A SequenceClient that also records how often fetch() was invoked."""

    def __init__(self, contents: list[bytes]) -> None:
        super().__init__(contents)
        self.call_count = 0

    async def fetch(self, **_kwargs: object) -> PublicConfigFetchResult:
        self.call_count += 1
        return await super().fetch(**_kwargs)


async def _enable_site_monitoring(
    *, site_id: uuid.UUID, tenant_id: uuid.UUID, at: datetime
) -> None:
    """Force monitoring ON with an explicit watermark without the fixture's
    deep-past default; establishes exact-boundary authorization epochs."""
    from sqlalchemy import update

    from app.browser.models import Site as BrowserSite

    factory = get_session_factory()
    async with factory() as session, session.begin():
        await session.execute(
            update(BrowserSite)
            .where(BrowserSite.id == site_id)
            .values(monitoring_state="ON", monitoring_state_updated_at=at)
        )


async def _count_rows(session: Any, model: Any, *, tenant_id: uuid.UUID) -> int:
    count = await session.scalar(
        select(func.count()).select_from(model).where(model.tenant_id == tenant_id)
    )
    return int(count or 0)


async def test_scheduled_fetch_skips_with_zero_contact_when_monitoring_off(
    public_config_fixture: PublicConfigFixture,
) -> None:
    """PC-GATE-3 (EP-030 M2): a scheduled fetch against a disabled site raises
    PublicConfigMonitoringSkippedError with zero publisher contact and zero
    downstream artifacts."""
    fixture = public_config_fixture
    factory = get_session_factory()
    repository = PublicConfigRepository(factory)
    client = _ProbeClient()
    service = PublicConfigService(
        repository,
        JobQueue(factory),
        cast(Any, client),
        clock=_MinuteClock(),
    )
    from app.browser.monitoring_control import set_monitoring_state

    await set_monitoring_state(
        factory,
        tenant_id=fixture.tenant_id,
        site_id=fixture.site_id,
        enabled=False,
        actor_id=fixture.tenant_id,
    )
    with pytest.raises(PublicConfigMonitoringSkippedError):
        await service.run_scheduled(
            tenant_id=fixture.tenant_id,
            site_id=fixture.site_id,
            config_type="ROBOTS_TXT",
            scheduled_for=datetime(2026, 8, 21, 12, tzinfo=UTC),
            attempt=1,
            rule_version=PUBLIC_CONFIG_RULE_VERSION,
        )
    assert client.called is False
    async with factory() as session:
        assert await _count_rows(session, PublicConfigSnapshot, tenant_id=fixture.tenant_id) == 0
        assert await _count_rows(session, AdsTxtRecord, tenant_id=fixture.tenant_id) == 0
        assert await _count_rows(session, Event, tenant_id=fixture.tenant_id) == 0


async def test_scheduled_fetch_skips_on_exact_boundary_stale_epoch(
    public_config_fixture: PublicConfigFixture,
) -> None:
    """PC-GATE-3 exact-boundary: an ON site whose enable watermark equals the
    scheduled instant is a stale epoch (at-or-before) and fails closed."""
    fixture = public_config_fixture
    factory = get_session_factory()
    repository = PublicConfigRepository(factory)
    client = _ProbeClient()
    service = PublicConfigService(
        repository,
        JobQueue(factory),
        cast(Any, client),
        clock=_MinuteClock(),
    )
    scheduled_for = datetime(2026, 8, 21, 12, tzinfo=UTC)
    await _enable_site_monitoring(
        site_id=fixture.site_id, tenant_id=fixture.tenant_id, at=scheduled_for
    )
    with pytest.raises(PublicConfigMonitoringSkippedError):
        await service.run_scheduled(
            tenant_id=fixture.tenant_id,
            site_id=fixture.site_id,
            config_type="ROBOTS_TXT",
            scheduled_for=scheduled_for,
            attempt=1,
            rule_version=PUBLIC_CONFIG_RULE_VERSION,
        )
    assert client.called is False
    async with factory() as session:
        assert await _count_rows(session, PublicConfigSnapshot, tenant_id=fixture.tenant_id) == 0


async def test_scheduled_fetch_full_path_proceeds_when_authorized(
    public_config_fixture: PublicConfigFixture,
) -> None:
    """PC-GATE-3 positive path: an ON site with a strict-past watermark performs
    the real scheduled fetch, persists a snapshot, and requests no validation
    identically to the pre-M2 contract."""
    fixture = public_config_fixture
    factory = get_session_factory()
    repository = PublicConfigRepository(factory)
    client = _PublicConfigSnapshotClient(
        [b"User-agent: *\nDisallow: /private\n", b"User-agent: *\nDisallow: /\n"]
    )
    service = PublicConfigService(
        repository,
        JobQueue(factory),
        cast(Any, client),
        clock=_MinuteClock(),
    )
    await _enable_site_monitoring(
        site_id=fixture.site_id,
        tenant_id=fixture.tenant_id,
        at=datetime(2020, 1, 1, tzinfo=UTC),  # strict-past: first slot is authorized
    )
    scheduled_for = datetime(2026, 8, 21, tzinfo=UTC)
    result = await service.run_scheduled(
        tenant_id=fixture.tenant_id,
        site_id=fixture.site_id,
        config_type="ROBOTS_TXT",
        scheduled_for=scheduled_for,
        attempt=1,
        rule_version=PUBLIC_CONFIG_RULE_VERSION,
    )
    assert client.call_count == 1
    stored = await repository.load_snapshot(
        tenant_id=fixture.tenant_id,
        site_id=fixture.site_id,
        snapshot_id=result.snapshot_id,
    )
    assert stored.fetch_kind == "SCHEDULED"
    assert stored.config_type == "ROBOTS_TXT"


async def test_scheduler_exact_boundary_enqueues_nothing(
    public_config_fixture: PublicConfigFixture,
) -> None:
    """PC-GATE-2 (EP-030 M2): an ON site whose enable watermark lands exactly on
    the resolved slot start is stale; schedule_due enqueues no FETCH jobs."""
    fixture = public_config_fixture
    factory = get_session_factory()
    repository = PublicConfigRepository(factory)
    scheduler = PublicConfigSchedulingService(repository, JobQueue(factory))
    current = datetime(2026, 8, 21, 12, 15, tzinfo=UTC)
    slot = resolve_public_config_slot(current, "UTC")
    await _enable_site_monitoring(site_id=fixture.site_id, tenant_id=fixture.tenant_id, at=slot)
    result = await scheduler.schedule_due(now=current)
    assert result.site_count == 0
    assert result.job_count == 0
    async with factory() as session:
        jobs = list(
            (
                await session.scalars(
                    select(Job).where(
                        Job.tenant_id == fixture.tenant_id,
                        Job.job_type == "FETCH_PUBLIC_CONFIG",
                    )
                )
            ).all()
        )
    assert jobs == []


async def test_queued_fetch_skips_at_worker_level_when_disabled(
    public_config_fixture: PublicConfigFixture,
) -> None:
    """PC-GATE-3 (EP-030 M2) worker orchestration: a FETCH_PUBLIC_CONFIG job
    queued while ON but claimed after a disable completes as an intentional skip
    with zero publisher contact, no retry, no snapshot, no event."""
    from app.browser.monitoring_control import set_monitoring_state
    from app.worker import handle_job

    fixture = public_config_fixture
    factory = get_session_factory()
    repository = PublicConfigRepository(factory)
    queue = JobQueue(factory)
    client = _ProbeClient()
    service = PublicConfigService(
        repository,
        queue,
        cast(Any, client),
        clock=_MinuteClock(),
    )
    scheduled_for = datetime(2026, 8, 21, tzinfo=UTC)
    job_id = await queue.enqueue(
        job_type="FETCH_PUBLIC_CONFIG",
        tenant_id=fixture.tenant_id,
        payload={
            "site_id": str(fixture.site_id),
            "config_type": "ROBOTS_TXT",
            "scheduled_for": scheduled_for.isoformat(),
            "rule_version": PUBLIC_CONFIG_RULE_VERSION,
        },
        idempotency_key=f"fetch:{fixture.site_id}:ROBOTS_TXT:{scheduled_for.isoformat()}",
        max_attempts=2,
        scheduled_at=datetime(2000, 1, 1, tzinfo=UTC),
    )
    # Disable after enqueue (PC-R2): the claimed job must fail closed pre-flight.
    await set_monitoring_state(
        factory,
        tenant_id=fixture.tenant_id,
        site_id=fixture.site_id,
        enabled=False,
        actor_id=fixture.tenant_id,
    )
    lease = await queue.claim(worker_id="w1", lease_seconds=30, job_type="FETCH_PUBLIC_CONFIG")
    assert lease is not None
    await handle_job(
        queue=queue,
        lease=lease,
        backoff_seconds=0,
        public_config_service=service,
    )

    assert client.called is False
    async with factory() as session:
        stored = await session.get(Job, job_id)
        assert stored is not None
        assert stored.status == "COMPLETE"
        assert stored.attempt == 1
        assert stored.last_error_class is None
        assert await _count_rows(session, PublicConfigSnapshot, tenant_id=fixture.tenant_id) == 0
        assert await _count_rows(session, Event, tenant_id=fixture.tenant_id) == 0


async def test_fetch_missing_scheduled_for_fails_non_retryable_zero_contact(
    public_config_fixture: PublicConfigFixture,
) -> None:
    """EP-030 M2 payload validation: a FETCH job missing a required key (here
    `scheduled_for`) fails deterministically as a non-retryable invalid job with
    zero publisher contact and zero derived records — never treated as a
    monitoring-disabled skip, never retried."""
    from app.worker import handle_job

    fixture = public_config_fixture
    factory = get_session_factory()
    queue = JobQueue(factory)
    client = _ProbeClient()
    service = PublicConfigService(
        repository=PublicConfigRepository(factory),
        queue=queue,
        client=cast(Any, client),
        clock=_MinuteClock(),
    )
    job_id = await queue.enqueue(
        job_type="FETCH_PUBLIC_CONFIG",
        tenant_id=fixture.tenant_id,
        payload={
            "site_id": str(fixture.site_id),
            "config_type": "ROBOTS_TXT",
            "rule_version": PUBLIC_CONFIG_RULE_VERSION,
            # `scheduled_for` deliberately omitted
        },
        idempotency_key=f"missing:{fixture.site_id}:{uuid.uuid4()}",
        max_attempts=3,
        scheduled_at=datetime(2000, 1, 1, tzinfo=UTC),
    )
    lease = await queue.claim(worker_id="w1", lease_seconds=30, job_type="FETCH_PUBLIC_CONFIG")
    assert lease is not None
    await handle_job(
        queue=queue,
        lease=lease,
        backoff_seconds=0,
        public_config_service=service,
    )
    assert client.called is False
    async with factory() as session:
        stored = await session.get(Job, job_id)
        assert stored is not None
        assert stored.status == "FAILED"
        assert stored.last_error_class == "INVALID_PUBLIC_CONFIG_JOB"
        assert stored.last_error_message == "INVALID_JOB_PAYLOAD"
        assert await _count_rows(session, PublicConfigSnapshot, tenant_id=fixture.tenant_id) == 0
        assert await _count_rows(session, AdsTxtRecord, tenant_id=fixture.tenant_id) == 0
        assert await _count_rows(session, Event, tenant_id=fixture.tenant_id) == 0


async def test_fetch_malformed_scheduled_for_fails_non_retryable_zero_contact(
    public_config_fixture: PublicConfigFixture,
) -> None:
    """EP-030 M2 payload validation: a FETCH job with a malformed `scheduled_for`
    fails deterministically as a non-retryable invalid job with zero publisher
    contact and zero derived records."""
    from app.worker import handle_job

    fixture = public_config_fixture
    factory = get_session_factory()
    queue = JobQueue(factory)
    client = _ProbeClient()
    service = PublicConfigService(
        repository=PublicConfigRepository(factory),
        queue=queue,
        client=cast(Any, client),
        clock=_MinuteClock(),
    )
    job_id = await queue.enqueue(
        job_type="FETCH_PUBLIC_CONFIG",
        tenant_id=fixture.tenant_id,
        payload={
            "site_id": str(fixture.site_id),
            "config_type": "ROBOTS_TXT",
            "scheduled_for": "not-a-datetime",
            "rule_version": PUBLIC_CONFIG_RULE_VERSION,
        },
        idempotency_key=f"malformed:{fixture.site_id}:{uuid.uuid4()}",
        max_attempts=3,
        scheduled_at=datetime(2000, 1, 1, tzinfo=UTC),
    )
    lease = await queue.claim(worker_id="w1", lease_seconds=30, job_type="FETCH_PUBLIC_CONFIG")
    assert lease is not None
    await handle_job(
        queue=queue,
        lease=lease,
        backoff_seconds=0,
        public_config_service=service,
    )
    assert client.called is False
    async with factory() as session:
        stored = await session.get(Job, job_id)
        assert stored is not None
        assert stored.status == "FAILED"
        assert stored.last_error_class == "INVALID_PUBLIC_CONFIG_JOB"
        assert stored.last_error_message == "INVALID_JOB_PAYLOAD"
        assert await _count_rows(session, PublicConfigSnapshot, tenant_id=fixture.tenant_id) == 0
        assert await _count_rows(session, AdsTxtRecord, tenant_id=fixture.tenant_id) == 0
        assert await _count_rows(session, Event, tenant_id=fixture.tenant_id) == 0


async def _create_validation_primary(
    fixture: "PublicConfigFixture",
    repository: PublicConfigRepository,
    queue: JobQueue,
) -> "PublicConfigRunResult":
    """Authorize the fixture site (deep-past watermark), perform a healthy fetch
    then a broad-block scheduled fetch so the transition requests validation, and
    return the high-risk primary eligible for VALIDATE. Uses one shared
    `_SequenceClient` so the healthy-then-broad content order is preserved across
    the two scheduled fetches."""
    await _enable_site_monitoring(
        site_id=fixture.site_id,
        tenant_id=fixture.tenant_id,
        at=datetime(2020, 1, 1, tzinfo=UTC),
    )
    client = _SequenceClient(
        [
            b"User-agent: *\nDisallow: /private\n",  # healthy
            b"User-agent: *\nDisallow: /\n",  # broad block
        ]
    )
    service = PublicConfigService(
        repository=repository,
        queue=queue,
        client=client,  # type: ignore[arg-type]
        clock=_MinuteClock(),
    )
    await service.run_scheduled(
        tenant_id=fixture.tenant_id,
        site_id=fixture.site_id,
        config_type="ROBOTS_TXT",
        scheduled_for=datetime(2026, 8, 21, 0, 0, tzinfo=UTC),
        attempt=1,
        rule_version=PUBLIC_CONFIG_RULE_VERSION,
    )
    primary = await service.run_scheduled(
        tenant_id=fixture.tenant_id,
        site_id=fixture.site_id,
        config_type="ROBOTS_TXT",
        scheduled_for=datetime(2026, 8, 21, 6, 0, tzinfo=UTC),
        attempt=1,
        rule_version=PUBLIC_CONFIG_RULE_VERSION,
    )
    assert primary.validation_requested is True
    # Remove the VALIDATE job auto-enqueued by the scheduler so a manual enqueue
    # below is the only claimable VALIDATE job in the queue.
    async with get_session_factory()() as session, session.begin():
        await session.execute(
            delete(Job).where(
                Job.tenant_id == fixture.tenant_id,
                Job.job_type == "VALIDATE_PUBLIC_CONFIG",
            )
        )
    return primary


async def _enqueue_and_run_validation(
    fixture: "PublicConfigFixture",
    queue: JobQueue,
    client: _ProbeClient,
    primary_snapshot_id: uuid.UUID,
) -> uuid.UUID:
    from app.worker import handle_job

    service = PublicConfigService(
        repository=PublicConfigRepository(get_session_factory()),
        queue=queue,
        client=cast(Any, client),
        clock=_MinuteClock(),
    )
    job_id = await queue.enqueue(
        job_type="VALIDATE_PUBLIC_CONFIG",
        tenant_id=fixture.tenant_id,
        payload={
            "site_id": str(fixture.site_id),
            "config_type": "ROBOTS_TXT",
            "primary_snapshot_id": str(primary_snapshot_id),
            "rule_version": PUBLIC_CONFIG_RULE_VERSION,
        },
        idempotency_key=f"manual-validation:{fixture.site_id}:{primary_snapshot_id}:{uuid.uuid4()}",
        max_attempts=3,
        scheduled_at=datetime(2000, 1, 1, tzinfo=UTC),
    )
    lease = await queue.claim(worker_id="w1", lease_seconds=30, job_type="VALIDATE_PUBLIC_CONFIG")
    assert lease is not None
    assert lease.payload["primary_snapshot_id"] == str(primary_snapshot_id)
    await handle_job(
        queue=queue,
        lease=lease,
        backoff_seconds=0,
        public_config_service=service,
    )
    return job_id


async def test_queued_validation_worker_skips_when_off_zero_contact(
    public_config_fixture: PublicConfigFixture,
) -> None:
    """EP-030 M2 PC-GATE-3 worker orchestration: a VALIDATE_PUBLIC_CONFIG job
    queued while monitoring is ON but claimed after a disable completes as an
    intentional monitoring-disabled skip exercising the real DB/service/worker
    path — PC-GATE-3 runs before `_observe`/`client.fetch`, zero publisher
    contact, no retry, no snapshot/event."""
    from app.browser.monitoring_control import set_monitoring_state

    fixture = public_config_fixture
    factory = get_session_factory()
    repository = PublicConfigRepository(factory)
    queue = JobQueue(factory)
    primary = await _create_validation_primary(fixture, repository, queue)
    # Disable AFTER the primary was created/authorized (PC-R2 for VALIDATE).
    await set_monitoring_state(
        factory,
        tenant_id=fixture.tenant_id,
        site_id=fixture.site_id,
        enabled=False,
        actor_id=fixture.tenant_id,
    )
    client = _ProbeClient()
    job_id = await _enqueue_and_run_validation(fixture, queue, client, primary.snapshot_id)
    assert client.called is False
    async with factory() as session:
        stored = await session.get(Job, job_id)
        assert stored is not None
        assert stored.status == "COMPLETE"
        assert stored.last_error_class is None
        # primary helper persisted two scheduled snapshots; the skipped VALIDATE
        # adds no new snapshot.
        assert await _count_rows(session, PublicConfigSnapshot, tenant_id=fixture.tenant_id) == 2
        assert await _count_rows(session, Event, tenant_id=fixture.tenant_id) == 0


async def test_stale_validation_after_re_enable_completes_skip_zero_contact(
    public_config_fixture: PublicConfigFixture,
) -> None:
    """EP-030 M2 PC-GATE-3 stale-epoch: a VALIDATE job referencing a primary
    observed before a NEWER monitoring watermark (OFF then re-ON) completes as a
    monitoring-disabled/stale skip with zero client.fetch — the validation
    re-fetch belongs to an expired authorization epoch."""
    from app.browser.monitoring_control import set_monitoring_state

    fixture = public_config_fixture
    factory = get_session_factory()
    repository = PublicConfigRepository(factory)
    queue = JobQueue(factory)
    primary = await _create_validation_primary(fixture, repository, queue)
    # OFF then re-ON advances the watermark past primary.observed_at (the fixed
    # 2026-08-21 clock value), so the queued validation is stale (at-or-before).
    await set_monitoring_state(
        factory,
        tenant_id=fixture.tenant_id,
        site_id=fixture.site_id,
        enabled=False,
        actor_id=fixture.tenant_id,
    )
    await set_monitoring_state(
        factory,
        tenant_id=fixture.tenant_id,
        site_id=fixture.site_id,
        enabled=True,
        actor_id=fixture.tenant_id,
    )
    client = _ProbeClient()
    job_id = await _enqueue_and_run_validation(fixture, queue, client, primary.snapshot_id)
    assert client.called is False
    async with factory() as session:
        stored = await session.get(Job, job_id)
        assert stored is not None
        assert stored.status == "COMPLETE"
        assert stored.last_error_class is None
        assert await _count_rows(session, PublicConfigSnapshot, tenant_id=fixture.tenant_id) == 2
        assert await _count_rows(session, Event, tenant_id=fixture.tenant_id) == 0
