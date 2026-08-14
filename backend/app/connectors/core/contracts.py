import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal, Protocol

FreshnessStatus = Literal["PRELIMINARY", "MATURE", "STALE", "UNKNOWN"]


class ConnectorError(RuntimeError):
    """Sanitized connector failure safe for job and connection state."""

    def __init__(self, code: str, *, retryable: bool, message: str) -> None:
        super().__init__(message)
        self.code = code[:100]
        self.retryable = retryable


class SecretResolutionError(ConnectorError):
    pass


@dataclass(frozen=True, slots=True)
class AccessCredential:
    access_token: str


class AccessTokenResolver(Protocol):
    async def resolve(self, secret_reference: str) -> AccessCredential: ...


class PersistableExtractDefinition(Protocol):
    @property
    def code(self) -> str: ...

    @property
    def connector_version(self) -> str: ...


@dataclass(frozen=True, slots=True)
class ConnectionSnapshot:
    id: uuid.UUID
    tenant_id: uuid.UUID
    site_id: uuid.UUID
    provider: str
    external_property_id: str
    status: str
    scopes: tuple[str, ...]
    secret_reference: str
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ExtractPeriod:
    start_date: date
    end_date: date

    def __post_init__(self) -> None:
        if self.end_date < self.start_date:
            raise ValueError("extract end_date must be on or after start_date")
        if (self.end_date - self.start_date).days > 31:
            raise ValueError("routine extract period cannot exceed 32 inclusive days")


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    api_name: str
    metric_code: str
    unit: Literal["COUNT", "RATIO", "NUMBER"]


@dataclass(frozen=True, slots=True)
class ExtractDefinition:
    code: str
    connector_version: str
    semantics_version: str
    granularity: Literal["HOUR", "DAY"]
    dimensions: tuple[str, ...]
    metrics: tuple[MetricDefinition, ...]

    def query_definition(self, period: ExtractPeriod) -> dict[str, Any]:
        return {
            "definition": self.code,
            "connectorVersion": self.connector_version,
            "dimensions": list(self.dimensions),
            "metrics": [metric.api_name for metric in self.metrics],
            "dateRanges": [
                {
                    "startDate": period.start_date.isoformat(),
                    "endDate": period.end_date.isoformat(),
                }
            ],
            "filters": None,
            "keepEmptyRows": False,
            "returnPropertyQuota": True,
        }


@dataclass(frozen=True, slots=True)
class NormalizedMetricPoint:
    metric_code: str
    metric_semantics_version: str
    unit: str
    granularity: str
    dimensions: dict[str, str]
    source_time: str
    period_start: datetime
    period_end: datetime
    value: float
    numerator: float | None = None
    denominator: float | None = None
    freshness_status: FreshnessStatus | None = None


@dataclass(frozen=True, slots=True)
class NormalizedExtract:
    source_timezone: str
    points: tuple[NormalizedMetricPoint, ...]
    response_metadata: dict[str, Any]
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExtractStart:
    extract_id: uuid.UUID
    created: bool
    already_complete: bool
