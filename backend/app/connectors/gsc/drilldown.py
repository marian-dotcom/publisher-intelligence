from app.connectors.gsc.definitions import (
    GSC_CONNECTOR_VERSION,
    GSC_SEMANTICS_VERSION,
    GSCExtractDefinition,
    _metrics,
)

GSC_INCIDENT_WEB_PAGE_DEVICE_V1 = GSCExtractDefinition(
    code="GSC_INCIDENT_WEB_PAGE_DEVICE_V1",
    connector_version=GSC_CONNECTOR_VERSION,
    semantics_version=GSC_SEMANTICS_VERSION,
    granularity="DAY",
    search_type="web",
    data_state="final",
    dimensions=("date", "page", "device"),
    metrics=_metrics("web"),
)
GSC_INCIDENT_WEB_TOP_QUERIES_PAGE_V1 = GSCExtractDefinition(
    code="GSC_INCIDENT_WEB_TOP_QUERIES_PAGE_V1",
    connector_version=GSC_CONNECTOR_VERSION,
    semantics_version=GSC_SEMANTICS_VERSION,
    granularity="DAY",
    search_type="web",
    data_state="final",
    dimensions=("date", "query", "device"),
    metrics=_metrics("web"),
    row_limit=5_000,
    max_rows=5_000,
)
GSC_INCIDENT_DISCOVER_PAGE_DEVICE_V1 = GSCExtractDefinition(
    code="GSC_INCIDENT_DISCOVER_PAGE_DEVICE_V1",
    connector_version=GSC_CONNECTOR_VERSION,
    semantics_version=GSC_SEMANTICS_VERSION,
    granularity="DAY",
    search_type="discover",
    data_state="final",
    dimensions=("date", "page", "device"),
    metrics=_metrics("discover"),
)

GSC_DRILLDOWN_DEFINITIONS = {
    definition.code: definition
    for definition in (
        GSC_INCIDENT_WEB_PAGE_DEVICE_V1,
        GSC_INCIDENT_WEB_TOP_QUERIES_PAGE_V1,
        GSC_INCIDENT_DISCOVER_PAGE_DEVICE_V1,
    )
}


def get_gsc_drilldown_definition(code: str) -> GSCExtractDefinition:
    try:
        return GSC_DRILLDOWN_DEFINITIONS[code]
    except KeyError as error:
        raise ValueError("unsupported GSC drill-down definition") from error
