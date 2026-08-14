from datetime import date

from app.connectors.core.contracts import ExtractPeriod
from app.connectors.gsc.definitions import (
    GSC_DEFINITIONS,
    GSC_DISCOVER_DAILY_V1,
    GSC_SEARCH_DAILY_V1,
    GSC_SEARCH_FRESH_DAILY_V1,
    GSC_SEARCH_HOURLY_V1,
)


def test_fixed_definitions_cover_final_all_and_hourly_without_merging_surfaces() -> None:
    assert set(GSC_DEFINITIONS) == {
        "GSC_SEARCH_DAILY_V1",
        "GSC_DISCOVER_DAILY_V1",
        "GSC_SEARCH_FRESH_DAILY_V1",
        "GSC_SEARCH_HOURLY_V1",
    }
    assert GSC_SEARCH_DAILY_V1.search_type == "web"
    assert GSC_DISCOVER_DAILY_V1.search_type == "discover"
    assert GSC_SEARCH_FRESH_DAILY_V1.data_state == "all"
    assert GSC_SEARCH_HOURLY_V1.data_state == "hourly_all"
    assert GSC_SEARCH_HOURLY_V1.dimensions == ("hour", "device")
    assert GSC_SEARCH_DAILY_V1.metrics[0].metric_code == "gsc.web.clicks"
    assert GSC_DISCOVER_DAILY_V1.metrics[0].metric_code == "gsc.discover.clicks"


def test_query_provenance_is_bounded_and_source_native() -> None:
    query = GSC_SEARCH_DAILY_V1.query_definition(ExtractPeriod(date(2026, 8, 7), date(2026, 8, 13)))
    assert query == {
        "definition": "GSC_SEARCH_DAILY_V1",
        "connectorVersion": "search-console-api-v3-1",
        "startDate": "2026-08-07",
        "endDate": "2026-08-13",
        "dimensions": ["date", "device"],
        "type": "web",
        "dataState": "final",
        "aggregationType": "auto",
        "rowLimit": 25000,
        "maxRows": 50000,
    }
