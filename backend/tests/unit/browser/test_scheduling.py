from datetime import UTC, datetime, timedelta

import pytest

from app.browser.scheduling import resolve_six_hour_window


def test_resolve_utc_six_hour_window() -> None:
    bounds = resolve_six_hour_window(datetime(2026, 8, 14, 13, 27, tzinfo=UTC), "UTC")

    assert bounds.scheduled_for == datetime(2026, 8, 14, 12, tzinfo=UTC)
    assert bounds.window_start == bounds.scheduled_for
    assert bounds.window_end == datetime(2026, 8, 14, 18, tzinfo=UTC)


def test_resolve_bucharest_window_in_utc() -> None:
    bounds = resolve_six_hour_window(datetime(2026, 8, 14, 10, 30, tzinfo=UTC), "Europe/Bucharest")

    assert bounds.scheduled_for == datetime(2026, 8, 14, 9, tzinfo=UTC)
    assert bounds.window_end == datetime(2026, 8, 14, 15, tzinfo=UTC)


def test_spring_dst_window_preserves_local_boundaries() -> None:
    bounds = resolve_six_hour_window(datetime(2026, 3, 29, 0, tzinfo=UTC), "Europe/Bucharest")

    assert bounds.window_start == datetime(2026, 3, 28, 22, tzinfo=UTC)
    assert bounds.window_end == datetime(2026, 3, 29, 3, tzinfo=UTC)
    assert bounds.window_end - bounds.window_start == timedelta(hours=5)


def test_autumn_dst_window_preserves_local_boundaries() -> None:
    bounds = resolve_six_hour_window(datetime(2026, 10, 25, 2, 30, tzinfo=UTC), "Europe/Bucharest")

    assert bounds.window_start == datetime(2026, 10, 24, 21, tzinfo=UTC)
    assert bounds.window_end == datetime(2026, 10, 25, 4, tzinfo=UTC)
    assert bounds.window_end - bounds.window_start == timedelta(hours=7)


def test_reject_naive_instant_and_unknown_timezone() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        resolve_six_hour_window(datetime(2026, 8, 14, 12), "UTC")
    with pytest.raises(ValueError, match="not recognized"):
        resolve_six_hour_window(datetime(2026, 8, 14, 12, tzinfo=UTC), "Mars/Olympus")
