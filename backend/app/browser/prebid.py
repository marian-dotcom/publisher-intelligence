from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlsplit

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page

from app.browser.contracts import (
    CollectorResult,
    CollectorStatus,
    NetworkObservation,
    PrebidAuctionObservation,
    PrebidBidderObservation,
)

PREBID_COLLECTOR_VERSION = "prebid-b6-v1"
MAX_EVENTS = 2_000
_BIDDER_CODE = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
_AUCTION_EVENT_TYPES = {
    "auctionInit",
    "auctionEnd",
    "auctionTimeout",
    "bidRequested",
    "bidResponse",
    "noBid",
    "bidTimeout",
    "bidWon",
}

_INIT_SCRIPT = r"""
(() => {
  const state = {
    schema: "pi-prebid-b6/v1",
    startedAt: performance.now(),
    present: false,
    observable: false,
    events: [],
    seen: new Set(),
    auctions: new Map(),
    nextAuction: 1,
    errors: [],
  };
  const auctionEvents = new Set([
    "auctionInit", "auctionEnd", "auctionTimeout", "bidRequested",
    "bidResponse", "noBid", "bidTimeout", "bidWon"
  ]);
  window.__piPrebidB6 = state;
  const at = () => Math.max(0, Math.round(performance.now() - state.startedAt));
  const text = (value, max = 100) => {
    if (typeof value !== "string" && typeof value !== "number") return null;
    const result = String(value).trim();
    return result ? result.slice(0, max) : null;
  };
  const number = (value) => Number.isFinite(value) && value >= 0 ? value : null;
  const auctionKey = (raw) => {
    const value = text(raw, 200);
    if (!value) return "auction-unassigned";
    if (!state.auctions.has(value) && state.auctions.size < 200) {
      state.auctions.set(value, `auction-${String(state.nextAuction++).padStart(3, "0")}`);
    }
    return state.auctions.get(value) || "auction-overflow";
  };
  const bidder = (value) => {
    const result = text(value, 100);
    return result && /^[A-Za-z0-9_.-]+$/.test(result) ? result : null;
  };
  const project = (event, occurrence) => {
    if (!event || typeof event !== "object") return [];
    const type = text(event.eventType, 50);
    const args = event.args;
    if (!type || !auctionEvents.has(type) || !args) return [];
    const elapsedAtMs = number(event.elapsedTime);
    const rawAuction = args.auctionId || args.auction_id || args.auction;
    const base = {
      event_type: type,
      auction_key: auctionKey(rawAuction),
      elapsed_at_ms: elapsedAtMs,
      configured_timeout_ms: number(args.timeout),
      ad_unit_count: Array.isArray(args.adUnits) ? Math.min(args.adUnits.length, 500) : null,
      response_time_ms: number(args.timeToRespond),
    };
    let bidders = [];
    if (type === "bidTimeout" && Array.isArray(args)) {
      return args.slice(0, 100).map(item => ({
        ...base,
        auction_key: auctionKey(item && (item.auctionId || item.auction_id)),
        bidder_code: bidder(item && (item.bidder || item.bidderCode)),
        occurrence,
      }));
    } else if (type === "bidRequested" && Array.isArray(args.bids)) {
      bidders = args.bids
        .map(item => bidder(item && (item.bidder || item.bidderCode)))
        .filter(Boolean);
      if (!bidders.length) bidders = [bidder(args.bidderCode || args.bidder)].filter(Boolean);
    } else {
      bidders = [bidder(args.bidderCode || args.bidder)].filter(Boolean);
    }
    if (!bidders.length) bidders = [null];
    return bidders.slice(0, 100).map(code => ({...base, bidder_code: code, occurrence}));
  };
  const sample = () => {
    const pbjs = window.pbjs;
    if (!pbjs || typeof pbjs !== "object") return;
    state.present = true;
    if (typeof pbjs.getEvents !== "function") return;
    state.observable = true;
    try {
      const events = pbjs.getEvents();
      if (!Array.isArray(events)) return;
      const occurrences = {};
      for (const event of events.slice(-2000)) {
        const type = text(event && event.eventType, 50) || "unknown";
        const elapsed = number(event && event.elapsedTime);
        const args = event && event.args;
        const rawAuction = args && (args.auctionId || args.auction_id || args.auction);
        const code = args && (args.bidderCode || args.bidder);
        const root = `${type}|${elapsed}|${text(rawAuction, 200)}|${text(code, 100)}`;
        occurrences[root] = (occurrences[root] || 0) + 1;
        for (const item of project(event, occurrences[root])) {
          const signature = `${root}|${item.bidder_code}|${item.occurrence}`;
          if (state.seen.has(signature) || state.events.length >= 2000) continue;
          state.seen.add(signature);
          state.events.push(item);
        }
      }
    } catch (_) {
      if (state.errors.length < 20) state.errors.push("GET_EVENTS_ERROR");
    }
  };
  const safeSnapshot = () => {
    sample();
    const pbjs = window.pbjs;
    let version = null;
    let configuredTimeoutMs = null;
    let serverSideConfigured = false;
    let installedModules = [];
    let configuredAdUnitCount = null;
    let configuredBidders = [];
    let targetingKeys = [];
    try {
      const rawVersion = pbjs && typeof pbjs.getVersion === "function"
        ? pbjs.getVersion() : pbjs && pbjs.version;
      version = text(rawVersion, 100);
    } catch (_) {}
    try {
      if (pbjs && typeof pbjs.getConfig === "function") {
        const timeout = pbjs.getConfig("bidderTimeout");
        const rawTimeout = timeout && typeof timeout === "object"
          ? timeout.bidderTimeout : timeout;
        configuredTimeoutMs = number(rawTimeout);
        const s2s = pbjs.getConfig("s2sConfig");
        serverSideConfigured = Boolean(s2s && (Array.isArray(s2s) ? s2s.length : true));
      }
    } catch (_) {}
    try {
      installedModules = Array.isArray(pbjs && pbjs.installedModules)
        ? pbjs.installedModules.map(item => text(item, 100)).filter(Boolean).slice(0, 200) : [];
    } catch (_) {}
    try {
      const adUnits = pbjs && pbjs.adUnits;
      if (Array.isArray(adUnits)) {
        configuredAdUnitCount = Math.min(adUnits.length, 500);
        const codes = new Set();
        for (const unit of adUnits.slice(0, 500)) {
          for (const bid of (Array.isArray(unit && unit.bids) ? unit.bids : []).slice(0, 100)) {
            const code = bidder(bid && bid.bidder);
            if (code) codes.add(code);
          }
        }
        configuredBidders = Array.from(codes).slice(0, 500);
      }
    } catch (_) {}
    try {
      if (pbjs && typeof pbjs.getAdserverTargeting === "function") {
        const targeting = pbjs.getAdserverTargeting();
        const keys = new Set();
        if (targeting && typeof targeting === "object") {
          for (const value of Object.values(targeting).slice(0, 500)) {
            if (!value || typeof value !== "object") continue;
            for (const key of Object.keys(value).slice(0, 100)) {
              if (/^hb_[A-Za-z0-9_.-]{1,80}$/.test(key)) keys.add(key);
            }
          }
        }
        targetingKeys = Array.from(keys).sort().slice(0, 200);
      }
    } catch (_) {}
    return {
      schema: state.schema,
      captured_at_ms: at(),
      present: state.present,
      observable: state.observable,
      version,
      configured_timeout_ms: configuredTimeoutMs,
      server_side_configured: serverSideConfigured,
      installed_modules: installedModules,
      configured_ad_unit_count: configuredAdUnitCount,
      configured_bidders: configuredBidders,
      targeting_keys: targetingKeys,
      events: state.events.slice(0, 2000),
      errors: state.errors.slice(0, 20),
    };
  };
  state.snapshot = safeSnapshot;
  sample();
  let attempts = 0;
  const timer = setInterval(() => {
    attempts += 1;
    sample();
    if (attempts >= 600) clearInterval(timer);
  }, 100);
})();
"""


@dataclass(slots=True)
class _AuctionState:
    key: str
    started_at_ms: int | None = None
    ended_at_ms: int | None = None
    configured_timeout_ms: int | None = None
    ad_unit_count: int | None = None
    bidder_request_count: int = 0
    bid_response_count: int = 0
    no_bid_count: int = 0
    timeout_count: int = 0


@dataclass(slots=True)
class _BidderState:
    auction_key: str
    bidder_code: str
    request_count: int = 0
    response_count: int = 0
    no_bid_count: int = 0
    timeout_count: int = 0
    winning_bid_count: int = 0
    response_times: list[float] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class PrebidCollection:
    present: bool
    version: str | None
    server_side_configured: bool
    targeting_keys: list[str]
    limitations: list[str]
    auctions: list[PrebidAuctionObservation]
    bidders: list[PrebidBidderObservation]
    result: CollectorResult


def _text(value: object, limit: int = 100) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    result = str(value).strip()
    return result[:limit] if result else None


def _integer(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return None
    return min(int(value), 2_147_483_647)


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return None
    return min(float(value), 2_147_483_647.0)


def _bidder(value: object) -> str | None:
    result = _text(value)
    return result if result is not None and _BIDDER_CODE.fullmatch(result) else None


def prebid_server_endpoint_observed(observations: list[NetworkObservation]) -> bool:
    for observation in observations:
        path = urlsplit(observation.url).path.lower()
        if "/openrtb2/auction" in path or "/openrtb2/amp" in path:
            return True
    return False


def first_ad_server_request_at_ms(
    observations: list[NetworkObservation], *, after_ms: int | None = None
) -> int | None:
    candidates = []
    for observation in observations:
        parsed = urlsplit(observation.url)
        host = (parsed.hostname or "").lower()
        path = parsed.path.lower()
        if (
            "doubleclick" in host
            or "googlesyndication" in host
            or "securepubads" in host
            or "/gampad/ads" in path
        ) and observation.request_started_at_ms is not None:
            if after_ms is not None and observation.request_started_at_ms < after_ms:
                continue
            candidates.append(observation.request_started_at_ms)
    return min(candidates) if candidates else None


def parse_prebid_snapshot(
    raw: object,
    observations: list[NetworkObservation],
    *,
    network_clock_ms: int,
) -> tuple[
    bool,
    bool,
    str | None,
    bool,
    list[str],
    list[str],
    list[PrebidAuctionObservation],
    list[PrebidBidderObservation],
]:
    payload = raw if isinstance(raw, dict) else {}
    present = payload.get("present") is True
    observable = payload.get("observable") is True
    version = _text(payload.get("version"))
    server_side_configured = payload.get("server_side_configured") is True
    captured_at_ms = _integer(payload.get("captured_at_ms")) or 0
    offset = max(0, network_clock_ms - captured_at_ms)
    default_timeout = _integer(payload.get("configured_timeout_ms"))
    default_ad_units = _integer(payload.get("configured_ad_unit_count"))
    targeting = payload.get("targeting_keys")
    targeting_keys = (
        sorted({item for item in (_text(value) for value in targeting) if item is not None})[:200]
        if isinstance(targeting, list)
        else []
    )
    modules = payload.get("installed_modules")
    installed_modules = (
        sorted({item for item in (_text(value) for value in modules) if item is not None})[:200]
        if isinstance(modules, list)
        else []
    )
    auctions: dict[str, _AuctionState] = {}
    bidders: dict[tuple[str, str], _BidderState] = {}
    raw_events = payload.get("events")
    events = raw_events[:MAX_EVENTS] if isinstance(raw_events, list) else []
    for event in events:
        if not isinstance(event, dict):
            continue
        event_type = _text(event.get("event_type"), 50)
        auction_key = _text(event.get("auction_key"), 50)
        if event_type not in _AUCTION_EVENT_TYPES or auction_key is None:
            continue
        state = auctions.setdefault(auction_key, _AuctionState(key=auction_key))
        elapsed = _integer(event.get("elapsed_at_ms"))
        elapsed_on_network_clock = elapsed + offset if elapsed is not None else None
        state.configured_timeout_ms = (
            _integer(event.get("configured_timeout_ms"))
            or state.configured_timeout_ms
            or default_timeout
        )
        state.ad_unit_count = (
            _integer(event.get("ad_unit_count")) or state.ad_unit_count or default_ad_units
        )
        if event_type == "auctionInit" and state.started_at_ms is None:
            state.started_at_ms = elapsed_on_network_clock
        elif event_type in {"auctionEnd", "auctionTimeout"}:
            state.ended_at_ms = elapsed_on_network_clock
        bidder_code = _bidder(event.get("bidder_code"))
        bidder_state = None
        if bidder_code is not None:
            bidder_state = bidders.setdefault(
                (auction_key, bidder_code),
                _BidderState(auction_key=auction_key, bidder_code=bidder_code),
            )
        if event_type == "bidRequested":
            state.bidder_request_count += 1
            if bidder_state is not None:
                bidder_state.request_count += 1
        elif event_type == "bidResponse":
            state.bid_response_count += 1
            if bidder_state is not None:
                bidder_state.response_count += 1
                response_time = _number(event.get("response_time_ms"))
                if response_time is not None and len(bidder_state.response_times) < 1_000:
                    bidder_state.response_times.append(response_time)
        elif event_type == "noBid":
            state.no_bid_count += 1
            if bidder_state is not None:
                bidder_state.no_bid_count += 1
        elif event_type in {"bidTimeout", "auctionTimeout"}:
            state.timeout_count += 1
            if bidder_state is not None:
                bidder_state.timeout_count += 1
        elif event_type == "bidWon" and bidder_state is not None:
            bidder_state.winning_bid_count += 1
    auction_rows = [
        PrebidAuctionObservation(
            auction_key=state.key,
            started_at_ms=state.started_at_ms,
            ended_at_ms=state.ended_at_ms,
            configured_timeout_ms=state.configured_timeout_ms,
            ad_unit_count=state.ad_unit_count,
            bidder_request_count=state.bidder_request_count,
            bid_response_count=state.bid_response_count,
            no_bid_count=state.no_bid_count,
            timeout_count=state.timeout_count,
            first_ad_server_request_at_ms=first_ad_server_request_at_ms(
                observations,
                after_ms=(
                    state.ended_at_ms if state.ended_at_ms is not None else state.started_at_ms
                ),
            ),
        )
        for state in (auctions[key] for key in sorted(auctions))
    ]
    bidder_rows = []
    for key in sorted(bidders):
        bidder_item = bidders[key]
        times = bidder_item.response_times
        bidder_rows.append(
            PrebidBidderObservation(
                auction_key=bidder_item.auction_key,
                bidder_code=bidder_item.bidder_code,
                request_count=bidder_item.request_count,
                response_count=bidder_item.response_count,
                no_bid_count=bidder_item.no_bid_count,
                timeout_count=bidder_item.timeout_count,
                response_time_ms_min=min(times) if times else None,
                response_time_ms_max=max(times) if times else None,
                response_time_ms_avg=(sum(times) / len(times) if times else None),
                winning_bid_count=bidder_item.winning_bid_count,
            )
        )
    return (
        present,
        observable,
        version,
        server_side_configured,
        installed_modules,
        targeting_keys,
        auction_rows,
        bidder_rows,
    )


class PrebidCollector:
    async def attach(self, page: Page) -> None:
        await page.add_init_script(_INIT_SCRIPT)

    async def collect(
        self,
        page: Page,
        observations: list[NetworkObservation],
        network_clock_ms: int,
    ) -> PrebidCollection:
        started_at = datetime.now(UTC)
        server_endpoint = prebid_server_endpoint_observed(observations)
        try:
            raw = await page.evaluate(
                "() => window.__piPrebidB6 && window.__piPrebidB6.snapshot "
                "? window.__piPrebidB6.snapshot() : null"
            )
            (
                present,
                observable,
                version,
                server_side_configured,
                modules,
                targeting_keys,
                auctions,
                bidders,
            ) = parse_prebid_snapshot(raw, observations, network_clock_ms=network_clock_ms)
            hidden_server_detail = server_endpoint and not observable
            limitations = (
                ["prebid_server_bidder_details_not_observable"]
                if hidden_server_detail or server_side_configured
                else []
            )
            status: CollectorStatus = (
                "OK"
                if observable
                else "NOT_OBSERVABLE"
                if present or server_endpoint
                else "NOT_PRESENT"
            )
            return PrebidCollection(
                present=present,
                version=version,
                server_side_configured=server_side_configured,
                targeting_keys=targeting_keys,
                limitations=limitations,
                auctions=auctions,
                bidders=bidders,
                result=CollectorResult(
                    collector_type="PREBID_AUCTION",
                    collector_version=PREBID_COLLECTOR_VERSION,
                    status=status,
                    started_at=started_at,
                    completed_at=datetime.now(UTC),
                    summary={
                        "prebid_present": present,
                        "prebid_observable": observable,
                        "prebid_version": version,
                        "installed_modules": modules,
                        "server_side_configured": server_side_configured,
                        "server_endpoint_observed": server_endpoint,
                        "auction_count": len(auctions),
                        "bidder_count": len({item.bidder_code for item in bidders}),
                        "targeting_key_count": len(targeting_keys),
                        "limitations": limitations,
                    },
                ),
            )
        except PlaywrightError:
            return PrebidCollection(
                present=False,
                version=None,
                server_side_configured=False,
                targeting_keys=[],
                limitations=[],
                auctions=[],
                bidders=[],
                result=CollectorResult(
                    collector_type="PREBID_AUCTION",
                    collector_version=PREBID_COLLECTOR_VERSION,
                    status="ERROR",
                    started_at=started_at,
                    completed_at=datetime.now(UTC),
                    summary={"server_endpoint_observed": server_endpoint},
                    error_code="PLAYWRIGHT_ERROR",
                    error_message="Prebid snapshot failed",
                ),
            )
