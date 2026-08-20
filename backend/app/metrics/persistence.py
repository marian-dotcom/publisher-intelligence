import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.browser.models import Site
from app.connectors.core.persistence import _series_key
from app.connectors.models import DataConnection, MetricPoint, MetricSeries, SourceExtract
from app.metrics.contracts import (
    CROSS_SOURCE_ENGINE_VERSION,
    CROSS_SOURCE_RULE_VERSION,
    EXACT_UTC_ALIGNMENT,
    STRICT_FRESHNESS_POLICY,
    RatioCandidate,
    SourceMetricPoint,
)
from app.metrics.models import MetricDerivation, MetricDerivationInput


class MetricDerivationStateError(RuntimeError):
    pass


class MetricDerivationRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def load_source_points(
        self,
        *,
        tenant_id: uuid.UUID,
        site_id: uuid.UUID,
        window_start: datetime,
        window_end: datetime,
    ) -> tuple[SourceMetricPoint, ...]:
        async with self._session_factory() as session:
            site = await session.scalar(
                select(Site.id).where(Site.id == site_id, Site.tenant_id == tenant_id)
            )
            if site is None:
                raise MetricDerivationStateError("site does not belong to metric tenant")
            rows = (
                await session.execute(
                    select(MetricPoint, MetricSeries, SourceExtract)
                    .join(MetricSeries, MetricSeries.id == MetricPoint.series_id)
                    .join(SourceExtract, SourceExtract.id == MetricPoint.source_extract_id)
                    .where(
                        MetricPoint.tenant_id == tenant_id,
                        MetricPoint.site_id == site_id,
                        MetricPoint.period_start >= window_start,
                        MetricPoint.period_end <= window_end,
                        MetricPoint.source_extract_id.is_not(None),
                        MetricSeries.tenant_id == tenant_id,
                        MetricSeries.site_id == site_id,
                        MetricSeries.source.in_(["GA4", "GAM"]),
                        MetricSeries.granularity == "HOUR",
                        SourceExtract.tenant_id == tenant_id,
                        SourceExtract.site_id == site_id,
                        SourceExtract.status == "COMPLETE",
                    )
                )
            ).all()
        result: list[SourceMetricPoint] = []
        for point, series, extract in rows:
            result.append(
                SourceMetricPoint(
                    id=point.id,
                    series_id=series.id,
                    source=series.source,
                    metric_code=series.metric_code,
                    metric_semantics_version=series.metric_semantics_version,
                    extract_type=extract.extract_type,
                    period_start=point.period_start,
                    period_end=point.period_end,
                    value=point.value,
                    freshness_status=point.freshness_status,
                    sample_status=point.sample_status,
                    retrieved_at=point.retrieved_at,
                    limitations=_limitations(extract.response_metadata),
                )
            )
        return tuple(result)

    async def persist_candidate(
        self,
        *,
        tenant_id: uuid.UUID,
        site_id: uuid.UUID,
        candidate: RatioCandidate,
    ) -> bool:
        derivation_key = _derivation_key(tenant_id, site_id, candidate)
        derivation_id = uuid.uuid4()
        now = datetime.now(UTC)
        input_ids = {item.point_id for item in candidate.inputs}
        async with self._session_factory() as session, session.begin():
            await self._validate_inputs(
                session,
                tenant_id=tenant_id,
                site_id=site_id,
                candidate=candidate,
                input_ids=input_ids,
            )
            created_derivation = await session.scalar(
                insert(MetricDerivation)
                .values(
                    id=derivation_id,
                    tenant_id=tenant_id,
                    site_id=site_id,
                    definition_code=candidate.definition.metric_code,
                    rule_version=CROSS_SOURCE_RULE_VERSION,
                    engine_version=CROSS_SOURCE_ENGINE_VERSION,
                    alignment_policy=EXACT_UTC_ALIGNMENT,
                    freshness_policy=STRICT_FRESHNESS_POLICY,
                    granularity="HOUR",
                    period_start=candidate.period_start,
                    period_end=candidate.period_end,
                    freshness_status=candidate.freshness_status,
                    input_fingerprint=candidate.input_fingerprint,
                    derivation_key=derivation_key,
                    limitations=list(candidate.limitations),
                    definition=_definition_payload(candidate),
                )
                .on_conflict_do_nothing(constraint="uq_metric_derivations_key")
                .returning(MetricDerivation.id)
            )
            if created_derivation is None:
                return False

            dimensions = {
                "alignment": EXACT_UTC_ALIGNMENT,
                "denominator": "GA4_MEASURED_SCREEN_PAGE_VIEWS",
                "scope": "SITE",
            }
            series_key = _series_key(
                tenant_id=tenant_id,
                site_id=site_id,
                source="DERIVED",
                metric_code=candidate.definition.metric_code,
                semantics_version=CROSS_SOURCE_RULE_VERSION,
                granularity="HOUR",
                dimensions=dimensions,
            )
            proposed_series_id = uuid.uuid4()
            series_id = await session.scalar(
                insert(MetricSeries)
                .values(
                    id=proposed_series_id,
                    tenant_id=tenant_id,
                    site_id=site_id,
                    source="DERIVED",
                    metric_code=candidate.definition.metric_code,
                    metric_semantics_version=CROSS_SOURCE_RULE_VERSION,
                    unit="RATIO",
                    granularity="HOUR",
                    dimensions=dimensions,
                    series_key=series_key,
                )
                .on_conflict_do_nothing(constraint="uq_metric_series_key")
                .returning(MetricSeries.id)
            )
            if series_id is None:
                series_id = await session.scalar(
                    select(MetricSeries.id).where(
                        MetricSeries.series_key == series_key,
                        MetricSeries.tenant_id == tenant_id,
                        MetricSeries.site_id == site_id,
                    )
                )
            if series_id is None:
                raise MetricDerivationStateError("derived metric series conflict was unresolved")

            await session.execute(
                insert(MetricPoint).values(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    site_id=site_id,
                    series_id=series_id,
                    source_extract_id=None,
                    derivation_id=derivation_id,
                    source_time=candidate.period_start.isoformat(),
                    period_start=candidate.period_start,
                    period_end=candidate.period_end,
                    value=candidate.value,
                    numerator=candidate.numerator,
                    denominator=candidate.denominator,
                    sample_status="LIMITED" if candidate.limitations else "COMPLETE",
                    freshness_status=candidate.freshness_status,
                    retrieved_at=now,
                )
            )
            await session.execute(
                insert(MetricDerivationInput),
                [
                    {
                        "id": uuid.uuid4(),
                        "tenant_id": tenant_id,
                        "site_id": site_id,
                        "derivation_id": derivation_id,
                        "source_metric_point_id": item.point_id,
                        "role": item.role,
                    }
                    for item in candidate.inputs
                ],
            )
        return True

    async def schedulable_sites(self) -> tuple[tuple[uuid.UUID, uuid.UUID], ...]:
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(DataConnection.tenant_id, DataConnection.site_id)
                    .where(
                        DataConnection.provider.in_(["GA4", "GAM"]),
                        DataConnection.status.in_(["CONNECTED", "DEGRADED"]),
                        DataConnection.archived_at.is_(None),
                    )
                    .group_by(DataConnection.tenant_id, DataConnection.site_id)
                    .having(func.count(func.distinct(DataConnection.provider)) == 2)
                )
            ).all()
        return tuple((tenant_id, site_id) for tenant_id, site_id in rows)

    async def _validate_inputs(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        site_id: uuid.UUID,
        candidate: RatioCandidate,
        input_ids: set[uuid.UUID],
    ) -> None:
        if len(input_ids) != len(candidate.inputs):
            raise MetricDerivationStateError("derived input roles contain duplicates")
        rows = (
            await session.execute(
                select(MetricPoint, MetricSeries, SourceExtract)
                .join(MetricSeries, MetricSeries.id == MetricPoint.series_id)
                .join(SourceExtract, SourceExtract.id == MetricPoint.source_extract_id)
                .where(
                    MetricPoint.id.in_(input_ids),
                    MetricPoint.tenant_id == tenant_id,
                    MetricPoint.site_id == site_id,
                    MetricSeries.tenant_id == tenant_id,
                    MetricSeries.site_id == site_id,
                    SourceExtract.tenant_id == tenant_id,
                    SourceExtract.site_id == site_id,
                    SourceExtract.status == "COMPLETE",
                )
            )
        ).all()
        if len(rows) != len(input_ids):
            raise MetricDerivationStateError("derived input ownership or completeness changed")
        by_id = {point.id: (point, series, extract) for point, series, extract in rows}
        for derivation_input in candidate.inputs:
            point, series, extract = by_id[derivation_input.point_id]
            expected_source, expected_code, expected_semantics, expected_extract = (
                (
                    candidate.definition.numerator_source,
                    candidate.definition.numerator_metric_code,
                    candidate.definition.numerator_semantics_version,
                    candidate.definition.numerator_extract_type,
                )
                if derivation_input.role == "NUMERATOR"
                else (
                    candidate.definition.denominator_source,
                    candidate.definition.denominator_metric_code,
                    candidate.definition.denominator_semantics_version,
                    candidate.definition.denominator_extract_type,
                )
            )
            if (
                series.source != expected_source
                or series.metric_code != expected_code
                or series.metric_semantics_version != expected_semantics
                or series.granularity != "HOUR"
                or extract.extract_type != expected_extract
                or point.period_start != candidate.period_start
                or point.period_end != candidate.period_end
                or point.freshness_status != candidate.freshness_status
                or point.source_extract_id is None
                or point.derivation_id is not None
            ):
                raise MetricDerivationStateError("derived input semantics or interval changed")


def _limitations(metadata: Any) -> tuple[str, ...]:
    if not isinstance(metadata, dict):
        return ()
    values = metadata.get("limitations", [])
    if not isinstance(values, list):
        return ()
    return tuple(
        sorted({value for value in values if isinstance(value, str) and len(value) <= 100})
    )


def _definition_payload(candidate: RatioCandidate) -> dict[str, Any]:
    definition = candidate.definition
    return {
        "metricCode": definition.metric_code,
        "numerator": {
            "source": definition.numerator_source,
            "metricCode": definition.numerator_metric_code,
            "semanticsVersion": definition.numerator_semantics_version,
            "extractType": definition.numerator_extract_type,
        },
        "denominator": {
            "source": definition.denominator_source,
            "metricCode": definition.denominator_metric_code,
            "semanticsVersion": definition.denominator_semantics_version,
            "extractType": definition.denominator_extract_type,
            "meaning": "GA4 measured screen/page views, not physical pageview truth",
        },
        "alignmentPolicy": EXACT_UTC_ALIGNMENT,
        "freshnessPolicy": STRICT_FRESHNESS_POLICY,
    }


def _derivation_key(tenant_id: uuid.UUID, site_id: uuid.UUID, candidate: RatioCandidate) -> str:
    canonical = json.dumps(
        {
            "tenantId": str(tenant_id),
            "siteId": str(site_id),
            "metricCode": candidate.definition.metric_code,
            "ruleVersion": CROSS_SOURCE_RULE_VERSION,
            "periodStart": candidate.period_start.isoformat(),
            "periodEnd": candidate.period_end.isoformat(),
            "inputFingerprint": candidate.input_fingerprint,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(canonical).hexdigest()
