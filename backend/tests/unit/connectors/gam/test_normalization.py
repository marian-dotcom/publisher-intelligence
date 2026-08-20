import json
from pathlib import Path
from typing import Any, cast

import pytest

from app.connectors.gam.definitions import GAM_INVENTORY_HEALTH_V1
from app.connectors.gam.normalization import (
    GAMNormalizationError,
    normalize_network,
    normalize_report,
    validate_report,
)

FIXTURES = Path(__file__).parents[3] / "fixtures" / "connectors" / "gam"


def load(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((FIXTURES / name).read_text()))


def complete_payload() -> dict[str, Any]:
    first = load("inventory_rows_page_1.json")
    second = load("inventory_rows_page_2.json")
    first["rows"].extend(second["rows"])
    first.pop("nextPageToken")
    first.update(
        {
            "reportResource": "networks/1234567/reports/101",
            "operationName": "networks/1234567/operations/reports/101/runs/run-1",
            "reportResult": "networks/1234567/reports/101/results/result-1",
            "pagination": {
                "pagesFetched": 2,
                "pageSize": 10000,
                "totalRowCount": 2,
                "allPagesFetched": True,
            },
        }
    )
    return first


def test_report_definition_and_network_are_strictly_validated() -> None:
    network = normalize_network(load("network.json"), "1234567")
    capability = validate_report(
        load("inventory_today_report.json"),
        definition=GAM_INVENTORY_HEALTH_V1,
        profile="TODAY",
        network=network,
        expected_resource="networks/1234567/reports/101",
    )
    assert len(capability["definitionFingerprint"]) == 64

    changed = load("inventory_today_report.json")
    changed["reportDefinition"]["expandedCompatibility"] = True
    with pytest.raises(GAMNormalizationError) as raised:
        validate_report(
            changed,
            definition=GAM_INVENTORY_HEALTH_V1,
            profile="TODAY",
            network=network,
            expected_resource="networks/1234567/reports/101",
        )
    assert raised.value.code == "REPORT_INCOMPATIBLE"

    compared = load("inventory_today_report.json")
    compared["reportDefinition"]["comparisonDateRange"] = {"relative": "PREVIOUS_PERIOD"}
    with pytest.raises(GAMNormalizationError) as compared_error:
        validate_report(
            compared,
            definition=GAM_INVENTORY_HEALTH_V1,
            profile="TODAY",
            network=network,
            expected_resource="networks/1234567/reports/101",
        )
    assert compared_error.value.code == "REPORT_INCOMPATIBLE"


def test_optional_network_display_name_falls_back_to_network_code() -> None:
    payload = load("network.json")
    payload.pop("displayName")
    assert normalize_network(payload, "1234567").display_name == "1234567"


def test_rows_preserve_network_time_currency_and_preliminary_maturity() -> None:
    network = normalize_network(load("network.json"), "1234567")
    result = normalize_report(
        complete_payload(),
        definition=GAM_INVENTORY_HEALTH_V1,
        network=network,
        profile="TODAY",
    )
    assert len(result.normalized.points) == 6
    first = result.normalized.points[0]
    assert first.metric_code == "gam.ad_requests"
    assert first.source_time == "2026-08-20T10:00[Europe/Bucharest]"
    assert first.period_start.isoformat() == "2026-08-20T07:00:00+00:00"
    assert first.dimensions["currency_code"] == "EUR"
    assert first.freshness_status == "PRELIMINARY"
    assert "RECENT_DATA_PRELIMINARY" in result.normalized.limitations


def test_last_seven_days_reconciliation_advances_older_rows_to_mature() -> None:
    network = normalize_network(load("network.json"), "1234567")
    payload = complete_payload()
    payload["rows"][0]["dimensionValues"][0] = {"stringValue": "2026-08-19"}
    payload["rows"][1]["dimensionValues"][0] = {"stringValue": "2026-08-18"}
    payload["dateRanges"] = [
        {
            "startDate": {"year": 2026, "month": 8, "day": 13},
            "endDate": {"year": 2026, "month": 8, "day": 19},
        }
    ]
    result = normalize_report(
        payload,
        definition=GAM_INVENTORY_HEALTH_V1,
        network=network,
        profile="LAST_7_DAYS",
    )
    assert [point.freshness_status for point in result.normalized.points] == [
        "PRELIMINARY",
        "PRELIMINARY",
        "PRELIMINARY",
        "MATURE",
        "MATURE",
        "MATURE",
    ]


def test_empty_complete_report_remains_missing_instead_of_zero() -> None:
    network = normalize_network(load("network.json"), "1234567")
    payload = complete_payload()
    payload["rows"] = []
    payload["pagination"]["totalRowCount"] = 0
    result = normalize_report(
        payload,
        definition=GAM_INVENTORY_HEALTH_V1,
        network=network,
        profile="TODAY",
    )
    assert result.normalized.points == ()
    assert result.normalized.limitations == ("NO_ROWS_RETURNED",)


def test_partial_result_never_normalizes_as_complete() -> None:
    network = normalize_network(load("network.json"), "1234567")
    payload = complete_payload()
    payload["pagination"]["allPagesFetched"] = False
    with pytest.raises(GAMNormalizationError) as raised:
        normalize_report(
            payload,
            definition=GAM_INVENTORY_HEALTH_V1,
            network=network,
            profile="TODAY",
        )
    assert raised.value.code == "PARTIAL_RESULT"
