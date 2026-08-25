"""EP-026 M2b-2 — deterministic browser source health + recovery/recheck.

Full production path: controlled challenge/degraded diagnostic observation →
automatic degradation Event → operator-triggered healthy DIAGNOSTIC recheck →
automatic BROWSER_SOURCE_RECOVERED → deterministic source-health projection.
No publisher/site-failure semantics anywhere.
"""

import asyncio
import http.server
import threading
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.browser.persistence import CheckpointRepository
from app.browser_worker import run as run_browser_worker
from app.config.settings import get_settings
from app.db.models import Job
from app.db.session import get_session_factory
from app.events.models import Event, EventEvidenceRef
from app.events.registry import definition_id
from app.events.source_health import BrowserSourceHealth
from app.jobs.queue import JobQueue
from app.worker import handle_job

pytestmark = pytest.mark.integration

CHALLENGE_BODY = (
    b"<!doctype html><html><head><title>Attention Required! | Cloudflare</title>"
    b"</head><body><p>checking your browser before accessing; complete the "
    b"captcha to continue.</p></body></html>"
)
HEALTHY_BODY = b"<!doctype html><html><body><h1>Fixture</h1></body></html>"


class RecheckHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path.startswith("/challenge"):
            self._send(403, CHALLENGE_BODY)
        else:
            self._send(200, HEALTHY_BODY)

    def _send(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        del format, args


@pytest.fixture()
def recheck_site() -> Iterator[str]:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), RecheckHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


async def _register_diagnostic(base_url: str, path: str, slug: str) -> dict[str, uuid.UUID]:
    from app.browser.service import CheckpointService

    settings = get_settings()
    factory = get_session_factory()
    service = CheckpointService(factory, JobQueue(factory), settings)
    registered = await service.register_and_enqueue(
        tenant_slug=slug,
        tenant_name="Recheck Fixture Tenant",
        publisher_name="Recheck Fixture Publisher",
        site_name="Recheck Fixture Site",
        url=f"{base_url}{path}",
    )
    return {
        "tenant_id": registered.tenant_id,
        "checkpoint_run_id": registered.checkpoint_run_id,
    }


def _run_browser_once() -> None:
    asyncio.run(run_browser_worker(once=True))


def _process_one_derive_job() -> bool:
    from app.events.persistence import EventRepository
    from app.events.service import EventService

    async def act() -> bool:
        factory = get_session_factory()
        queue = JobQueue(factory)
        lease = await queue.claim(worker_id="recovery-test", lease_seconds=60)
        if lease is None:
            return False
        assert lease.job_type == "DERIVE_BROWSER_EVENTS"
        await handle_job(
            queue,
            lease,
            1,
            None,
            None,
            None,
            None,
            EventService(EventRepository(get_session_factory())),
        )
        return True

    return asyncio.run(act())


def _process_all_derive_jobs_for(tenant_id: uuid.UUID) -> int:
    processed = 0
    while True:
        jobs = asyncio.run(_pending_jobs(tenant_id))
        if not jobs:
            break
        assert _process_one_derive_job() is True
        processed += 1
    return processed


async def _pending_jobs(tenant_id: uuid.UUID) -> list[Job]:
    factory = get_session_factory()
    async with factory() as session:
        return list(
            (
                await session.scalars(
                    select(Job).where(
                        Job.tenant_id == tenant_id,
                        Job.job_type == "DERIVE_BROWSER_EVENTS",
                        Job.status.in_(("PENDING", "RUNNING")),
                    )
                )
            ).all()
        )


def _events_and_refs(
    tenant_id: uuid.UUID, site_id: uuid.UUID
) -> tuple[list[Event], list[EventEvidenceRef]]:
    async def act() -> tuple[list[Event], list[EventEvidenceRef]]:
        factory = get_session_factory()
        async with factory() as session:
            events = list(
                (
                    await session.scalars(
                        select(Event)
                        .where(Event.tenant_id == tenant_id, Event.site_id == site_id)
                        .order_by(Event.detected_at, Event.id)
                    )
                ).all()
            )
            refs = list(
                (
                    await session.scalars(
                        select(EventEvidenceRef).where(EventEvidenceRef.tenant_id == tenant_id)
                    )
                ).all()
            )
        return events, refs

    return asyncio.run(act())


def _code_of(event: Event) -> str | None:
    for code in (
        "BROWSER_SOURCE_DEGRADED",
        "BROWSER_ACCESS_CHALLENGE_SUSPECTED",
        "BROWSER_SOURCE_RECOVERED",
    ):
        if event.event_definition_id == definition_id(code):
            return code
    return None


def _diagnose_once(base_url: str, path: str, slug: str) -> dict[str, uuid.UUID]:
    """Register a DIAGNOSTIC observation, run the real browser worker, then
    process every derive job through the real worker."""
    registered = asyncio.run(_register_diagnostic(base_url, path, slug))
    _run_browser_once()
    _process_all_derive_jobs_for(registered["tenant_id"])
    return registered


def _health(tenant_id: uuid.UUID, site_id: uuid.UUID) -> BrowserSourceHealth:
    from app.events.source_health import browser_source_health

    async def act() -> BrowserSourceHealth:
        factory = get_session_factory()
        async with factory() as session:
            return await browser_source_health(session, tenant_id=tenant_id, site_id=site_id)

    return asyncio.run(act())


def test_degradation_recheck_recovery_full_automatic_path(recheck_site: str) -> None:
    slug = f"recheck-{uuid.uuid4().hex}"
    settings = get_settings()
    assert settings.browser_allow_private_networks, (
        "integration fixture requires explicit test opt-in"
    )

    # 1-3. Degradation episode through the full production path.
    degraded = _diagnose_once(recheck_site, "/challenge", slug)
    tenant_id = degraded["tenant_id"]
    degraded_run_id = degraded["checkpoint_run_id"]

    stored_degraded = asyncio.run(
        CheckpointRepository(get_session_factory()).get_for_tenant(
            tenant_id=tenant_id, checkpoint_run_id=degraded_run_id
        )
    )
    assert stored_degraded is not None
    assert stored_degraded.browser_access_classification is not None
    site_id = stored_degraded.site_id

    events, refs = _events_and_refs(tenant_id, site_id)
    assert [_code_of(event) for event in events if _code_of(event)] == [
        "BROWSER_ACCESS_CHALLENGE_SUSPECTED"
    ]

    health = _health(tenant_id, site_id)
    assert health.state == "DEGRADED"
    assert health.source_event_code == "BROWSER_ACCESS_CHALLENGE_SUSPECTED"
    assert health.evidence_checkpoint_run_id == degraded_run_id

    # 4-5. Qualifying healthy DIAGNOSTIC recheck through the same path.
    rechecked = _diagnose_once(recheck_site, "/healthy-recheck", slug)
    assert rechecked["tenant_id"] == tenant_id
    recheck_run_id = rechecked["checkpoint_run_id"]
    assert recheck_run_id != degraded_run_id

    events, refs = _events_and_refs(tenant_id, site_id)
    recovered = [event for event in events if _code_of(event) == "BROWSER_SOURCE_RECOVERED"]
    assert len(recovered) == 1
    recovery = recovered[0]
    assert recovery.severity == "LOW"
    assert recovery.status == "RECORDED"
    assert "recovered" in recovery.summary.lower()
    assert "publisher" not in recovery.summary.lower()
    assert "site recovered" not in recovery.summary.lower()

    # Temporal bounds: lower bound = prior degradation detection; upper/detection =
    # healthy recheck observation.
    degradation_event = next(
        event for event in events if _code_of(event) == "BROWSER_ACCESS_CHALLENGE_SUSPECTED"
    )
    assert recovery.occurred_after_at is not None
    assert degradation_event.detected_at is not None
    assert recovery.occurred_after_at == degradation_event.detected_at
    assert recovery.detected_at >= degradation_event.detected_at

    # Evidence relations: prior degraded observation BEFORE, healthy recheck TRIGGER_AFTER.
    recovery_refs = [ref for ref in refs if ref.event_id == recovery.id]
    by_relation = {(ref.evidence_kind, ref.relation, ref.source_id) for ref in recovery_refs}
    assert ("CHECKPOINT_RUN", "BEFORE", degraded_run_id) in by_relation
    assert ("CHECKPOINT_RUN", "TRIGGER_AFTER", recheck_run_id) in by_relation

    # Projection flips to HEALTHY with recovery linkage.
    health = _health(tenant_id, site_id)
    assert health.state == "HEALTHY"
    assert health.source_event_code == "BROWSER_SOURCE_RECOVERED"
    assert health.source_event_id == recovery.id


def test_episode_semantics_degrade_recover_degrade(recheck_site: str) -> None:
    slug = f"recheck-{uuid.uuid4().hex}"
    first = _diagnose_once(recheck_site, "/challenge", slug)
    tenant_id = first["tenant_id"]
    stored = asyncio.run(
        CheckpointRepository(get_session_factory()).get_for_tenant(
            tenant_id=tenant_id, checkpoint_run_id=first["checkpoint_run_id"]
        )
    )
    assert stored is not None
    site_id = stored.site_id

    _diagnose_once(recheck_site, "/healthy-recheck", slug)
    second = _diagnose_once(recheck_site, "/challenge", slug)

    events, _ = _events_and_refs(tenant_id, site_id)
    codes = [_code_of(event) for event in events if _code_of(event)]
    assert codes == [
        "BROWSER_ACCESS_CHALLENGE_SUSPECTED",
        "BROWSER_SOURCE_RECOVERED",
        "BROWSER_ACCESS_CHALLENGE_SUSPECTED",
    ]
    # Historical facts immutable: all three rows remain RECORDED.
    assert all(event.status == "RECORDED" for event in events if _code_of(event))
    assert second["tenant_id"] == tenant_id
    health = _health(tenant_id, site_id)
    assert health.state == "DEGRADED"


def test_recovery_idempotent_on_repeated_processing(recheck_site: str) -> None:
    slug = f"recheck-{uuid.uuid4().hex}"
    first = _diagnose_once(recheck_site, "/challenge", slug)
    tenant_id = first["tenant_id"]
    degraded_run_id = first["checkpoint_run_id"]
    stored = asyncio.run(
        CheckpointRepository(get_session_factory()).get_for_tenant(
            tenant_id=tenant_id, checkpoint_run_id=degraded_run_id
        )
    )
    assert stored is not None
    site_id = stored.site_id
    _diagnose_once(recheck_site, "/healthy-recheck", slug)

    events, refs = _events_and_refs(tenant_id, site_id)
    recovered_before = [event for event in events if _code_of(event) == "BROWSER_SOURCE_RECOVERED"]
    assert len(recovered_before) == 1

    # Reprocess identical derive work via canonical enqueue + worker.
    async def reschedule(run_id: uuid.UUID, key_suffix: str) -> None:
        factory = get_session_factory()
        queue = JobQueue(factory)
        await queue.enqueue(
            tenant_id=tenant_id,
            job_type="DERIVE_BROWSER_EVENTS",
            payload={"checkpoint_run_id": str(run_id)},
            idempotency_key=f"derive-browser-events:{run_id}:{key_suffix}",
        )

    asyncio.run(reschedule(first["checkpoint_run_id"], "retry-degradation"))
    assert _process_one_derive_job() is True

    events, refs = _events_and_refs(tenant_id, site_id)
    recovered = [event for event in events if _code_of(event) == "BROWSER_SOURCE_RECOVERED"]
    assert len(recovered) == 1
    recovery_refs = [ref for ref in refs if ref.event_id == recovered[0].id]
    assert len(recovery_refs) == 2


def test_unrelated_scheduled_browser_success_does_not_recover(recheck_site: str) -> None:
    """ADR-130: SCHEDULED runs never enter the diagnostic derivation path, so a
    routine scheduled success cannot recover a degraded monitoring source."""
    slug = f"recheck-{uuid.uuid4().hex}"
    first = _diagnose_once(recheck_site, "/challenge", slug)
    tenant_id = first["tenant_id"]
    stored = asyncio.run(
        CheckpointRepository(get_session_factory()).get_for_tenant(
            tenant_id=tenant_id, checkpoint_run_id=first["checkpoint_run_id"]
        )
    )
    assert stored is not None
    site_id = stored.site_id

    # A completed healthy SCHEDULED run exists for the site (factory pattern).
    scheduled_run_id = uuid.uuid4()
    asyncio.run(_seed_completed_scheduled_run(tenant_id, site_id, scheduled_run_id))

    from app.events.persistence import EventRepository, EventRunResult
    from app.events.service import EventService

    async def derive_scheduled() -> EventRunResult:
        service = EventService(EventRepository(get_session_factory()))
        return await service.derive(tenant_id=tenant_id, checkpoint_run_id=scheduled_run_id)

    result = asyncio.run(derive_scheduled())
    assert result.candidate_count == 0

    events, _ = _events_and_refs(tenant_id, site_id)
    recovered = [event for event in events if _code_of(event) == "BROWSER_SOURCE_RECOVERED"]
    assert recovered == []


async def _seed_completed_scheduled_run(
    tenant_id: uuid.UUID, site_id: uuid.UUID, run_id: uuid.UUID
) -> None:
    from datetime import timedelta

    from app.browser.models import (
        BrowserScenario,
        CheckpointRun,
        CheckpointWindow,
        MonitoredUrl,
        Template,
    )

    factory = get_session_factory()
    when = datetime.now(UTC)
    async with factory() as session, session.begin():
        scenario = await session.scalar(
            select(BrowserScenario).where(BrowserScenario.tenant_id == tenant_id)
        )
        template = await session.scalar(select(Template).where(Template.tenant_id == tenant_id))
        monitored_url = await session.scalar(
            select(MonitoredUrl).where(MonitoredUrl.tenant_id == tenant_id)
        )
        assert scenario is not None and template is not None and monitored_url is not None
        window = CheckpointWindow(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            site_id=site_id,
            scheduled_for=when,
            window_start=when,
            window_end=when + timedelta(minutes=30),
        )
        session.add(window)
        await session.flush()
        session.add(
            CheckpointRun(
                id=run_id,
                tenant_id=tenant_id,
                site_id=site_id,
                checkpoint_window_id=window.id,
                monitored_url_id=monitored_url.id,
                template_id=template.id,
                scenario_id=scenario.id,
                observation_kind="SCHEDULED",
                scheduled_for=when,
                started_at=when,
                completed_at=when + timedelta(minutes=5),
                status="COMPLETE",
                attempt_count=1,
                collector_bundle_version="b8-v1",
                environment={},
                limitations=[],
                manifest={},
            )
        )


def test_load_diagnostic_input_returns_connection_to_pool(recheck_site: str) -> None:
    """Lifecycle regression (EP-026 M3b CI investigation): the DIAGNOSTIC
    derivation input loader must return its pooled DB connection before
    returning. Reusing the session after its context manager had closed left
    an open transaction-bound connection orphaned on a dead event loop until
    GC, blocking later DDL (e.g. alembic downgrade) on its locks."""
    from typing import cast

    from sqlalchemy.pool import QueuePool

    from app.db.session import get_engine
    from app.events.contracts import DiagnosticInput
    from app.events.persistence import EventRepository

    ids = asyncio.run(
        _register_diagnostic(recheck_site, "/challenge", f"pool-{uuid.uuid4().hex[:8]}")
    )
    _run_browser_once()

    factory = get_session_factory()
    repository = EventRepository(factory)
    engine = get_engine()

    async def act() -> DiagnosticInput | None:
        return await repository.load_diagnostic_input(
            tenant_id=ids["tenant_id"], checkpoint_run_id=ids["checkpoint_run_id"]
        )

    diagnostic = asyncio.run(act())
    assert diagnostic is not None
    pool = cast(QueuePool, engine.sync_engine.pool)
    assert pool.checkedout() == 0
