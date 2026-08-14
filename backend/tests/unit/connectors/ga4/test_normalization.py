import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from app.connectors.core.contracts import ConnectorError
from app.connectors.ga4.definitions import GA4_BEHAVIOR_DAILY_V1, GA4_TRAFFIC_HOURLY_V1
from app.connectors.ga4.normalization import (
    GA4NormalizationError,
    normalize_report,
    validate_metadata,
)

FIXTURES = Path(__file__).parents[3] / "fixtures" / "connectors" / "ga4"


def load(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((FIXTURES / name).read_text()))


def test_complete_hourly_report_preserves_timezone_dimensions_quota_and_provenance() -> None:
    normalized = normalize_report(load("traffic_complete.json"), GA4_TRAFFIC_HOURLY_V1)

    assert normalized.source_timezone == "Europe/Bucharest"
    assert len(normalized.points) == 8
    point = normalized.points[0]
    assert point.metric_code == "ga4.active_users"
    assert point.dimensions == {
        "deviceCategory": "mobile",
        "sessionDefaultChannelGroup": "Organic Search",
    }
    assert point.source_time == "2026081310"
    assert point.period_start == datetime(2026, 8, 13, 7, tzinfo=UTC)
    assert point.period_end == datetime(2026, 8, 13, 8, tzinfo=UTC)
    assert point.value == 120.0
    assert normalized.limitations == ()
    assert normalized.response_metadata["propertyQuota"]["tokensPerDay"] == {
        "consumed": 3,
        "remaining": 199997,
    }


def test_daily_behavior_keeps_source_ratio_semantics() -> None:
    normalized = normalize_report(load("behavior_complete.json"), GA4_BEHAVIOR_DAILY_V1)

    assert len(normalized.points) == 6
    engagement = next(
        point for point in normalized.points if point.metric_code == "ga4.engagement_rate"
    )
    assert engagement.unit == "RATIO"
    assert engagement.value == 0.62
    assert engagement.period_start == datetime(2026, 8, 11, 21, tzinfo=UTC)
    assert engagement.period_end == datetime(2026, 8, 12, 21, tzinfo=UTC)


def test_thresholded_empty_response_is_limited_and_does_not_invent_zero_points() -> None:
    normalized = normalize_report(load("traffic_thresholded.json"), GA4_TRAFFIC_HOURLY_V1)

    assert normalized.points == ()
    assert normalized.limitations == ("OTHER_ROW_DATA_LOSS", "THRESHOLDING_APPLIED")
    assert normalized.response_metadata["rowCount"] == 0


def test_property_metadata_must_contain_every_required_field() -> None:
    metadata = load("metadata_core.json")
    snapshot = validate_metadata(metadata, GA4_BEHAVIOR_DAILY_V1)
    assert "engagementRate" in snapshot["validatedMetrics"]

    metadata["metrics"] = [
        metric for metric in metadata["metrics"] if metric["apiName"] != "engagementRate"
    ]
    with pytest.raises(ConnectorError) as raised:
        validate_metadata(metadata, GA4_BEHAVIOR_DAILY_V1)
    assert raised.value.code == "SCHEMA_INCOMPATIBLE"


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong_headers",
        "missing_metric_value",
        "negative_value",
        "nan_value",
        "invalid_timezone",
        "invalid_hour",
        "invalid_quota",
    ],
)
def test_malformed_provider_payload_fails_before_persistence(mutation: str) -> None:
    payload = deepcopy(load("traffic_complete.json"))
    if mutation == "wrong_headers":
        payload["dimensionHeaders"][0]["name"] = "date"
    elif mutation == "missing_metric_value":
        payload["rows"][0]["metricValues"].pop()
    elif mutation == "negative_value":
        payload["rows"][0]["metricValues"][0]["value"] = "-1"
    elif mutation == "nan_value":
        payload["rows"][0]["metricValues"][0]["value"] = "NaN"
    elif mutation == "invalid_timezone":
        payload["metadata"]["timeZone"] = "Secret/Not-A-Timezone"
    elif mutation == "invalid_hour":
        payload["rows"][0]["dimensionValues"][0]["value"] = "2026081325"
    else:
        payload["propertyQuota"]["tokensPerDay"]["remaining"] = -1

    with pytest.raises(GA4NormalizationError):
        normalize_report(payload, GA4_TRAFFIC_HOURLY_V1)
