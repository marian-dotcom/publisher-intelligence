import math
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.connectors.core.contracts import (
    ConnectorError,
    ExtractDefinition,
    NormalizedExtract,
    NormalizedMetricPoint,
)


class GA4NormalizationError(ConnectorError):
    def __init__(self, message: str) -> None:
        super().__init__("INVALID_RESPONSE", retryable=False, message=message)


def validate_metadata(payload: Mapping[str, Any], definition: ExtractDefinition) -> dict[str, Any]:
    dimensions = _metadata_names(payload.get("dimensions"), "dimensions")
    metrics = _metadata_names(payload.get("metrics"), "metrics")
    missing_dimensions = sorted(set(definition.dimensions) - dimensions)
    required_metrics = {metric.api_name for metric in definition.metrics}
    missing_metrics = sorted(required_metrics - metrics)
    if missing_dimensions or missing_metrics:
        raise ConnectorError(
            "SCHEMA_INCOMPATIBLE",
            retryable=False,
            message="GA4 property does not support the required report schema",
        )
    return {
        "metadataName": _optional_string(payload.get("name"), 300),
        "validatedDimensions": sorted(definition.dimensions),
        "validatedMetrics": sorted(required_metrics),
    }


def _metadata_names(raw: Any, field: str) -> set[str]:
    if not isinstance(raw, list):
        raise GA4NormalizationError(f"GA4 metadata {field} must be a list")
    names: set[str] = set()
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("apiName"), str):
            raise GA4NormalizationError(f"GA4 metadata {field} contains an invalid item")
        name = cast(str, item["apiName"])
        if not name or len(name) > 300:
            raise GA4NormalizationError(f"GA4 metadata {field} contains an invalid API name")
        names.add(name)
    return names


def normalize_report(
    payload: Mapping[str, Any], definition: ExtractDefinition
) -> NormalizedExtract:
    dimension_headers = _header_names(payload.get("dimensionHeaders"), "dimensionHeaders")
    metric_headers = _header_names(payload.get("metricHeaders"), "metricHeaders")
    if dimension_headers != definition.dimensions:
        raise GA4NormalizationError("GA4 dimension headers do not match the extract definition")
    expected_metrics = tuple(metric.api_name for metric in definition.metrics)
    if metric_headers != expected_metrics:
        raise GA4NormalizationError("GA4 metric headers do not match the extract definition")

    metadata = _mapping(payload.get("metadata", {}), "metadata")
    timezone_name = _required_string(metadata.get("timeZone"), "metadata.timeZone", 100)
    try:
        source_timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as error:
        raise GA4NormalizationError("GA4 property timezone is invalid") from error

    rows_raw = payload.get("rows", [])
    if not isinstance(rows_raw, list):
        raise GA4NormalizationError("GA4 rows must be a list")
    if len(rows_raw) > 250_000:
        raise GA4NormalizationError("GA4 response exceeds the supported row bound")

    points: list[NormalizedMetricPoint] = []
    for row in rows_raw:
        row_map = _mapping(row, "row")
        dimension_values = _row_values(
            row_map.get("dimensionValues"), len(dimension_headers), "dimensionValues"
        )
        metric_values = _row_values(
            row_map.get("metricValues"), len(metric_headers), "metricValues"
        )
        dimension_map = dict(zip(dimension_headers, dimension_values, strict=True))
        period_start, period_end, source_time = _period(
            dimension_map, definition.granularity, source_timezone
        )
        series_dimensions = {
            key: value for key, value in dimension_map.items() if key not in {"date", "dateHour"}
        }
        for metric, raw_value in zip(definition.metrics, metric_values, strict=True):
            value = _number(raw_value, metric.unit)
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
                )
            )

    response_metadata, limitations = _response_metadata(payload, metadata, len(rows_raw))
    response_metadata["sourceTimezone"] = timezone_name
    return NormalizedExtract(
        source_timezone=timezone_name,
        points=tuple(points),
        response_metadata=response_metadata,
        limitations=tuple(limitations),
    )


def _header_names(raw: Any, field: str) -> tuple[str, ...]:
    if not isinstance(raw, list):
        raise GA4NormalizationError(f"GA4 {field} must be a list")
    names: list[str] = []
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise GA4NormalizationError(f"GA4 {field} contains an invalid header")
        name = cast(str, item["name"])
        if not name or len(name) > 300:
            raise GA4NormalizationError(f"GA4 {field} contains an invalid header name")
        names.append(name)
    return tuple(names)


def _row_values(raw: Any, expected: int, field: str) -> tuple[str, ...]:
    if not isinstance(raw, list) or len(raw) != expected:
        raise GA4NormalizationError(f"GA4 {field} cardinality does not match headers")
    values: list[str] = []
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("value"), str):
            raise GA4NormalizationError(f"GA4 {field} contains an invalid value")
        value = cast(str, item["value"])
        if len(value) > 1000:
            raise GA4NormalizationError(f"GA4 {field} value exceeds the supported bound")
        values.append(value)
    return tuple(values)


def _period(
    dimensions: Mapping[str, str], granularity: str, timezone: ZoneInfo
) -> tuple[datetime, datetime, str]:
    temporal_name = "dateHour" if granularity == "HOUR" else "date"
    raw = dimensions.get(temporal_name)
    expected_length = 10 if temporal_name == "dateHour" else 8
    if raw is None or len(raw) != expected_length or not raw.isdigit():
        raise GA4NormalizationError("GA4 temporal dimension is invalid")
    try:
        naive = datetime.strptime(raw, "%Y%m%d%H" if temporal_name == "dateHour" else "%Y%m%d")
    except ValueError as error:
        raise GA4NormalizationError("GA4 temporal dimension is invalid") from error
    local_start = naive.replace(tzinfo=timezone, fold=0)
    local_end = local_start + (timedelta(hours=1) if granularity == "HOUR" else timedelta(days=1))
    return local_start.astimezone(UTC), local_end.astimezone(UTC), raw


def _number(raw: str, unit: str) -> float:
    try:
        value = float(raw)
    except ValueError as error:
        raise GA4NormalizationError("GA4 metric value is not numeric") from error
    if not math.isfinite(value) or value < 0:
        raise GA4NormalizationError("GA4 metric value must be finite and non-negative")
    if unit == "RATIO" and value > 1_000_000:
        raise GA4NormalizationError("GA4 ratio exceeds the supported bound")
    if unit == "COUNT" and value > 1e18:
        raise GA4NormalizationError("GA4 count exceeds the supported bound")
    return value


def _response_metadata(
    payload: Mapping[str, Any], metadata: Mapping[str, Any], row_count: int
) -> tuple[dict[str, Any], list[str]]:
    other_row = _optional_bool(payload.get("dataLossFromOtherRow"), "dataLossFromOtherRow")
    thresholding = _optional_bool(
        metadata.get("subjectToThresholding"), "metadata.subjectToThresholding"
    )
    limitations: list[str] = []
    if other_row:
        limitations.append("OTHER_ROW_DATA_LOSS")
    if thresholding:
        limitations.append("THRESHOLDING_APPLIED")

    sampling = _sanitized_sampling(metadata.get("samplingMetadatas"))
    if sampling:
        limitations.append("SAMPLING_APPLIED")
    restrictions = _sanitized_restrictions(metadata.get("schemaRestrictionResponse"))
    if restrictions:
        limitations.append("PROPERTY_PERMISSION_LIMIT")
    quota = _sanitized_quota(payload.get("propertyQuota"))
    result: dict[str, Any] = {
        "rowCount": _row_count(payload.get("rowCount"), row_count),
        "returnedRowCount": row_count,
        "dataLossFromOtherRow": other_row,
        "subjectToThresholding": thresholding,
        "emptyReason": _optional_string(metadata.get("emptyReason"), 300),
        "sampling": sampling,
        "schemaRestrictions": restrictions,
        "propertyQuota": quota,
        "limitations": sorted(set(limitations)),
    }
    return result, sorted(set(limitations))


def _sanitized_sampling(raw: Any) -> list[dict[str, int]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise GA4NormalizationError("GA4 sampling metadata is invalid")
    result: list[dict[str, int]] = []
    for item in raw:
        mapping = _mapping(item, "sampling metadata")
        read = _nonnegative_int(mapping.get("samplesReadCount"), "samplesReadCount")
        space = _nonnegative_int(mapping.get("samplingSpaceSize"), "samplingSpaceSize")
        if read > space:
            raise GA4NormalizationError("GA4 sampling metadata is inconsistent")
        result.append({"samplesReadCount": read, "samplingSpaceSize": space})
    return result


def _sanitized_restrictions(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    mapping = _mapping(raw, "schemaRestrictionResponse")
    active = mapping.get("activeMetricRestrictions", [])
    if not isinstance(active, list):
        raise GA4NormalizationError("GA4 metric restrictions are invalid")
    result: list[dict[str, Any]] = []
    for item in active:
        restriction = _mapping(item, "active metric restriction")
        name = _required_string(restriction.get("metricName"), "metricName", 300)
        types = restriction.get("restrictedMetricTypes", [])
        if not isinstance(types, list) or not all(isinstance(value, str) for value in types):
            raise GA4NormalizationError("GA4 restriction types are invalid")
        result.append({"metricName": name, "restrictedMetricTypes": sorted(set(types))})
    return result


def _sanitized_quota(raw: Any) -> dict[str, dict[str, int]]:
    if raw is None:
        return {}
    mapping = _mapping(raw, "propertyQuota")
    result: dict[str, dict[str, int]] = {}
    for name, value in mapping.items():
        if name not in {
            "tokensPerDay",
            "tokensPerHour",
            "concurrentRequests",
            "serverErrorsPerProjectPerHour",
            "potentiallyThresholdedRequestsPerHour",
            "tokensPerProjectPerHour",
        }:
            continue
        status = _mapping(value, f"propertyQuota.{name}")
        result[name] = {
            "consumed": _nonnegative_int(status.get("consumed"), f"{name}.consumed"),
            "remaining": _nonnegative_int(status.get("remaining"), f"{name}.remaining"),
        }
    return result


def _row_count(raw: Any, fallback: int) -> int:
    if raw is None:
        return fallback
    return _nonnegative_int(raw, "rowCount")


def _nonnegative_int(raw: Any, field: str) -> int:
    if isinstance(raw, bool):
        raise GA4NormalizationError(f"GA4 {field} must be a non-negative integer")
    try:
        value = int(raw)
    except (TypeError, ValueError) as error:
        raise GA4NormalizationError(f"GA4 {field} must be a non-negative integer") from error
    if value < 0 or str(value) != str(raw):
        raise GA4NormalizationError(f"GA4 {field} must be a non-negative integer")
    return value


def _mapping(raw: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(raw, dict):
        raise GA4NormalizationError(f"GA4 {field} must be an object")
    return cast(dict[str, Any], raw)


def _required_string(raw: Any, field: str, limit: int) -> str:
    if not isinstance(raw, str) or not raw or len(raw) > limit:
        raise GA4NormalizationError(f"GA4 {field} must be a bounded string")
    return raw


def _optional_string(raw: Any, limit: int) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str) or len(raw) > limit:
        raise GA4NormalizationError("GA4 optional metadata string is invalid")
    return raw


def _optional_bool(raw: Any, field: str) -> bool:
    if raw is None:
        return False
    if not isinstance(raw, bool):
        raise GA4NormalizationError(f"GA4 {field} must be boolean")
    return raw
