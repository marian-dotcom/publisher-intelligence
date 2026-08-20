from datetime import UTC, datetime, timedelta

import pytest

from app.metrics.divergence import (
    AlignedMetricValue,
    MetricWindow,
    compare_aligned_movements,
)

START = datetime(2026, 8, 18, tzinfo=UTC)


def window(previous: float, current: float, *, offset: int = 0) -> MetricWindow:
    first = START + timedelta(hours=offset)
    second = first + timedelta(hours=1)
    return MetricWindow(
        previous=AlignedMetricValue(first, first + timedelta(hours=1), previous, "MATURE"),
        current=AlignedMetricValue(second, second + timedelta(hours=1), current, "MATURE"),
    )


def test_reports_factual_down_vs_stable_divergence() -> None:
    fact = compare_aligned_movements(window(100, 70), window(200, 198))

    assert fact.left_movement == "DOWN"
    assert fact.right_movement == "STABLE"
    assert fact.diverged is True
    assert fact.left_change_fraction == pytest.approx(-0.3)


def test_zero_baseline_is_undefined_not_an_infinite_change() -> None:
    fact = compare_aligned_movements(window(0, 10), window(100, 90))

    assert fact.left_movement == "UNDEFINED"
    assert fact.diverged is False


def test_rejects_unaligned_intervals() -> None:
    with pytest.raises(ValueError, match="same explicit intervals"):
        compare_aligned_movements(window(10, 9), window(10, 10, offset=1))
