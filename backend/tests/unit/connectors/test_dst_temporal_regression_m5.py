"""EP-026 M5 — DST/timezone cross-source hardening regression.

Exercises the REAL normalization contracts (GA4/GSC/GAM normalizers) and the
REAL browser six-hour window scheduler across actual Europe/Bucharest and
America/Los_Angeles DST transitions:

- Bucharest fall-back 2026-10-25 (04:00 EEST -> 03:00 EET at 01:00Z): local
  hour 03:00 exists twice; two distinct absolute instants share one label.
- Bucharest spring-forward 2026-03-29 (03:00 EET -> 04:00 EEST at 01:00Z):
  local hour 03:00 does not exist.

Invariants proven here: no naive-datetime fallback anywhere; conversions are
deterministic; ambiguous wall-clock hours remain distinguishable where the
source contract allows it; nonexistent local hours never fabricate instants;
cross-source alignment happens on absolute instants.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

from app.browser.scheduling import resolve_six_hour_window
from app.connectors.ga4.definitions import GA4_TRAFFIC_HOURLY_V1
from app.connectors.ga4.normalization import normalize_report as ga4_normalize
from app.connectors.gam.definitions import GAM_INVENTORY_HEALTH_V1
from app.connectors.gam.normalization import (
    GAMNetwork,
    GAMNormalizationError,
    normalize_network,
    normalize_report,
)
from app.connectors.gsc.definitions import GSC_SEARCH_DAILY_V1, GSC_SEARCH_HOURLY_V1
from app.connectors.gsc.normalization import normalize_query as gsc_normalize

FIXTURES = Path(__file__).parents[2] / "fixtures" / "connectors"
BUCHAREST = ZoneInfo("Europe/Bucharest")


def _load(relative: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((FIXTURES / relative).read_text()))


# ---------------------------------------------------------------- GA4 ----
def _ga4_hourly_payload(date_hour: str) -> dict[str, Any]:
    payload = _load("ga4/traffic_complete.json")
    payload["rows"] = [
        {
            "dimensionValues": [
                {"value": date_hour},
                {"value": "mobile"},
                {"value": "Organic Search"},
            ],
            "metricValues": [
                {"value": "120"},
                {"value": "150"},
                {"value": "225"},
                {"value": "95"},
            ],
        }
    ]
    return payload


def test_ga4_fall_back_repeated_local_hour_normalizes_to_first_occurrence() -> None:
    """Bucharest 2026-10-25: local 03:00 occurs twice (EEST +03 then EET +02).
    The GA4 contract reports one row per local wall-clock label; normalization
    deterministically anchors it at the FIRST absolute instant (fold=0), and
    the label's period truthfully spans both real occurrences."""
    normalized = ga4_normalize(_ga4_hourly_payload("2026102503"), GA4_TRAFFIC_HOURLY_V1)
    point = normalized.points[0]
    assert point.period_start == datetime(2026, 10, 25, 0, 0, tzinfo=UTC)
    assert point.period_end == datetime(2026, 10, 25, 2, 0, tzinfo=UTC)
    assert point.period_start.tzinfo is not None


def test_ga4_fall_back_wall_clock_label_maps_to_two_distinct_real_instants() -> None:
    """The distinction itself: one wall-clock hour corresponds to two genuinely
    different absolute instants one real hour apart; both stay representable
    with explicit fold semantics and remain distinguishable by offset."""
    naive = datetime(2026, 10, 25, 3, 0)
    first = naive.replace(tzinfo=BUCHAREST, fold=0).astimezone(UTC)
    second = naive.replace(tzinfo=BUCHAREST, fold=1).astimezone(UTC)
    assert first == datetime(2026, 10, 25, 0, 0, tzinfo=UTC)
    assert second == datetime(2026, 10, 25, 1, 0, tzinfo=UTC)
    assert first != second
    assert first.astimezone(BUCHAREST).utcoffset() != second.astimezone(BUCHAREST).utcoffset()


def test_ga4_spring_forward_nonexistent_hour_is_deterministic_not_naive() -> None:
    """Local 03:00-04:00 does not exist on 2026-03-29. The GA4 contract still
    yields exactly one deterministic UTC interval (PEP 495 pre-transition
    offset) — never a naive datetime, never a fabricated extra instant."""
    normalized = ga4_normalize(_ga4_hourly_payload("2026032903"), GA4_TRAFFIC_HOURLY_V1)
    point = normalized.points[0]
    # 03:00 attached with the pre-transition offset (+02) -> 01:00Z, the very
    # instant clocks jump from 03:00 to 04:00. The hour never existed, so its
    # normalized period truthfully collapses to a ZERO-length interval there:
    # deterministic, UTC-aware, and never fabricated into fake data.
    assert point.period_start == datetime(2026, 3, 29, 1, 0, tzinfo=UTC)
    assert point.period_end == datetime(2026, 3, 29, 1, 0, tzinfo=UTC)


# ---------------------------------------------------------------- GSC ----
def _gsc_daily_payload(day: str) -> dict[str, Any]:
    return {
        "rows": [
            {
                "keys": [day, "MOBILE"],
                "clicks": 10,
                "impressions": 100,
                "ctr": 0.1,
                "position": 1.0,
            }
        ],
        "responseAggregationType": "byProperty",
        "metadata": {},
        "pagination": {
            "pagesRequested": 1,
            "returnedRows": 1,
            "rowLimit": 25000,
            "maxRows": 50000,
            "capReached": False,
        },
    }


def _gsc_hourly_payload(hour_key: str) -> dict[str, Any]:
    return {
        "rows": [
            {
                "keys": [hour_key, "MOBILE"],
                "clicks": 1,
                "impressions": 2,
                "ctr": 0.5,
                "position": 1.0,
            }
        ],
        "responseAggregationType": "byProperty",
        "metadata": {},
        "pagination": {
            "pagesRequested": 1,
            "returnedRows": 1,
            "rowLimit": 25000,
            "maxRows": 50000,
            "capReached": False,
        },
    }


def test_gsc_fall_back_day_spans_twenty_five_real_hours() -> None:
    """GSC pins America/Los_Angeles. Its 2026-11-01 fall-back day runs from
    00:00 PDT (-07) to 00:00 PST (-08) next day: 25 REAL hours in UTC terms,
    preserved exactly by normalization."""
    normalized = gsc_normalize(_gsc_daily_payload("2026-11-01"), GSC_SEARCH_DAILY_V1)
    point = normalized.points[0]
    assert point.period_start == datetime(2026, 11, 1, 7, tzinfo=UTC)
    assert point.period_end == datetime(2026, 11, 2, 8, tzinfo=UTC)
    assert (point.period_end - point.period_start) == timedelta(hours=25)


def test_gsc_offset_hour_is_validated_against_source_zone_and_converted() -> None:
    """Offset-bearing hours convert deterministically when consistent with Los
    Angeles; a contradicting offset is rejected instead of reinterpreted."""
    good = gsc_normalize(_gsc_hourly_payload("2026-11-01T05:00:00-08:00"), GSC_SEARCH_HOURLY_V1)
    assert good.points[0].period_start == datetime(2026, 11, 1, 13, 0, tzinfo=UTC)

    from app.connectors.gsc.normalization import GSCNormalizationError

    try:
        gsc_normalize(_gsc_hourly_payload("2026-11-01T05:00:00+00:00"), GSC_SEARCH_HOURLY_V1)
    except GSCNormalizationError as error:
        assert "America/Los_Angeles" in str(error)
    else:  # pragma: no cover
        raise AssertionError("offset-inconsistent GSC hour must be rejected")


# ---------------------------------------------------------------- GAM ----
_GAM_NETWORK_JSON = "gam/network.json"


def _gam_network() -> "GAMNetwork":
    return normalize_network(_load(_GAM_NETWORK_JSON), "1234567")


def _gam_payload(*rows: tuple[str, int], run_time: str = "2026-10-25T10:15:00Z") -> dict[str, Any]:
    def row(local_date: str, hour: int) -> dict[str, Any]:
        return {
            "dimensionValues": [
                {"stringValue": local_date},
                {"intValue": str(hour)},
                {"intValue": "2001"},
                {"stringValue": "Desktop"},
                {"stringValue": "Banner"},
            ],
            "metricValueGroups": [
                {"primaryValues": [{"intValue": "1200"}, {"intValue": "940"}, {"intValue": "970"}]}
            ],
        }

    year, month, day = (int(part) for part in run_time[:10].split("-"))
    date_range = {
        "startDate": {"year": year, "month": month, "day": day},
        "endDate": {"year": year, "month": month, "day": day},
    }
    return {
        "runTime": run_time,
        "dateRanges": [date_range],
        "comparisonDateRanges": [],
        "reportResource": "networks/1234567/reports/101",
        "operationName": "networks/1234567/operations/reports/101/runs/run-1",
        "reportResult": "networks/1234567/reports/101/results/result-1",
        "pagination": {
            "pagesFetched": 1,
            "pageSize": 10000,
            "totalRowCount": len(rows),
            "allPagesFetched": True,
        },
        "rows": [row(date, hour) for date, hour in rows],
    }


def test_gam_fall_back_ambiguous_hour_spans_both_absolute_instants() -> None:
    """GAM's contract keeps the repeated local hour distinguishable: the
    normalized period spans BOTH absolute instants and is explicitly flagged."""
    result = normalize_report(
        _gam_payload(("2026-10-25", 3)),
        definition=GAM_INVENTORY_HEALTH_V1,
        network=_gam_network(),
        profile="TODAY",
    )
    point = result.normalized.points[0]
    assert point.period_start == datetime(2026, 10, 25, 0, 0, tzinfo=UTC)
    assert point.period_end == datetime(2026, 10, 25, 2, 0, tzinfo=UTC)
    assert "DST_AMBIGUOUS_HOUR" in result.normalized.limitations


def test_gam_nonexistent_spring_forward_hour_is_refused() -> None:
    """Local 03:00 does not exist on 2026-03-29; normalization refuses rather
    than fabricating an impossible instant."""
    try:
        normalize_report(
            _gam_payload(("2026-03-29", 3), run_time="2026-03-29T10:15:00Z"),
            definition=GAM_INVENTORY_HEALTH_V1,
            network=_gam_network(),
            profile="TODAY",
        )
    except GAMNormalizationError as error:
        assert "nonexistent local DST hour" in str(error)
    else:  # pragma: no cover
        raise AssertionError("nonexistent local hour must not fabricate an instant")


# ------------------------------------------------------- cross-source ----
def test_cross_sources_align_on_absolute_instants_across_the_boundary() -> None:
    """GA4 (property tz), GAM (publisher tz), GSC (LA offset hours) and the
    browser scheduler all describe the same Bucharest fall-back boundary
    instant 2026-10-25 00:00Z; alignment is by absolute instant."""
    los_angeles = ZoneInfo("America/Los_Angeles")
    boundary = datetime(2026, 10, 25, 0, 0, tzinfo=UTC)

    ga4_point = ga4_normalize(_ga4_hourly_payload("2026102503"), GA4_TRAFFIC_HOURLY_V1).points[0]
    gam_result = normalize_report(
        _gam_payload(("2026-10-25", 3)),
        definition=GAM_INVENTORY_HEALTH_V1,
        network=_gam_network(),
        profile="TODAY",
    )
    gam_point = gam_result.normalized.points[0]
    gsc_point = gsc_normalize(
        _gsc_hourly_payload("2026-10-24T17:00:00-07:00"), GSC_SEARCH_HOURLY_V1
    ).points[0]
    window = resolve_six_hour_window(boundary, "Europe/Bucharest")

    # All four providers describe the identical absolute boundary instant.
    assert ga4_point.period_start == boundary
    assert gam_point.period_start == boundary
    assert gsc_point.period_start == boundary
    assert window.window_start <= boundary < window.window_end
    assert window.window_start.tzinfo is not None and window.window_end.tzinfo is not None
    # Wall-clock labels disagree across zones while instants agree.
    assert ga4_point.period_start.astimezone(BUCHAREST).hour == 3
    assert gsc_point.period_start.astimezone(los_angeles).day == 24
    # Deterministic absolute-instant ordering across sources.
    ordered = sorted(
        [ga4_point.period_start, gam_point.period_start, gsc_point.period_start, boundary]
    )
    assert ordered == [boundary] * 4


# --------------------------------------------- browser scheduler DST ----
def test_browser_windows_remain_deterministic_and_utc_aware_through_transitions() -> None:
    """Fall-back night: local [00:00,06:00) spans 7 REAL hours.
    Spring-forward night: local [00:00,06:00) spans 5 REAL hours.
    Both bounds are timezone-aware; resolution is deterministic; naive input
    stays rejected on this exercised path."""

    def bounds(instant: datetime) -> tuple[datetime, datetime]:
        resolved = resolve_six_hour_window(instant, "Europe/Bucharest")
        assert resolved.window_start.tzinfo is not None
        assert resolved.window_end.tzinfo is not None
        assert resolved.scheduled_for.tzinfo is not None
        again = resolve_six_hour_window(instant, "Europe/Bucharest")
        assert (again.window_start, again.window_end) == (
            resolved.window_start,
            resolved.window_end,
        )
        return resolved.window_start, resolved.window_end

    # Fall-back night (transition at 01:00Z inside this local window).
    start, end = bounds(datetime(2026, 10, 25, 0, 0, tzinfo=UTC))
    assert start == datetime(2026, 10, 24, 21, 0, tzinfo=UTC)
    assert end == datetime(2026, 10, 25, 4, 0, tzinfo=UTC)
    assert (end - start) == timedelta(hours=7)

    # The two occurrences of the repeated local hour lie inside the window.
    repeated_first = datetime(2026, 10, 25, 0, 0, tzinfo=UTC)  # 03:00 +03
    repeated_second = datetime(2026, 10, 25, 1, 0, tzinfo=UTC)  # 03:00 +02
    assert start <= repeated_first < repeated_second <= end

    # Spring-forward night (transition at 01:00Z inside this local window).
    start, end = bounds(datetime(2026, 3, 28, 23, 30, tzinfo=UTC))
    assert start == datetime(2026, 3, 28, 22, 0, tzinfo=UTC)
    assert end == datetime(2026, 3, 29, 3, 0, tzinfo=UTC)
    assert (end - start) == timedelta(hours=5)

    # Naive input stays rejected on this exercised path.
    try:
        resolve_six_hour_window(datetime(2026, 10, 25, 0, 0), "Europe/Bucharest")
    except ValueError as error:
        assert "timezone-aware" in str(error)
    else:  # pragma: no cover
        raise AssertionError("naive scheduler instant must be rejected")
