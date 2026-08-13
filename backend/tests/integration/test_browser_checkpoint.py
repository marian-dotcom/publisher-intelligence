import hashlib
import threading
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from sqlalchemy import delete, select

from app.browser.gpt import gpt_stable_key
from app.browser.models import (
    Artifact,
    BrowserScenario,
    CheckpointAttempt,
    CheckpointRun,
    CheckpointWindow,
    CollectorRun,
    DomainEntity,
    EntityObservation,
    GPTSlotObservation,
    InteractionProfile,
    JavaScriptErrorObservation,
    MonitoredUrl,
    Publisher,
    Site,
    Template,
    TemplateExpectedEntity,
)
from app.browser.persistence import CheckpointRepository
from app.browser.scheduling import CheckpointSchedulingService, resolve_six_hour_window
from app.browser.service import CheckpointService
from app.browser_worker import run as run_browser_worker
from app.config.settings import get_settings
from app.db.models import Job, Tenant
from app.db.session import get_session_factory
from app.jobs.queue import JobQueue
from app.storage.s3 import S3Storage

pytestmark = pytest.mark.integration


class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path.startswith("/asset.js"):
            self._send(200, "application/javascript", b"window.fixtureLoaded = true;")
            return
        if self.path.startswith("/site-error"):
            self._send(503, "text/html", b"<html><body>fixture unavailable</body></html>")
            return
        if self.path.startswith("/gpt"):
            self._send(200, "text/html", _gpt_fixture_html())
            return
        html = b"""<!doctype html><html><body><h1>Fixture</h1>
        <script src="/asset.js?token=manifest-secret"></script>
        <script>console.error('fixture console');
        setTimeout(() => { throw new Error('fixture js error'); }, 0);</script>
        <img src="http://127.0.0.1:1/missing?token=network-secret">
        </body></html>"""
        self._send(200, "text/html", html)

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        del format, args


def _gpt_fixture_html() -> bytes:
    return b"""<!doctype html><html><body style="height:4000px">
    <h1>Deterministic GPT fixture</h1>
    <div id="eager-slot"></div><div id="lazy-slot" style="margin-top:2500px"></div>
    <script>
    (() => {
      const listeners = {};
      const makeSlot = (path, element, sizes) => ({
        getAdUnitPath: () => path,
        getSlotElementId: () => element,
        getSizes: () => sizes.map(([width, height]) => ({
          getWidth: () => width, getHeight: () => height
        }))
      });
      const eager = makeSlot('/123/article/eager', 'eager-slot', [[300, 250]]);
      const lazy = makeSlot('/123/article/lazy', 'lazy-slot', [[728, 90]]);
      const pubads = {
        addEventListener: (name, callback) => {
          (listeners[name] ||= []).push(callback);
        },
        getSlots: () => [eager, lazy]
      };
      const emit = (name, slot, extra = {}) => {
        for (const callback of listeners[name] || []) callback({slot, ...extra});
      };
      const cmd = [];
      window.googletag = {
        cmd,
        getVersion: () => 'fixture-gpt-1',
        pubads: () => pubads
      };
      const pump = setInterval(() => {
        while (cmd.length) cmd.shift()();
        if (listeners.slotRequested) clearInterval(pump);
      }, 10);
      setTimeout(() => {
        emit('slotRequested', eager);
        emit('slotRequested', eager);
        emit('slotResponseReceived', eager);
        emit('slotRenderEnded', eager, {
          isEmpty: false, creativeId: 'creative-eager', lineItemId: 'line-eager'
        });
        emit('slotOnload', eager);
        emit('impressionViewable', eager);
      }, 100);
      let lazyRequested = false;
      window.addEventListener('scroll', () => {
        if (lazyRequested || window.scrollY <= 0) return;
        lazyRequested = true;
        emit('slotRequested', lazy);
        emit('slotResponseReceived', lazy);
        emit('slotRenderEnded', lazy, {
          isEmpty: false, creativeId: 'creative-lazy', lineItemId: 'line-lazy'
        });
        emit('slotOnload', lazy);
        emit('impressionViewable', lazy);
      });
    })();
    </script></body></html>"""


@pytest.fixture
def fixture_site() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


async def _cleanup_tenant(tenant_id: uuid.UUID, storage: S3Storage) -> None:
    factory = get_session_factory()
    async with factory() as session:
        keys = list(
            (
                await session.scalars(
                    select(Artifact.object_key).where(Artifact.tenant_id == tenant_id)
                )
            ).all()
        )
    for key in keys:
        storage.delete(key=key)
    async with factory() as session, session.begin():
        for model in (
            Artifact,
            CollectorRun,
            EntityObservation,
            JavaScriptErrorObservation,
            GPTSlotObservation,
            CheckpointAttempt,
            CheckpointRun,
            TemplateExpectedEntity,
            DomainEntity,
            MonitoredUrl,
            CheckpointWindow,
            BrowserScenario,
            InteractionProfile,
            Template,
            Site,
            Publisher,
            Job,
        ):
            await session.execute(delete(model).where(model.tenant_id == tenant_id))
        await session.execute(delete(Tenant).where(Tenant.id == tenant_id))


async def test_gpt_lifecycle_persists_eager_lazy_and_expected_absent_slots(
    fixture_site: str,
) -> None:
    settings = get_settings()
    assert settings.browser_allow_private_networks
    factory = get_session_factory()
    queue = JobQueue(factory)
    service = CheckpointService(factory, queue, settings)
    repository = CheckpointRepository(factory)
    storage = S3Storage(settings)
    registered = await service.register_and_enqueue(
        tenant_slug=f"gpt-{uuid.uuid4().hex}",
        tenant_name="GPT Browser Tenant",
        publisher_name="GPT Publisher",
        site_name="GPT Site",
        url=f"{fixture_site}/gpt",
    )
    paths = ("/123/article/eager", "/123/article/lazy", "/123/article/missing")
    try:
        async with factory() as session, session.begin():
            run = await session.get(CheckpointRun, registered.checkpoint_run_id)
            assert run is not None
            scenario = await session.scalar(
                select(BrowserScenario).where(
                    BrowserScenario.tenant_id == registered.tenant_id,
                    BrowserScenario.site_id == run.site_id,
                    BrowserScenario.code == "core_desktop_v2",
                )
            )
            assert scenario is not None
            run.scenario_id = scenario.id
            for path in paths:
                entity = DomainEntity(
                    id=uuid.uuid4(),
                    tenant_id=registered.tenant_id,
                    site_id=run.site_id,
                    entity_kind="GPT_SLOT",
                    stable_key=gpt_stable_key(path, None) or "",
                    source_system="CONFIG",
                    first_seen_at=run.scheduled_for,
                    identity_metadata={
                        "ad_unit_path": path,
                        "sizes": ["300x250" if path.endswith("eager") else "728x90"],
                    },
                )
                session.add(entity)
                session.add(
                    TemplateExpectedEntity(
                        id=uuid.uuid4(),
                        tenant_id=registered.tenant_id,
                        site_id=run.site_id,
                        template_id=run.template_id,
                        entity_id=entity.id,
                        expectation_type="EXPECTED",
                        valid_from=run.scheduled_for - timedelta(seconds=1),
                        source="TEST_CONFIGURATION",
                        confidence="HIGH",
                    )
                )

        await run_browser_worker(once=True)

        run = await repository.get_for_tenant(
            tenant_id=registered.tenant_id,
            checkpoint_run_id=registered.checkpoint_run_id,
        )
        assert run is not None
        assert run.status == "COMPLETE"
        assert run.collector_bundle_version == "b4-v1"
        assert run.manifest["schema"] == "browser-checkpoint-manifest/v4"
        assert run.manifest["gpt"]["present"] is True
        assert run.manifest["gpt"]["version"] == "fixture-gpt-1"

        slots = await repository.gpt_slots_for_tenant(
            tenant_id=registered.tenant_id,
            checkpoint_run_id=registered.checkpoint_run_id,
        )
        assert len(slots) == 3
        by_path = {slot.ad_unit_path: slot for slot in slots}
        eager = by_path["/123/article/eager"]
        assert eager.expected and eager.present
        assert eager.request_count == 2
        assert eager.defined_at_ms is not None
        assert eager.requested_at_ms is not None
        assert eager.response_at_ms is not None
        assert eager.render_ended_at_ms is not None
        assert eager.onload_at_ms is not None
        assert eager.viewable_at_ms is not None
        assert eager.is_empty is False
        assert eager.creative_id == "creative-eager"

        lazy = by_path["/123/article/lazy"]
        assert lazy.expected and lazy.present
        assert lazy.defined_at_ms is not None
        assert lazy.requested_at_ms is not None
        assert lazy.requested_at_ms > lazy.defined_at_ms
        assert lazy.viewable_at_ms is not None
        assert lazy.request_count == 1

        missing = by_path["/123/article/missing"]
        assert missing.expected and not missing.present
        assert missing.defined_at_ms is None
        assert missing.requested_at_ms is None
        assert missing.response_at_ms is None
        assert missing.render_ended_at_ms is None
        assert missing.onload_at_ms is None
        assert missing.viewable_at_ms is None
        assert missing.request_count == 0

        assert (
            await repository.gpt_slots_for_tenant(
                tenant_id=uuid.uuid4(),
                checkpoint_run_id=registered.checkpoint_run_id,
            )
            == []
        )
        async with factory() as session:
            collector = await session.scalar(
                select(CollectorRun).where(
                    CollectorRun.checkpoint_run_id == registered.checkpoint_run_id,
                    CollectorRun.collector_type == "GPT_LIFECYCLE",
                )
            )
            assert collector is not None
            assert collector.status == "OK"
            assert collector.collector_version == "gpt-b4-v1"
            assert collector.summary["expected_slot_count"] == 3
    finally:
        await _cleanup_tenant(registered.tenant_id, storage)


async def test_real_browser_checkpoint_persists_evidence_and_site_error(
    fixture_site: str,
) -> None:
    settings = get_settings()
    assert settings.browser_allow_private_networks, (
        "integration fixture requires explicit test opt-in"
    )
    factory = get_session_factory()
    queue = JobQueue(factory)
    service = CheckpointService(factory, queue, settings)
    repository = CheckpointRepository(factory)
    storage = S3Storage(settings)
    tenant_slug = f"browser-{uuid.uuid4().hex}"
    first = await service.register_and_enqueue(
        tenant_slug=tenant_slug,
        tenant_name="Browser Fixture Tenant",
        publisher_name="Fixture Publisher",
        site_name="Fixture Site",
        url=f"{fixture_site}/complete?operator-secret=not-retained",
    )
    try:
        await run_browser_worker(once=True)
        run = await repository.get_for_tenant(
            tenant_id=first.tenant_id,
            checkpoint_run_id=first.checkpoint_run_id,
        )
        assert run is not None
        assert run.status == "COMPLETE"
        assert run.http_status == 200
        assert run.final_url == f"{fixture_site}/complete"
        assert run.playwright_version
        assert run.chromium_version
        assert run.manifest["schema"] == "browser-checkpoint-manifest/v4"
        assert run.manifest["normalized_state"]["dom"]["normalizer_version"] == "dom-b3-v1"
        assert "manifest-secret" not in str(run.manifest)
        assert "network-secret" not in str(run.manifest)
        assert "operator-secret" not in str(run.manifest)
        assert run.manifest["javascript_errors"]
        artifacts = await repository.artifacts_for_tenant(
            tenant_id=first.tenant_id,
            checkpoint_run_id=first.checkpoint_run_id,
        )
        assert {item.artifact_type for item in artifacts} == {
            "SCREENSHOT_VIEWPORT",
            "SCREENSHOT_FULL_PAGE",
            "RAW_DOM",
            "NORMALIZED_DOM",
            "MANIFEST",
        }
        for artifact in artifacts:
            content = storage.get_bytes(key=artifact.object_key)
            assert hashlib.sha256(content).hexdigest() == artifact.sha256
        assert (
            await repository.get_for_tenant(
                tenant_id=uuid.uuid4(), checkpoint_run_id=first.checkpoint_run_id
            )
            is None
        )
        assert (
            await repository.artifacts_for_tenant(
                tenant_id=uuid.uuid4(), checkpoint_run_id=first.checkpoint_run_id
            )
            == []
        )
        entity_observations = await repository.entity_observations_for_tenant(
            tenant_id=first.tenant_id,
            checkpoint_run_id=first.checkpoint_run_id,
        )
        assert entity_observations
        assert {item.collector_version for item in entity_observations} == {"b3-v1"}
        assert (
            await repository.entity_observations_for_tenant(
                tenant_id=uuid.uuid4(), checkpoint_run_id=first.checkpoint_run_id
            )
            == []
        )
        normalized_errors = await repository.javascript_errors_for_tenant(
            tenant_id=first.tenant_id,
            checkpoint_run_id=first.checkpoint_run_id,
        )
        assert normalized_errors
        assert (
            await repository.javascript_errors_for_tenant(
                tenant_id=uuid.uuid4(), checkpoint_run_id=first.checkpoint_run_id
            )
            == []
        )

        second = await service.register_and_enqueue(
            tenant_slug=tenant_slug,
            tenant_name="Browser Fixture Tenant",
            publisher_name="Fixture Publisher",
            site_name="Fixture Site",
            url=f"{fixture_site}/site-error",
        )
        await run_browser_worker(once=True)
        site_error = await repository.get_for_tenant(
            tenant_id=first.tenant_id,
            checkpoint_run_id=second.checkpoint_run_id,
        )
        assert site_error is not None
        assert site_error.status == "SITE_ERROR"
        assert site_error.http_status == 503
        job = await queue.get_for_tenant(tenant_id=first.tenant_id, job_id=second.job_id)
        assert job is not None
        assert job.status == "COMPLETE"
        assert job.attempt == 1
    finally:
        await _cleanup_tenant(first.tenant_id, storage)


async def test_scheduler_produces_repeatable_desktop_and_mobile_runs(
    fixture_site: str,
) -> None:
    settings = get_settings()
    assert settings.browser_allow_private_networks
    factory = get_session_factory()
    queue = JobQueue(factory)
    service = CheckpointService(factory, queue, settings)
    scheduler = CheckpointSchedulingService(factory, queue, settings)
    repository = CheckpointRepository(factory)
    storage = S3Storage(settings)
    tenant_slug = f"repeatable-{uuid.uuid4().hex}"
    registered = await service.register_and_enqueue(
        tenant_slug=tenant_slug,
        tenant_name="Repeatable Browser Tenant",
        publisher_name="Repeatable Publisher",
        site_name="Repeatable Site",
        url=f"{fixture_site}/complete",
    )
    try:
        await run_browser_worker(once=True)
        first_window_time = datetime.now(UTC)
        first_bounds = resolve_six_hour_window(first_window_time, "UTC")
        first_pass = await scheduler.schedule_due(now=first_window_time)
        repeated_pass = await scheduler.schedule_due(now=first_window_time)
        assert first_pass.run_count == 2
        assert repeated_pass.run_count == 2

        async with factory() as session:
            site = await session.scalar(select(Site).where(Site.tenant_id == registered.tenant_id))
            assert site is not None
            first_window = await session.scalar(
                select(CheckpointWindow).where(
                    CheckpointWindow.site_id == site.id,
                    CheckpointWindow.scheduled_for == first_bounds.scheduled_for,
                )
            )
            assert first_window is not None
            first_runs = list(
                (
                    await session.scalars(
                        select(CheckpointRun)
                        .where(CheckpointRun.checkpoint_window_id == first_window.id)
                        .order_by(CheckpointRun.scenario_id)
                    )
                ).all()
            )
            assert len(first_runs) == 2
            assert {run.collector_bundle_version for run in first_runs} == {"b4-v1"}
            first_run_ids = {run.id for run in first_runs}
            scheduled_jobs = list(
                (
                    await session.scalars(
                        select(Job).where(
                            Job.tenant_id == registered.tenant_id,
                            Job.job_type == "BROWSER_CHECKPOINT",
                        )
                    )
                ).all()
            )
            assert (
                len(
                    [
                        job
                        for job in scheduled_jobs
                        if uuid.UUID(str(job.payload["checkpoint_run_id"])) in first_run_ids
                    ]
                )
                == 2
            )

        await run_browser_worker(once=True)
        async with factory() as session:
            in_progress_window = await session.get(CheckpointWindow, first_window.id)
            assert in_progress_window is not None
            assert in_progress_window.status == "RUNNING"
        await run_browser_worker(once=True)

        async with factory() as session:
            complete_window = await session.get(CheckpointWindow, first_window.id)
            assert complete_window is not None
            assert complete_window.status == "COMPLETE"
            completed_runs = list(
                (
                    await session.scalars(
                        select(CheckpointRun).where(CheckpointRun.id.in_(first_run_ids))
                    )
                ).all()
            )
            assert {run.status for run in completed_runs} == {"COMPLETE"}
            assert {run.environment["is_mobile"] for run in completed_runs} == {False, True}
            for run in completed_runs:
                scrolls = [
                    action
                    for action in run.manifest["actions"]
                    if action["type"] == "scroll_percent"
                ]
                assert [action["percent"] for action in scrolls] == [25, 50, 75]
                assert all(action["actual_y"] >= 0 for action in scrolls)
                assert run.manifest["actions"][-1]["kind"] == "full_page"

            monitored_url = await session.scalar(
                select(MonitoredUrl).where(
                    MonitoredUrl.tenant_id == registered.tenant_id,
                    MonitoredUrl.status == "ACTIVE",
                )
            )
            assert monitored_url is not None
            monitored_url.status = "RETIRED"
            monitored_url.valid_to = first_bounds.window_end
            rotated_url = MonitoredUrl(
                id=uuid.uuid4(),
                tenant_id=registered.tenant_id,
                site_id=site.id,
                template_id=monitored_url.template_id,
                url=f"{fixture_site}/complete?representative=rotated",
                priority=monitored_url.priority,
                is_canary=monitored_url.is_canary,
                status="ACTIVE",
                valid_from=first_bounds.window_end,
            )
            session.add(rotated_url)
            await session.commit()

        second_window_time = first_bounds.window_end + timedelta(minutes=1)
        second_bounds = resolve_six_hour_window(second_window_time, "UTC")
        await scheduler.schedule_due(now=second_window_time)
        async with factory() as session:
            second_window = await session.scalar(
                select(CheckpointWindow).where(
                    CheckpointWindow.site_id == site.id,
                    CheckpointWindow.scheduled_for == second_bounds.scheduled_for,
                )
            )
            assert second_window is not None
            second_runs = list(
                (
                    await session.scalars(
                        select(CheckpointRun).where(
                            CheckpointRun.checkpoint_window_id == second_window.id
                        )
                    )
                ).all()
            )
            assert len(second_runs) == 2
        for run in second_runs:
            previous = await repository.previous_comparable_selection(
                tenant_id=registered.tenant_id,
                checkpoint_run_id=run.id,
            )
            assert previous is not None
            assert previous.run.id in first_run_ids
            assert previous.run.scenario_id == run.scenario_id
            assert previous.selection_scope == "SAME_TEMPLATE_URL_ROTATION"
        assert (
            await repository.previous_comparable(
                tenant_id=uuid.uuid4(),
                checkpoint_run_id=second_runs[0].id,
            )
            is None
        )
    finally:
        await _cleanup_tenant(registered.tenant_id, storage)
