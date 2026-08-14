import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from app.connectors.core.contracts import ConnectorError
from app.connectors.gsc.definitions import (
    GSC_DISCOVER_DAILY_V1,
    GSC_SEARCH_DAILY_V1,
    GSC_SEARCH_FRESH_DAILY_V1,
    GSC_SEARCH_HOURLY_V1,
)
from app.connectors.gsc.normalization import (
    GSCNormalizationError,
    normalize_inspection,
    normalize_query,
    validate_property_access,
)

FIXTURES = Path(__file__).parents[3] / "fixtures" / "connectors" / "gsc"


def load(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((FIXTURES / name).read_text()))


def test_final_daily_search_preserves_pacific_time_ctr_components_and_limit() -> None:
    normalized = normalize_query(load("search_daily.json"), GSC_SEARCH_DAILY_V1)

    assert normalized.source_timezone == "America/Los_Angeles"
    assert len(normalized.points) == 8
    click = normalized.points[0]
    assert click.metric_code == "gsc.web.clicks"
    assert click.dimensions == {"device": "MOBILE"}
    assert click.source_time == "2026-08-12"
    assert click.period_start == datetime(2026, 8, 12, 7, tzinfo=UTC)
    assert click.period_end == datetime(2026, 8, 13, 7, tzinfo=UTC)
    assert click.freshness_status == "MATURE"
    ctr = normalized.points[2]
    assert ctr.metric_code == "gsc.web.ctr"
    assert ctr.numerator == 120
    assert ctr.denominator == 2400
    assert normalized.limitations == ("TOP_ROWS_ONLY",)


def test_discover_empty_response_stays_missing_and_separate() -> None:
    normalized = normalize_query(load("discover_empty.json"), GSC_DISCOVER_DAILY_V1)

    assert normalized.points == ()
    assert normalized.response_metadata["searchType"] == "discover"
    assert normalized.limitations == ("TOP_ROWS_ONLY",)


def test_hourly_incomplete_boundary_marks_only_partial_points_preliminary() -> None:
    normalized = normalize_query(load("search_hourly_incomplete.json"), GSC_SEARCH_HOURLY_V1)

    assert normalized.points[0].period_start == datetime(2026, 8, 13, 16, tzinfo=UTC)
    assert normalized.points[0].freshness_status == "MATURE"
    assert normalized.points[4].period_start == datetime(2026, 8, 13, 17, tzinfo=UTC)
    assert normalized.points[4].freshness_status == "PRELIMINARY"
    assert "INCOMPLETE_DATA" in normalized.limitations
    assert normalized.response_metadata["firstIncompleteHour"] == "2026-08-13T17:00:00+00:00"
    assert normalized.response_metadata["firstIncompleteHourSource"] == (
        "2026-08-13T10:00:00-07:00"
    )


def test_all_data_state_marks_incomplete_date_and_row_cap_explicitly() -> None:
    payload = load("search_daily.json")
    payload["metadata"] = {"first_incomplete_date": "2026-08-12"}
    payload["pagination"]["capReached"] = True
    normalized = normalize_query(payload, GSC_SEARCH_FRESH_DAILY_V1)

    assert all(point.freshness_status == "PRELIMINARY" for point in normalized.points)
    assert normalized.limitations == (
        "TOP_ROWS_ONLY",
        "ROW_LIMIT_REACHED",
        "INCOMPLETE_DATA",
    )
    assert normalized.response_metadata["firstIncompleteDateSource"] == "2026-08-12"


def test_property_permission_and_url_inspection_are_sanitized() -> None:
    assert validate_property_access(load("sites_accessible.json"), "sc-domain:example.com") == (
        "siteFullUser"
    )
    inspection = normalize_inspection(load("url_inspection.json"))
    assert inspection["indexStatusResult"]["verdict"] == "PASS"
    assert "inspectionResultLink" not in inspection


def test_unverified_property_fails_closed() -> None:
    payload = {
        "siteEntry": [{"siteUrl": "sc-domain:example.com", "permissionLevel": "siteUnverifiedUser"}]
    }
    with pytest.raises(ConnectorError) as raised:
        validate_property_access(payload, "sc-domain:example.com")
    assert raised.value.code == "PERMISSION_ERROR"


@pytest.mark.parametrize(
    "mutation", ["wrong_keys", "negative", "nan", "ctr", "hour_zone", "final_incomplete"]
)
def test_malformed_provider_rows_fail_before_persistence(mutation: str) -> None:
    if mutation in {"hour_zone"}:
        payload = deepcopy(load("search_hourly_incomplete.json"))
        payload["rows"][0]["keys"][0] = "2026-08-13T09:00:00+00:00"
        definition = GSC_SEARCH_HOURLY_V1
    else:
        payload = deepcopy(load("search_daily.json"))
        definition = GSC_SEARCH_DAILY_V1
        if mutation == "wrong_keys":
            payload["rows"][0]["keys"].pop()
        elif mutation == "negative":
            payload["rows"][0]["clicks"] = -1
        elif mutation == "nan":
            payload["rows"][0]["position"] = "NaN"
        elif mutation == "ctr":
            payload["rows"][0]["ctr"] = 1.1
        else:
            payload["metadata"]["first_incomplete_date"] = "2026-08-12"
    with pytest.raises(GSCNormalizationError):
        normalize_query(payload, definition)
