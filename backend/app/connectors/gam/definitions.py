from dataclasses import dataclass
from typing import Any, Literal

from app.connectors.core.contracts import MetricDefinition

GAM_READONLY_SCOPE = "https://www.googleapis.com/auth/admanager.readonly"
GAM_API_ROOT = "https://admanager.googleapis.com/v1"
GAM_CONNECTOR_VERSION = "ad-manager-rest-v1-beta-1"
GAM_SEMANTICS_VERSION = "gam-historical-v1"
GAM_RESULT_PAGE_SIZE = 10_000
GAM_MAX_RESULT_ROWS = 100_000

GAMProfile = Literal["TODAY", "LAST_7_DAYS"]


@dataclass(frozen=True, slots=True)
class GAMExtractDefinition:
    code: str
    connector_version: str
    semantics_version: str
    granularity: Literal["HOUR"]
    dimensions: tuple[str, ...]
    metrics: tuple[MetricDefinition, ...]
    report_type: Literal["HISTORICAL", "ADS_TRAFFIC_NAVIGATOR"] = "HISTORICAL"

    def query_definition(self, *, report_resource: str, profile: GAMProfile) -> dict[str, Any]:
        return {
            "definition": self.code,
            "connectorVersion": self.connector_version,
            "semanticsVersion": self.semantics_version,
            "reportResource": report_resource,
            "reportType": self.report_type,
            "profile": profile,
            "relativeDateRange": profile,
            "dimensions": list(self.dimensions),
            "metrics": [metric.api_name for metric in self.metrics],
            "timeZoneSource": "PUBLISHER",
            "expandedCompatibility": False,
            "pageSize": GAM_RESULT_PAGE_SIZE,
            "maxRows": GAM_MAX_RESULT_ROWS,
        }


GAM_INVENTORY_HEALTH_V1 = GAMExtractDefinition(
    code="GAM_INVENTORY_HEALTH_V1",
    connector_version=GAM_CONNECTOR_VERSION,
    semantics_version=GAM_SEMANTICS_VERSION,
    granularity="HOUR",
    dimensions=(
        "DATE",
        "HOUR",
        "AD_UNIT_ID",
        "DEVICE_CATEGORY_NAME",
        "INVENTORY_FORMAT_NAME",
    ),
    metrics=(
        MetricDefinition("AD_REQUESTS", "gam.ad_requests", "COUNT"),
        MetricDefinition("AD_SERVER_IMPRESSIONS", "gam.ad_server_impressions", "COUNT"),
        MetricDefinition("AD_SERVER_RESPONSES_SERVED", "gam.ad_server_responses_served", "COUNT"),
    ),
)

GAM_DEMAND_HEALTH_V1 = GAMExtractDefinition(
    code="GAM_DEMAND_HEALTH_V1",
    connector_version=GAM_CONNECTOR_VERSION,
    semantics_version=GAM_SEMANTICS_VERSION,
    granularity="HOUR",
    dimensions=(
        "DATE",
        "HOUR",
        "DEVICE_CATEGORY_NAME",
        "DEMAND_CHANNEL_NAME",
        "PROGRAMMATIC_CHANNEL_NAME",
    ),
    metrics=(
        MetricDefinition("AD_EXCHANGE_TOTAL_REQUESTS", "gam.ad_exchange_total_requests", "COUNT"),
        MetricDefinition(
            "AD_EXCHANGE_PLUS_YIELD_GROUP_IMPRESSIONS",
            "gam.ad_exchange_plus_yield_group_impressions",
            "COUNT",
        ),
        MetricDefinition(
            "AD_EXCHANGE_PLUS_YIELD_GROUP_ECPM",
            "gam.ad_exchange_plus_yield_group_ecpm",
            "CURRENCY",
        ),
    ),
)

GAM_DELIVERY_COMPOSITION_V1 = GAMExtractDefinition(
    code="GAM_DELIVERY_COMPOSITION_V1",
    connector_version=GAM_CONNECTOR_VERSION,
    semantics_version=GAM_SEMANTICS_VERSION,
    granularity="HOUR",
    dimensions=(
        "DATE",
        "HOUR",
        "DEVICE_CATEGORY_NAME",
        "LINE_ITEM_TYPE_NAME",
        "DEMAND_CHANNEL_NAME",
    ),
    metrics=(
        MetricDefinition("AD_SERVER_IMPRESSIONS", "gam.delivery_impressions", "COUNT"),
        MetricDefinition(
            "AD_EXCHANGE_PLUS_YIELD_GROUP_IMPRESSIONS",
            "gam.programmatic_impressions",
            "COUNT",
        ),
    ),
)

GAM_DEFINITIONS = {
    definition.code: definition
    for definition in (
        GAM_INVENTORY_HEALTH_V1,
        GAM_DEMAND_HEALTH_V1,
        GAM_DELIVERY_COMPOSITION_V1,
    )
}
GAM_PROFILES: tuple[GAMProfile, ...] = ("TODAY", "LAST_7_DAYS")


def get_gam_definition(code: str) -> GAMExtractDefinition:
    try:
        return GAM_DEFINITIONS[code]
    except KeyError as error:
        raise ValueError("unsupported GAM extract definition") from error


def binding_key(definition_code: str, profile: GAMProfile) -> str:
    return f"{definition_code}:{profile}"
