import hashlib
from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import datetime
from typing import cast

from app.metrics.contracts import (
    DerivationInput,
    Freshness,
    RatioCandidate,
    RatioDefinition,
    SourceMetricPoint,
)

_ACCEPTED_FRESHNESS = {"PRELIMINARY", "MATURE"}
_FRESHNESS_RANK = {"PRELIMINARY": 1, "MATURE": 2}


def derive_ratios(
    points: Iterable[SourceMetricPoint], definition: RatioDefinition
) -> tuple[tuple[RatioCandidate, ...], dict[str, int]]:
    relevant = tuple(point for point in points if _matches_definition(point, definition))
    selected = _best_current_points(relevant)
    grouped: dict[tuple[datetime, datetime, str], list[SourceMetricPoint]] = defaultdict(list)
    for point in selected:
        grouped[(point.period_start, point.period_end, point.metric_code)].append(point)

    numerator_buckets = {
        (start, end): bucket
        for (start, end, code), bucket in grouped.items()
        if code == definition.numerator_metric_code
    }
    denominator_buckets = {
        (start, end): bucket
        for (start, end, code), bucket in grouped.items()
        if code == definition.denominator_metric_code
    }
    skipped: Counter[str] = Counter()
    candidates: list[RatioCandidate] = []
    all_intervals = sorted(set(numerator_buckets) | set(denominator_buckets))
    for interval in all_intervals:
        numerators = numerator_buckets.get(interval)
        denominators = denominator_buckets.get(interval)
        if numerators is None:
            skipped["MISSING_NUMERATOR"] += 1
            continue
        if denominators is None:
            skipped["MISSING_DENOMINATOR"] += 1
            continue
        freshness = _compatible_freshness(numerators, denominators)
        if freshness is None:
            skipped["INCOMPATIBLE_FRESHNESS"] += 1
            continue
        numerator = sum(point.value for point in numerators)
        denominator = sum(point.value for point in denominators)
        if denominator <= 0:
            skipped["ZERO_DENOMINATOR"] += 1
            continue
        inputs = tuple(
            sorted(
                (
                    *(DerivationInput(point.id, "NUMERATOR") for point in numerators),
                    *(DerivationInput(point.id, "DENOMINATOR") for point in denominators),
                ),
                key=lambda item: (item.role, item.point_id.hex),
            )
        )
        limitations = tuple(
            sorted(
                {
                    limitation
                    for point in (*numerators, *denominators)
                    for limitation in point.limitations
                }
                | {
                    "SOURCE_POINT_LIMITED"
                    for point in (*numerators, *denominators)
                    if point.sample_status == "LIMITED"
                }
            )
        )
        fingerprint = _input_fingerprint(inputs)
        candidates.append(
            RatioCandidate(
                definition=definition,
                period_start=interval[0],
                period_end=interval[1],
                numerator=numerator,
                denominator=denominator,
                value=numerator / denominator,
                freshness_status=freshness,
                limitations=limitations,
                inputs=inputs,
                input_fingerprint=fingerprint,
            )
        )
    return tuple(candidates), dict(sorted(skipped.items()))


def _matches_definition(point: SourceMetricPoint, definition: RatioDefinition) -> bool:
    numerator = (
        point.source == definition.numerator_source
        and point.metric_code == definition.numerator_metric_code
        and point.metric_semantics_version == definition.numerator_semantics_version
        and point.extract_type == definition.numerator_extract_type
    )
    denominator = (
        point.source == definition.denominator_source
        and point.metric_code == definition.denominator_metric_code
        and point.metric_semantics_version == definition.denominator_semantics_version
        and point.extract_type == definition.denominator_extract_type
    )
    return numerator or denominator


def _best_current_points(points: Iterable[SourceMetricPoint]) -> tuple[SourceMetricPoint, ...]:
    selected: dict[tuple[object, datetime, datetime], SourceMetricPoint] = {}
    for point in points:
        key = (point.series_id, point.period_start, point.period_end)
        incumbent = selected.get(key)
        if incumbent is None or _selection_key(point) > _selection_key(incumbent):
            selected[key] = point
    return tuple(selected.values())


def _selection_key(point: SourceMetricPoint) -> tuple[int, datetime, str]:
    return (_FRESHNESS_RANK.get(point.freshness_status, 0), point.retrieved_at, point.id.hex)


def _compatible_freshness(
    numerators: Iterable[SourceMetricPoint], denominators: Iterable[SourceMetricPoint]
) -> Freshness | None:
    statuses = {point.freshness_status for point in (*tuple(numerators), *tuple(denominators))}
    if len(statuses) != 1:
        return None
    status = statuses.pop()
    return cast(Freshness, status) if status in _ACCEPTED_FRESHNESS else None


def _input_fingerprint(inputs: Iterable[DerivationInput]) -> str:
    canonical = "|".join(
        f"{item.role}:{item.point_id}"
        for item in sorted(inputs, key=lambda x: (x.role, x.point_id.hex))
    )
    return hashlib.sha256(canonical.encode()).hexdigest()
