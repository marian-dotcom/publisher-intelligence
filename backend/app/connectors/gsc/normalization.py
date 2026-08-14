import math
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

from app.connectors.core.contracts import (
    ConnectorError,
    FreshnessStatus,
    NormalizedExtract,
    NormalizedMetricPoint,
)
from app.connectors.gsc.definitions import GSC_SOURCE_TIMEZONE, GSCExtractDefinition

_SOURCE_ZONE = ZoneInfo(GSC_SOURCE_TIMEZONE)


class GSCNormalizationError(ConnectorError):
    def __init__(self, message: str) -> None:
        super().__init__("INVALID_RESPONSE", retryable=False, message=message)


def validate_property_access(payload: Mapping[str, Any], property_id: str) -> str:
    entries = payload.get("siteEntry", [])
    if not isinstance(entries, list):
        raise GSCNormalizationError("GSC siteEntry must be a list")
    for raw in entries:
        entry = _mapping(raw, "siteEntry item")
        site_url = _required_string(entry.get("siteUrl"), "siteUrl", 200)
        if site_url != property_id:
            continue
        permission = _required_string(entry.get("permissionLevel"), "permissionLevel", 50)
        if permission == "siteUnverifiedUser":
            raise ConnectorError(
                "PERMISSION_ERROR",
                retryable=False,
                message="GSC property is not verified for this credential",
            )
        if permission not in {"siteOwner", "siteFullUser", "siteRestrictedUser"}:
            raise GSCNormalizationError("GSC property permission is unknown")
        return permission
    raise ConnectorError(
        "PERMISSION_ERROR", retryable=False, message="GSC property is not accessible"
    )


def normalize_query(
    payload: Mapping[str, Any], definition: GSCExtractDefinition
) -> NormalizedExtract:
    rows = payload.get("rows", [])
    if not isinstance(rows, list) or len(rows) > definition.max_rows:
        raise GSCNormalizationError("GSC rows exceed the fixed response bound")
    metadata = _mapping(payload.get("metadata", {}), "metadata")
    pagination = _mapping(payload.get("pagination", {}), "pagination")
    aggregation = payload.get("responseAggregationType")
    if aggregation not in {None, "auto", "byPage", "byProperty"}:
        raise GSCNormalizationError("GSC response aggregation is invalid")

    incomplete_date = _optional_date(metadata.get("first_incomplete_date"))
    incomplete_hour = _optional_hour(metadata.get("first_incomplete_hour"))
    if definition.data_state == "final" and (incomplete_date or incomplete_hour):
        raise GSCNormalizationError("Final GSC response cannot declare incomplete data")
    if definition.data_state == "all" and incomplete_hour is not None:
        raise GSCNormalizationError("Daily GSC response returned hourly incomplete metadata")
    if definition.data_state == "hourly_all" and incomplete_date is not None:
        raise GSCNormalizationError("Hourly GSC response returned daily incomplete metadata")

    points: list[NormalizedMetricPoint] = []
    for raw in rows:
        row = _mapping(raw, "row")
        keys = _keys(row.get("keys"), len(definition.dimensions))
        dimensions = dict(zip(definition.dimensions, keys, strict=True))
        period_start, period_end, source_time, row_freshness = _period(
            dimensions,
            definition,
            incomplete_date=incomplete_date,
            incomplete_hour=incomplete_hour,
        )
        series_dimensions = {
            key: value for key, value in dimensions.items() if key not in {"date", "hour"}
        }
        values = {
            metric.api_name: _metric_value(row.get(metric.api_name), metric.api_name, metric.unit)
            for metric in definition.metrics
        }
        for metric in definition.metrics:
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
                    value=values[metric.api_name],
                    numerator=values["clicks"] if metric.api_name == "ctr" else None,
                    denominator=values["impressions"] if metric.api_name == "ctr" else None,
                    freshness_status=row_freshness,
                )
            )

    cap_reached = _optional_bool(pagination.get("capReached"), "pagination.capReached")
    limitations = ["TOP_ROWS_ONLY"]
    if cap_reached:
        limitations.append("ROW_LIMIT_REACHED")
    if incomplete_date is not None or incomplete_hour is not None:
        limitations.append("INCOMPLETE_DATA")
    response_metadata = {
        "searchType": definition.search_type,
        "dataState": definition.data_state,
        "sourceTimezone": GSC_SOURCE_TIMEZONE,
        "responseAggregationType": aggregation,
        "firstIncompleteDate": incomplete_date.isoformat() if incomplete_date else None,
        "firstIncompleteHour": incomplete_hour.isoformat() if incomplete_hour else None,
        "firstIncompleteDateSource": metadata.get("first_incomplete_date"),
        "firstIncompleteHourSource": metadata.get("first_incomplete_hour"),
        "pagination": _sanitize_pagination(pagination, len(rows)),
        "returnedRowCount": len(rows),
        "limitations": limitations,
    }
    return NormalizedExtract(
        source_timezone=GSC_SOURCE_TIMEZONE,
        points=tuple(points),
        response_metadata=response_metadata,
        limitations=tuple(limitations),
    )


def normalize_inspection(payload: Mapping[str, Any]) -> dict[str, Any]:
    result = _mapping(payload.get("inspectionResult"), "inspectionResult")
    index = _mapping(result.get("indexStatusResult"), "indexStatusResult")
    allowed = {
        "verdict",
        "coverageState",
        "robotsTxtState",
        "indexingState",
        "pageFetchState",
        "googleCanonical",
        "userCanonical",
        "lastCrawlTime",
        "crawledAs",
    }
    sanitized: dict[str, str] = {}
    for name in allowed:
        raw = index.get(name)
        if raw is not None:
            sanitized[name] = _required_string(raw, f"indexStatusResult.{name}", 2048)
    if "verdict" not in sanitized:
        raise GSCNormalizationError("GSC URL Inspection verdict is missing")
    return {"indexStatusResult": sanitized}


def _period(
    dimensions: Mapping[str, str],
    definition: GSCExtractDefinition,
    *,
    incomplete_date: date | None,
    incomplete_hour: datetime | None,
) -> tuple[datetime, datetime, str, FreshnessStatus]:
    if definition.granularity == "DAY":
        raw = dimensions.get("date")
        try:
            local_date = date.fromisoformat(raw or "")
        except ValueError as error:
            raise GSCNormalizationError("GSC date dimension is invalid") from error
        local_start = datetime.combine(local_date, datetime.min.time(), tzinfo=_SOURCE_ZONE)
        freshness: FreshnessStatus = (
            "PRELIMINARY"
            if incomplete_date is not None and local_date >= incomplete_date
            else "MATURE"
        )
        return (
            local_start.astimezone(UTC),
            (local_start + timedelta(days=1)).astimezone(UTC),
            raw or "",
            freshness,
        )
    raw = dimensions.get("hour")
    try:
        parsed = datetime.fromisoformat(raw or "")
    except ValueError as error:
        raise GSCNormalizationError("GSC hour dimension is invalid") from error
    if parsed.tzinfo is None or parsed.minute or parsed.second or parsed.microsecond:
        raise GSCNormalizationError("GSC hour dimension must be an offset hour")
    local = parsed.astimezone(_SOURCE_ZONE)
    if parsed.utcoffset() != local.utcoffset() or parsed.replace(tzinfo=None) != local.replace(
        tzinfo=None
    ):
        raise GSCNormalizationError("GSC hour is not in America/Los_Angeles")
    start = parsed.astimezone(UTC)
    freshness = (
        "PRELIMINARY" if incomplete_hour is not None and start >= incomplete_hour else "MATURE"
    )
    return start, start + timedelta(hours=1), raw or "", freshness


def _metric_value(raw: Any, field: str, unit: str) -> float:
    if isinstance(raw, bool):
        raise GSCNormalizationError(f"GSC {field} must be numeric")
    try:
        value = float(raw)
    except (TypeError, ValueError) as error:
        raise GSCNormalizationError(f"GSC {field} must be numeric") from error
    if not math.isfinite(value) or value < 0 or value > 1e18:
        raise GSCNormalizationError(f"GSC {field} is outside the supported bound")
    if field == "ctr" and value > 1:
        raise GSCNormalizationError("GSC ctr must be between zero and one")
    if unit == "COUNT" and not value.is_integer():
        raise GSCNormalizationError(f"GSC {field} count must be integral")
    return value


def _keys(raw: Any, expected: int) -> tuple[str, ...]:
    if not isinstance(raw, list) or len(raw) != expected:
        raise GSCNormalizationError("GSC row key cardinality does not match the definition")
    if not all(isinstance(value, str) and len(value) <= 2048 for value in raw):
        raise GSCNormalizationError("GSC row contains an invalid key")
    return tuple(cast(list[str], raw))


def _optional_date(raw: Any) -> date | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise GSCNormalizationError("GSC first incomplete date is invalid")
    try:
        return date.fromisoformat(raw)
    except ValueError as error:
        raise GSCNormalizationError("GSC first incomplete date is invalid") from error


def _optional_hour(raw: Any) -> datetime | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise GSCNormalizationError("GSC first incomplete hour is invalid")
    try:
        value = datetime.fromisoformat(raw)
    except ValueError as error:
        raise GSCNormalizationError("GSC first incomplete hour is invalid") from error
    if value.tzinfo is None or value.minute or value.second or value.microsecond:
        raise GSCNormalizationError("GSC first incomplete hour is invalid")
    local = value.astimezone(_SOURCE_ZONE)
    if value.utcoffset() != local.utcoffset() or value.replace(tzinfo=None) != local.replace(
        tzinfo=None
    ):
        raise GSCNormalizationError("GSC incomplete hour is not Pacific time")
    return value.astimezone(UTC)


def _sanitize_pagination(raw: Mapping[str, Any], returned: int) -> dict[str, Any]:
    return {
        "pagesRequested": _nonnegative_int(raw.get("pagesRequested"), "pagesRequested"),
        "returnedRows": _nonnegative_int(raw.get("returnedRows"), "returnedRows"),
        "rowLimit": _positive_int(raw.get("rowLimit"), "rowLimit"),
        "maxRows": _positive_int(raw.get("maxRows"), "maxRows"),
        "capReached": _optional_bool(raw.get("capReached"), "capReached"),
        "normalizedRows": returned,
    }


def _nonnegative_int(raw: Any, field: str) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
        raise GSCNormalizationError(f"GSC pagination {field} is invalid")
    return cast(int, raw)


def _positive_int(raw: Any, field: str) -> int:
    value = _nonnegative_int(raw, field)
    if value < 1:
        raise GSCNormalizationError(f"GSC pagination {field} is invalid")
    return value


def _optional_bool(raw: Any, field: str) -> bool:
    if raw is None:
        return False
    if not isinstance(raw, bool):
        raise GSCNormalizationError(f"GSC {field} must be boolean")
    return raw


def _mapping(raw: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(raw, dict):
        raise GSCNormalizationError(f"GSC {field} must be an object")
    return cast(dict[str, Any], raw)


def _required_string(raw: Any, field: str, limit: int) -> str:
    if not isinstance(raw, str) or not raw or len(raw) > limit:
        raise GSCNormalizationError(f"GSC {field} must be a bounded string")
    return raw
