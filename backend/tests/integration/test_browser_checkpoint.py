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
    CMPObservation,
    CollectorRun,
    ConsentPhaseDependencyObservation,
    DomainEntity,
    EntityObservation,
    GPTSlotObservation,
    InteractionProfile,
    JavaScriptErrorObservation,
    MonitoredUrl,
    PrebidAuctionObservation,
    PrebidBidderObservation,
    Publisher,
    SeoObservation,
    Site,
    SyntheticPerformanceObservation,
    Template,
    TemplateExpectedEntity,
    VideoPlayerObservation,
)
from app.browser.persistence import CheckpointRepository
from app.browser.scheduling import CheckpointSchedulingService, resolve_six_hour_window
from app.browser.service import B2_DESKTOP_SCENARIO_CODE, B5_REJECT_SCENARIO_CODE, CheckpointService
from app.browser_worker import run as run_browser_worker
from app.config.settings import get_settings
from app.db.models import Job, Tenant
from app.db.session import get_session_factory
from app.events.models import Event, EventEvidenceRef
from app.incidents.models import InvestigationUsageEntry
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
        if self.path.startswith("/cmp-pre.js"):
            self._send(200, "application/javascript", b"window.cmpPreLoaded = true;")
            return
        if self.path.startswith("/consent-network/accept"):
            self._send(200, "application/json", b'{"decision":"accept"}')
            return
        if self.path.startswith("/consent-network/reject"):
            self._send(200, "application/json", b'{"decision":"reject"}')
            return
        if self.path.startswith("/cmp"):
            self._send(200, "text/html", _cmp_fixture_html())
            return
        if self.path.startswith("/gampad/ads"):
            self._send(200, "application/json", b'{"adserver":"ok"}')
            return
        if self.path.startswith("/openrtb2/auction"):
            self._send(200, "application/json", b'{"seatbid":[]}')
            return
        if self.path.startswith("/prebid-client"):
            self._send(200, "text/html", _prebid_fixture_html())
            return
        if self.path.startswith("/prebid-server"):
            self._send(200, "text/html", _prebid_server_fixture_html())
            return
        if self.path.startswith("/vast/"):
            status = 502 if "wrapper-error" in self.path else 200
            self._send(status, "application/xml", b"<VAST version='4.3'></VAST>")
            return
        if self.path.startswith("/media/"):
            self._send(200, "video/mp4", b"fixture-media-not-retained")
            return
        if self.path.startswith("/video-native"):
            self._send(200, "text/html", _video_fixture_html())
            return
        if self.path.startswith("/video-opaque"):
            self._send(200, "text/html", _opaque_video_fixture_html())
            return
        if self.path.startswith("/performance-resource.js"):
            self._send(200, "application/javascript", b"window.performanceFixtureAsset = true;")
            return
        if self.path.startswith("/performance-data"):
            self._send(200, "application/json", b'{"fixture":"ok"}')
            return
        if self.path.startswith("/performance-error"):
            self._send(200, "text/html", _performance_error_fixture_html())
            return
        if self.path.startswith("/performance-fixture"):
            self._send(200, "text/html", _performance_fixture_html())
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


def _cmp_fixture_html() -> bytes:
    return b"""<!doctype html><html><body>
    <h1>Deterministic CMP fixture</h1>
    <div id="cmp-banner">
      <button id="cmp-accept">Accept</button>
      <button id="cmp-reject">Reject</button>
    </div>
    <div id="cmp-complete" hidden>Consent complete</div>
    <script src="/cmp-pre.js"></script>
    <script>
    (() => {
      const listeners = new Map();
      let nextListenerId = 1;
      let tcData = {
        tcString: 'fixture-tc-before-action',
        gdprApplies: true,
        cmpId: 42,
        cmpVersion: 7,
        cmpStatus: 'loaded',
        eventStatus: 'cmpuishown'
      };
      const emit = () => {
        for (const [listenerId, callback] of listeners) {
          callback({...tcData, listenerId}, true);
        }
      };
      window.__tcfapi = (command, version, callback, parameter) => {
        if (version !== 2) { callback(null, false); return; }
        if (command === 'ping') {
          callback({cmpLoaded: true, cmpStatus: 'loaded', gdprApplies: true}, true);
          return;
        }
        if (command === 'addEventListener') {
          const listenerId = nextListenerId++;
          listeners.set(listenerId, callback);
          callback({...tcData, listenerId}, true);
          return;
        }
        if (command === 'removeEventListener') {
          callback(listeners.delete(parameter), true);
          return;
        }
        callback(null, false);
      };
      const decide = async (decision) => {
        tcData = {
          ...tcData,
          tcString: `fixture-tc-${decision}-sensitive`,
          eventStatus: 'useractioncomplete'
        };
        emit();
        await fetch(`/consent-network/${decision}?secret=not-retained`);
        document.querySelector('#cmp-banner').hidden = true;
        document.querySelector('#cmp-complete').hidden = false;
      };
      document.querySelector('#cmp-accept').addEventListener('click', () => decide('accept'));
      document.querySelector('#cmp-reject').addEventListener('click', () => decide('reject'));
    })();
    </script></body></html>"""


def _prebid_fixture_html() -> bytes:
    return b"""<!doctype html><html><body>
    <h1>Deterministic Prebid fixture</h1>
    <script>
    (() => {
      const started = performance.now();
      const events = [];
      const auctionId = 'raw-auction-secret-123';
      const emit = (eventType, args) => events.push({
        eventType, args, elapsedTime: Math.round(performance.now() - started)
      });
      window.pbjs = {
        version: 'fixture-prebid-11',
        installedModules: ['consentManagementTcf', 'floors'],
        adUnits: [{
          code: 'slot-secret-code',
          bids: [{bidder: 'fast-bidder'}, {bidder: 'slow-bidder'}]
        }],
        getEvents: () => events,
        getConfig: (name) => name === 'bidderTimeout' ? 120 : null,
        getAdserverTargeting: () => ({
          'slot-secret-code': {
            hb_bidder: 'fast-bidder', hb_pb: '9.99', hb_adid: 'raw-bid-secret'
          }
        })
      };
      setTimeout(() => emit('auctionInit', {
        auctionId, timeout: 120, adUnits: window.pbjs.adUnits
      }), 20);
      setTimeout(() => emit('bidRequested', {
        auctionId,
        bids: [{bidder: 'fast-bidder'}, {bidder: 'slow-bidder'}]
      }), 35);
      setTimeout(() => emit('bidResponse', {
        auctionId, bidderCode: 'fast-bidder', timeToRespond: 45,
        cpm: 9.99, requestId: 'raw-bid-secret'
      }), 80);
      setTimeout(() => emit('bidTimeout', [
        {auctionId, bidder: 'slow-bidder', bidId: 'timeout-secret'}
      ]), 155);
      setTimeout(() => emit('bidWon', {
        auctionId, bidderCode: 'fast-bidder', cpm: 9.99
      }), 165);
      setTimeout(() => emit('auctionEnd', {auctionId}), 170);
      setTimeout(() => fetch('/gampad/ads?auctionId=raw-auction-secret-123'), 180);
    })();
    </script></body></html>"""


def _prebid_server_fixture_html() -> bytes:
    return b"""<!doctype html><html><body>
    <h1>Prebid Server hidden fixture</h1>
    <script>fetch('/openrtb2/auction?auctionId=server-secret');</script>
    </body></html>"""


def _video_fixture_html() -> bytes:
    return b"""<!doctype html><html><body style="height:5000px;margin:0">
    <h1>Deterministic native video fixture</h1>
    <div id="player-shell" style="width:360px;margin-top:400px;background:#111"></div>
    <script>
    (() => {
      const shell = document.querySelector('#player-shell');
      const video = document.createElement('video');
      video.id = 'fixture-sensitive-id';
      video.width = 360;
      video.height = 202;
      video.autoplay = true;
      video.muted = true;
      video.controls = true;
      const close = document.createElement('button');
      close.setAttribute('aria-label', 'Close player');
      close.textContent = 'X';
      setTimeout(() => { shell.append(video, close); }, 50);
      setTimeout(() => video.dispatchEvent(new Event('playing')), 200);
      setTimeout(() => fetch('/vast/adtag?token=vast-secret'), 220);
      setTimeout(() => fetch('/vast/wrapper-error?token=wrapper-secret'), 240);
      setTimeout(() => fetch('/media/video.mp4?token=media-secret'), 260);
      const makeSticky = () => {
        if (window.scrollY < 500) return;
        shell.style.position = 'fixed';
        shell.style.top = '20px';
        shell.style.right = '20px';
        shell.style.marginTop = '0';
        shell.style.zIndex = '1000';
      };
      window.addEventListener('scroll', makeSticky);
      setInterval(makeSticky, 50);
    })();
    </script></body></html>"""


def _opaque_video_fixture_html() -> bytes:
    return b"""<!doctype html><html><body>
    <h1>Opaque video network fixture</h1>
    <script>
    fetch('/vast/opaque-adtag?token=opaque-vast-secret');
    fetch('/media/opaque.mp4?token=opaque-media-secret');
    </script></body></html>"""


def _performance_fixture_html() -> bytes:
    return b"""<!doctype html><html><head>
    <script src="/performance-resource.js?token=resource-secret"></script>
    </head><body style="height:4000px;margin:0">
    <div id="fixture-top" style="height:20px"></div>
    <h1 id="fixture-lcp" style="display:block;width:600px;height:120px;margin:0;font-size:48px">
      Deterministic synthetic performance fixture
    </h1>
    <p id="shift-target" style="height:80px;margin:0">Visible content that will move.</p>
    <script>
    (() => {
      setTimeout(() => fetch('/performance-data?secret=fetch-secret'), 60);
      setTimeout(() => {
        const block = document.createElement('div');
        block.style.height = '220px';
        block.textContent = 'Late block';
        document.body.insertBefore(block, document.querySelector('#fixture-lcp'));
      }, 150);
      setTimeout(() => {
        const started = performance.now();
        while (performance.now() - started < 90) {}
      }, 300);
    })();
    </script></body></html>"""


def _performance_error_fixture_html() -> bytes:
    return b"""<!doctype html><html><body><h1>Performance failure fixture</h1>
    <script>
    setTimeout(() => {
      if (window.__piPerformanceB8) {
        window.__piPerformanceB8.snapshot = () => { throw new Error('fixture failure'); };
      }
    }, 20);
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
            InvestigationUsageEntry,
            EventEvidenceRef,
            Event,
            SeoObservation,
            Artifact,
            CollectorRun,
            PrebidBidderObservation,
            PrebidAuctionObservation,
            VideoPlayerObservation,
            SyntheticPerformanceObservation,
            ConsentPhaseDependencyObservation,
            CMPObservation,
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
        assert run.collector_bundle_version == "b8-v1"
        assert run.manifest["schema"] == "browser-checkpoint-manifest/v8"
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


async def test_prebid_client_auction_persists_safe_timing_and_bidder_evidence(
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
        tenant_slug=f"prebid-client-{uuid.uuid4().hex}",
        tenant_name="Prebid Client Tenant",
        publisher_name="Prebid Publisher",
        site_name="Prebid Client Site",
        url=f"{fixture_site}/prebid-client",
    )
    try:
        await run_browser_worker(once=True)

        run = await repository.get_for_tenant(
            tenant_id=registered.tenant_id,
            checkpoint_run_id=registered.checkpoint_run_id,
        )
        assert run is not None
        assert run.status == "COMPLETE"
        assert run.collector_bundle_version == "b8-v1"
        assert run.manifest["schema"] == "browser-checkpoint-manifest/v8"
        prebid = run.manifest["prebid"]
        assert prebid["present"] is True
        assert prebid["version"] == "fixture-prebid-11"
        assert prebid["server_side_configured"] is False
        assert prebid["targeting_keys"] == ["hb_adid", "hb_bidder", "hb_pb"]
        assert prebid["limitations"] == []

        auctions = await repository.prebid_auctions_for_tenant(
            tenant_id=registered.tenant_id,
            checkpoint_run_id=registered.checkpoint_run_id,
        )
        assert len(auctions) == 1
        auction = auctions[0]
        assert auction.auction_key == "auction-001"
        assert auction.configured_timeout_ms == 120
        assert auction.ad_unit_count == 1
        assert auction.bidder_request_count == 2
        assert auction.bid_response_count == 1
        assert auction.no_bid_count == 0
        assert auction.timeout_count == 1
        assert auction.started_at_ms is not None
        assert auction.ended_at_ms is not None
        first_gam_request = auction.metadata_json["first_ad_server_request_at_ms"]
        assert first_gam_request is not None
        assert first_gam_request >= auction.ended_at_ms

        bidders = await repository.prebid_bidders_for_tenant(
            tenant_id=registered.tenant_id,
            checkpoint_run_id=registered.checkpoint_run_id,
        )
        assert len(bidders) == 2
        by_bidder = {item.bidder_code: item for item in bidders}
        fast = by_bidder["fast-bidder"]
        assert fast.request_count == 1
        assert fast.response_count == 1
        assert fast.timeout_count == 0
        assert fast.response_time_ms_min == 45
        assert fast.response_time_ms_max == 45
        assert fast.response_time_ms_avg == 45
        assert fast.winning_bid_count == 1
        slow = by_bidder["slow-bidder"]
        assert slow.request_count == 1
        assert slow.response_count == 0
        assert slow.timeout_count == 1
        assert slow.winning_bid_count == 0

        serialized_manifest = str(run.manifest)
        for forbidden in (
            "raw-auction-secret-123",
            "raw-bid-secret",
            "timeout-secret",
            "slot-secret-code",
        ):
            assert forbidden not in serialized_manifest
        # The fixture CPM must never leak into any Prebid evidence surface.
        # It is not scanned against the whole manifest because unrelated B8
        # timing floats can legitimately contain the same digit substring.
        serialized_prebid = str([prebid, auctions, bidders])
        assert "9.99" not in serialized_prebid
        assert (
            await repository.prebid_auctions_for_tenant(
                tenant_id=uuid.uuid4(),
                checkpoint_run_id=registered.checkpoint_run_id,
            )
            == []
        )
        assert (
            await repository.prebid_bidders_for_tenant(
                tenant_id=uuid.uuid4(),
                checkpoint_run_id=registered.checkpoint_run_id,
            )
            == []
        )
        async with factory() as session:
            collector = await session.scalar(
                select(CollectorRun).where(
                    CollectorRun.checkpoint_run_id == registered.checkpoint_run_id,
                    CollectorRun.collector_type == "PREBID_AUCTION",
                )
            )
            assert collector is not None
            assert collector.status == "OK"
            assert collector.collector_version == "prebid-b6-v1"
            assert collector.summary["auction_count"] == 1
            assert collector.summary["bidder_count"] == 2
    finally:
        await _cleanup_tenant(registered.tenant_id, storage)


async def test_prebid_server_endpoint_is_explicitly_not_observable(
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
        tenant_slug=f"prebid-server-{uuid.uuid4().hex}",
        tenant_name="Prebid Server Tenant",
        publisher_name="Prebid Publisher",
        site_name="Prebid Server Site",
        url=f"{fixture_site}/prebid-server",
    )
    try:
        await run_browser_worker(once=True)

        run = await repository.get_for_tenant(
            tenant_id=registered.tenant_id,
            checkpoint_run_id=registered.checkpoint_run_id,
        )
        assert run is not None
        assert run.status == "COMPLETE"
        prebid = run.manifest["prebid"]
        assert prebid["present"] is False
        assert prebid["auctions"] == []
        assert prebid["bidders"] == []
        assert prebid["limitations"] == ["prebid_server_bidder_details_not_observable"]
        assert "server-secret" not in str(run.manifest)

        async with factory() as session:
            collector = await session.scalar(
                select(CollectorRun).where(
                    CollectorRun.checkpoint_run_id == registered.checkpoint_run_id,
                    CollectorRun.collector_type == "PREBID_AUCTION",
                )
            )
            assert collector is not None
            assert collector.status == "NOT_OBSERVABLE"
            assert collector.summary["server_endpoint_observed"] is True
            assert collector.summary["auction_count"] == 0
            assert collector.summary["bidder_count"] == 0
    finally:
        await _cleanup_tenant(registered.tenant_id, storage)


async def test_native_video_player_persists_sticky_playback_and_network_evidence(
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
        tenant_slug=f"video-native-{uuid.uuid4().hex}",
        tenant_name="Native Video Tenant",
        publisher_name="Video Publisher",
        site_name="Native Video Site",
        url=f"{fixture_site}/video-native",
    )
    try:
        async with factory() as session, session.begin():
            run = await session.get(CheckpointRun, registered.checkpoint_run_id)
            assert run is not None
            scenario = await session.scalar(
                select(BrowserScenario).where(
                    BrowserScenario.tenant_id == registered.tenant_id,
                    BrowserScenario.site_id == run.site_id,
                    BrowserScenario.code == B2_DESKTOP_SCENARIO_CODE,
                )
            )
            assert scenario is not None
            run.scenario_id = scenario.id

        await run_browser_worker(once=True)

        run = await repository.get_for_tenant(
            tenant_id=registered.tenant_id,
            checkpoint_run_id=registered.checkpoint_run_id,
        )
        assert run is not None
        assert run.status == "COMPLETE"
        assert run.collector_bundle_version == "b8-v1"
        assert run.manifest["schema"] == "browser-checkpoint-manifest/v8"
        video = run.manifest["video"]
        assert video["present"] is True
        assert video["limitations"] == ["vast_payload_not_inspected"]
        assert len(video["players"]) == 1

        players = await repository.video_players_for_tenant(
            tenant_id=registered.tenant_id,
            checkpoint_run_id=registered.checkpoint_run_id,
        )
        assert len(players) == 1
        player = players[0]
        assert player.present is True
        assert player.visible is True
        assert player.sticky is True
        assert player.fixed is True
        assert player.autoplay is True
        assert player.muted is True
        assert player.controls_present is True
        assert player.dismiss_control_present is True
        assert player.width_px == 360
        assert player.height_px == 202
        assert player.vast_request_count == 2
        assert player.vast_error_count == 1
        assert player.media_request_count == 1
        assert player.playback_started is True
        assert player.collector_version == "video-b7-v1"

        serialized_manifest = str(run.manifest)
        for forbidden in (
            "fixture-sensitive-id",
            "vast-secret",
            "wrapper-secret",
            "media-secret",
            "fixture-media-not-retained",
        ):
            assert forbidden not in serialized_manifest
        assert (
            await repository.video_players_for_tenant(
                tenant_id=uuid.uuid4(),
                checkpoint_run_id=registered.checkpoint_run_id,
            )
            == []
        )
        async with factory() as session:
            collector = await session.scalar(
                select(CollectorRun).where(
                    CollectorRun.checkpoint_run_id == registered.checkpoint_run_id,
                    CollectorRun.collector_type == "VIDEO_PLAYER",
                )
            )
            assert collector is not None
            assert collector.status == "OK"
            assert collector.collector_version == "video-b7-v1"
            assert collector.summary["player_count"] == 1
            assert collector.summary["sticky_player_count"] == 1
            assert collector.summary["playback_started_count"] == 1
            assert collector.summary["vast_request_count"] == 2
            assert collector.summary["vast_http_error_count"] == 1
            assert collector.summary["media_request_count"] == 1
    finally:
        await _cleanup_tenant(registered.tenant_id, storage)


async def test_video_network_without_native_player_is_not_observable(
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
        tenant_slug=f"video-opaque-{uuid.uuid4().hex}",
        tenant_name="Opaque Video Tenant",
        publisher_name="Video Publisher",
        site_name="Opaque Video Site",
        url=f"{fixture_site}/video-opaque",
    )
    try:
        await run_browser_worker(once=True)

        run = await repository.get_for_tenant(
            tenant_id=registered.tenant_id,
            checkpoint_run_id=registered.checkpoint_run_id,
        )
        assert run is not None
        assert run.status == "COMPLETE"
        assert run.manifest["video"] == {
            "present": False,
            "limitations": [
                "vast_payload_not_inspected",
                "video_network_player_not_observable",
            ],
            "players": [],
        }
        assert "opaque-vast-secret" not in str(run.manifest)
        assert "opaque-media-secret" not in str(run.manifest)
        assert (
            await repository.video_players_for_tenant(
                tenant_id=registered.tenant_id,
                checkpoint_run_id=registered.checkpoint_run_id,
            )
            == []
        )
        async with factory() as session:
            collector = await session.scalar(
                select(CollectorRun).where(
                    CollectorRun.checkpoint_run_id == registered.checkpoint_run_id,
                    CollectorRun.collector_type == "VIDEO_PLAYER",
                )
            )
            assert collector is not None
            assert collector.status == "NOT_OBSERVABLE"
            assert collector.summary["player_count"] == 0
            assert collector.summary["vast_request_count"] == 1
            assert collector.summary["media_request_count"] == 1
    finally:
        await _cleanup_tenant(registered.tenant_id, storage)


async def test_synthetic_performance_persists_bounded_metrics_and_provenance(
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
        tenant_slug=f"performance-{uuid.uuid4().hex}",
        tenant_name="Synthetic Performance Tenant",
        publisher_name="Performance Publisher",
        site_name="Synthetic Performance Site",
        url=f"{fixture_site}/performance-fixture?operator-secret=not-retained",
    )
    try:
        async with factory() as session, session.begin():
            run = await session.get(CheckpointRun, registered.checkpoint_run_id)
            assert run is not None
            scenario = await session.scalar(
                select(BrowserScenario).where(
                    BrowserScenario.tenant_id == registered.tenant_id,
                    BrowserScenario.site_id == run.site_id,
                    BrowserScenario.code == B2_DESKTOP_SCENARIO_CODE,
                )
            )
            assert scenario is not None
            run.scenario_id = scenario.id

        await run_browser_worker(once=True)

        run = await repository.get_for_tenant(
            tenant_id=registered.tenant_id,
            checkpoint_run_id=registered.checkpoint_run_id,
        )
        assert run is not None
        assert run.status == "COMPLETE"
        assert run.collector_bundle_version == "b8-v1"
        assert run.manifest["schema"] == "browser-checkpoint-manifest/v8"
        performance = run.manifest["performance"]
        assert performance["source"] == "synthetic_browser"
        observation = performance["observation"]
        assert observation is not None
        assert observation["lcp_ms"] > 0
        assert observation["cls"] > 0
        assert observation["inp_ms"] is None
        assert observation["inp_method"] is None
        assert observation["ttfb_ms"] >= 0
        assert observation["dom_content_loaded_ms"] > 0
        assert observation["load_event_ms"] > 0
        assert observation["long_task_count"] >= 1
        assert observation["long_task_total_ms"] >= 50
        assert observation["metadata"]["source"] == "synthetic_browser"
        assert observation["metadata"]["dom_node_count"] >= 6
        assert observation["metadata"]["resource_timing"]["entry_count"] >= 2
        assert (
            "inp_proxy_unavailable_no_qualifying_interaction"
            in observation["metadata"]["limitations"]
        )

        persisted = await repository.synthetic_performance_for_tenant(
            tenant_id=registered.tenant_id,
            checkpoint_run_id=registered.checkpoint_run_id,
        )
        assert persisted is not None
        assert persisted.lcp_ms == observation["lcp_ms"]
        assert persisted.cls == observation["cls"]
        assert persisted.inp_ms is None
        assert persisted.long_task_count is not None and persisted.long_task_count >= 1
        assert persisted.collector_version == "performance-b8-v1"
        assert persisted.metadata_json["source"] == "synthetic_browser"
        assert persisted.metadata_json["environment_synthetic"] is True
        assert persisted.metadata_json["scenario_code"] == B2_DESKTOP_SCENARIO_CODE
        assert (
            await repository.synthetic_performance_for_tenant(
                tenant_id=uuid.uuid4(),
                checkpoint_run_id=registered.checkpoint_run_id,
            )
            is None
        )
        serialized_manifest = str(run.manifest)
        for forbidden in ("resource-secret", "fetch-secret", "operator-secret"):
            assert forbidden not in serialized_manifest
        async with factory() as session:
            collector = await session.scalar(
                select(CollectorRun).where(
                    CollectorRun.checkpoint_run_id == registered.checkpoint_run_id,
                    CollectorRun.collector_type == "SYNTHETIC_PERFORMANCE",
                )
            )
            assert collector is not None
            assert collector.status == "OK"
            assert collector.collector_version == "performance-b8-v1"
            assert collector.summary["source"] == "synthetic_browser"
    finally:
        await _cleanup_tenant(registered.tenant_id, storage)


async def test_performance_collector_failure_retains_other_checkpoint_evidence(
    fixture_site: str,
) -> None:
    settings = get_settings()
    factory = get_session_factory()
    queue = JobQueue(factory)
    service = CheckpointService(factory, queue, settings)
    repository = CheckpointRepository(factory)
    storage = S3Storage(settings)
    registered = await service.register_and_enqueue(
        tenant_slug=f"performance-error-{uuid.uuid4().hex}",
        tenant_name="Performance Error Tenant",
        publisher_name="Performance Publisher",
        site_name="Performance Error Site",
        url=f"{fixture_site}/performance-error",
    )
    try:
        await run_browser_worker(once=True)
        run = await repository.get_for_tenant(
            tenant_id=registered.tenant_id,
            checkpoint_run_id=registered.checkpoint_run_id,
        )
        assert run is not None
        assert run.status == "PARTIAL"
        assert run.manifest["performance"] == {
            "source": "synthetic_browser",
            "observation": None,
        }
        assert run.manifest["normalized_state"]
        assert run.manifest["actions"][-1]["kind"] == "full_page"
        assert (
            await repository.synthetic_performance_for_tenant(
                tenant_id=registered.tenant_id,
                checkpoint_run_id=registered.checkpoint_run_id,
            )
            is None
        )
        async with factory() as session:
            collector = await session.scalar(
                select(CollectorRun).where(
                    CollectorRun.checkpoint_run_id == registered.checkpoint_run_id,
                    CollectorRun.collector_type == "SYNTHETIC_PERFORMANCE",
                )
            )
            assert collector is not None
            assert collector.status == "ERROR"
            assert collector.error_code == "PLAYWRIGHT_ERROR"
    finally:
        await _cleanup_tenant(registered.tenant_id, storage)


@pytest.mark.parametrize(
    ("scenario_code", "decision", "expected_phase"),
    [
        (B2_DESKTOP_SCENARIO_CODE, "accept", "POST_ACCEPT"),
        (B5_REJECT_SCENARIO_CODE, "reject", "POST_REJECT"),
    ],
)
async def test_cmp_action_persists_tcf_and_phase_evidence(
    fixture_site: str,
    scenario_code: str,
    decision: str,
    expected_phase: str,
) -> None:
    settings = get_settings()
    assert settings.browser_allow_private_networks
    factory = get_session_factory()
    queue = JobQueue(factory)
    service = CheckpointService(factory, queue, settings)
    repository = CheckpointRepository(factory)
    storage = S3Storage(settings)
    registered = await service.register_and_enqueue(
        tenant_slug=f"cmp-{decision}-{uuid.uuid4().hex}",
        tenant_name=f"CMP {decision} Tenant",
        publisher_name="CMP Publisher",
        site_name="CMP Site",
        url=f"{fixture_site}/cmp",
    )
    try:
        async with factory() as session, session.begin():
            run = await session.get(CheckpointRun, registered.checkpoint_run_id)
            assert run is not None
            scenario = await session.scalar(
                select(BrowserScenario).where(
                    BrowserScenario.tenant_id == registered.tenant_id,
                    BrowserScenario.site_id == run.site_id,
                    BrowserScenario.code == scenario_code,
                )
            )
            assert scenario is not None
            run.scenario_id = scenario.id
            template = await session.get(Template, run.template_id)
            assert template is not None
            template.expected_features = {
                **template.expected_features,
                "consent_adapter": {
                    "type": "manual_config",
                    "vendor": "fixture-cmp",
                    "accept_selector": "#cmp-accept",
                    "reject_selector": "#cmp-reject",
                    "ready_selector": "#cmp-complete",
                },
            }

        await run_browser_worker(once=True)

        run = await repository.get_for_tenant(
            tenant_id=registered.tenant_id,
            checkpoint_run_id=registered.checkpoint_run_id,
        )
        assert run is not None
        assert run.status == "COMPLETE"
        assert run.manifest["schema"] == "browser-checkpoint-manifest/v8"
        consent = run.manifest["consent"]
        assert consent["path"] == ("PRIMARY" if decision == "accept" else "REJECT")
        observation = consent["observation"]
        assert observation["cmp_detected"] is True
        assert observation["tcf_api_detected"] is True
        assert observation["consent_action_status"] == "COMPLETED"
        assert observation["event_status"] == "useractioncomplete"
        assert observation["cmp_id"] == 42
        expected_tc_string = f"fixture-tc-{decision}-sensitive"
        assert (
            observation["tc_string_hash"] == hashlib.sha256(expected_tc_string.encode()).hexdigest()
        )
        assert expected_tc_string not in str(run.manifest)
        assert "not-retained" not in str(run.manifest)

        cmp_row = await repository.cmp_for_tenant(
            tenant_id=registered.tenant_id,
            checkpoint_run_id=registered.checkpoint_run_id,
        )
        assert cmp_row is not None
        assert cmp_row.consent_action_status == "COMPLETED"
        assert cmp_row.tc_string_hash == observation["tc_string_hash"]
        assert (
            await repository.cmp_for_tenant(
                tenant_id=uuid.uuid4(),
                checkpoint_run_id=registered.checkpoint_run_id,
            )
            is None
        )

        phases = await repository.consent_dependencies_for_tenant(
            tenant_id=registered.tenant_id,
            checkpoint_run_id=registered.checkpoint_run_id,
        )
        assert {item.phase for item in phases} >= {"PRE_CONSENT", expected_phase}
        assert (
            await repository.consent_dependencies_for_tenant(
                tenant_id=uuid.uuid4(),
                checkpoint_run_id=registered.checkpoint_run_id,
            )
            == []
        )
        manifest_phase_items = [
            item for item in consent["phase_dependencies"] if item["phase"] == expected_phase
        ]
        assert any(decision in item["path_family"] for item in manifest_phase_items)

        artifacts = await repository.artifacts_for_tenant(
            tenant_id=registered.tenant_id,
            checkpoint_run_id=registered.checkpoint_run_id,
        )
        assert {
            "SCREENSHOT_VIEWPORT_PRECONSENT",
            "SCREENSHOT_VIEWPORT_POSTCONSENT",
        } <= {item.artifact_type for item in artifacts}
    finally:
        await _cleanup_tenant(registered.tenant_id, storage)


async def test_present_cmp_with_unavailable_required_action_is_partial(
    fixture_site: str,
) -> None:
    settings = get_settings()
    factory = get_session_factory()
    queue = JobQueue(factory)
    service = CheckpointService(factory, queue, settings)
    repository = CheckpointRepository(factory)
    storage = S3Storage(settings)
    registered = await service.register_and_enqueue(
        tenant_slug=f"cmp-unavailable-{uuid.uuid4().hex}",
        tenant_name="CMP Unavailable Tenant",
        publisher_name="CMP Publisher",
        site_name="CMP Site",
        url=f"{fixture_site}/cmp",
    )
    try:
        async with factory() as session, session.begin():
            run = await session.get(CheckpointRun, registered.checkpoint_run_id)
            assert run is not None
            scenario = await session.scalar(
                select(BrowserScenario).where(
                    BrowserScenario.tenant_id == registered.tenant_id,
                    BrowserScenario.site_id == run.site_id,
                    BrowserScenario.code == B2_DESKTOP_SCENARIO_CODE,
                )
            )
            assert scenario is not None
            run.scenario_id = scenario.id
            template = await session.get(Template, run.template_id)
            assert template is not None
            template.expected_features = {
                "consent_adapter": {
                    "type": "manual_config",
                    "vendor": "fixture-cmp",
                    "accept_selector": "#not-present",
                }
            }

        await run_browser_worker(once=True)

        run = await repository.get_for_tenant(
            tenant_id=registered.tenant_id,
            checkpoint_run_id=registered.checkpoint_run_id,
        )
        assert run is not None
        assert run.status == "PARTIAL"
        observation = run.manifest["consent"]["observation"]
        assert observation["cmp_detected"] is True
        assert observation["tcf_api_detected"] is True
        assert observation["consent_action_status"] == "UNAVAILABLE"
        artifacts = await repository.artifacts_for_tenant(
            tenant_id=registered.tenant_id,
            checkpoint_run_id=registered.checkpoint_run_id,
        )
        artifact_types = {item.artifact_type for item in artifacts}
        assert "SCREENSHOT_VIEWPORT_PRECONSENT" in artifact_types
        assert "SCREENSHOT_VIEWPORT_POSTCONSENT" not in artifact_types
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
        assert run.manifest["schema"] == "browser-checkpoint-manifest/v8"
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
        # EP-026 M3a-0: canonical retention classes (SECURITY.md §105-106) —
        # routine screenshots and raw DOM are RAW_MEDIUM; normalized DOM is
        # CORE_LONG; no CORE_MEDIUM artifact exists in the vocabulary.
        assert {
            item.artifact_type: item.retention_class
            for item in artifacts
            if item.artifact_type != "MANIFEST"
        } == {
            "SCREENSHOT_VIEWPORT": "RAW_MEDIUM",
            "SCREENSHOT_FULL_PAGE": "RAW_MEDIUM",
            "RAW_DOM": "RAW_MEDIUM",
            "NORMALIZED_DOM": "CORE_LONG",
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
            assert {run.collector_bundle_version for run in first_runs} == {"b8-v1"}
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
