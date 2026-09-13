"""EP-026 M4 — measured cost telemetry, hard caps, circuit breaker.

Cost is measured at execution time through the investigation budget ledger
(resource_kind CHECKPOINT_RUN), one idempotent entry per executed checkpoint
run over a bounded one-page set. The circuit breaker is a deterministic
read-time projection of that same ledger: once a site/window reaches its cap,
no further runs/jobs are scheduled for the scope and browser monitoring
surfaces BLOCKED. Never fabricated data; never publisher/site failure.
"""

import asyncio
import http.server
import threading
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app.browser.cost import (
    DEFAULT_CHECKPOINTS_PER_SITE_WINDOW,
    breaker_open_for_usage,
    record_checkpoint_cost,
    site_window_scope,
)
from app.browser.models import CheckpointRun
from app.browser.scheduling import resolve_six_hour_window
from app.config.settings import get_settings
from app.db.session import get_session_factory
from app.incidents.models import InvestigationUsageEntry
from app.jobs.queue import JobQueue
from tests.integration.purge import make_purge

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _clean_db() -> None:
    asyncio.run(make_purge(get_session_factory)())


HEALTHY_BODY = b"<!doctype html><html><body><h1>Fixture</h1></body></html>"


class HealthyHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(HEALTHY_BODY)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(HEALTHY_BODY)

    def log_message(self, format: str, *args: object) -> None:
        del format, args


@pytest.fixture()
def healthy_site_url() -> Iterator[str]:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), HealthyHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _register_diagnostic(base_url: str) -> dict[str, uuid.UUID]:
    from app.browser.service import CheckpointService

    factory = get_session_factory()
    service = CheckpointService(factory, JobQueue(factory), get_settings())
    registered = asyncio.run(
        service.register_and_enqueue(
            tenant_slug=f"m4-{uuid.uuid4().hex[:8]}",
            tenant_name="M4 Tenant",
            publisher_name="M4 Publisher",
            site_name="M4 Site",
            url=f"{base_url}/",
        )
    )
    return {
        "tenant_id": registered.tenant_id,
        "checkpoint_run_id": registered.checkpoint_run_id,
    }


def _run_browser_once() -> None:
    from app.browser_worker import run as run_browser_worker

    asyncio.run(run_browser_worker(once=True))


def _usage_rows(tenant_id: uuid.UUID) -> list[InvestigationUsageEntry]:
    async def act() -> list[InvestigationUsageEntry]:
        factory = get_session_factory()
        async with factory() as session:
            return list(
                (
                    await session.scalars(
                        select(InvestigationUsageEntry).where(
                            InvestigationUsageEntry.tenant_id == tenant_id,
                            InvestigationUsageEntry.resource_kind == "CHECKPOINT_RUN",
                        )
                    )
                ).all()
            )

    return asyncio.run(act())


def test_checkpoint_execution_records_measured_cost_once(healthy_site_url: str) -> None:
    """Cost telemetry on successful execution: exactly one idempotent
    CHECKPOINT_RUN ledger entry per run, amounting one run unit over the
    bounded one-page set, with measured facts in the audit detail."""
    ids = _register_diagnostic(healthy_site_url)
    run_id = ids["checkpoint_run_id"]
    tenant_id = ids["tenant_id"]
    assert _usage_rows(tenant_id) == []

    _run_browser_once()

    rows = _usage_rows(tenant_id)
    assert len(rows) == 1
    row = rows[0]
    assert row.amount == 1
    assert row.detail["checkpoint_run_id"] == str(run_id)
    assert row.detail["pages"] == 1
    assert row.detail["status"] == "COMPLETE"
    assert row.investigation_key.startswith("site:")

    # Bounded retries fold into one entry: reprocessing never double counts.
    _run_browser_once()
    assert len(_usage_rows(tenant_id)) == 1


async def _seed_site_with_current_window(
    slug: str,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Seed an ACTIVE site whose latest window is the scheduler's current
    six-hour window, containing one COMPLETE scheduled run. Returns
    (tenant_id, site_id, window_id)."""
    from app.browser.models import (
        BrowserScenario,
        CheckpointWindow,
        MonitoredUrl,
        Publisher,
        Site,
        Template,
    )
    from app.db.models import Tenant

    factory = get_session_factory()
    now = datetime.now(UTC)
    bounds = resolve_six_hour_window(now, "UTC")
    async with factory() as session, session.begin():
        tenant_id, publisher_id, site_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        session.add(Tenant(id=tenant_id, slug=slug, name=slug.title()))
        await session.flush()
        session.add(
            Publisher(
                id=publisher_id,
                tenant_id=tenant_id,
                name="P",
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
                name="S",
                canonical_domain=f"{site_id.hex}.example.com",
                canonical_scheme="https",
                timezone="UTC",
                status="ACTIVE",
                # EP-030 M2: scheduled monitoring is fail-closed by default.
                # This seed drives the SCHEDULED scheduler path, so authorize
                # monitoring with a deep-past watermark so GATE-2 treats the
                # current six-hour window as strictly future and schedulable.
                monitoring_state="ON",
                monitoring_state_updated_at=datetime(2020, 1, 1, tzinfo=UTC),
            )
        )
        await session.flush()
        template_id, monitored_url_id, scenario_id, window_id, run_id = (
            uuid.uuid4(),
            uuid.uuid4(),
            uuid.uuid4(),
            uuid.uuid4(),
            uuid.uuid4(),
        )
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
        await session.flush()
        session.add(
            BrowserScenario(
                id=scenario_id,
                tenant_id=tenant_id,
                site_id=site_id,
                code=f"core_desktop_{uuid.uuid4().hex[:6]}",
                version=1,
                status="ACTIVE",
            )
        )
        session.add(
            CheckpointWindow(
                id=window_id,
                tenant_id=tenant_id,
                site_id=site_id,
                scheduled_for=bounds.scheduled_for,
                window_start=bounds.window_start,
                window_end=bounds.window_end,
            )
        )
        await session.flush()
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
                scheduled_for=now,
                status="COMPLETE",
                collector_bundle_version="b8-v1",
                environment={"is_mobile": False},
                limitations=[],
                manifest={},
            )
        )
        return tenant_id, site_id, window_id


def test_recorder_resolves_run_scope_and_is_idempotent() -> None:
    tenant_id, site_id, window_id = asyncio.run(
        _seed_site_with_current_window(f"m4-rec-{uuid.uuid4().hex[:8]}")
    )
    factory = get_session_factory()
    run_row_id = asyncio.run(_only_run_id(site_id))

    created = asyncio.run(
        record_checkpoint_cost(
            factory,
            tenant_id=tenant_id,
            checkpoint_run_id=run_row_id,
            status="PARTIAL",
            attempt_count=2,
        )
    )
    repeated = asyncio.run(
        record_checkpoint_cost(
            factory,
            tenant_id=tenant_id,
            checkpoint_run_id=run_row_id,
            status="PARTIAL",
            attempt_count=2,
        )
    )
    assert (created, repeated) == (True, False)
    rows = _usage_rows(tenant_id)
    assert len(rows) == 1
    assert rows[0].amount == 1
    assert rows[0].investigation_key == site_window_scope(site_id=site_id, window_id=window_id)


async def _only_run_id(site_id: uuid.UUID) -> uuid.UUID:
    factory = get_session_factory()
    async with factory() as session:
        run_id = await session.scalar(
            select(CheckpointRun.id).where(CheckpointRun.site_id == site_id)
        )
        assert run_id is not None
        return run_id


def test_breaker_boundary_is_deterministic() -> None:
    limit = DEFAULT_CHECKPOINTS_PER_SITE_WINDOW
    assert not breaker_open_for_usage(used=limit - 1)
    assert breaker_open_for_usage(used=limit)
    assert breaker_open_for_usage(used=limit + 1)


def _seed_usage(
    tenant_id: uuid.UUID,
    *,
    site_id: uuid.UUID,
    window_id: uuid.UUID,
    units: int,
) -> None:
    async def act() -> None:
        factory = get_session_factory()
        async with factory() as session, session.begin():
            for _index in range(units):
                session.add(
                    InvestigationUsageEntry(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        incident_id=None,
                        investigation_key=site_window_scope(site_id=site_id, window_id=window_id),
                        resource_kind="CHECKPOINT_RUN",
                        amount=1,
                        usage_key=f"{site_id}|{window_id}|{uuid.uuid4()}",
                        detail={},
                        occurred_at=datetime.now(UTC),
                    )
                )

    asyncio.run(act())


async def _site_run_count(site_id: uuid.UUID) -> int:
    factory = get_session_factory()
    async with factory() as session:
        return int(
            await session.scalar(
                select(func.count())
                .select_from(CheckpointRun)
                .where(CheckpointRun.site_id == site_id)
            )
            or 0
        )


def test_circuit_breaker_stops_scheduling_when_cap_reached() -> None:
    """Hard cap: once per-site/per-window usage reaches the cap, schedule_due
    creates NO further runs/jobs for that scope (fail closed, auditable)."""
    from app.browser.scheduling import CheckpointSchedulingService

    factory = get_session_factory()
    tenant_id, site_id, window_id = asyncio.run(
        _seed_site_with_current_window(f"m4-breaker-{uuid.uuid4().hex[:8]}")
    )

    # Below cap: scheduling proceeds normally for this scope.
    _seed_usage(
        tenant_id,
        site_id=site_id,
        window_id=window_id,
        units=DEFAULT_CHECKPOINTS_PER_SITE_WINDOW - 1,
    )
    before = asyncio.run(_site_run_count(site_id))
    result = asyncio.run(
        CheckpointSchedulingService(factory, JobQueue(factory), get_settings()).schedule_due()
    )
    assert result.breaker_skipped_sites == 0
    after_below_cap = asyncio.run(_site_run_count(site_id))
    assert after_below_cap > before

    # At cap exactly: circuit open — no new runs/jobs for this scope.
    _seed_usage(tenant_id, site_id=site_id, window_id=window_id, units=1)
    result = asyncio.run(
        CheckpointSchedulingService(factory, JobQueue(factory), get_settings()).schedule_due()
    )
    assert result.breaker_skipped_sites == 1
    assert asyncio.run(_site_run_count(site_id)) == after_below_cap
