from app.connectors.core.contracts import ExtractDefinition, MetricDefinition

GA4_READONLY_SCOPE = "https://www.googleapis.com/auth/analytics.readonly"
GA4_CONNECTOR_VERSION = "ga4-data-api-v1beta-1"
GA4_SEMANTICS_VERSION = "ga4-core-v1"

GA4_TRAFFIC_HOURLY_V1 = ExtractDefinition(
    code="GA4_TRAFFIC_HOURLY_V1",
    connector_version=GA4_CONNECTOR_VERSION,
    semantics_version=GA4_SEMANTICS_VERSION,
    granularity="HOUR",
    dimensions=("dateHour", "deviceCategory", "sessionDefaultChannelGroup"),
    metrics=(
        MetricDefinition("activeUsers", "ga4.active_users", "COUNT"),
        MetricDefinition("sessions", "ga4.sessions", "COUNT"),
        MetricDefinition("screenPageViews", "ga4.screen_page_views", "COUNT"),
        MetricDefinition("engagedSessions", "ga4.engaged_sessions", "COUNT"),
    ),
)

GA4_BEHAVIOR_DAILY_V1 = ExtractDefinition(
    code="GA4_BEHAVIOR_DAILY_V1",
    connector_version=GA4_CONNECTOR_VERSION,
    semantics_version=GA4_SEMANTICS_VERSION,
    granularity="DAY",
    dimensions=("date", "deviceCategory"),
    metrics=(
        MetricDefinition("activeUsers", "ga4.active_users", "COUNT"),
        MetricDefinition("sessions", "ga4.sessions", "COUNT"),
        MetricDefinition("screenPageViews", "ga4.screen_page_views", "COUNT"),
        MetricDefinition("screenPageViewsPerUser", "ga4.screen_page_views_per_user", "RATIO"),
        MetricDefinition("screenPageViewsPerSession", "ga4.screen_page_views_per_session", "RATIO"),
        MetricDefinition("engagementRate", "ga4.engagement_rate", "RATIO"),
    ),
)

GA4_DEFINITIONS = {
    definition.code: definition for definition in (GA4_TRAFFIC_HOURLY_V1, GA4_BEHAVIOR_DAILY_V1)
}


def get_ga4_definition(code: str) -> ExtractDefinition:
    try:
        return GA4_DEFINITIONS[code]
    except KeyError as error:
        raise ValueError("unsupported GA4 extract definition") from error
