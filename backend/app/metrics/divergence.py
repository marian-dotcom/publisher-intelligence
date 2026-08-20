from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.metrics.contracts import Freshness

Movement = Literal["UP", "DOWN", "STABLE", "UNDEFINED"]


@dataclass(frozen=True, slots=True)
class AlignedMetricValue:
    period_start: datetime
    period_end: datetime
    value: float
    freshness_status: Freshness


@dataclass(frozen=True, slots=True)
class MetricWindow:
    previous: AlignedMetricValue
    current: AlignedMetricValue


@dataclass(frozen=True, slots=True)
class DivergenceFact:
    left_movement: Movement
    right_movement: Movement
    left_change_fraction: float | None
    right_change_fraction: float | None
    diverged: bool


def compare_aligned_movements(
    left: MetricWindow,
    right: MetricWindow,
    *,
    stable_tolerance: float = 0.05,
) -> DivergenceFact:
    if stable_tolerance < 0 or stable_tolerance >= 1:
        raise ValueError("stable_tolerance must be in [0, 1)")
    if (
        left.previous.period_start != right.previous.period_start
        or left.previous.period_end != right.previous.period_end
        or left.current.period_start != right.current.period_start
        or left.current.period_end != right.current.period_end
    ):
        raise ValueError("metric windows must use the same explicit intervals")
    if left.previous.period_end > left.current.period_start:
        raise ValueError("metric windows must be ordered and non-overlapping")
    if (
        left.previous.freshness_status != right.previous.freshness_status
        or left.current.freshness_status != right.current.freshness_status
    ):
        raise ValueError("metric windows must use compatible freshness")
    left_change = _fractional_change(left.previous.value, left.current.value)
    right_change = _fractional_change(right.previous.value, right.current.value)
    left_movement = _movement(left_change, stable_tolerance)
    right_movement = _movement(right_change, stable_tolerance)
    return DivergenceFact(
        left_movement=left_movement,
        right_movement=right_movement,
        left_change_fraction=left_change,
        right_change_fraction=right_change,
        diverged=(
            left_movement != "UNDEFINED"
            and right_movement != "UNDEFINED"
            and left_movement != right_movement
        ),
    )


def _fractional_change(previous: float, current: float) -> float | None:
    if previous < 0 or current < 0:
        raise ValueError("metric values must be non-negative")
    if previous == 0:
        return None
    return (current - previous) / previous


def _movement(change: float | None, tolerance: float) -> Movement:
    if change is None:
        return "UNDEFINED"
    if change > tolerance:
        return "UP"
    if change < -tolerance:
        return "DOWN"
    return "STABLE"
