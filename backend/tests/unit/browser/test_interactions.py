from typing import Any, cast

import pytest
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page

from app.browser.interactions import (
    MAX_INTERACTION_STEPS,
    execute_interaction_steps,
    parse_interaction_steps,
)


class FakePage:
    def __init__(self, *, fail_scroll: bool = False) -> None:
        self.waits: list[int] = []
        self.scrolls: list[int] = []
        self.fail_scroll = fail_scroll

    async def wait_for_timeout(self, duration_ms: int) -> None:
        self.waits.append(duration_ms)

    async def evaluate(self, expression: str, percent: int) -> dict[str, int]:
        del expression
        if self.fail_scroll:
            raise PlaywrightError("sensitive page failure must not be retained")
        self.scrolls.append(percent)
        return {
            "percent": percent,
            "target_y": 900,
            "actual_y": 900,
            "page_height": 4_500,
            "viewport_height": 900,
        }


def test_parse_bounded_interaction_profile() -> None:
    parsed = parse_interaction_steps(
        [
            {"type": "wait", "duration_ms": 250},
            {"type": "scroll", "percent": 25},
            {"type": "inspect", "marker": "sticky_and_video"},
        ]
    )

    assert [step.step_type for step in parsed] == ["WAIT", "SCROLL_PERCENT", "INSPECT"]
    assert parsed[0].duration_ms == 250
    assert parsed[1].percent == 25
    assert parsed[2].marker == "sticky_and_video"


@pytest.mark.parametrize(
    "steps",
    [
        [{"type": "click", "selector": "#advert"}],
        [{"type": "scroll", "percent": 101}],
        [{"type": "wait", "duration_ms": 5_001}],
        [{"type": "inspect", "marker": "arbitrary"}],
        [{"type": "scroll", "percent": 25, "javascript": "alert(1)"}],
        [{"type": "wait"}],
        [{"type": "scroll", "percent": True}],
    ],
)
def test_reject_unsupported_or_unbounded_interaction_steps(
    steps: list[dict[str, object]],
) -> None:
    with pytest.raises(ValueError):
        parse_interaction_steps(steps)


def test_reject_excessive_interaction_step_count() -> None:
    with pytest.raises(ValueError):
        parse_interaction_steps([{"type": "wait", "duration_ms": 1}] * (MAX_INTERACTION_STEPS + 1))


async def test_execute_interaction_steps_records_deterministic_state() -> None:
    page = FakePage()
    steps = parse_interaction_steps(
        [
            {"type": "wait", "duration_ms": 250},
            {"type": "scroll", "percent": 25},
            {"type": "inspect", "marker": "sticky_and_video"},
        ]
    )

    result = await execute_interaction_steps(cast(Page, cast(Any, page)), steps)

    assert not result.failed
    assert page.waits == [250]
    assert page.scrolls == [25]
    assert [action["type"] for action in result.actions] == [
        "wait",
        "scroll_percent",
        "inspect",
    ]
    assert result.actions[1]["percent"] == 25
    assert result.actions[1]["target_y"] == 900
    assert result.actions[2]["marker"] == "sticky_and_video"


async def test_execute_interaction_failure_is_safe_and_bounded() -> None:
    page = FakePage(fail_scroll=True)
    steps = parse_interaction_steps(
        [
            {"type": "scroll", "percent": 25},
            {"type": "scroll", "percent": 50},
        ]
    )

    result = await execute_interaction_steps(cast(Page, cast(Any, page)), steps)

    assert result.failed
    assert result.error_code == "PLAYWRIGHT_ERROR"
    assert len(result.actions) == 1
    assert "sensitive" not in str(result.actions)
