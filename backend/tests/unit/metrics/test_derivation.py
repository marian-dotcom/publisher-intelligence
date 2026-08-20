import uuid
from datetime import UTC, datetime, timedelta

from app.metrics.contracts import REQUESTS_PER_VIEW_V1, SourceMetricPoint
from app.metrics.derivation import derive_ratios

START = datetime(2026, 8, 19, 10, tzinfo=UTC)
END = START + timedelta(hours=1)


def point(
    *,
    source: str,
    code: str,
    value: float,
    freshness: str = "MATURE",
    series_id: uuid.UUID | None = None,
    retrieved_offset: int = 0,
    semantics: str | None = None,
    extract_type: str | None = None,
    sample_status: str = "COMPLETE",
    limitations: tuple[str, ...] = (),
) -> SourceMetricPoint:
    return SourceMetricPoint(
        id=uuid.uuid4(),
        series_id=series_id or uuid.uuid4(),
        source=source,
        metric_code=code,
        metric_semantics_version=semantics
        or ("ga4-core-v1" if source == "GA4" else "gam-historical-v1"),
        extract_type=extract_type
        or ("GA4_TRAFFIC_HOURLY_V1" if source == "GA4" else "GAM_INVENTORY_HEALTH_V1"),
        period_start=START,
        period_end=END,
        value=value,
        freshness_status=freshness,
        sample_status=sample_status,
        retrieved_at=END + timedelta(minutes=retrieved_offset),
        limitations=limitations,
    )


def test_ratio_aggregates_dimensions_and_preserves_all_inputs() -> None:
    points = (
        point(source="GA4", code="ga4.screen_page_views", value=60),
        point(source="GA4", code="ga4.screen_page_views", value=40),
        point(source="GAM", code="gam.ad_requests", value=150),
        point(
            source="GAM",
            code="gam.ad_requests",
            value=50,
            sample_status="LIMITED",
            limitations=("DST_AMBIGUOUS_HOUR",),
        ),
    )

    candidates, skipped = derive_ratios(points, REQUESTS_PER_VIEW_V1)

    assert skipped == {}
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.numerator == 200
    assert candidate.denominator == 100
    assert candidate.value == 2
    assert candidate.freshness_status == "MATURE"
    assert candidate.limitations == ("DST_AMBIGUOUS_HOUR", "SOURCE_POINT_LIMITED")
    assert len(candidate.inputs) == 4


def test_best_current_prefers_mature_reconciliation_without_double_counting() -> None:
    series_id = uuid.uuid4()
    points = (
        point(
            source="GA4",
            code="ga4.screen_page_views",
            value=80,
            freshness="PRELIMINARY",
            series_id=series_id,
            retrieved_offset=10,
        ),
        point(
            source="GA4",
            code="ga4.screen_page_views",
            value=100,
            freshness="MATURE",
            series_id=series_id,
        ),
        point(source="GAM", code="gam.ad_requests", value=200),
    )

    candidates, skipped = derive_ratios(points, REQUESTS_PER_VIEW_V1)

    assert skipped == {}
    assert len(candidates) == 1
    assert candidates[0].denominator == 100
    assert candidates[0].value == 2
    assert len(candidates[0].inputs) == 2


def test_missing_zero_and_incompatible_freshness_never_create_a_ratio() -> None:
    missing, missing_skips = derive_ratios(
        (point(source="GAM", code="gam.ad_requests", value=10),), REQUESTS_PER_VIEW_V1
    )
    zero, zero_skips = derive_ratios(
        (
            point(source="GAM", code="gam.ad_requests", value=10),
            point(source="GA4", code="ga4.screen_page_views", value=0),
        ),
        REQUESTS_PER_VIEW_V1,
    )
    mixed, mixed_skips = derive_ratios(
        (
            point(source="GAM", code="gam.ad_requests", value=10, freshness="PRELIMINARY"),
            point(source="GA4", code="ga4.screen_page_views", value=10),
        ),
        REQUESTS_PER_VIEW_V1,
    )

    assert missing == () and missing_skips == {"MISSING_DENOMINATOR": 1}
    assert zero == () and zero_skips == {"ZERO_DENOMINATOR": 1}
    assert mixed == () and mixed_skips == {"INCOMPATIBLE_FRESHNESS": 1}


def test_wrong_source_semantics_are_missing_not_comparable() -> None:
    candidates, skipped = derive_ratios(
        (
            point(source="GAM", code="gam.ad_requests", value=10),
            point(
                source="GA4",
                code="ga4.screen_page_views",
                value=10,
                semantics="ga4-core-v2",
            ),
        ),
        REQUESTS_PER_VIEW_V1,
    )

    assert candidates == ()
    assert skipped == {"MISSING_DENOMINATOR": 1}
