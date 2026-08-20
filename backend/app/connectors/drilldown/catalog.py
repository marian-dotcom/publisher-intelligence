from dataclasses import dataclass
from datetime import date
from typing import Literal
from urllib.parse import urlsplit

from app.connectors.core.contracts import ConnectorError

DRILLDOWN_CATALOG_VERSION = "incident-drilldown-v1"
MAX_EXPLICIT_WINDOW_DAYS = 7
MAX_DRILLDOWNS_PER_INVESTIGATION = 4
MAX_DRILLDOWNS_PER_CONNECTION_DAY = 8

DrilldownProvider = Literal["GA4", "GSC", "GAM"]
WindowMode = Literal["EXPLICIT_DATES", "GAM_PROFILE"]


@dataclass(frozen=True, slots=True)
class DrilldownDefinition:
    code: str
    provider: DrilldownProvider
    provider_definition_code: str
    window_mode: WindowMode
    required_parameters: tuple[str, ...] = ()
    cost_units: int = 1
    catalog_version: str = DRILLDOWN_CATALOG_VERSION


_DEFINITIONS = (
    DrilldownDefinition(
        "traffic_by_hour_device_channel",
        "GA4",
        "GA4_INCIDENT_TRAFFIC_HOUR_DEVICE_CHANNEL_V1",
        "EXPLICIT_DATES",
    ),
    DrilldownDefinition(
        "traffic_by_page_device",
        "GA4",
        "GA4_INCIDENT_TRAFFIC_PAGE_DEVICE_V1",
        "EXPLICIT_DATES",
    ),
    DrilldownDefinition(
        "traffic_by_country_device",
        "GA4",
        "GA4_INCIDENT_TRAFFIC_COUNTRY_DEVICE_V1",
        "EXPLICIT_DATES",
    ),
    DrilldownDefinition(
        "landing_page_by_channel",
        "GA4",
        "GA4_INCIDENT_LANDING_PAGE_CHANNEL_V1",
        "EXPLICIT_DATES",
    ),
    DrilldownDefinition(
        "web_by_page_device",
        "GSC",
        "GSC_INCIDENT_WEB_PAGE_DEVICE_V1",
        "EXPLICIT_DATES",
    ),
    DrilldownDefinition(
        "web_top_queries_for_page",
        "GSC",
        "GSC_INCIDENT_WEB_TOP_QUERIES_PAGE_V1",
        "EXPLICIT_DATES",
        ("page",),
    ),
    DrilldownDefinition(
        "discover_by_page_device",
        "GSC",
        "GSC_INCIDENT_DISCOVER_PAGE_DEVICE_V1",
        "EXPLICIT_DATES",
    ),
    DrilldownDefinition(
        "ad_unit_by_device",
        "GAM",
        "GAM_INCIDENT_AD_UNIT_DEVICE_V1",
        "GAM_PROFILE",
    ),
    DrilldownDefinition(
        "demand_channel_by_device",
        "GAM",
        "GAM_INCIDENT_DEMAND_CHANNEL_DEVICE_V1",
        "GAM_PROFILE",
    ),
    DrilldownDefinition(
        "line_item_type_by_device",
        "GAM",
        "GAM_INCIDENT_LINE_ITEM_TYPE_DEVICE_V1",
        "GAM_PROFILE",
    ),
    DrilldownDefinition(
        "yield_partner_by_ad_unit",
        "GAM",
        "GAM_INCIDENT_YIELD_PARTNER_AD_UNIT_V1",
        "GAM_PROFILE",
    ),
    DrilldownDefinition(
        "restriction_by_inventory",
        "GAM",
        "GAM_INCIDENT_RESTRICTION_INVENTORY_V1",
        "GAM_PROFILE",
    ),
)

DRILLDOWN_CATALOG = {definition.code: definition for definition in _DEFINITIONS}


def get_drilldown_definition(
    code: str, *, catalog_version: str = DRILLDOWN_CATALOG_VERSION
) -> DrilldownDefinition:
    if catalog_version != DRILLDOWN_CATALOG_VERSION:
        raise ConnectorError(
            "CATALOG_VERSION_INVALID",
            retryable=False,
            message="Incident drill-down catalog version is not current",
        )
    try:
        return DRILLDOWN_CATALOG[code]
    except KeyError as error:
        raise ConnectorError(
            "DRILLDOWN_NOT_ALLOWED",
            retryable=False,
            message="Incident drill-down is not allowlisted",
        ) from error


def validate_drilldown_scope(
    definition: DrilldownDefinition,
    *,
    start_date: date | None,
    end_date: date | None,
    profile: str | None,
    parameters: dict[str, str],
    today: date,
) -> None:
    if set(parameters) != set(definition.required_parameters):
        raise ConnectorError(
            "DRILLDOWN_PARAMETERS_INVALID",
            retryable=False,
            message="Incident drill-down parameters do not match the fixed definition",
        )
    if any(
        not isinstance(value, str) or not value or len(value) > 2048
        for value in parameters.values()
    ):
        raise ConnectorError(
            "DRILLDOWN_PARAMETERS_INVALID",
            retryable=False,
            message="Incident drill-down parameter is invalid",
        )
    if "page" in parameters:
        parsed = urlsplit(parameters["page"])
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ConnectorError(
                "DRILLDOWN_PARAMETERS_INVALID",
                retryable=False,
                message="Incident drill-down page must be an absolute HTTP URL",
            )
    if definition.window_mode == "EXPLICIT_DATES":
        if start_date is None or end_date is None or profile is not None:
            raise ConnectorError(
                "DRILLDOWN_WINDOW_INVALID",
                retryable=False,
                message="Incident drill-down requires an explicit date window",
            )
        inclusive_days = (end_date - start_date).days + 1
        if inclusive_days < 1 or inclusive_days > MAX_EXPLICIT_WINDOW_DAYS or end_date > today:
            raise ConnectorError(
                "DRILLDOWN_WINDOW_INVALID",
                retryable=False,
                message="Incident drill-down date window is outside fixed bounds",
            )
        return
    if start_date is not None or end_date is not None or profile not in {"TODAY", "LAST_7_DAYS"}:
        raise ConnectorError(
            "DRILLDOWN_WINDOW_INVALID",
            retryable=False,
            message="GAM drill-down requires an allowlisted rolling profile",
        )


def provider_codes(provider: DrilldownProvider) -> tuple[str, ...]:
    return tuple(sorted(item.code for item in _DEFINITIONS if item.provider == provider))
