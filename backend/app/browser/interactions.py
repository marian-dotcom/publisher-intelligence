from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic
from typing import Any

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page

from app.browser.contracts import InteractionStep

MAX_INTERACTION_STEPS = 16
MAX_WAIT_MS = 5_000
ALLOWED_INSPECTION_MARKERS = frozenset({"sticky_and_video"})


@dataclass(frozen=True, slots=True)
class InteractionExecutionResult:
    actions: list[dict[str, object]]
    failed: bool = False
    error_code: str | None = None


def parse_interaction_steps(raw_steps: Sequence[dict[str, Any]]) -> tuple[InteractionStep, ...]:
    if len(raw_steps) > MAX_INTERACTION_STEPS:
        raise ValueError(f"interaction profile exceeds {MAX_INTERACTION_STEPS} steps")

    parsed: list[InteractionStep] = []
    for position, raw in enumerate(raw_steps):
        step_type = raw.get("type")
        if step_type == "wait":
            _require_keys(raw, {"type", "duration_ms"}, position)
            duration_ms = raw.get("duration_ms")
            if not isinstance(duration_ms, int) or isinstance(duration_ms, bool):
                raise ValueError(f"interaction step {position} duration_ms must be an integer")
            if not 0 <= duration_ms <= MAX_WAIT_MS:
                raise ValueError(
                    f"interaction step {position} duration_ms must be between 0 and {MAX_WAIT_MS}"
                )
            parsed.append(InteractionStep(step_type="WAIT", duration_ms=duration_ms))
            continue

        if step_type == "scroll":
            _require_keys(raw, {"type", "percent"}, position)
            percent = raw.get("percent")
            if not isinstance(percent, int) or isinstance(percent, bool):
                raise ValueError(f"interaction step {position} percent must be an integer")
            if not 0 <= percent <= 100:
                raise ValueError(f"interaction step {position} percent must be between 0 and 100")
            parsed.append(InteractionStep(step_type="SCROLL_PERCENT", percent=percent))
            continue

        if step_type == "inspect":
            _require_keys(raw, {"type", "marker"}, position)
            marker = raw.get("marker")
            if not isinstance(marker, str) or marker not in ALLOWED_INSPECTION_MARKERS:
                raise ValueError(f"interaction step {position} marker is not supported")
            parsed.append(InteractionStep(step_type="INSPECT", marker=marker))
            continue

        raise ValueError(f"interaction step {position} type is not supported")

    return tuple(parsed)


def _require_keys(raw: dict[str, Any], allowed: set[str], position: int) -> None:
    if set(raw) != allowed:
        raise ValueError(f"interaction step {position} contains unexpected or missing fields")


async def execute_interaction_steps(
    page: Page,
    steps: Sequence[InteractionStep],
) -> InteractionExecutionResult:
    actions: list[dict[str, object]] = []
    for position, step in enumerate(steps):
        started_at = datetime.now(UTC)
        started_clock = monotonic()
        try:
            if step.step_type == "WAIT":
                duration_ms = step.duration_ms or 0
                await page.wait_for_timeout(duration_ms)
                details: dict[str, object] = {"duration_ms": duration_ms}
            elif step.step_type == "SCROLL_PERCENT":
                percent = step.percent or 0
                raw = await page.evaluate(
                    """
                    percent => {
                      const root = document.documentElement;
                      const body = document.body;
                      const pageHeight = Math.max(
                        root ? root.scrollHeight : 0,
                        body ? body.scrollHeight : 0,
                        window.innerHeight
                      );
                      const viewportHeight = window.innerHeight;
                      const targetY = Math.round(
                        Math.max(pageHeight - viewportHeight, 0) * percent / 100
                      );
                      window.scrollTo({top: targetY, behavior: "auto"});
                      return {
                        percent,
                        target_y: targetY,
                        actual_y: Math.round(window.scrollY),
                        page_height: pageHeight,
                        viewport_height: viewportHeight
                      };
                    }
                    """,
                    percent,
                )
                details = _safe_scroll_result(raw, percent)
            else:
                details = {"marker": step.marker or "unknown"}
        except PlaywrightError:
            actions.append(
                {
                    "type": step.step_type.lower(),
                    "position": position,
                    "started_at": started_at.isoformat(),
                    "duration_ms": round((monotonic() - started_clock) * 1_000),
                    "status": "ERROR",
                    "error_code": "PLAYWRIGHT_ERROR",
                }
            )
            return InteractionExecutionResult(
                actions=actions,
                failed=True,
                error_code="PLAYWRIGHT_ERROR",
            )

        actions.append(
            {
                "type": step.step_type.lower(),
                "position": position,
                "started_at": started_at.isoformat(),
                "duration_ms": round((monotonic() - started_clock) * 1_000),
                "status": "OK",
                **details,
            }
        )
    return InteractionExecutionResult(actions=actions)


def _safe_scroll_result(raw: object, percent: int) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise PlaywrightError("scroll result was not structured")
    result: dict[str, object] = {"percent": percent}
    for field in ("target_y", "actual_y", "page_height", "viewport_height"):
        value = raw.get(field)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise PlaywrightError("scroll result field was invalid")
        result[field] = round(value)
    return result
