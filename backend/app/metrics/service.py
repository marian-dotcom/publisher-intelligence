import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta

from app.metrics.contracts import CROSS_SOURCE_RATIO_DEFINITIONS, DerivationResult
from app.metrics.derivation import derive_ratios
from app.metrics.persistence import MetricDerivationRepository


class CrossSourceMetricService:
    def __init__(self, repository: MetricDerivationRepository) -> None:
        self._repository = repository

    async def derive_site(
        self,
        *,
        tenant_id: uuid.UUID,
        site_id: uuid.UUID,
        window_start: datetime,
        window_end: datetime,
    ) -> DerivationResult:
        if window_start.tzinfo is None or window_end.tzinfo is None:
            raise ValueError("derivation window must use timezone-aware timestamps")
        start = window_start.astimezone(UTC)
        end = window_end.astimezone(UTC)
        if end <= start:
            raise ValueError("derivation window must have positive duration")
        if end - start > timedelta(days=7):
            raise ValueError("derivation window cannot exceed seven days")
        points = await self._repository.load_source_points(
            tenant_id=tenant_id,
            site_id=site_id,
            window_start=start,
            window_end=end,
        )
        if not points:
            return DerivationResult(0, 0, {"NO_SOURCE_POINTS": 1})
        skipped: Counter[str] = Counter()
        candidate_count = 0
        created_count = 0
        for definition in CROSS_SOURCE_RATIO_DEFINITIONS:
            candidates, definition_skips = derive_ratios(points, definition)
            candidate_count += len(candidates)
            skipped.update(definition_skips)
            for candidate in candidates:
                created_count += int(
                    await self._repository.persist_candidate(
                        tenant_id=tenant_id,
                        site_id=site_id,
                        candidate=candidate,
                    )
                )
        return DerivationResult(candidate_count, created_count, dict(sorted(skipped.items())))
