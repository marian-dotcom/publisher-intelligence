import hashlib
import threading
import uuid
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from sqlalchemy import delete, select

from app.browser.models import (
    Artifact,
    BrowserScenario,
    CheckpointAttempt,
    CheckpointRun,
    CheckpointWindow,
    CollectorRun,
    MonitoredUrl,
    Publisher,
    Site,
    Template,
)
from app.browser.persistence import CheckpointRepository
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
            CheckpointAttempt,
            CheckpointRun,
            MonitoredUrl,
            CheckpointWindow,
            BrowserScenario,
            Template,
            Site,
            Publisher,
            Job,
        ):
            await session.execute(delete(model).where(model.tenant_id == tenant_id))
        await session.execute(delete(Tenant).where(Tenant.id == tenant_id))


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
        assert run.manifest["schema"] == "browser-checkpoint-manifest/v1"
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
