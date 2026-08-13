from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page

from app.browser.contracts import (
    CollectorResult,
    CollectorStatus,
    ExpectedGPTSlot,
    GPTSlotObservation,
)

GPT_COLLECTOR_VERSION = "gpt-b4-v1"
MAX_SLOTS = 200
MAX_TEXT = 500

_INIT_SCRIPT = r"""
(() => {
  const state = {
    schema: "pi-gpt-b4/v1",
    startedAt: performance.now(),
    present: false,
    observable: false,
    attached: false,
    version: null,
    errors: [],
    slots: {},
  };
  window.__piGptB4 = state;
  const bounded = (value, max = 500) => {
    if (value === null || value === undefined) return null;
    return String(value).slice(0, max);
  };
  const at = () => Math.max(0, Math.round(performance.now() - state.startedAt));
  const sizeText = (size) => {
    try {
      if (size && typeof size.getWidth === "function" && typeof size.getHeight === "function") {
        return `${size.getWidth()}x${size.getHeight()}`;
      }
      return bounded(size, 50);
    } catch (_) { return null; }
  };
  const slotIdentity = (slot) => {
    let adUnitPath = null;
    let domElementId = null;
    let sizes = [];
    try { adUnitPath = bounded(slot.getAdUnitPath(), 500); } catch (_) {}
    try { domElementId = bounded(slot.getSlotElementId(), 300); } catch (_) {}
    try {
      const raw = slot.getSizes();
      if (Array.isArray(raw)) sizes = raw.map(sizeText).filter(Boolean).slice(0, 50);
    } catch (_) {}
    const key = adUnitPath ? `ad-unit:${adUnitPath}` : domElementId ? `dom:${domElementId}` : null;
    return {key, adUnitPath, domElementId, sizes};
  };
  const ensure = (slot) => {
    const identity = slotIdentity(slot);
    if (!identity.key) return null;
    if (!state.slots[identity.key] && Object.keys(state.slots).length < 200) {
      state.slots[identity.key] = {
        ...identity,
        definedAtMs: at(),
        requestedAtMs: null,
        responseAtMs: null,
        renderEndedAtMs: null,
        onloadAtMs: null,
        viewableAtMs: null,
        isEmpty: null,
        creativeId: null,
        lineItemId: null,
        requestCount: 0,
      };
    }
    return state.slots[identity.key] || null;
  };
  const mark = (event, field) => {
    const item = event && event.slot ? ensure(event.slot) : null;
    if (item && item[field] === null) item[field] = at();
    return item;
  };
  const inventory = () => {
    try {
      const slots = window.googletag.pubads().getSlots();
      if (Array.isArray(slots)) slots.slice(0, 200).forEach(ensure);
    } catch (error) { state.errors.push(bounded(error, 200)); }
  };
  state.snapshot = () => {
    if (state.present && state.observable) inventory();
    return {
      schema: state.schema,
      present: state.present,
      observable: state.observable,
      attached: state.attached,
      version: state.version,
      errors: state.errors.slice(0, 10),
      slots: Object.values(state.slots).slice(0, 200),
    };
  };
  const attach = () => {
    const gt = window.googletag;
    if (!gt || typeof gt !== "object") return;
    state.present = true;
    try { if (typeof gt.getVersion === "function") state.version = bounded(gt.getVersion(), 100); }
    catch (_) {}
    if (state.attached || !gt.cmd || typeof gt.cmd.push !== "function") return;
    state.attached = true;
    try {
      gt.cmd.push(() => {
        try {
          const pubads = gt.pubads();
          if (!pubads || typeof pubads.addEventListener !== "function") return;
          state.observable = true;
          pubads.addEventListener("slotRequested", (event) => {
            const item = mark(event, "requestedAtMs");
            if (item) item.requestCount = Math.min(item.requestCount + 1, 1000);
          });
          pubads.addEventListener("slotResponseReceived", (event) => mark(event, "responseAtMs"));
          pubads.addEventListener("slotRenderEnded", (event) => {
            const item = mark(event, "renderEndedAtMs");
            if (!item) return;
            if (typeof event.isEmpty === "boolean") item.isEmpty = event.isEmpty;
            item.creativeId = bounded(event.creativeId, 300);
            item.lineItemId = bounded(event.lineItemId, 300);
          });
          pubads.addEventListener("slotOnload", (event) => mark(event, "onloadAtMs"));
          pubads.addEventListener("impressionViewable", (event) => mark(event, "viewableAtMs"));
          inventory();
        } catch (error) { state.errors.push(bounded(error, 200)); }
      });
    } catch (error) { state.errors.push(bounded(error, 200)); }
  };
  attach();
  let attempts = 0;
  const timer = setInterval(() => {
    attempts += 1;
    attach();
    if (state.observable || attempts >= 400) clearInterval(timer);
  }, 25);
})();
"""


@dataclass(frozen=True, slots=True)
class GPTCollection:
    present: bool
    version: str | None
    slots: list[GPTSlotObservation]
    result: CollectorResult


def _text(value: object, limit: int = MAX_TEXT) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    cleaned = str(value).strip()
    return cleaned[:limit] if cleaned else None


def _integer(value: object, maximum: int = 2_147_483_647) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and 0 <= value <= maximum:
        return int(value)
    return None


def gpt_stable_key(ad_unit_path: str | None, dom_element_id: str | None) -> str | None:
    path = _text(ad_unit_path)
    if path is not None:
        return f"gpt|ad-unit|{path}"
    element = _text(dom_element_id, 300)
    return f"gpt|dom|{element}" if element is not None else None


def _sizes(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    cleaned = {_text(item, 50) for item in value}
    return tuple(sorted(item for item in cleaned if item is not None)[:50])


def parse_gpt_snapshot(
    raw: object, expected_slots: tuple[ExpectedGPTSlot, ...]
) -> tuple[bool, bool, str | None, list[GPTSlotObservation], list[str]]:
    payload = raw if isinstance(raw, dict) else {}
    present = payload.get("present") is True
    observable = payload.get("observable") is True
    version = _text(payload.get("version"), 100)
    errors = (
        [
            item
            for item in (_text(value, 200) for value in payload.get("errors", []))
            if item is not None
        ]
        if isinstance(payload.get("errors"), list)
        else []
    )
    observed: dict[str, GPTSlotObservation] = {}
    raw_slots = payload.get("slots")
    if isinstance(raw_slots, list):
        for item in raw_slots[:MAX_SLOTS]:
            if not isinstance(item, dict):
                continue
            ad_unit_path = _text(item.get("adUnitPath"))
            dom_element_id = _text(item.get("domElementId"), 300)
            stable_key = gpt_stable_key(ad_unit_path, dom_element_id)
            if stable_key is None:
                continue
            observed[stable_key] = GPTSlotObservation(
                stable_key=stable_key,
                ad_unit_path=ad_unit_path,
                dom_element_id=dom_element_id,
                sizes=_sizes(item.get("sizes")),
                expected=False,
                present=True,
                defined_at_ms=_integer(item.get("definedAtMs")),
                requested_at_ms=_integer(item.get("requestedAtMs")),
                response_at_ms=_integer(item.get("responseAtMs")),
                render_ended_at_ms=_integer(item.get("renderEndedAtMs")),
                onload_at_ms=_integer(item.get("onloadAtMs")),
                viewable_at_ms=_integer(item.get("viewableAtMs")),
                is_empty=item.get("isEmpty") if isinstance(item.get("isEmpty"), bool) else None,
                creative_id=_text(item.get("creativeId"), 300),
                line_item_id=_text(item.get("lineItemId"), 300),
                request_count=_integer(item.get("requestCount"), 1_000) or 0,
            )
    for expected in expected_slots:
        key = expected.stable_key
        current = observed.get(key)
        if current is None:
            observed[key] = GPTSlotObservation(
                stable_key=key,
                ad_unit_path=expected.ad_unit_path,
                dom_element_id=expected.dom_element_id,
                sizes=expected.sizes,
                expected=True,
                present=False,
            )
        else:
            observed[key] = replace(current, expected=True)
    return (
        present,
        observable,
        version,
        sorted(observed.values(), key=lambda item: item.stable_key),
        errors,
    )


class GPTLifecycleCollector:
    async def attach(self, page: Page) -> None:
        await page.add_init_script(_INIT_SCRIPT)

    async def collect(
        self, page: Page, expected_slots: tuple[ExpectedGPTSlot, ...]
    ) -> GPTCollection:
        started_at = datetime.now(UTC)
        try:
            raw = await page.evaluate(
                "() => window.__piGptB4 && window.__piGptB4.snapshot "
                "? window.__piGptB4.snapshot() : null"
            )
            present, observable, version, slots, errors = parse_gpt_snapshot(raw, expected_slots)
            status: CollectorStatus = (
                "OK" if observable else "NOT_OBSERVABLE" if present else "NOT_PRESENT"
            )
            return GPTCollection(
                present=present,
                version=version,
                slots=slots,
                result=CollectorResult(
                    collector_type="GPT_LIFECYCLE",
                    collector_version=GPT_COLLECTOR_VERSION,
                    status=status,
                    started_at=started_at,
                    completed_at=datetime.now(UTC),
                    summary={
                        "gpt_present": present,
                        "slot_count": len(slots),
                        "expected_slot_count": len([slot for slot in slots if slot.expected]),
                        "present_slot_count": len([slot for slot in slots if slot.present]),
                        "observer_error_count": len(errors),
                    },
                ),
            )
        except PlaywrightError:
            return GPTCollection(
                present=False,
                version=None,
                slots=[
                    GPTSlotObservation(
                        stable_key=item.stable_key,
                        ad_unit_path=item.ad_unit_path,
                        dom_element_id=item.dom_element_id,
                        sizes=item.sizes,
                        expected=True,
                        present=False,
                    )
                    for item in expected_slots
                ],
                result=CollectorResult(
                    collector_type="GPT_LIFECYCLE",
                    collector_version=GPT_COLLECTOR_VERSION,
                    status="ERROR",
                    started_at=started_at,
                    completed_at=datetime.now(UTC),
                    summary={"expected_slot_count": len(expected_slots)},
                    error_code="PLAYWRIGHT_ERROR",
                    error_message="GPT lifecycle snapshot failed",
                ),
            )
