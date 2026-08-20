import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

Freshness = Literal["PRELIMINARY", "MATURE"]
InputRole = Literal["NUMERATOR", "DENOMINATOR"]

CROSS_SOURCE_RULE_VERSION = "cross-source-ratios-v1"
CROSS_SOURCE_ENGINE_VERSION = "metrics-engine-v1"
EXACT_UTC_ALIGNMENT = "EXACT_UTC_INTERVAL_V1"
STRICT_FRESHNESS_POLICY = "EQUAL_NON_STALE_V1"


@dataclass(frozen=True, slots=True)
class RatioDefinition:
    metric_code: str
    numerator_source: str
    numerator_metric_code: str
    numerator_semantics_version: str
    numerator_extract_type: str
    denominator_source: str
    denominator_metric_code: str
    denominator_semantics_version: str
    denominator_extract_type: str


REQUESTS_PER_VIEW_V1 = RatioDefinition(
    metric_code="derived.requests_per_view_v1",
    numerator_source="GAM",
    numerator_metric_code="gam.ad_requests",
    numerator_semantics_version="gam-historical-v1",
    numerator_extract_type="GAM_INVENTORY_HEALTH_V1",
    denominator_source="GA4",
    denominator_metric_code="ga4.screen_page_views",
    denominator_semantics_version="ga4-core-v1",
    denominator_extract_type="GA4_TRAFFIC_HOURLY_V1",
)

IMPRESSIONS_PER_VIEW_V1 = RatioDefinition(
    metric_code="derived.impressions_per_view_v1",
    numerator_source="GAM",
    numerator_metric_code="gam.ad_server_impressions",
    numerator_semantics_version="gam-historical-v1",
    numerator_extract_type="GAM_INVENTORY_HEALTH_V1",
    denominator_source="GA4",
    denominator_metric_code="ga4.screen_page_views",
    denominator_semantics_version="ga4-core-v1",
    denominator_extract_type="GA4_TRAFFIC_HOURLY_V1",
)

CROSS_SOURCE_RATIO_DEFINITIONS = (REQUESTS_PER_VIEW_V1, IMPRESSIONS_PER_VIEW_V1)


@dataclass(frozen=True, slots=True)
class SourceMetricPoint:
    id: uuid.UUID
    series_id: uuid.UUID
    source: str
    metric_code: str
    metric_semantics_version: str
    extract_type: str
    period_start: datetime
    period_end: datetime
    value: float
    freshness_status: str
    sample_status: str | None
    retrieved_at: datetime
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DerivationInput:
    point_id: uuid.UUID
    role: InputRole


@dataclass(frozen=True, slots=True)
class RatioCandidate:
    definition: RatioDefinition
    period_start: datetime
    period_end: datetime
    numerator: float
    denominator: float
    value: float
    freshness_status: Freshness
    limitations: tuple[str, ...]
    inputs: tuple[DerivationInput, ...]
    input_fingerprint: str


@dataclass(frozen=True, slots=True)
class DerivationResult:
    candidate_count: int
    created_count: int
    skipped_counts: dict[str, int]
