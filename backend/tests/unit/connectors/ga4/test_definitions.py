from datetime import date

import pytest

from app.connectors.core.contracts import ExtractPeriod
from app.connectors.ga4.definitions import (
    GA4_BEHAVIOR_DAILY_V1,
    GA4_READONLY_SCOPE,
    GA4_TRAFFIC_HOURLY_V1,
    get_ga4_definition,
)


def test_extract_definitions_are_small_versioned_and_source_namespaced() -> None:
    assert GA4_READONLY_SCOPE.endswith("/analytics.readonly")
    assert GA4_TRAFFIC_HOURLY_V1.dimensions == (
        "dateHour",
        "deviceCategory",
        "sessionDefaultChannelGroup",
    )
    assert len(GA4_TRAFFIC_HOURLY_V1.metrics) == 4
    assert GA4_BEHAVIOR_DAILY_V1.dimensions == ("date", "deviceCategory")
    assert all(metric.metric_code.startswith("ga4.") for metric in GA4_TRAFFIC_HOURLY_V1.metrics)
    assert all(metric.metric_code.startswith("ga4.") for metric in GA4_BEHAVIOR_DAILY_V1.metrics)
    assert get_ga4_definition("GA4_TRAFFIC_HOURLY_V1") is GA4_TRAFFIC_HOURLY_V1


def test_unknown_definition_and_unbounded_period_fail_closed() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        get_ga4_definition("GA4_ARBITRARY_REPORT")
    with pytest.raises(ValueError, match="32 inclusive"):
        ExtractPeriod(date(2026, 1, 1), date(2026, 2, 2))
