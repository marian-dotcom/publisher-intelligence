import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.connectors.core.contracts import (
    ConnectorError,
    ExtractPeriod,
    FreshnessStatus,
    NormalizedExtract,
    NormalizedMetricPoint,
)
from app.connectors.gam.client import GAMClient
from app.connectors.gam.definitions import GAMExtractDefinition, GAMProfile


class GAMNormalizationError(ConnectorError):
    def __init__(self, message: str, *, code: str = "INVALID_RESPONSE") -> None:
        super().__init__(code, retryable=False, message=message)


@dataclass(frozen=True, slots=True)
class GAMNetwork:
    network_code: str
    timezone: str
    currency_code: str
    display_name: str


@dataclass(frozen=True, slots=True)
class GAMNormalizedResult:
    normalized: NormalizedExtract
    period: ExtractPeriod


def validate_network_access(payload: Mapping[str, Any], network_code: str) -> None:
    networks = payload.get("networks", [])
    if not isinstance(networks, list):
        raise GAMNormalizationError("GAM networks must be a list")
    expected = f"networks/{network_code}"
    for raw in networks:
        network = _mapping(raw, "network list item")
        if network.get("name") == expected and network.get("networkCode") == network_code:
            return
    raise ConnectorError(
        "PERMISSION_ERROR", retryable=False, message="GAM network is not accessible"
    )


def normalize_network(payload: Mapping[str, Any], network_code: str) -> GAMNetwork:
    if payload.get("name") != f"networks/{network_code}":
        raise GAMNormalizationError("GAM network resource identity changed")
    if payload.get("networkCode") != network_code:
        raise GAMNormalizationError("GAM network code changed")
    timezone = _required_string(payload.get("timeZone"), "network.timeZone", 100)
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as error:
        raise GAMNormalizationError("GAM network timezone is not an IANA timezone") from error
    currency = _required_string(payload.get("currencyCode"), "network.currencyCode", 3)
    if len(currency) != 3 or not currency.isalpha() or currency != currency.upper():
        raise GAMNormalizationError("GAM network currency is not an ISO-4217 code")
    raw_display_name = payload.get("displayName")
    display_name = (
        _required_string(raw_display_name, "network.displayName", 200)
        if raw_display_name not in (None, "")
        else network_code
    )
    return GAMNetwork(network_code, timezone, currency, display_name)


def validate_report(
    payload: Mapping[str, Any],
    *,
    definition: GAMExtractDefinition,
    profile: GAMProfile,
    network: GAMNetwork,
    expected_resource: str,
) -> dict[str, Any]:
    resource = GAMClient.canonical_report_resource(network.network_code, expected_resource)
    if payload.get("name") != resource:
        raise GAMNormalizationError("GAM report identity changed", code="REPORT_INCOMPATIBLE")
    report = _mapping(payload.get("reportDefinition"), "reportDefinition")
    dimensions = _string_tuple(report.get("dimensions"), "report dimensions")
    metrics = _string_tuple(report.get("metrics"), "report metrics")
    if dimensions != definition.dimensions or metrics != tuple(
        metric.api_name for metric in definition.metrics
    ):
        raise GAMNormalizationError(
            "GAM report columns do not match the versioned cube", code="REPORT_INCOMPATIBLE"
        )
    if report.get("reportType") != definition.report_type:
        raise GAMNormalizationError(
            "GAM report type does not match the versioned cube", code="REPORT_INCOMPATIBLE"
        )
    timezone_source = report.get("timeZoneSource", "PUBLISHER")
    if timezone_source not in {"PUBLISHER", "TIME_ZONE_SOURCE_UNSPECIFIED"}:
        raise GAMNormalizationError(
            "GAM report must use the publisher timezone", code="REPORT_INCOMPATIBLE"
        )
    supplied_timezone = report.get("timeZone")
    if supplied_timezone not in {None, "", network.timezone}:
        raise GAMNormalizationError(
            "GAM report timezone differs from the network", code="REPORT_INCOMPATIBLE"
        )
    currency = report.get("currencyCode")
    if currency not in {None, "", network.currency_code}:
        raise GAMNormalizationError(
            "GAM report currency differs from the network", code="REPORT_INCOMPATIBLE"
        )
    if report.get("expandedCompatibility", False) is not False:
        raise GAMNormalizationError(
            "GAM expanded compatibility changes reservation semantics",
            code="REPORT_INCOMPATIBLE",
        )
    if report.get("filters") not in (None, [], ()):
        raise GAMNormalizationError(
            "GAM routine cube must not contain unversioned filters", code="REPORT_INCOMPATIBLE"
        )
    if report.get("comparisonDateRange") not in (None, {}):
        raise GAMNormalizationError(
            "GAM routine cube must not contain a comparison range",
            code="REPORT_INCOMPATIBLE",
        )
    if report.get("timePeriodColumn") not in (None, "TIME_PERIOD_COLUMN_UNSPECIFIED"):
        raise GAMNormalizationError(
            "GAM routine cube must not contain time-period comparison columns",
            code="REPORT_INCOMPATIBLE",
        )
    if report.get("flags") not in (None, [], ()):
        raise GAMNormalizationError(
            "GAM routine cube must not contain report flags", code="REPORT_INCOMPATIBLE"
        )
    date_range = _mapping(report.get("dateRange"), "report dateRange")
    if date_range.get("relative") != profile or set(date_range) != {"relative"}:
        raise GAMNormalizationError(
            "GAM report relative date range does not match its profile",
            code="REPORT_INCOMPATIBLE",
        )
    fingerprint_source = {
        "reportType": definition.report_type,
        "dimensions": dimensions,
        "metrics": metrics,
        "timeZoneSource": "PUBLISHER",
        "currencyCode": network.currency_code,
        "relativeDateRange": profile,
        "expandedCompatibility": False,
    }
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_source, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "reportResource": resource,
        "profile": profile,
        "definitionFingerprint": fingerprint,
        "displayName": payload.get("displayName"),
    }


def normalize_report(
    payload: Mapping[str, Any],
    *,
    definition: GAMExtractDefinition,
    network: GAMNetwork,
    profile: GAMProfile,
) -> GAMNormalizedResult:
    rows = payload.get("rows", [])
    if not isinstance(rows, list):
        raise GAMNormalizationError("GAM rows must be a list")
    pagination = _mapping(payload.get("pagination"), "pagination")
    if pagination.get("allPagesFetched") is not True:
        raise GAMNormalizationError("GAM result is partial", code="PARTIAL_RESULT")
    total_rows = _nonnegative_int(pagination.get("totalRowCount"), "totalRowCount")
    if total_rows != len(rows):
        raise GAMNormalizationError("GAM normalized row count is partial", code="PARTIAL_RESULT")
    date_ranges = payload.get("dateRanges")
    if not isinstance(date_ranges, list) or len(date_ranges) != 1:
        raise GAMNormalizationError("GAM result must contain one fixed date range")
    fixed_range = _mapping(date_ranges[0], "dateRange")
    start_date = _google_date(fixed_range.get("startDate"), "dateRange.startDate")
    end_date = _google_date(fixed_range.get("endDate"), "dateRange.endDate")
    period = ExtractPeriod(start_date, end_date)
    run_time = _rfc3339(payload.get("runTime"), "runTime")
    source_zone = ZoneInfo(network.timezone)
    run_local_date = run_time.astimezone(source_zone).date()
    expected_end = run_local_date if profile == "TODAY" else run_local_date - timedelta(days=1)
    expected_start = expected_end if profile == "TODAY" else expected_end - timedelta(days=6)
    if (start_date, end_date) != (expected_start, expected_end):
        raise GAMNormalizationError("GAM result date range differs from its validated profile")
    maturity_boundary = run_time.astimezone(source_zone).date() - timedelta(days=1)

    points: list[NormalizedMetricPoint] = []
    limitations: set[str] = set()
    if not rows:
        limitations.add("NO_ROWS_RETURNED")
    for raw in rows:
        row = _mapping(raw, "row")
        raw_dimensions = row.get("dimensionValues")
        if not isinstance(raw_dimensions, list) or len(raw_dimensions) != len(
            definition.dimensions
        ):
            raise GAMNormalizationError("GAM dimension cardinality changed")
        dimensions = {
            name: _dimension_value(value, name)
            for name, value in zip(definition.dimensions, raw_dimensions, strict=True)
        }
        local_date = _iso_date(dimensions.get("DATE"), "DATE")
        if local_date < start_date or local_date > end_date:
            raise GAMNormalizationError("GAM row date is outside the reported range")
        hour = _hour(dimensions.get("HOUR"))
        period_start, period_end, ambiguous = _local_hour_interval(local_date, hour, source_zone)
        if ambiguous:
            limitations.add("DST_AMBIGUOUS_HOUR")
        freshness: FreshnessStatus = "PRELIMINARY" if local_date >= maturity_boundary else "MATURE"
        if freshness == "PRELIMINARY":
            limitations.add("RECENT_DATA_PRELIMINARY")
        metric_groups = row.get("metricValueGroups")
        if not isinstance(metric_groups, list) or len(metric_groups) != 1:
            raise GAMNormalizationError("GAM metric group cardinality changed")
        group = _mapping(metric_groups[0], "metricValueGroup")
        raw_metrics = group.get("primaryValues")
        if not isinstance(raw_metrics, list) or len(raw_metrics) != len(definition.metrics):
            raise GAMNormalizationError("GAM metric cardinality changed")
        series_dimensions = {
            name.lower(): value
            for name, value in dimensions.items()
            if name not in {"DATE", "HOUR"}
        }
        series_dimensions["network_code"] = network.network_code
        series_dimensions["currency_code"] = network.currency_code
        source_time = f"{local_date.isoformat()}T{hour:02d}:00[{network.timezone}]"
        for metric, raw_value in zip(definition.metrics, raw_metrics, strict=True):
            value = _metric_value(raw_value, metric.api_name, metric.unit)
            points.append(
                NormalizedMetricPoint(
                    metric_code=metric.metric_code,
                    metric_semantics_version=definition.semantics_version,
                    unit=metric.unit,
                    granularity=definition.granularity,
                    dimensions=series_dimensions,
                    source_time=source_time,
                    period_start=period_start,
                    period_end=period_end,
                    value=value,
                    freshness_status=freshness,
                )
            )
    response_metadata = {
        "networkCode": network.network_code,
        "sourceTimezone": network.timezone,
        "currencyCode": network.currency_code,
        "reportResource": _required_string(payload.get("reportResource"), "reportResource", 500),
        "operationName": _required_string(payload.get("operationName"), "operationName", 500),
        "reportResult": _required_string(payload.get("reportResult"), "reportResult", 500),
        "runTime": run_time.isoformat(),
        "dateRange": {"startDate": start_date.isoformat(), "endDate": end_date.isoformat()},
        "pagination": {
            "pagesFetched": _positive_int(pagination.get("pagesFetched"), "pagesFetched"),
            "pageSize": _positive_int(pagination.get("pageSize"), "pageSize"),
            "totalRowCount": total_rows,
            "allPagesFetched": True,
        },
        "lifecycle": [
            "API_REQUESTED",
            "REPORT_RUNNING",
            "RESULT_FETCHING",
            "NORMALIZING",
            "COMPLETE",
        ],
        "returnedRowCount": len(rows),
        "limitations": sorted(limitations),
    }
    normalized = NormalizedExtract(
        source_timezone=network.timezone,
        points=tuple(points),
        response_metadata=response_metadata,
        limitations=tuple(sorted(limitations)),
    )
    return GAMNormalizedResult(normalized, period)


def _local_hour_interval(
    local_date: date, hour: int, zone: ZoneInfo
) -> tuple[datetime, datetime, bool]:
    naive = datetime.combine(local_date, datetime.min.time()).replace(hour=hour)
    candidates: list[datetime] = []
    for fold in (0, 1):
        local = naive.replace(tzinfo=zone, fold=fold)
        utc = local.astimezone(UTC)
        if utc.astimezone(zone).replace(tzinfo=None) == naive and utc not in candidates:
            candidates.append(utc)
    if not candidates:
        raise GAMNormalizationError("GAM row refers to a nonexistent local DST hour")
    candidates.sort()
    return candidates[0], candidates[-1] + timedelta(hours=1), len(candidates) == 2


def _dimension_value(raw: Any, field: str) -> str:
    value = _mapping(raw, f"dimension {field}")
    keys = [key for key in ("stringValue", "intValue") if key in value]
    if len(keys) != 1 or len(value) != 1:
        raise GAMNormalizationError(f"GAM dimension {field} has an invalid value type")
    raw_value = value[keys[0]]
    if not isinstance(raw_value, str) or not raw_value or len(raw_value) > 2048:
        raise GAMNormalizationError(f"GAM dimension {field} is invalid")
    return raw_value


def _metric_value(raw: Any, field: str, unit: str) -> float:
    value = _mapping(raw, f"metric {field}")
    if unit == "COUNT":
        if set(value) != {"intValue"}:
            raise GAMNormalizationError(f"GAM count metric {field} must be integral")
        raw_value = value["intValue"]
        try:
            parsed = int(raw_value)
        except (TypeError, ValueError) as error:
            raise GAMNormalizationError(f"GAM count metric {field} is invalid") from error
        number = float(parsed)
    else:
        if set(value) == {"doubleValue"}:
            raw_value = value["doubleValue"]
        elif set(value) == {"intValue"}:
            raw_value = value["intValue"]
        else:
            raise GAMNormalizationError(f"GAM numeric metric {field} has an invalid type")
        if isinstance(raw_value, bool):
            raise GAMNormalizationError(f"GAM numeric metric {field} is invalid")
        try:
            number = float(raw_value)
        except (TypeError, ValueError) as error:
            raise GAMNormalizationError(f"GAM numeric metric {field} is invalid") from error
    if not math.isfinite(number) or number < 0 or number > 1e18:
        raise GAMNormalizationError(f"GAM metric {field} is outside the supported bound")
    return number


def _google_date(raw: Any, field: str) -> date:
    value = _mapping(raw, field)
    try:
        result = date(int(value["year"]), int(value["month"]), int(value["day"]))
    except (KeyError, TypeError, ValueError) as error:
        raise GAMNormalizationError(f"GAM {field} is invalid") from error
    return result


def _iso_date(raw: Any, field: str) -> date:
    if not isinstance(raw, str):
        raise GAMNormalizationError(f"GAM {field} is invalid")
    try:
        return date.fromisoformat(raw)
    except ValueError as error:
        raise GAMNormalizationError(f"GAM {field} is invalid") from error


def _hour(raw: Any) -> int:
    if not isinstance(raw, str):
        raise GAMNormalizationError("GAM HOUR is invalid")
    try:
        value = int(raw)
    except ValueError as error:
        raise GAMNormalizationError("GAM HOUR is invalid") from error
    if str(value) != raw or not 0 <= value <= 23:
        raise GAMNormalizationError("GAM HOUR is invalid")
    return value


def _rfc3339(raw: Any, field: str) -> datetime:
    if not isinstance(raw, str) or len(raw) > 100:
        raise GAMNormalizationError(f"GAM {field} is invalid")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as error:
        raise GAMNormalizationError(f"GAM {field} is invalid") from error
    if parsed.tzinfo is None:
        raise GAMNormalizationError(f"GAM {field} must include a timezone")
    return parsed.astimezone(UTC)


def _string_tuple(raw: Any, field: str) -> tuple[str, ...]:
    if not isinstance(raw, list) or not all(
        isinstance(item, str) and 0 < len(item) <= 200 for item in raw
    ):
        raise GAMNormalizationError(f"GAM {field} must be a bounded string list")
    return tuple(cast(list[str], raw))


def _mapping(raw: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(raw, dict):
        raise GAMNormalizationError(f"GAM {field} must be an object")
    return cast(dict[str, Any], raw)


def _required_string(raw: Any, field: str, limit: int) -> str:
    if not isinstance(raw, str) or not raw or len(raw) > limit:
        raise GAMNormalizationError(f"GAM {field} must be a bounded string")
    return raw


def _nonnegative_int(raw: Any, field: str) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
        raise GAMNormalizationError(f"GAM {field} is invalid")
    return cast(int, raw)


def _positive_int(raw: Any, field: str) -> int:
    value = _nonnegative_int(raw, field)
    if value < 1:
        raise GAMNormalizationError(f"GAM {field} is invalid")
    return value
