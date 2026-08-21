import uuid

from app.events.persistence import EventRunResult
from app.public_config.contracts import ConfigType
from app.public_config.evaluator import PublicConfigEvaluationInput, evaluate
from app.public_config.event_persistence import PublicConfigEventRepository
from app.public_config.persistence import PublicConfigRepository


class PublicConfigEventService:
    def __init__(
        self,
        snapshot_repository: PublicConfigRepository,
        event_repository: PublicConfigEventRepository,
    ) -> None:
        self._snapshots = snapshot_repository
        self._events = event_repository

    async def derive(
        self,
        *,
        tenant_id: uuid.UUID,
        site_id: uuid.UUID,
        config_type: ConfigType,
        primary_snapshot_id: uuid.UUID,
        validation_snapshot_id: uuid.UUID | None = None,
    ) -> EventRunResult:
        primary = await self._snapshots.load_snapshot(
            tenant_id=tenant_id,
            site_id=site_id,
            snapshot_id=primary_snapshot_id,
        )
        if primary.config_type != config_type or primary.fetch_kind != "SCHEDULED":
            raise ValueError("public configuration event primary is invalid")
        previous = await self._snapshots.previous_scheduled_snapshot(
            tenant_id=tenant_id,
            site_id=site_id,
            config_type=config_type,
            observed_before=primary.observed_at,
            normalizer_version=primary.normalizer_version,
        )
        if (
            config_type == "ADS_TXT"
            and primary.parse_status in {"VALID", "VALID_WITH_WARNINGS"}
            and (previous is None or previous.parse_status not in {"MISSING", "EMPTY", "INVALID"})
        ):
            affected = await self._snapshots.previous_ads_condition_snapshot(
                tenant_id=tenant_id,
                site_id=site_id,
                observed_before=primary.observed_at,
                normalizer_version=primary.normalizer_version,
            )
            healthy = await self._snapshots.previous_healthy_scheduled_snapshot(
                tenant_id=tenant_id,
                site_id=site_id,
                config_type=config_type,
                observed_before=primary.observed_at,
                normalizer_version=primary.normalizer_version,
            )
            if affected is not None and (
                healthy is None or affected.observed_at > healthy.observed_at
            ):
                previous = affected
        validation = None
        if validation_snapshot_id is not None:
            validation = await self._snapshots.load_snapshot(
                tenant_id=tenant_id,
                site_id=site_id,
                snapshot_id=validation_snapshot_id,
            )
        value = PublicConfigEvaluationInput(
            previous=previous,
            primary=primary,
            validation=validation,
        )
        result = evaluate(value)
        persisted = await self._events.persist(value, result.candidates)
        return EventRunResult(
            candidate_count=len(result.candidates),
            persisted_count=persisted.created_count,
            unsupported_count=0,
            skip_reasons=result.skip_reasons,
            updated_count=persisted.updated_count,
            resolved_count=persisted.resolved_count,
        )
