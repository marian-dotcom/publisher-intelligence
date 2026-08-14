from dataclasses import dataclass
from typing import Any, Literal

from app.connectors.core.contracts import ExtractPeriod, MetricDefinition

GSC_READONLY_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
GSC_CONNECTOR_VERSION = "search-console-api-v3-1"
GSC_SEMANTICS_VERSION = "gsc-search-analytics-v1"
GSC_SOURCE_TIMEZONE = "America/Los_Angeles"
GSC_ROW_LIMIT = 25_000
GSC_MAX_ROWS_PER_DAY_TYPE = 50_000

GSCSearchType = Literal["web", "discover"]
GSCDataState = Literal["final", "all", "hourly_all"]


@dataclass(frozen=True, slots=True)
class GSCExtractDefinition:
    code: str
    connector_version: str
    semantics_version: str
    granularity: Literal["HOUR", "DAY"]
    search_type: GSCSearchType
    data_state: GSCDataState
    dimensions: tuple[str, ...]
    metrics: tuple[MetricDefinition, ...]
    aggregation_type: Literal["auto"] = "auto"
    row_limit: int = GSC_ROW_LIMIT
    max_rows: int = GSC_MAX_ROWS_PER_DAY_TYPE

    def query_definition(self, period: ExtractPeriod) -> dict[str, Any]:
        return {
            "definition": self.code,
            "connectorVersion": self.connector_version,
            "startDate": period.start_date.isoformat(),
            "endDate": period.end_date.isoformat(),
            "dimensions": list(self.dimensions),
            "type": self.search_type,
            "dataState": self.data_state,
            "aggregationType": self.aggregation_type,
            "rowLimit": self.row_limit,
            "maxRows": self.max_rows,
        }


def _metrics(surface: GSCSearchType) -> tuple[MetricDefinition, ...]:
    return (
        MetricDefinition("clicks", f"gsc.{surface}.clicks", "COUNT"),
        MetricDefinition("impressions", f"gsc.{surface}.impressions", "COUNT"),
        MetricDefinition("ctr", f"gsc.{surface}.ctr", "RATIO"),
        MetricDefinition("position", f"gsc.{surface}.position", "NUMBER"),
    )


GSC_SEARCH_DAILY_V1 = GSCExtractDefinition(
    code="GSC_SEARCH_DAILY_V1",
    connector_version=GSC_CONNECTOR_VERSION,
    semantics_version=GSC_SEMANTICS_VERSION,
    granularity="DAY",
    search_type="web",
    data_state="final",
    dimensions=("date", "device"),
    metrics=_metrics("web"),
)

GSC_DISCOVER_DAILY_V1 = GSCExtractDefinition(
    code="GSC_DISCOVER_DAILY_V1",
    connector_version=GSC_CONNECTOR_VERSION,
    semantics_version=GSC_SEMANTICS_VERSION,
    granularity="DAY",
    search_type="discover",
    data_state="final",
    dimensions=("date", "device"),
    metrics=_metrics("discover"),
)

GSC_SEARCH_FRESH_DAILY_V1 = GSCExtractDefinition(
    code="GSC_SEARCH_FRESH_DAILY_V1",
    connector_version=GSC_CONNECTOR_VERSION,
    semantics_version=GSC_SEMANTICS_VERSION,
    granularity="DAY",
    search_type="web",
    data_state="all",
    dimensions=("date", "device"),
    metrics=_metrics("web"),
)

GSC_SEARCH_HOURLY_V1 = GSCExtractDefinition(
    code="GSC_SEARCH_HOURLY_V1",
    connector_version=GSC_CONNECTOR_VERSION,
    semantics_version=GSC_SEMANTICS_VERSION,
    granularity="HOUR",
    search_type="web",
    data_state="hourly_all",
    dimensions=("hour", "device"),
    metrics=_metrics("web"),
)

GSC_DEFINITIONS = {
    definition.code: definition
    for definition in (
        GSC_SEARCH_DAILY_V1,
        GSC_DISCOVER_DAILY_V1,
        GSC_SEARCH_FRESH_DAILY_V1,
        GSC_SEARCH_HOURLY_V1,
    )
}


def get_gsc_definition(code: str) -> GSCExtractDefinition:
    try:
        return GSC_DEFINITIONS[code]
    except KeyError as error:
        raise ValueError("unsupported GSC extract definition") from error
