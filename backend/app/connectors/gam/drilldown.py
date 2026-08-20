from app.connectors.core.contracts import MetricDefinition
from app.connectors.gam.definitions import (
    GAM_CONNECTOR_VERSION,
    GAM_SEMANTICS_VERSION,
    GAMExtractDefinition,
)

GAM_INCIDENT_AD_UNIT_DEVICE_V1 = GAMExtractDefinition(
    code="GAM_INCIDENT_AD_UNIT_DEVICE_V1",
    connector_version=GAM_CONNECTOR_VERSION,
    semantics_version=GAM_SEMANTICS_VERSION,
    granularity="HOUR",
    dimensions=("DATE", "HOUR", "AD_UNIT_ID", "DEVICE_CATEGORY_NAME"),
    metrics=(
        MetricDefinition("AD_REQUESTS", "gam.ad_requests", "COUNT"),
        MetricDefinition("AD_SERVER_IMPRESSIONS", "gam.ad_server_impressions", "COUNT"),
    ),
)
GAM_INCIDENT_DEMAND_CHANNEL_DEVICE_V1 = GAMExtractDefinition(
    code="GAM_INCIDENT_DEMAND_CHANNEL_DEVICE_V1",
    connector_version=GAM_CONNECTOR_VERSION,
    semantics_version=GAM_SEMANTICS_VERSION,
    granularity="HOUR",
    dimensions=("DATE", "HOUR", "DEMAND_CHANNEL_NAME", "DEVICE_CATEGORY_NAME"),
    metrics=(MetricDefinition("AD_SERVER_IMPRESSIONS", "gam.ad_server_impressions", "COUNT"),),
)
GAM_INCIDENT_LINE_ITEM_TYPE_DEVICE_V1 = GAMExtractDefinition(
    code="GAM_INCIDENT_LINE_ITEM_TYPE_DEVICE_V1",
    connector_version=GAM_CONNECTOR_VERSION,
    semantics_version=GAM_SEMANTICS_VERSION,
    granularity="HOUR",
    dimensions=("DATE", "HOUR", "LINE_ITEM_TYPE_NAME", "DEVICE_CATEGORY_NAME"),
    metrics=(MetricDefinition("AD_SERVER_IMPRESSIONS", "gam.ad_server_impressions", "COUNT"),),
)
GAM_INCIDENT_YIELD_PARTNER_AD_UNIT_V1 = GAMExtractDefinition(
    code="GAM_INCIDENT_YIELD_PARTNER_AD_UNIT_V1",
    connector_version=GAM_CONNECTOR_VERSION,
    semantics_version="gam-ads-traffic-navigator-v1",
    granularity="HOUR",
    dimensions=("DATE", "HOUR", "HBT_YIELD_PARTNER_NAME", "AD_UNIT_ID"),
    metrics=(
        MetricDefinition("ATN_HBT_CANDIDATE_BIDS", "gam.atn_hbt_candidate_bids", "COUNT"),
        MetricDefinition("ATN_HBT_REJECTED_BIDS", "gam.atn_hbt_rejected_bids", "COUNT"),
    ),
    report_type="ADS_TRAFFIC_NAVIGATOR",
)
GAM_INCIDENT_RESTRICTION_INVENTORY_V1 = GAMExtractDefinition(
    code="GAM_INCIDENT_RESTRICTION_INVENTORY_V1",
    connector_version=GAM_CONNECTOR_VERSION,
    semantics_version=GAM_SEMANTICS_VERSION,
    granularity="HOUR",
    dimensions=("DATE", "HOUR", "SERVING_RESTRICTION_NAME", "AD_UNIT_ID"),
    metrics=(
        MetricDefinition("AD_REQUESTS", "gam.ad_requests", "COUNT"),
        MetricDefinition("AD_SERVER_IMPRESSIONS", "gam.ad_server_impressions", "COUNT"),
    ),
)

GAM_DRILLDOWN_DEFINITIONS = {
    definition.code: definition
    for definition in (
        GAM_INCIDENT_AD_UNIT_DEVICE_V1,
        GAM_INCIDENT_DEMAND_CHANNEL_DEVICE_V1,
        GAM_INCIDENT_LINE_ITEM_TYPE_DEVICE_V1,
        GAM_INCIDENT_YIELD_PARTNER_AD_UNIT_V1,
        GAM_INCIDENT_RESTRICTION_INVENTORY_V1,
    )
}


def get_gam_drilldown_definition(code: str) -> GAMExtractDefinition:
    try:
        return GAM_DRILLDOWN_DEFINITIONS[code]
    except KeyError as error:
        raise ValueError("unsupported GAM drill-down definition") from error
