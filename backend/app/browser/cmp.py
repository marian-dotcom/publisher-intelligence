from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TypedDict

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.browser.contracts import (
    BrowserTarget,
    CMPObservation,
    CollectorResult,
    CollectorStatus,
    ConsentPhaseDependencyObservation,
    NetworkObservation,
)
from app.browser.normalization import dependency_identity
from app.config.settings import Settings

CMP_COLLECTOR_VERSION = "cmp-b5-v1"
MAX_ERRORS = 20

_INIT_SCRIPT = r"""
(() => {
  const state = {
    schema: "pi-cmp-b5/v1",
    startedAt: performance.now(),
    tcfApiDetected: false,
    apiReadyAtMs: null,
    tcStateAvailableAtMs: null,
    listenerId: null,
    latest: null,
    errors: [],
    attached: false,
  };
  window.__piCmpB5 = state;
  const at = () => Math.max(0, Math.round(performance.now() - state.startedAt));
  const text = (value, max = 100) => {
    if (value === null || value === undefined) return null;
    if (!["string", "number", "boolean"].includes(typeof value)) return null;
    return String(value).slice(0, max);
  };
  const error = (value) => {
    if (state.errors.length < 20) state.errors.push(text(value, 100) || "TCF_API_ERROR");
  };
  const safeData = (data) => {
    if (!data || typeof data !== "object") return null;
    return {
      tcString: text(data.tcString, 10000),
      gdprApplies: typeof data.gdprApplies === "boolean" ? data.gdprApplies : null,
      cmpId: Number.isInteger(data.cmpId) ? data.cmpId : null,
      cmpVersion: Number.isInteger(data.cmpVersion) ? data.cmpVersion : null,
      cmpStatus: text(data.cmpStatus, 30),
      eventStatus: text(data.eventStatus, 30),
    };
  };
  state.snapshot = () => ({
    schema: state.schema,
    capturedAtMs: at(),
    tcfApiDetected: state.tcfApiDetected,
    apiReadyAtMs: state.apiReadyAtMs,
    tcStateAvailableAtMs: state.tcStateAvailableAtMs,
    latest: state.latest,
    errors: state.errors.slice(0, 20),
  });
  state.finish = () => {
    const api = window.__tcfapi;
    if (typeof api === "function" && Number.isInteger(state.listenerId)) {
      try { api("removeEventListener", 2, () => {}, state.listenerId); } catch (_) {}
    }
    return state.snapshot();
  };
  const attach = () => {
    const api = window.__tcfapi;
    if (typeof api !== "function") return;
    state.tcfApiDetected = true;
    if (state.attached) return;
    state.attached = true;
    try {
      api("ping", 2, (ping, success) => {
        if (success === false) error("PING_FAILED");
        if (ping && (ping.cmpLoaded === true || ping.cmpStatus === "loaded")) {
          if (state.apiReadyAtMs === null) state.apiReadyAtMs = at();
        }
      });
    } catch (_) { error("PING_ERROR"); }
    try {
      api("addEventListener", 2, (data, success) => {
        if (success === false) { error("ADD_EVENT_LISTENER_FAILED"); return; }
        const safe = safeData(data);
        if (!safe) return;
        state.latest = safe;
        if (Number.isInteger(data.listenerId)) state.listenerId = data.listenerId;
        if (state.apiReadyAtMs === null && safe.cmpStatus === "loaded") state.apiReadyAtMs = at();
        if (safe.tcString && state.tcStateAvailableAtMs === null) state.tcStateAvailableAtMs = at();
        if (safe.cmpStatus === "error") error("CMP_STATUS_ERROR");
      });
    } catch (_) { error("ADD_EVENT_LISTENER_ERROR"); }
  };
  attach();
  let attempts = 0;
  const timer = setInterval(() => {
    attempts += 1;
    attach();
    if (state.attached || attempts >= 400) clearInterval(timer);
  }, 25);
})();
"""


@dataclass(frozen=True, slots=True)
class CMPPreState:
    tcf_api_detected: bool
    ui_detected: bool
    ui_detected_at_ms: int | None
    selector: str | None
    clock_offset_ms: int

    @property
    def cmp_detected(self) -> bool:
        return self.tcf_api_detected or self.ui_detected


@dataclass(frozen=True, slots=True)
class CMPCollection:
    observation: CMPObservation
    result: CollectorResult
    action_boundary_ms: int | None
    required_action_failed: bool
    capture_pre: bool
    capture_post: bool


class ParsedTCFSnapshot(TypedDict):
    tcf_api_detected: bool
    captured_at_ms: int | None
    api_ready_at_ms: int | None
    tc_state_available_at_ms: int | None
    gdpr_applies: bool | None
    tc_string_hash: str | None
    cmp_id: int | None
    cmp_version: int | None
    cmp_status: str | None
    event_status: str | None
    errors: tuple[str, ...]


@dataclass(slots=True)
class _PhaseAggregate:
    stable_key: str
    host: str
    path_family: str
    resource_type: str
    category: str
    request_count: int = 0
    error_count: int = 0
    first_request_at_ms: int | None = None


def _text(value: object, limit: int = 100) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    cleaned = str(value).strip()
    return cleaned[:limit] if cleaned else None


def _integer(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and 0 <= value <= 2_147_483_647:
        return int(value)
    return None


def parse_tcf_snapshot(raw: object) -> ParsedTCFSnapshot:
    payload = raw if isinstance(raw, dict) else {}
    latest_raw = payload.get("latest")
    latest = latest_raw if isinstance(latest_raw, dict) else {}
    tc_string = _text(latest.get("tcString"), 10_000)
    errors_raw = payload.get("errors")
    errors = errors_raw if isinstance(errors_raw, list) else []
    return {
        "tcf_api_detected": payload.get("tcfApiDetected") is True,
        "captured_at_ms": _integer(payload.get("capturedAtMs")),
        "api_ready_at_ms": _integer(payload.get("apiReadyAtMs")),
        "tc_state_available_at_ms": _integer(payload.get("tcStateAvailableAtMs")),
        "gdpr_applies": (
            latest.get("gdprApplies") if isinstance(latest.get("gdprApplies"), bool) else None
        ),
        "tc_string_hash": (
            hashlib.sha256(tc_string.encode()).hexdigest() if tc_string is not None else None
        ),
        "cmp_id": _integer(latest.get("cmpId")),
        "cmp_version": _integer(latest.get("cmpVersion")),
        "cmp_status": _text(latest.get("cmpStatus"), 30),
        "event_status": _text(latest.get("eventStatus"), 30),
        "errors": tuple(
            item
            for item in (_text(value, 100) for value in errors[:MAX_ERRORS])
            if item is not None
        ),
    }


def summarize_consent_dependencies(
    observations: list[NetworkObservation],
    *,
    action_boundary_ms: int | None,
    consent_path: str,
) -> list[ConsentPhaseDependencyObservation]:
    aggregates: dict[tuple[str, str], _PhaseAggregate] = {}
    post_phase = "POST_REJECT" if consent_path == "REJECT" else "POST_ACCEPT"
    for observation in observations:
        identity = dependency_identity(observation.url, observation.resource_type)
        if identity is None:
            continue
        observed_at_ms = observation.observed_at_ms
        phase = (
            post_phase
            if action_boundary_ms is not None
            and observed_at_ms is not None
            and observed_at_ms >= action_boundary_ms
            else "PRE_CONSENT"
        )
        key = (phase, identity["stable_key"])
        state = aggregates.setdefault(
            key,
            _PhaseAggregate(
                stable_key=identity["stable_key"],
                host=identity["host"],
                path_family=identity["path_family"],
                resource_type=identity["resource_type"],
                category=identity["category"],
                first_request_at_ms=observed_at_ms,
            ),
        )
        state.request_count += 1
        if observation.error_text is not None or (
            observation.status is not None and observation.status >= 400
        ):
            state.error_count += 1
        first = state.first_request_at_ms
        if observed_at_ms is not None and (first is None or observed_at_ms < first):
            state.first_request_at_ms = observed_at_ms
    result = []
    for key in sorted(aggregates)[:2_000]:
        state = aggregates[key]
        result.append(
            ConsentPhaseDependencyObservation(
                phase=key[0],
                stable_key=state.stable_key,
                host=state.host,
                path_family=state.path_family,
                resource_type=state.resource_type,
                category=state.category,
                request_count=state.request_count,
                error_count=state.error_count,
                first_request_at_ms=state.first_request_at_ms,
            )
        )
    return result


class CMPCollector:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def attach(self, page: Page) -> None:
        await page.add_init_script(_INIT_SCRIPT)

    @staticmethod
    def failure(target: BrowserTarget, started_at: datetime) -> CMPCollection:
        observation = CMPObservation(
            cmp_detected=False,
            tcf_api_detected=False,
            consent_action=target.consent_path,
            consent_action_status="ERROR",
            vendor=(target.consent_adapter.vendor if target.consent_adapter is not None else None),
        )
        return CMPCollection(
            observation=observation,
            result=CollectorResult(
                collector_type="CMP_CONSENT",
                collector_version=CMP_COLLECTOR_VERSION,
                status="ERROR",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                summary={
                    "cmp_detected": False,
                    "consent_action": target.consent_path,
                    "consent_action_status": "ERROR",
                },
                error_code="PLAYWRIGHT_ERROR",
                error_message="CMP observation failed",
            ),
            action_boundary_ms=None,
            required_action_failed=target.consent_path != "NONE",
            capture_pre=False,
            capture_post=False,
        )

    async def observe_pre(
        self,
        page: Page,
        target: BrowserTarget,
        elapsed_ms: Callable[[], int],
    ) -> CMPPreState:
        selector = self._selector(target)
        raw = await self._snapshot(page)
        parsed = parse_tcf_snapshot(raw)
        ui_detected = False
        ui_detected_at_ms = None
        if selector is not None:
            try:
                await page.locator(selector).first.wait_for(
                    state="visible",
                    timeout=self._settings.browser_consent_discovery_timeout_ms,
                )
                ui_detected = True
                ui_detected_at_ms = elapsed_ms()
            except PlaywrightTimeoutError:
                pass
            raw = await self._snapshot(page)
            parsed = parse_tcf_snapshot(raw)
        return CMPPreState(
            tcf_api_detected=parsed["tcf_api_detected"] is True,
            ui_detected=ui_detected,
            ui_detected_at_ms=ui_detected_at_ms,
            selector=selector,
            clock_offset_ms=max(0, elapsed_ms() - (parsed["captured_at_ms"] or 0)),
        )

    async def act_and_collect(
        self,
        page: Page,
        target: BrowserTarget,
        pre: CMPPreState,
        elapsed_ms: Callable[[], int],
    ) -> CMPCollection:
        started_at = datetime.now(UTC)
        action = target.consent_path
        action_status = "NOT_REQUESTED" if action == "NONE" else "NOT_PRESENT"
        action_started_at_ms = None
        action_completed_at_ms = None
        required_failed = False
        capture_post = False
        if action != "NONE" and pre.cmp_detected:
            if pre.selector is None or not pre.ui_detected:
                action_status = "UNAVAILABLE"
                required_failed = True
            else:
                action_started_at_ms = int(elapsed_ms())
                try:
                    await page.locator(pre.selector).first.click(
                        timeout=self._settings.browser_consent_action_timeout_ms
                    )
                    ready_selector = (
                        target.consent_adapter.ready_selector
                        if target.consent_adapter is not None
                        else None
                    )
                    if ready_selector is not None:
                        await page.locator(ready_selector).first.wait_for(
                            state="visible",
                            timeout=self._settings.browser_consent_action_timeout_ms,
                        )
                    action_completed_at_ms = int(elapsed_ms())
                    action_status = "COMPLETED"
                    capture_post = True
                    await page.wait_for_timeout(
                        self._settings.browser_post_consent_stabilization_ms
                    )
                except PlaywrightTimeoutError:
                    action_status = "TIMEOUT"
                    required_failed = True
                except PlaywrightError:
                    action_status = "ERROR"
                    required_failed = True
        raw = await self._finish(page)
        parsed = parse_tcf_snapshot(raw)
        api_ready_at_ms = self._on_network_clock(parsed["api_ready_at_ms"], pre.clock_offset_ms)
        tc_state_available_at_ms = self._on_network_clock(
            parsed["tc_state_available_at_ms"], pre.clock_offset_ms
        )
        cmp_detected = pre.ui_detected or parsed["tcf_api_detected"] is True
        status: CollectorStatus = (
            "NOT_PRESENT"
            if not cmp_detected
            else "NOT_OBSERVABLE"
            if action_status == "UNAVAILABLE"
            else "ERROR"
            if action_status in {"TIMEOUT", "ERROR"}
            else "OK"
        )
        observation = CMPObservation(
            cmp_detected=cmp_detected,
            tcf_api_detected=parsed["tcf_api_detected"] is True,
            ui_detected_at_ms=pre.ui_detected_at_ms,
            api_ready_at_ms=api_ready_at_ms,
            consent_action=action,
            consent_action_status=action_status,
            action_started_at_ms=action_started_at_ms,
            action_completed_at_ms=action_completed_at_ms,
            tc_state_available_at_ms=tc_state_available_at_ms,
            gdpr_applies=parsed["gdpr_applies"],
            tc_string_hash=parsed["tc_string_hash"],
            tcf_error_codes=parsed["errors"],
            cmp_id=parsed["cmp_id"],
            cmp_version=parsed["cmp_version"],
            cmp_status=parsed["cmp_status"],
            event_status=parsed["event_status"],
            vendor=(target.consent_adapter.vendor if target.consent_adapter is not None else None),
        )
        return CMPCollection(
            observation=observation,
            result=CollectorResult(
                collector_type="CMP_CONSENT",
                collector_version=CMP_COLLECTOR_VERSION,
                status=status,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                summary={
                    "cmp_detected": cmp_detected,
                    "tcf_api_detected": observation.tcf_api_detected,
                    "consent_action": action,
                    "consent_action_status": action_status,
                    "tcf_error_count": len(observation.tcf_error_codes),
                },
            ),
            action_boundary_ms=action_started_at_ms,
            required_action_failed=required_failed,
            capture_pre=pre.cmp_detected,
            capture_post=capture_post,
        )

    @staticmethod
    def _selector(target: BrowserTarget) -> str | None:
        adapter = target.consent_adapter
        if adapter is None:
            return None
        return (
            adapter.reject_selector if target.consent_path == "REJECT" else adapter.accept_selector
        )

    @staticmethod
    def _on_network_clock(value: int | None, clock_offset_ms: int) -> int | None:
        return value + clock_offset_ms if value is not None else None

    @staticmethod
    async def _snapshot(page: Page) -> object:
        return await page.evaluate(
            "() => window.__piCmpB5 && window.__piCmpB5.snapshot "
            "? window.__piCmpB5.snapshot() : null"
        )

    @staticmethod
    async def _finish(page: Page) -> object:
        return await page.evaluate(
            "() => window.__piCmpB5 && window.__piCmpB5.finish ? window.__piCmpB5.finish() : null"
        )
