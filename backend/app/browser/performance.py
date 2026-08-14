from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page

from app.browser.contracts import CollectorResult, SyntheticPerformanceObservation

PERFORMANCE_COLLECTOR_VERSION = "performance-b8-v1"
MAX_ENTRY_SAMPLES = 2_000
MAX_TIME_MS = 86_400_000.0
MAX_CLS = 10_000.0
MAX_RESOURCE_BYTES = 1_000_000_000_000
MAX_DOM_NODES = 10_000_000

_SUPPORTED_TYPES = {
    "event",
    "largest-contentful-paint",
    "layout-shift",
    "longtask",
    "navigation",
    "resource",
}
_INITIATOR_TYPES = {
    "audio",
    "beacon",
    "body",
    "css",
    "early-hint",
    "embed",
    "fetch",
    "frame",
    "iframe",
    "icon",
    "image",
    "img",
    "input",
    "link",
    "navigation",
    "object",
    "ping",
    "script",
    "track",
    "video",
    "xmlhttprequest",
}
_OBSERVER_ERRORS = {
    "EVENT_OBSERVER_ERROR",
    "LCP_OBSERVER_ERROR",
    "LAYOUT_SHIFT_OBSERVER_ERROR",
    "LONG_TASK_OBSERVER_ERROR",
    "SNAPSHOT_ERROR",
}

_INIT_SCRIPT = r"""
(() => {
  const state = {
    schema: "pi-performance-b8/v1",
    lcpCandidates: [],
    layoutShifts: [],
    interactions: [],
    longTaskCount: 0,
    longTaskTotalMs: 0,
    errors: [],
    observers: [],
    wasHidden: document.visibilityState !== "visible",
  };
  window.__piPerformanceB8 = state;

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState !== "visible") state.wasHidden = true;
  }, {passive: true});

  const supported = new Set(Array.from(PerformanceObserver.supportedEntryTypes || []));
  const rememberError = (code) => {
    if (state.errors.length < 20) state.errors.push(code);
  };
  const observe = (type, callback, code, extra = {}) => {
    if (!supported.has(type)) return;
    try {
      const observer = new PerformanceObserver(callback);
      observer.observe({type, buffered: true, ...extra});
      state.observers.push(observer);
    } catch (_) { rememberError(code); }
  };

  observe("largest-contentful-paint", list => {
    for (const entry of list.getEntries()) {
      if (state.lcpCandidates.length >= 2000) break;
      state.lcpCandidates.push(entry.startTime);
    }
  }, "LCP_OBSERVER_ERROR");

  observe("layout-shift", list => {
    for (const entry of list.getEntries()) {
      if (entry.hadRecentInput || state.layoutShifts.length >= 2000) continue;
      state.layoutShifts.push([entry.startTime, entry.value]);
    }
  }, "LAYOUT_SHIFT_OBSERVER_ERROR");

  observe("longtask", list => {
    for (const entry of list.getEntries()) {
      state.longTaskCount = Math.min(state.longTaskCount + 1, 1000000);
      state.longTaskTotalMs = Math.min(state.longTaskTotalMs + entry.duration, 86400000);
    }
  }, "LONG_TASK_OBSERVER_ERROR");

  observe("event", list => {
    for (const entry of list.getEntries()) {
      if (!entry.interactionId || state.interactions.length >= 2000) continue;
      state.interactions.push([entry.interactionId, entry.duration]);
    }
  }, "EVENT_OBSERVER_ERROR", {durationThreshold: 16});

  state.snapshot = () => {
    try {
      const navigation = performance.getEntriesByType("navigation")[0] || null;
      const resources = performance.getEntriesByType("resource");
      const initiatorCounts = {};
      let durationTotalMs = 0;
      let transferSizeTotalBytes = 0;
      for (const entry of resources.slice(0, 2000)) {
        const initiator = String(entry.initiatorType || "other").toLowerCase().slice(0, 40);
        initiatorCounts[initiator] = Math.min((initiatorCounts[initiator] || 0) + 1, 1000000);
        durationTotalMs = Math.min(durationTotalMs + Number(entry.duration || 0), 86400000);
        transferSizeTotalBytes = Math.min(
          transferSizeTotalBytes + Number(entry.transferSize || 0), 1000000000000
        );
      }
      return {
        schema: state.schema,
        supported_entry_types: Array.from(supported).slice(0, 100),
        was_hidden: state.wasHidden,
        measurement_end_ms: performance.now(),
        lcp_candidates: state.lcpCandidates.slice(0, 2000),
        layout_shifts: state.layoutShifts.slice(0, 2000),
        interactions: state.interactions.slice(0, 2000),
        long_task_count: state.longTaskCount,
        long_task_total_ms: state.longTaskTotalMs,
        navigation: navigation ? {
          response_start: navigation.responseStart,
          dom_content_loaded_end: navigation.domContentLoadedEventEnd,
          load_event_end: navigation.loadEventEnd,
        } : null,
        resources: {
          entry_count: Math.min(resources.length, 1000000),
          sampled_entry_count: Math.min(resources.length, 2000),
          truncated: resources.length > 2000,
          duration_total_ms: durationTotalMs,
          transfer_size_total_bytes: transferSizeTotalBytes,
          initiator_counts: initiatorCounts,
        },
        dom_node_count: Math.min(document.getElementsByTagName("*").length, 10000000),
        errors: state.errors.slice(0, 20),
        samples_truncated: {
          lcp: state.lcpCandidates.length >= 2000,
          layout_shift: state.layoutShifts.length >= 2000,
          interaction: state.interactions.length >= 2000,
        },
      };
    } catch (_) {
      rememberError("SNAPSHOT_ERROR");
      return null;
    }
  };
})();
"""


@dataclass(frozen=True, slots=True)
class PerformanceCollection:
    observation: SyntheticPerformanceObservation | None
    result: CollectorResult


def _number(value: object, *, maximum: float = MAX_TIME_MS) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    if not math.isfinite(result) or result < 0 or result > maximum:
        return None
    return result


def _integer(value: object, *, maximum: int) -> int | None:
    number = _number(value, maximum=float(maximum))
    if number is None or not number.is_integer():
        return None
    return int(number)


def calculate_cls(samples: list[tuple[float, float]]) -> float:
    maximum = 0.0
    session_value = 0.0
    session_start = 0.0
    previous_time = 0.0
    for start_time, value in sorted(samples):
        if (
            session_value > 0
            and start_time - previous_time < 1_000
            and start_time - session_start < 5_000
        ):
            session_value += value
        else:
            session_start = start_time
            session_value = value
        previous_time = start_time
        maximum = max(maximum, session_value)
    return min(maximum, MAX_CLS)


def _pairs(value: object, *, value_maximum: float) -> list[tuple[float, float]]:
    if not isinstance(value, list):
        return []
    result: list[tuple[float, float]] = []
    for item in value[:MAX_ENTRY_SAMPLES]:
        if not isinstance(item, list) or len(item) != 2:
            continue
        first = _number(item[0])
        second = _number(item[1], maximum=value_maximum)
        if first is not None and second is not None:
            result.append((first, second))
    return result


def _supported_types(value: object) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {item for item in value[:100] if isinstance(item, str) and item in _SUPPORTED_TYPES}


def _resource_summary(value: object) -> dict[str, object]:
    payload = value if isinstance(value, dict) else {}
    initiators_raw = payload.get("initiator_counts")
    initiators: dict[str, int] = {}
    if isinstance(initiators_raw, dict):
        for key, raw_count in list(initiators_raw.items())[:50]:
            count = _integer(raw_count, maximum=1_000_000)
            if isinstance(key, str) and key in _INITIATOR_TYPES and count is not None:
                initiators[key] = count
    return {
        "entry_count": _integer(payload.get("entry_count"), maximum=1_000_000),
        "sampled_entry_count": _integer(
            payload.get("sampled_entry_count"), maximum=MAX_ENTRY_SAMPLES
        ),
        "truncated": payload.get("truncated")
        if isinstance(payload.get("truncated"), bool)
        else None,
        "duration_total_ms": _number(payload.get("duration_total_ms")),
        "transfer_size_total_bytes": _integer(
            payload.get("transfer_size_total_bytes"), maximum=MAX_RESOURCE_BYTES
        ),
        "initiator_counts": dict(sorted(initiators.items())),
    }


def _interaction_proxy(value: object) -> float | None:
    samples = _pairs(value, value_maximum=MAX_TIME_MS)
    by_interaction: dict[int, float] = {}
    for raw_id, duration in samples:
        interaction_id = int(raw_id)
        if interaction_id <= 0 or interaction_id > 1_000_000_000:
            continue
        by_interaction[interaction_id] = max(by_interaction.get(interaction_id, 0.0), duration)
    return max(by_interaction.values(), default=None)


def parse_performance_snapshot(raw: object) -> SyntheticPerformanceObservation | None:
    if not isinstance(raw, dict) or raw.get("schema") != "pi-performance-b8/v1":
        return None
    supported = _supported_types(raw.get("supported_entry_types"))
    was_hidden = raw.get("was_hidden") is True
    limitations: list[str] = []

    raw_lcp_candidates = raw.get("lcp_candidates")
    lcp_values: list[object] = raw_lcp_candidates if isinstance(raw_lcp_candidates, list) else []
    lcp_candidates = [
        parsed for item in lcp_values[:MAX_ENTRY_SAMPLES] if (parsed := _number(item)) is not None
    ]
    if "largest-contentful-paint" not in supported:
        lcp_ms = None
        limitations.append("lcp_api_unsupported")
    elif was_hidden:
        lcp_ms = None
        limitations.append("performance_observation_backgrounded")
    else:
        lcp_ms = max(lcp_candidates, default=None)
        if lcp_ms is None:
            limitations.append("lcp_candidate_not_observed")

    if "layout-shift" not in supported:
        cls = None
        limitations.append("layout_shift_api_unsupported")
    elif was_hidden:
        cls = None
        if "performance_observation_backgrounded" not in limitations:
            limitations.append("performance_observation_backgrounded")
    else:
        cls = calculate_cls(_pairs(raw.get("layout_shifts"), value_maximum=MAX_CLS))

    if "event" not in supported:
        inp_ms = None
        inp_method = None
        limitations.append("inp_proxy_event_timing_unsupported")
    else:
        inp_ms = _interaction_proxy(raw.get("interactions"))
        inp_method = "event_timing_worst_observed_interaction_proxy" if inp_ms is not None else None
        if inp_ms is None:
            limitations.append("inp_proxy_unavailable_no_qualifying_interaction")

    if "longtask" in supported:
        long_task_count = _integer(raw.get("long_task_count"), maximum=1_000_000)
        long_task_total_ms = _number(raw.get("long_task_total_ms"))
    else:
        long_task_count = None
        long_task_total_ms = None
        limitations.append("long_task_api_unsupported")

    raw_navigation = raw.get("navigation")
    navigation: dict[str, object] = (
        {str(key): value for key, value in raw_navigation.items()}
        if isinstance(raw_navigation, dict)
        else {}
    )
    ttfb_ms = _number(navigation.get("response_start"))
    dom_content_loaded_ms = _number(navigation.get("dom_content_loaded_end"))
    load_event_ms = _number(navigation.get("load_event_end"))
    if not navigation:
        limitations.append("navigation_timing_not_observed")
    elif load_event_ms == 0:
        load_event_ms = None
        limitations.append("load_event_not_observed")

    errors = raw.get("errors")
    observer_errors = sorted(
        {
            item
            for item in (errors[:20] if isinstance(errors, list) else [])
            if isinstance(item, str) and item in _OBSERVER_ERRORS
        }
    )
    if observer_errors:
        limitations.append("performance_observer_partial_error")

    truncation = raw.get("samples_truncated")
    truncated_samples = sorted(
        key
        for key in ("interaction", "layout_shift", "lcp")
        if isinstance(truncation, dict) and truncation.get(key) is True
    )
    if truncated_samples:
        limitations.append("performance_samples_truncated")

    metadata: dict[str, object] = {
        "source": "synthetic_browser",
        "schema": "pi-performance-b8/v1",
        "foreground_entire_observation": not was_hidden,
        "measurement_end_ms": _number(raw.get("measurement_end_ms")),
        "supported_entry_types": sorted(supported),
        "resource_timing": _resource_summary(raw.get("resources")),
        "dom_node_count": _integer(raw.get("dom_node_count"), maximum=MAX_DOM_NODES),
        "methods": {
            "lcp": "last_foreground_lcp_candidate",
            "cls": "maximum_session_window_unexpected_shifts",
            "inp": inp_method,
            "ttfb": "navigation_response_start_from_navigation_start",
        },
        "limitations": limitations,
        "observer_errors": observer_errors,
        "truncated_samples": truncated_samples,
    }
    return SyntheticPerformanceObservation(
        lcp_ms=lcp_ms,
        cls=cls,
        inp_ms=inp_ms,
        inp_method=inp_method,
        ttfb_ms=ttfb_ms,
        dom_content_loaded_ms=dom_content_loaded_ms,
        load_event_ms=load_event_ms,
        long_task_count=long_task_count,
        long_task_total_ms=long_task_total_ms,
        metadata=metadata,
    )


class SyntheticPerformanceCollector:
    async def attach(self, page: Page) -> None:
        await page.add_init_script(_INIT_SCRIPT)

    async def collect(self, page: Page) -> PerformanceCollection:
        started_at = datetime.now(UTC)
        try:
            raw = await page.evaluate("() => window.__piPerformanceB8?.snapshot?.() ?? null")
            observation = parse_performance_snapshot(raw)
            completed_at = datetime.now(UTC)
            if observation is None:
                return PerformanceCollection(
                    observation=None,
                    result=CollectorResult(
                        collector_type="SYNTHETIC_PERFORMANCE",
                        collector_version=PERFORMANCE_COLLECTOR_VERSION,
                        status="NOT_OBSERVABLE",
                        started_at=started_at,
                        completed_at=completed_at,
                        summary={"source": "synthetic_browser"},
                        error_code="PERFORMANCE_SNAPSHOT_NOT_OBSERVABLE",
                        error_message="Synthetic performance snapshot was not observable",
                    ),
                )
            limitations = observation.metadata.get("limitations", [])
            return PerformanceCollection(
                observation=observation,
                result=CollectorResult(
                    collector_type="SYNTHETIC_PERFORMANCE",
                    collector_version=PERFORMANCE_COLLECTOR_VERSION,
                    status="OK",
                    started_at=started_at,
                    completed_at=completed_at,
                    summary={
                        "source": "synthetic_browser",
                        "metric_count": len(
                            [
                                value
                                for value in (
                                    observation.lcp_ms,
                                    observation.cls,
                                    observation.inp_ms,
                                    observation.ttfb_ms,
                                    observation.dom_content_loaded_ms,
                                    observation.load_event_ms,
                                    observation.long_task_count,
                                    observation.long_task_total_ms,
                                )
                                if value is not None
                            ]
                        ),
                        "limitation_count": len(limitations)
                        if isinstance(limitations, list)
                        else 0,
                    },
                ),
            )
        except PlaywrightError:
            completed_at = datetime.now(UTC)
            return PerformanceCollection(
                observation=None,
                result=CollectorResult(
                    collector_type="SYNTHETIC_PERFORMANCE",
                    collector_version=PERFORMANCE_COLLECTOR_VERSION,
                    status="ERROR",
                    started_at=started_at,
                    completed_at=completed_at,
                    summary={"source": "synthetic_browser"},
                    error_code="PLAYWRIGHT_ERROR",
                    error_message="Synthetic performance collection failed",
                ),
            )
