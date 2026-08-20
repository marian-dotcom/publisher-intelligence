from app.connectors.core.contracts import ExtractDefinition, MetricDefinition
from app.connectors.ga4.definitions import GA4_CONNECTOR_VERSION, GA4_SEMANTICS_VERSION


def _metrics() -> tuple[MetricDefinition, ...]:
    return (
        MetricDefinition("activeUsers", "ga4.active_users", "COUNT"),
        MetricDefinition("sessions", "ga4.sessions", "COUNT"),
        MetricDefinition("screenPageViews", "ga4.screen_page_views", "COUNT"),
    )


GA4_INCIDENT_TRAFFIC_HOUR_DEVICE_CHANNEL_V1 = ExtractDefinition(
    code="GA4_INCIDENT_TRAFFIC_HOUR_DEVICE_CHANNEL_V1",
    connector_version=GA4_CONNECTOR_VERSION,
    semantics_version=GA4_SEMANTICS_VERSION,
    granularity="HOUR",
    dimensions=("dateHour", "deviceCategory", "sessionDefaultChannelGroup"),
    metrics=_metrics(),
)
GA4_INCIDENT_TRAFFIC_PAGE_DEVICE_V1 = ExtractDefinition(
    code="GA4_INCIDENT_TRAFFIC_PAGE_DEVICE_V1",
    connector_version=GA4_CONNECTOR_VERSION,
    semantics_version=GA4_SEMANTICS_VERSION,
    granularity="DAY",
    dimensions=("date", "pagePath", "deviceCategory"),
    metrics=_metrics(),
)
GA4_INCIDENT_TRAFFIC_COUNTRY_DEVICE_V1 = ExtractDefinition(
    code="GA4_INCIDENT_TRAFFIC_COUNTRY_DEVICE_V1",
    connector_version=GA4_CONNECTOR_VERSION,
    semantics_version=GA4_SEMANTICS_VERSION,
    granularity="DAY",
    dimensions=("date", "country", "deviceCategory"),
    metrics=_metrics(),
)
GA4_INCIDENT_LANDING_PAGE_CHANNEL_V1 = ExtractDefinition(
    code="GA4_INCIDENT_LANDING_PAGE_CHANNEL_V1",
    connector_version=GA4_CONNECTOR_VERSION,
    semantics_version=GA4_SEMANTICS_VERSION,
    granularity="DAY",
    dimensions=("date", "landingPagePlusQueryString", "sessionDefaultChannelGroup"),
    metrics=_metrics(),
)

GA4_DRILLDOWN_DEFINITIONS = {
    definition.code: definition
    for definition in (
        GA4_INCIDENT_TRAFFIC_HOUR_DEVICE_CHANNEL_V1,
        GA4_INCIDENT_TRAFFIC_PAGE_DEVICE_V1,
        GA4_INCIDENT_TRAFFIC_COUNTRY_DEVICE_V1,
        GA4_INCIDENT_LANDING_PAGE_CHANNEL_V1,
    )
}


def get_ga4_drilldown_definition(code: str) -> ExtractDefinition:
    try:
        return GA4_DRILLDOWN_DEFINITIONS[code]
    except KeyError as error:
        raise ValueError("unsupported GA4 drill-down definition") from error
