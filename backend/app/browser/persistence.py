import asyncio
import json
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.browser.comparison import compare_normalized_state
from app.browser.contracts import (
    BrowserEvidence,
    BrowserTarget,
    ConsentAdapterConfig,
    ExpectedGPTSlot,
    StoredArtifactRecord,
)
from app.browser.interactions import parse_interaction_steps
from app.browser.models import (
    FINAL_CHECKPOINT_STATUSES,
    Artifact,
    BrowserScenario,
    CheckpointAttempt,
    CheckpointRun,
    CheckpointWindow,
    CollectorRun,
    DomainEntity,
    EntityObservation,
    GPTSlotObservation,
    InteractionProfile,
    JavaScriptErrorObservation,
    MonitoredUrl,
    SeoObservation,
    Site,
    Template,
    TemplateExpectedEntity,
)
from app.browser.models import (
    CMPObservation as CMPObservationModel,
)
from app.browser.models import (
    ConsentPhaseDependencyObservation as ConsentPhaseDependencyObservationModel,
)
from app.browser.models import (
    PrebidAuctionObservation as PrebidAuctionObservationModel,
)
from app.browser.models import (
    PrebidBidderObservation as PrebidBidderObservationModel,
)
from app.browser.models import (
    SyntheticPerformanceObservation as SyntheticPerformanceObservationModel,
)
from app.browser.models import (
    VideoPlayerObservation as VideoPlayerObservationModel,
)
from app.browser.performance import PERFORMANCE_COLLECTOR_VERSION
from app.db.models import Job
from app.storage.s3 import S3Storage


class CheckpointStateError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ComparableCheckpoint:
    run: CheckpointRun
    selection_scope: str


class CheckpointRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    @staticmethod
    def _target_from_row(
        row: tuple[
            CheckpointRun,
            MonitoredUrl,
            Site,
            BrowserScenario,
            InteractionProfile | None,
            Template,
        ],
        expected_gpt_slots: tuple[ExpectedGPTSlot, ...] = (),
    ) -> BrowserTarget:
        run, monitored_url, site, scenario, interaction_profile, template = row
        viewport = scenario.device_profile.get("viewport", {})
        steps = (
            parse_interaction_steps(interaction_profile.steps)
            if interaction_profile is not None
            else ()
        )
        return BrowserTarget(
            checkpoint_run_id=run.id,
            tenant_id=run.tenant_id,
            site_id=run.site_id,
            monitored_url_id=run.monitored_url_id,
            scenario_id=run.scenario_id,
            url=monitored_url.url,
            canonical_domain=site.canonical_domain,
            scenario_code=scenario.code,
            scenario_version=scenario.version,
            locale=scenario.locale,
            timezone=scenario.timezone,
            viewport_width=int(viewport.get("width", 1440)),
            viewport_height=int(viewport.get("height", 900)),
            scheduled_for=run.scheduled_for,
            device_scale_factor=float(scenario.device_profile.get("device_scale_factor", 1.0)),
            user_agent=cast(str | None, scenario.device_profile.get("user_agent")),
            is_mobile=bool(scenario.device_profile.get("is_mobile", False)),
            has_touch=bool(scenario.device_profile.get("has_touch", False)),
            interaction_profile_id=(
                interaction_profile.id if interaction_profile is not None else None
            ),
            interaction_profile_code=(
                interaction_profile.code if interaction_profile is not None else None
            ),
            interaction_profile_version=(
                interaction_profile.version if interaction_profile is not None else None
            ),
            interaction_steps=steps,
            template_id=template.id,
            template_code=template.code,
            template_family=template.template_family,
            template_fingerprint_version=template.fingerprint_version,
            template_expected_features=template.expected_features,
            expected_gpt_slots=expected_gpt_slots,
            consent_path=scenario.consent_path,
            consent_adapter=CheckpointRepository._consent_adapter(template.expected_features),
        )

    @staticmethod
    def _consent_adapter(expected_features: dict[str, object]) -> ConsentAdapterConfig | None:
        raw = expected_features.get("consent_adapter")
        if not isinstance(raw, dict) or raw.get("type") != "manual_config":
            return None

        def value(name: str, limit: int) -> str | None:
            item = raw.get(name)
            if not isinstance(item, str):
                return None
            cleaned = item.strip()
            return cleaned[:limit] if cleaned else None

        return ConsentAdapterConfig(
            vendor=value("vendor", 100),
            accept_selector=value("accept_selector", 500),
            reject_selector=value("reject_selector", 500),
            ready_selector=value("ready_selector", 500),
        )

    @staticmethod
    async def _expected_gpt_slots(
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        site_id: uuid.UUID,
        template_id: uuid.UUID,
        effective_at: datetime,
    ) -> tuple[ExpectedGPTSlot, ...]:
        rows = (
            await session.execute(
                select(DomainEntity, TemplateExpectedEntity)
                .join(
                    TemplateExpectedEntity,
                    TemplateExpectedEntity.entity_id == DomainEntity.id,
                )
                .where(
                    DomainEntity.tenant_id == tenant_id,
                    DomainEntity.site_id == site_id,
                    DomainEntity.entity_kind == "GPT_SLOT",
                    TemplateExpectedEntity.tenant_id == tenant_id,
                    TemplateExpectedEntity.site_id == site_id,
                    TemplateExpectedEntity.template_id == template_id,
                    TemplateExpectedEntity.expectation_type == "EXPECTED",
                    TemplateExpectedEntity.valid_from <= effective_at,
                    or_(
                        TemplateExpectedEntity.valid_to.is_(None),
                        TemplateExpectedEntity.valid_to > effective_at,
                    ),
                )
                .order_by(DomainEntity.stable_key)
            )
        ).all()
        slots: list[ExpectedGPTSlot] = []
        for entity, _expectation in rows:
            metadata = entity.identity_metadata
            raw_sizes = metadata.get("sizes", [])
            sizes = (
                tuple(str(item)[:50] for item in raw_sizes[:50])
                if isinstance(raw_sizes, list)
                else ()
            )
            slots.append(
                ExpectedGPTSlot(
                    entity_id=entity.id,
                    stable_key=entity.stable_key,
                    ad_unit_path=(
                        str(metadata["ad_unit_path"])[:500]
                        if metadata.get("ad_unit_path") is not None
                        else None
                    ),
                    dom_element_id=(
                        str(metadata["dom_element_id"])[:300]
                        if metadata.get("dom_element_id") is not None
                        else None
                    ),
                    sizes=sizes,
                )
            )
        return tuple(slots)

    @staticmethod
    def _target_statement(tenant_id: uuid.UUID, checkpoint_run_id: uuid.UUID) -> Any:
        return (
            select(
                CheckpointRun,
                MonitoredUrl,
                Site,
                BrowserScenario,
                InteractionProfile,
                Template,
            )
            .join(MonitoredUrl, MonitoredUrl.id == CheckpointRun.monitored_url_id)
            .join(Site, Site.id == CheckpointRun.site_id)
            .join(BrowserScenario, BrowserScenario.id == CheckpointRun.scenario_id)
            .outerjoin(
                InteractionProfile,
                InteractionProfile.id == BrowserScenario.interaction_profile_id,
            )
            .join(Template, Template.id == CheckpointRun.template_id)
            .where(
                CheckpointRun.id == checkpoint_run_id,
                CheckpointRun.tenant_id == tenant_id,
                MonitoredUrl.tenant_id == tenant_id,
                MonitoredUrl.site_id == CheckpointRun.site_id,
                Site.tenant_id == tenant_id,
                BrowserScenario.tenant_id == tenant_id,
                BrowserScenario.site_id == CheckpointRun.site_id,
                or_(
                    BrowserScenario.interaction_profile_id.is_(None),
                    (
                        (InteractionProfile.tenant_id == tenant_id)
                        & (InteractionProfile.site_id == CheckpointRun.site_id)
                    ),
                ),
                Template.tenant_id == tenant_id,
                Template.site_id == CheckpointRun.site_id,
            )
        )

    async def load_target(
        self, *, tenant_id: uuid.UUID, checkpoint_run_id: uuid.UUID
    ) -> BrowserTarget | None:
        async with self._session_factory() as session:
            row = (
                await session.execute(self._target_statement(tenant_id, checkpoint_run_id))
            ).one_or_none()
            if row is None:
                return None
            typed_row = cast(
                tuple[
                    CheckpointRun,
                    MonitoredUrl,
                    Site,
                    BrowserScenario,
                    InteractionProfile | None,
                    Template,
                ],
                row._tuple(),
            )
            run = typed_row[0]
            expected = await self._expected_gpt_slots(
                session,
                tenant_id=tenant_id,
                site_id=run.site_id,
                template_id=run.template_id,
                effective_at=run.scheduled_for,
            )
            return self._target_from_row(
                typed_row,
                expected,
            )

    async def begin_attempt(
        self,
        *,
        tenant_id: uuid.UUID,
        checkpoint_run_id: uuid.UUID,
        attempt_number: int,
    ) -> BrowserTarget:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            statement = self._target_statement(tenant_id, checkpoint_run_id).with_for_update(
                of=CheckpointRun
            )
            row = (await session.execute(statement)).one_or_none()
            if row is None:
                raise CheckpointStateError("checkpoint does not belong to the job tenant")
            run = row[0]
            if run.status in FINAL_CHECKPOINT_STATUSES:
                raise CheckpointStateError("finalized checkpoint cannot be restarted")
            existing_attempt = await session.scalar(
                select(CheckpointAttempt).where(
                    CheckpointAttempt.tenant_id == tenant_id,
                    CheckpointAttempt.checkpoint_run_id == checkpoint_run_id,
                    CheckpointAttempt.attempt_number == attempt_number,
                )
            )
            if existing_attempt is not None:
                raise CheckpointStateError("checkpoint attempt already exists")
            run.status = "RUNNING"
            run.started_at = run.started_at or now
            run.attempt_count = max(run.attempt_count, attempt_number)
            window = await session.scalar(
                select(CheckpointWindow).where(
                    CheckpointWindow.id == run.checkpoint_window_id,
                    CheckpointWindow.tenant_id == tenant_id,
                )
            )
            if window is not None:
                window.status = "RUNNING"
            session.add(
                CheckpointAttempt(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    checkpoint_run_id=checkpoint_run_id,
                    attempt_number=attempt_number,
                    started_at=now,
                    status="RUNNING",
                    metadata_json={},
                )
            )
            typed_row = cast(
                tuple[
                    CheckpointRun,
                    MonitoredUrl,
                    Site,
                    BrowserScenario,
                    InteractionProfile | None,
                    Template,
                ],
                row._tuple(),
            )
            expected = await self._expected_gpt_slots(
                session,
                tenant_id=tenant_id,
                site_id=run.site_id,
                template_id=run.template_id,
                effective_at=run.scheduled_for,
            )
            return self._target_from_row(
                typed_row,
                expected,
            )

    async def record_retryable_failure(
        self,
        *,
        tenant_id: uuid.UUID,
        checkpoint_run_id: uuid.UUID,
        attempt_number: int,
        failure_class: str,
        failure_message: str,
    ) -> None:
        async with self._session_factory() as session, session.begin():
            run = await session.scalar(
                select(CheckpointRun)
                .where(
                    CheckpointRun.id == checkpoint_run_id,
                    CheckpointRun.tenant_id == tenant_id,
                    CheckpointRun.status == "RUNNING",
                )
                .with_for_update()
            )
            attempt = await session.scalar(
                select(CheckpointAttempt).where(
                    CheckpointAttempt.checkpoint_run_id == checkpoint_run_id,
                    CheckpointAttempt.tenant_id == tenant_id,
                    CheckpointAttempt.attempt_number == attempt_number,
                    CheckpointAttempt.status == "RUNNING",
                )
            )
            if run is None or attempt is None:
                raise CheckpointStateError("running checkpoint attempt was not found")
            attempt.status = "BROWSER_ERROR"
            attempt.completed_at = datetime.now(UTC)
            attempt.failure_class = failure_class[:100]
            attempt.failure_message = failure_message[:1_000]
            run.status = "PENDING"

    async def finalize_terminal_failure(
        self,
        *,
        tenant_id: uuid.UUID,
        checkpoint_run_id: uuid.UUID,
        attempt_number: int,
        failure_class: str,
        failure_message: str,
    ) -> None:
        completed_at = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            run, attempt = await self._locked_run_and_attempt(
                session, tenant_id, checkpoint_run_id, attempt_number
            )
            attempt.status = "BROWSER_ERROR"
            attempt.completed_at = completed_at
            attempt.failure_class = failure_class[:100]
            attempt.failure_message = failure_message[:1_000]
            run.status = "BROWSER_ERROR"
            run.completed_at = completed_at
            run.limitations = ["evidence_storage_unavailable"]
            await self._refresh_window_status(session, run.checkpoint_window_id, completed_at)

    async def finalize(
        self,
        *,
        target: BrowserTarget,
        attempt_number: int,
        evidence: BrowserEvidence,
        artifacts: list[StoredArtifactRecord],
        manifest: dict[str, Any],
    ) -> None:
        async with self._session_factory() as session, session.begin():
            run, attempt = await self._locked_run_and_attempt(
                session, target.tenant_id, target.checkpoint_run_id, attempt_number
            )
            for record in artifacts:
                session.add(
                    Artifact(
                        id=uuid.uuid4(),
                        tenant_id=target.tenant_id,
                        site_id=target.site_id,
                        checkpoint_run_id=target.checkpoint_run_id,
                        artifact_type=record.artifact_type,
                        storage_provider="S3_COMPATIBLE",
                        object_key=record.object_key,
                        content_type=record.content_type,
                        byte_size=record.byte_size,
                        sha256=record.sha256,
                        retention_class=record.retention_class,
                        metadata_json={},
                    )
                )
            for collector in evidence.collectors:
                session.add(
                    CollectorRun(
                        id=uuid.uuid4(),
                        tenant_id=target.tenant_id,
                        checkpoint_run_id=target.checkpoint_run_id,
                        collector_type=collector.collector_type,
                        collector_version=collector.collector_version,
                        status=collector.status,
                        started_at=collector.started_at,
                        completed_at=collector.completed_at,
                        error_code=collector.error_code,
                        error_message=collector.error_message,
                        summary=collector.summary,
                    )
                )
            await self._persist_normalized_observations(session, target, evidence)
            await self._persist_gpt_observations(session, target, evidence)
            await self._persist_cmp_observations(session, target, evidence)
            await self._persist_prebid_observations(session, target, evidence)
            await self._persist_video_observations(session, target, evidence)
            await self._persist_synthetic_performance(session, target, evidence)
            await self._persist_seo_and_javascript_error_observations(session, target, evidence)
            attempt.status = evidence.status
            attempt.completed_at = evidence.completed_at
            attempt.failure_class = evidence.failure_class
            attempt.failure_message = evidence.failure_message
            attempt.metadata_json = {"environment": evidence.environment}
            run.status = evidence.status
            run.completed_at = evidence.completed_at
            run.final_url = evidence.final_url
            run.http_status = evidence.http_status
            run.playwright_version = evidence.playwright_version
            run.chromium_version = evidence.chromium_version
            run.environment = evidence.environment
            run.limitations = evidence.limitations
            run.manifest = manifest
            await session.execute(
                insert(Job)
                .values(
                    id=uuid.uuid4(),
                    tenant_id=target.tenant_id,
                    job_type="DERIVE_BROWSER_EVENTS",
                    payload={"checkpoint_run_id": str(target.checkpoint_run_id)},
                    priority=-10,
                    max_attempts=3,
                    idempotency_key=f"derive-browser-events:{target.checkpoint_run_id}:e2-v1",
                )
                .on_conflict_do_nothing()
            )
            await self._refresh_window_status(
                session, run.checkpoint_window_id, evidence.completed_at
            )

    @staticmethod
    async def _persist_normalized_observations(
        session: AsyncSession,
        target: BrowserTarget,
        evidence: BrowserEvidence,
    ) -> None:
        for observation in evidence.normalized_entities:
            entity_id = (
                await session.execute(
                    insert(DomainEntity)
                    .values(
                        id=uuid.uuid4(),
                        tenant_id=target.tenant_id,
                        site_id=target.site_id,
                        entity_kind=observation.entity_kind,
                        stable_key=observation.stable_key,
                        first_seen_at=evidence.completed_at,
                        last_seen_at=evidence.completed_at,
                        identity_metadata={},
                    )
                    .on_conflict_do_update(
                        index_elements=["site_id", "entity_kind", "stable_key"],
                        set_={"last_seen_at": evidence.completed_at},
                    )
                    .returning(DomainEntity.id)
                )
            ).scalar_one()
            await session.execute(
                insert(EntityObservation)
                .values(
                    id=uuid.uuid4(),
                    tenant_id=target.tenant_id,
                    site_id=target.site_id,
                    checkpoint_run_id=target.checkpoint_run_id,
                    entity_id=entity_id,
                    observation_type="PRESENCE_STATE",
                    observed_at=evidence.completed_at,
                    state_hash=observation.state_hash,
                    state=observation.state,
                    collector_version="b3-v1",
                )
                .on_conflict_do_nothing(
                    index_elements=[
                        "checkpoint_run_id",
                        "entity_id",
                        "observation_type",
                    ]
                )
            )

    @staticmethod
    async def _persist_seo_and_javascript_error_observations(
        session: AsyncSession, target: BrowserTarget, evidence: BrowserEvidence
    ) -> None:
        observation = evidence.seo_observation
        if observation is not None:
            await session.execute(
                insert(SeoObservation)
                .values(
                    id=uuid.uuid4(),
                    tenant_id=target.tenant_id,
                    site_id=target.site_id,
                    checkpoint_run_id=target.checkpoint_run_id,
                    final_url=observation.final_url,
                    http_status=observation.http_status,
                    title_hash=observation.title_hash,
                    meta_robots=observation.meta_robots,
                    canonical_url=observation.canonical_url,
                    redirect_count=observation.redirect_count,
                    collector_version=observation.collector_version,
                    metadata_json={},
                )
                .on_conflict_do_nothing(index_elements=["checkpoint_run_id"])
            )

        error_state = evidence.normalized_state.get("javascript_errors")
        if not isinstance(error_state, dict):
            return
        normalizer_version = str(error_state.get("normalizer_version", "unknown"))[:50]
        errors = error_state.get("errors")
        if not isinstance(errors, list):
            return
        for item in errors:
            if not isinstance(item, dict) or not isinstance(item.get("fingerprint"), str):
                continue
            await session.execute(
                insert(JavaScriptErrorObservation)
                .values(
                    id=uuid.uuid4(),
                    tenant_id=target.tenant_id,
                    site_id=target.site_id,
                    checkpoint_run_id=target.checkpoint_run_id,
                    fingerprint=str(item["fingerprint"])[:64],
                    normalized_message=str(item.get("normalized_message", ""))[:1_000],
                    source_host=(
                        str(item["source_host"])[:253]
                        if item.get("source_host") is not None
                        else None
                    ),
                    source_path=(
                        str(item["source_path"])[:1_000]
                        if item.get("source_path") is not None
                        else None
                    ),
                    count=max(1, int(item.get("count", 1))),
                    collector_version=normalizer_version,
                )
                .on_conflict_do_nothing(index_elements=["checkpoint_run_id", "fingerprint"])
            )

    @staticmethod
    async def _persist_gpt_observations(
        session: AsyncSession,
        target: BrowserTarget,
        evidence: BrowserEvidence,
    ) -> None:
        for slot in evidence.gpt_slots:
            last_seen = evidence.completed_at if slot.present else DomainEntity.last_seen_at
            entity_id = (
                await session.execute(
                    insert(DomainEntity)
                    .values(
                        id=uuid.uuid4(),
                        tenant_id=target.tenant_id,
                        site_id=target.site_id,
                        entity_kind="GPT_SLOT",
                        stable_key=slot.stable_key,
                        first_seen_at=evidence.completed_at,
                        last_seen_at=evidence.completed_at if slot.present else None,
                        source_system="GPT",
                        identity_metadata={
                            "ad_unit_path": slot.ad_unit_path,
                            "dom_element_id": slot.dom_element_id,
                            "sizes": list(slot.sizes),
                        },
                    )
                    .on_conflict_do_update(
                        index_elements=["site_id", "entity_kind", "stable_key"],
                        set_={"last_seen_at": last_seen},
                    )
                    .returning(DomainEntity.id)
                )
            ).scalar_one()
            await session.execute(
                insert(GPTSlotObservation)
                .values(
                    id=uuid.uuid4(),
                    tenant_id=target.tenant_id,
                    site_id=target.site_id,
                    checkpoint_run_id=target.checkpoint_run_id,
                    slot_entity_id=entity_id,
                    dom_element_id=slot.dom_element_id,
                    ad_unit_path=slot.ad_unit_path,
                    sizes=list(slot.sizes),
                    expected=slot.expected,
                    present=slot.present,
                    defined_at_ms=slot.defined_at_ms,
                    requested_at_ms=slot.requested_at_ms,
                    response_at_ms=slot.response_at_ms,
                    render_ended_at_ms=slot.render_ended_at_ms,
                    onload_at_ms=slot.onload_at_ms,
                    viewable_at_ms=slot.viewable_at_ms,
                    is_empty=slot.is_empty,
                    creative_id=slot.creative_id,
                    line_item_id=slot.line_item_id,
                    request_count=slot.request_count,
                    collector_version="gpt-b4-v1",
                )
                .on_conflict_do_nothing(index_elements=["checkpoint_run_id", "slot_entity_id"])
            )

    @staticmethod
    async def _persist_cmp_observations(
        session: AsyncSession,
        target: BrowserTarget,
        evidence: BrowserEvidence,
    ) -> None:
        observation = evidence.cmp_observation
        if observation is None:
            return
        cmp_entity_id = None
        if observation.cmp_id is not None or observation.vendor is not None:
            stable_key = (
                f"cmp|iab|{observation.cmp_id}"
                if observation.cmp_id is not None
                else f"cmp|vendor|{observation.vendor}"
            )
            cmp_entity_id = (
                await session.execute(
                    insert(DomainEntity)
                    .values(
                        id=uuid.uuid4(),
                        tenant_id=target.tenant_id,
                        site_id=target.site_id,
                        entity_kind="CMP",
                        stable_key=stable_key,
                        first_seen_at=evidence.completed_at,
                        last_seen_at=evidence.completed_at,
                        source_system="TCF",
                        identity_metadata={
                            "cmp_id": observation.cmp_id,
                            "vendor": observation.vendor,
                        },
                    )
                    .on_conflict_do_update(
                        index_elements=["site_id", "entity_kind", "stable_key"],
                        set_={"last_seen_at": evidence.completed_at},
                    )
                    .returning(DomainEntity.id)
                )
            ).scalar_one()
        await session.execute(
            insert(CMPObservationModel)
            .values(
                id=uuid.uuid4(),
                tenant_id=target.tenant_id,
                site_id=target.site_id,
                checkpoint_run_id=target.checkpoint_run_id,
                cmp_entity_id=cmp_entity_id,
                cmp_detected=observation.cmp_detected,
                tcf_api_detected=observation.tcf_api_detected,
                ui_detected_at_ms=observation.ui_detected_at_ms,
                api_ready_at_ms=observation.api_ready_at_ms,
                consent_action=observation.consent_action,
                consent_action_status=observation.consent_action_status,
                action_started_at_ms=observation.action_started_at_ms,
                action_completed_at_ms=observation.action_completed_at_ms,
                tc_state_available_at_ms=observation.tc_state_available_at_ms,
                gdpr_applies=observation.gdpr_applies,
                tc_string_hash=observation.tc_string_hash,
                tcf_error_codes=list(observation.tcf_error_codes),
                collector_version="cmp-b5-v1",
                metadata_json={
                    "cmp_id": observation.cmp_id,
                    "cmp_version": observation.cmp_version,
                    "cmp_status": observation.cmp_status,
                    "event_status": observation.event_status,
                    "vendor": observation.vendor,
                },
            )
            .on_conflict_do_nothing(index_elements=["checkpoint_run_id"])
        )
        for dependency in evidence.consent_phase_dependencies:
            entity_id = (
                await session.execute(
                    insert(DomainEntity)
                    .values(
                        id=uuid.uuid4(),
                        tenant_id=target.tenant_id,
                        site_id=target.site_id,
                        entity_kind="NETWORK_DEPENDENCY",
                        stable_key=dependency.stable_key,
                        first_seen_at=evidence.completed_at,
                        last_seen_at=evidence.completed_at,
                        identity_metadata={
                            "host": dependency.host,
                            "path_family": dependency.path_family,
                            "resource_type": dependency.resource_type,
                            "category": dependency.category,
                        },
                    )
                    .on_conflict_do_update(
                        index_elements=["site_id", "entity_kind", "stable_key"],
                        set_={"last_seen_at": evidence.completed_at},
                    )
                    .returning(DomainEntity.id)
                )
            ).scalar_one()
            await session.execute(
                insert(ConsentPhaseDependencyObservationModel)
                .values(
                    id=uuid.uuid4(),
                    tenant_id=target.tenant_id,
                    checkpoint_run_id=target.checkpoint_run_id,
                    phase=dependency.phase,
                    dependency_entity_id=entity_id,
                    request_count=dependency.request_count,
                    error_count=dependency.error_count,
                    first_request_at_ms=dependency.first_request_at_ms,
                )
                .on_conflict_do_nothing(
                    index_elements=["checkpoint_run_id", "phase", "dependency_entity_id"]
                )
            )

    @staticmethod
    async def _persist_prebid_observations(
        session: AsyncSession,
        target: BrowserTarget,
        evidence: BrowserEvidence,
    ) -> None:
        auction_ids: dict[str, uuid.UUID] = {}
        for auction in evidence.prebid_auctions:
            auction_id = (
                await session.execute(
                    insert(PrebidAuctionObservationModel)
                    .values(
                        id=uuid.uuid4(),
                        tenant_id=target.tenant_id,
                        site_id=target.site_id,
                        checkpoint_run_id=target.checkpoint_run_id,
                        auction_key=auction.auction_key,
                        started_at_ms=auction.started_at_ms,
                        ended_at_ms=auction.ended_at_ms,
                        configured_timeout_ms=auction.configured_timeout_ms,
                        ad_unit_count=auction.ad_unit_count,
                        bidder_request_count=auction.bidder_request_count,
                        bid_response_count=auction.bid_response_count,
                        no_bid_count=auction.no_bid_count,
                        timeout_count=auction.timeout_count,
                        collector_version="prebid-b6-v1",
                        metadata_json={
                            "first_ad_server_request_at_ms": (auction.first_ad_server_request_at_ms)
                        },
                    )
                    .on_conflict_do_update(
                        index_elements=["checkpoint_run_id", "auction_key"],
                        set_={
                            "ended_at_ms": auction.ended_at_ms,
                            "bidder_request_count": auction.bidder_request_count,
                            "bid_response_count": auction.bid_response_count,
                            "no_bid_count": auction.no_bid_count,
                            "timeout_count": auction.timeout_count,
                        },
                    )
                    .returning(PrebidAuctionObservationModel.id)
                )
            ).scalar_one()
            auction_ids[auction.auction_key] = auction_id

        for bidder in evidence.prebid_bidders:
            bidder_auction_id = auction_ids.get(bidder.auction_key)
            if bidder_auction_id is None:
                continue
            stable_key = f"prebid-bidder|{bidder.bidder_code}"
            bidder_entity_id = (
                await session.execute(
                    insert(DomainEntity)
                    .values(
                        id=uuid.uuid4(),
                        tenant_id=target.tenant_id,
                        site_id=target.site_id,
                        entity_kind="PREBID_BIDDER",
                        stable_key=stable_key,
                        display_name=bidder.bidder_code,
                        source_system="PREBID",
                        first_seen_at=evidence.completed_at,
                        last_seen_at=evidence.completed_at,
                        identity_metadata={"bidder_code": bidder.bidder_code},
                    )
                    .on_conflict_do_update(
                        index_elements=["site_id", "entity_kind", "stable_key"],
                        set_={"last_seen_at": evidence.completed_at},
                    )
                    .returning(DomainEntity.id)
                )
            ).scalar_one()
            await session.execute(
                insert(PrebidBidderObservationModel)
                .values(
                    id=uuid.uuid4(),
                    tenant_id=target.tenant_id,
                    site_id=target.site_id,
                    checkpoint_run_id=target.checkpoint_run_id,
                    auction_observation_id=bidder_auction_id,
                    bidder_entity_id=bidder_entity_id,
                    bidder_code=bidder.bidder_code,
                    request_count=bidder.request_count,
                    response_count=bidder.response_count,
                    no_bid_count=bidder.no_bid_count,
                    timeout_count=bidder.timeout_count,
                    response_time_ms_min=bidder.response_time_ms_min,
                    response_time_ms_max=bidder.response_time_ms_max,
                    response_time_ms_avg=bidder.response_time_ms_avg,
                    winning_bid_count=bidder.winning_bid_count,
                    collector_version="prebid-b6-v1",
                    metadata_json={},
                )
                .on_conflict_do_nothing(index_elements=["auction_observation_id", "bidder_code"])
            )

    @staticmethod
    async def _persist_video_observations(
        session: AsyncSession,
        target: BrowserTarget,
        evidence: BrowserEvidence,
    ) -> None:
        if len(evidence.video_players) == 1:
            only_player = evidence.video_players[0]
            network_attribution = (
                "PAGE_SINGLE_PLAYER"
                if only_player.vast_request_count > 0 or only_player.media_request_count > 0
                else "NO_MATCHING_VIDEO_NETWORK"
            )
        else:
            network_attribution = "AMBIGUOUS_NOT_ASSIGNED"
        for player in evidence.video_players:
            last_seen = evidence.completed_at if player.present else DomainEntity.last_seen_at
            player_entity_id = (
                await session.execute(
                    insert(DomainEntity)
                    .values(
                        id=uuid.uuid4(),
                        tenant_id=target.tenant_id,
                        site_id=target.site_id,
                        entity_kind="VIDEO_PLAYER",
                        stable_key=player.stable_key,
                        source_system="BROWSER_VIDEO",
                        first_seen_at=evidence.completed_at,
                        last_seen_at=evidence.completed_at if player.present else None,
                        identity_metadata={"identity_method": "hashed_structural_path_v1"},
                    )
                    .on_conflict_do_update(
                        index_elements=["site_id", "entity_kind", "stable_key"],
                        set_={"last_seen_at": last_seen},
                    )
                    .returning(DomainEntity.id)
                )
            ).scalar_one()
            await session.execute(
                insert(VideoPlayerObservationModel)
                .values(
                    id=uuid.uuid4(),
                    tenant_id=target.tenant_id,
                    site_id=target.site_id,
                    checkpoint_run_id=target.checkpoint_run_id,
                    player_entity_id=player_entity_id,
                    present=player.present,
                    visible=player.visible,
                    sticky=player.sticky,
                    fixed=player.fixed,
                    autoplay=player.autoplay,
                    muted=player.muted,
                    controls_present=player.controls_present,
                    dismiss_control_present=player.dismiss_control_present,
                    width_px=player.width_px,
                    height_px=player.height_px,
                    vast_request_count=player.vast_request_count,
                    vast_error_count=player.vast_error_count,
                    media_request_count=player.media_request_count,
                    playback_started=player.playback_started,
                    collector_version="video-b7-v1",
                    metadata_json={"network_attribution": network_attribution},
                )
                .on_conflict_do_nothing(index_elements=["checkpoint_run_id", "player_entity_id"])
            )

    @staticmethod
    async def _persist_synthetic_performance(
        session: AsyncSession,
        target: BrowserTarget,
        evidence: BrowserEvidence,
    ) -> None:
        observation = evidence.synthetic_performance
        if observation is None:
            return
        metadata = {
            **observation.metadata,
            "scenario_code": target.scenario_code,
            "scenario_version": target.scenario_version,
            "environment_synthetic": evidence.environment.get("synthetic") is True,
        }
        await session.execute(
            insert(SyntheticPerformanceObservationModel)
            .values(
                id=uuid.uuid4(),
                tenant_id=target.tenant_id,
                site_id=target.site_id,
                checkpoint_run_id=target.checkpoint_run_id,
                lcp_ms=observation.lcp_ms,
                cls=observation.cls,
                inp_ms=observation.inp_ms,
                inp_method=observation.inp_method,
                ttfb_ms=observation.ttfb_ms,
                dom_content_loaded_ms=observation.dom_content_loaded_ms,
                load_event_ms=observation.load_event_ms,
                long_task_count=observation.long_task_count,
                long_task_total_ms=observation.long_task_total_ms,
                collector_version=PERFORMANCE_COLLECTOR_VERSION,
                metadata_json=metadata,
            )
            .on_conflict_do_nothing(index_elements=["checkpoint_run_id"])
        )

    @staticmethod
    async def _refresh_window_status(
        session: AsyncSession,
        checkpoint_window_id: uuid.UUID,
        completed_at: datetime,
    ) -> None:
        window = await session.scalar(
            select(CheckpointWindow)
            .where(CheckpointWindow.id == checkpoint_window_id)
            .with_for_update()
        )
        if window is None:
            return
        statuses = list(
            (
                await session.scalars(
                    select(CheckpointRun.status).where(
                        CheckpointRun.checkpoint_window_id == checkpoint_window_id
                    )
                )
            ).all()
        )
        if not statuses:
            window.status = "SCHEDULED"
            window.completed_at = None
            return
        nonfinal = [status for status in statuses if status not in FINAL_CHECKPOINT_STATUSES]
        if nonfinal:
            window.status = (
                "RUNNING" if any(status != "PENDING" for status in statuses) else "SCHEDULED"
            )
            window.completed_at = None
            return
        browser_failures = statuses.count("BROWSER_ERROR")
        if browser_failures == len(statuses):
            window.status = "FAILED"
        elif browser_failures:
            window.status = "PARTIAL"
        else:
            window.status = "COMPLETE"
        window.completed_at = completed_at

    async def _locked_run_and_attempt(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        checkpoint_run_id: uuid.UUID,
        attempt_number: int,
    ) -> tuple[CheckpointRun, CheckpointAttempt]:
        run = await session.scalar(
            select(CheckpointRun)
            .where(
                CheckpointRun.id == checkpoint_run_id,
                CheckpointRun.tenant_id == tenant_id,
                CheckpointRun.status == "RUNNING",
            )
            .with_for_update()
        )
        attempt = await session.scalar(
            select(CheckpointAttempt).where(
                CheckpointAttempt.checkpoint_run_id == checkpoint_run_id,
                CheckpointAttempt.tenant_id == tenant_id,
                CheckpointAttempt.attempt_number == attempt_number,
                CheckpointAttempt.status == "RUNNING",
            )
        )
        if run is None or attempt is None:
            raise CheckpointStateError("running checkpoint attempt was not found or was finalized")
        return run, attempt

    async def get_for_tenant(
        self, *, tenant_id: uuid.UUID, checkpoint_run_id: uuid.UUID
    ) -> CheckpointRun | None:
        async with self._session_factory() as session:
            return cast(
                CheckpointRun | None,
                await session.scalar(
                    select(CheckpointRun).where(
                        CheckpointRun.id == checkpoint_run_id,
                        CheckpointRun.tenant_id == tenant_id,
                    )
                ),
            )

    async def artifacts_for_tenant(
        self, *, tenant_id: uuid.UUID, checkpoint_run_id: uuid.UUID
    ) -> list[Artifact]:
        async with self._session_factory() as session:
            return list(
                (
                    await session.scalars(
                        select(Artifact).where(
                            Artifact.checkpoint_run_id == checkpoint_run_id,
                            Artifact.tenant_id == tenant_id,
                        )
                    )
                ).all()
            )

    async def entity_observations_for_tenant(
        self, *, tenant_id: uuid.UUID, checkpoint_run_id: uuid.UUID
    ) -> list[EntityObservation]:
        async with self._session_factory() as session:
            return list(
                (
                    await session.scalars(
                        select(EntityObservation)
                        .join(DomainEntity, DomainEntity.id == EntityObservation.entity_id)
                        .where(
                            EntityObservation.tenant_id == tenant_id,
                            EntityObservation.checkpoint_run_id == checkpoint_run_id,
                            DomainEntity.tenant_id == tenant_id,
                            DomainEntity.site_id == EntityObservation.site_id,
                        )
                    )
                ).all()
            )

    async def javascript_errors_for_tenant(
        self, *, tenant_id: uuid.UUID, checkpoint_run_id: uuid.UUID
    ) -> list[JavaScriptErrorObservation]:
        async with self._session_factory() as session:
            return list(
                (
                    await session.scalars(
                        select(JavaScriptErrorObservation).where(
                            JavaScriptErrorObservation.tenant_id == tenant_id,
                            JavaScriptErrorObservation.checkpoint_run_id == checkpoint_run_id,
                        )
                    )
                ).all()
            )

    async def gpt_slots_for_tenant(
        self, *, tenant_id: uuid.UUID, checkpoint_run_id: uuid.UUID
    ) -> list[GPTSlotObservation]:
        async with self._session_factory() as session:
            return list(
                (
                    await session.scalars(
                        select(GPTSlotObservation)
                        .join(DomainEntity, DomainEntity.id == GPTSlotObservation.slot_entity_id)
                        .where(
                            GPTSlotObservation.tenant_id == tenant_id,
                            GPTSlotObservation.checkpoint_run_id == checkpoint_run_id,
                            DomainEntity.tenant_id == tenant_id,
                            DomainEntity.site_id == GPTSlotObservation.site_id,
                        )
                        .order_by(
                            GPTSlotObservation.ad_unit_path, GPTSlotObservation.dom_element_id
                        )
                    )
                ).all()
            )

    async def cmp_for_tenant(
        self, *, tenant_id: uuid.UUID, checkpoint_run_id: uuid.UUID
    ) -> CMPObservationModel | None:
        async with self._session_factory() as session:
            return cast(
                CMPObservationModel | None,
                await session.scalar(
                    select(CMPObservationModel).where(
                        CMPObservationModel.tenant_id == tenant_id,
                        CMPObservationModel.checkpoint_run_id == checkpoint_run_id,
                    )
                ),
            )

    async def consent_dependencies_for_tenant(
        self, *, tenant_id: uuid.UUID, checkpoint_run_id: uuid.UUID
    ) -> list[ConsentPhaseDependencyObservationModel]:
        async with self._session_factory() as session:
            return list(
                (
                    await session.scalars(
                        select(ConsentPhaseDependencyObservationModel)
                        .join(
                            DomainEntity,
                            DomainEntity.id
                            == ConsentPhaseDependencyObservationModel.dependency_entity_id,
                        )
                        .where(
                            ConsentPhaseDependencyObservationModel.tenant_id == tenant_id,
                            ConsentPhaseDependencyObservationModel.checkpoint_run_id
                            == checkpoint_run_id,
                            DomainEntity.tenant_id == tenant_id,
                        )
                    )
                ).all()
            )

    async def prebid_auctions_for_tenant(
        self, *, tenant_id: uuid.UUID, checkpoint_run_id: uuid.UUID
    ) -> list[PrebidAuctionObservationModel]:
        async with self._session_factory() as session:
            return list(
                (
                    await session.scalars(
                        select(PrebidAuctionObservationModel)
                        .where(
                            PrebidAuctionObservationModel.tenant_id == tenant_id,
                            PrebidAuctionObservationModel.checkpoint_run_id == checkpoint_run_id,
                        )
                        .order_by(PrebidAuctionObservationModel.auction_key)
                    )
                ).all()
            )

    async def prebid_bidders_for_tenant(
        self, *, tenant_id: uuid.UUID, checkpoint_run_id: uuid.UUID
    ) -> list[PrebidBidderObservationModel]:
        async with self._session_factory() as session:
            return list(
                (
                    await session.scalars(
                        select(PrebidBidderObservationModel)
                        .join(
                            PrebidAuctionObservationModel,
                            PrebidAuctionObservationModel.id
                            == PrebidBidderObservationModel.auction_observation_id,
                        )
                        .where(
                            PrebidBidderObservationModel.tenant_id == tenant_id,
                            PrebidBidderObservationModel.checkpoint_run_id == checkpoint_run_id,
                            PrebidAuctionObservationModel.tenant_id == tenant_id,
                        )
                        .order_by(PrebidBidderObservationModel.bidder_code)
                    )
                ).all()
            )

    async def video_players_for_tenant(
        self, *, tenant_id: uuid.UUID, checkpoint_run_id: uuid.UUID
    ) -> list[VideoPlayerObservationModel]:
        async with self._session_factory() as session:
            return list(
                (
                    await session.scalars(
                        select(VideoPlayerObservationModel)
                        .join(
                            DomainEntity,
                            DomainEntity.id == VideoPlayerObservationModel.player_entity_id,
                        )
                        .where(
                            VideoPlayerObservationModel.tenant_id == tenant_id,
                            VideoPlayerObservationModel.checkpoint_run_id == checkpoint_run_id,
                            DomainEntity.tenant_id == tenant_id,
                        )
                        .order_by(VideoPlayerObservationModel.player_entity_id)
                    )
                ).all()
            )

    async def synthetic_performance_for_tenant(
        self, *, tenant_id: uuid.UUID, checkpoint_run_id: uuid.UUID
    ) -> SyntheticPerformanceObservationModel | None:
        async with self._session_factory() as session:
            result = await session.scalar(
                select(SyntheticPerformanceObservationModel).where(
                    SyntheticPerformanceObservationModel.tenant_id == tenant_id,
                    SyntheticPerformanceObservationModel.checkpoint_run_id == checkpoint_run_id,
                )
            )
            return result

    async def previous_comparable(
        self,
        *,
        tenant_id: uuid.UUID,
        checkpoint_run_id: uuid.UUID,
    ) -> CheckpointRun | None:
        selection = await self.previous_comparable_selection(
            tenant_id=tenant_id,
            checkpoint_run_id=checkpoint_run_id,
        )
        return selection.run if selection is not None else None

    async def previous_comparable_selection(
        self,
        *,
        tenant_id: uuid.UUID,
        checkpoint_run_id: uuid.UUID,
    ) -> ComparableCheckpoint | None:
        async with self._session_factory() as session:
            current = await session.scalar(
                select(CheckpointRun).where(
                    CheckpointRun.id == checkpoint_run_id,
                    CheckpointRun.tenant_id == tenant_id,
                )
            )
            if current is None:
                return None
            base = (
                select(CheckpointRun)
                .where(
                    CheckpointRun.tenant_id == tenant_id,
                    CheckpointRun.site_id == current.site_id,
                    CheckpointRun.scenario_id == current.scenario_id,
                    CheckpointRun.id != current.id,
                    CheckpointRun.status.in_(FINAL_CHECKPOINT_STATUSES),
                    CheckpointRun.scheduled_for < current.scheduled_for,
                )
                .order_by(
                    CheckpointRun.scheduled_for.desc(),
                    CheckpointRun.completed_at.desc(),
                    CheckpointRun.id.desc(),
                )
                .limit(1)
            )
            same_url = cast(
                CheckpointRun | None,
                await session.scalar(
                    base.where(CheckpointRun.monitored_url_id == current.monitored_url_id)
                ),
            )
            if same_url is not None:
                return ComparableCheckpoint(same_url, "EXACT_MONITORED_URL")
            same_template = cast(
                CheckpointRun | None,
                await session.scalar(
                    base.where(
                        CheckpointRun.template_id == current.template_id,
                        CheckpointRun.monitored_url_id != current.monitored_url_id,
                    )
                ),
            )
            return (
                ComparableCheckpoint(same_template, "SAME_TEMPLATE_URL_ROTATION")
                if same_template is not None
                else None
            )


class EvidencePersister:
    def __init__(self, repository: CheckpointRepository, storage: S3Storage) -> None:
        self._repository = repository
        self._storage = storage

    async def persist(
        self, *, target: BrowserTarget, attempt_number: int, evidence: BrowserEvidence
    ) -> dict[str, Any]:
        stored: list[StoredArtifactRecord] = []
        base_key = (
            f"tenant/{target.tenant_id}/site/{target.site_id}/"
            f"checkpoints/{target.checkpoint_run_id}"
        )
        for artifact in evidence.artifacts:
            result = await asyncio.to_thread(
                self._storage.put_bytes,
                key=f"{base_key}/{artifact.filename}",
                content=artifact.content,
                content_type=artifact.content_type,
            )
            stored.append(
                StoredArtifactRecord(
                    artifact_type=artifact.artifact_type,
                    object_key=result.key,
                    content_type=artifact.content_type,
                    byte_size=result.size,
                    sha256=result.sha256,
                    retention_class=artifact.retention_class,
                )
            )
        previous = await self._repository.previous_comparable_selection(
            tenant_id=target.tenant_id,
            checkpoint_run_id=target.checkpoint_run_id,
        )
        manifest = self._manifest(
            target,
            evidence,
            stored,
            previous_checkpoint_run_id=previous.run.id if previous is not None else None,
            previous_manifest=previous.run.manifest if previous is not None else None,
            comparison_scope=previous.selection_scope if previous is not None else None,
        )
        manifest_bytes = json.dumps(
            manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        manifest_result = await asyncio.to_thread(
            self._storage.put_bytes,
            key=f"{base_key}/manifest.json",
            content=manifest_bytes,
            content_type="application/json",
        )
        stored.append(
            StoredArtifactRecord(
                artifact_type="MANIFEST",
                object_key=manifest_result.key,
                content_type="application/json",
                byte_size=manifest_result.size,
                sha256=manifest_result.sha256,
                retention_class="CORE_LONG",
            )
        )
        await self._repository.finalize(
            target=target,
            attempt_number=attempt_number,
            evidence=evidence,
            artifacts=stored,
            manifest=manifest,
        )
        return manifest

    @staticmethod
    def _manifest(
        target: BrowserTarget,
        evidence: BrowserEvidence,
        artifacts: list[StoredArtifactRecord],
        *,
        previous_checkpoint_run_id: uuid.UUID | None,
        previous_manifest: dict[str, Any] | None,
        comparison_scope: str | None,
    ) -> dict[str, Any]:
        comparison = compare_normalized_state(evidence.normalized_state, previous_manifest)
        return {
            "schema": "browser-checkpoint-manifest/v8",
            "checkpoint_run_id": str(target.checkpoint_run_id),
            "tenant_id": str(target.tenant_id),
            "site_id": str(target.site_id),
            "monitored_url_id": str(target.monitored_url_id),
            "template": {
                "id": str(target.template_id) if target.template_id is not None else None,
                "code": target.template_code,
                "family": target.template_family,
                "fingerprint_version": target.template_fingerprint_version,
                "expected_features": target.template_expected_features,
            },
            "scenario_id": str(target.scenario_id),
            "scheduled_for": (
                target.scheduled_for.isoformat() if target.scheduled_for is not None else None
            ),
            "scenario": {
                "code": target.scenario_code,
                "version": target.scenario_version,
                "interaction_profile_id": (
                    str(target.interaction_profile_id)
                    if target.interaction_profile_id is not None
                    else None
                ),
                "interaction_profile_code": target.interaction_profile_code,
                "interaction_profile_version": target.interaction_profile_version,
            },
            "comparison_lineage": {
                "previous_checkpoint_run_id": (
                    str(previous_checkpoint_run_id)
                    if previous_checkpoint_run_id is not None
                    else None
                ),
                "selection_scope": comparison_scope,
                "identity": (
                    "tenant+site+monitored_url+exact_scenario_id"
                    if comparison_scope == "EXACT_MONITORED_URL"
                    else "tenant+site+template+exact_scenario_id"
                    if comparison_scope == "SAME_TEMPLATE_URL_ROTATION"
                    else None
                ),
            },
            "normalized_state": evidence.normalized_state,
            "gpt": {
                "present": evidence.gpt_present,
                "version": evidence.gpt_version,
                "slots": [asdict(item) for item in evidence.gpt_slots],
            },
            "consent": {
                "path": target.consent_path,
                "observation": (
                    asdict(evidence.cmp_observation)
                    if evidence.cmp_observation is not None
                    else None
                ),
                "phase_dependencies": [
                    asdict(item) for item in evidence.consent_phase_dependencies
                ],
            },
            "prebid": {
                "present": evidence.prebid_present,
                "version": evidence.prebid_version,
                "server_side_configured": evidence.prebid_server_side_configured,
                "targeting_keys": evidence.prebid_targeting_keys,
                "limitations": evidence.prebid_limitations,
                "auctions": [asdict(item) for item in evidence.prebid_auctions],
                "bidders": [asdict(item) for item in evidence.prebid_bidders],
            },
            "video": {
                "present": evidence.video_present,
                "limitations": evidence.video_limitations,
                "players": [asdict(item) for item in evidence.video_players],
            },
            "performance": {
                "source": "synthetic_browser",
                "observation": (
                    asdict(evidence.synthetic_performance)
                    if evidence.synthetic_performance is not None
                    else None
                ),
            },
            "comparison": comparison,
            "started_at": evidence.started_at.isoformat(),
            "completed_at": evidence.completed_at.isoformat(),
            "status": evidence.status,
            "final_url": evidence.final_url,
            "http_status": evidence.http_status,
            "observer": {
                "playwright_version": evidence.playwright_version,
                "chromium_version": evidence.chromium_version,
            },
            "environment": evidence.environment,
            "redirect_chain": evidence.redirect_chain,
            "scripts": evidence.scripts,
            "network_hosts": evidence.network_hosts,
            "third_party_hosts": evidence.third_party_hosts,
            "request_count": evidence.request_count,
            "request_failures": [asdict(item) for item in evidence.request_failures],
            "javascript_errors": [asdict(item) for item in evidence.javascript_errors],
            "console_errors": [asdict(item) for item in evidence.console_errors],
            "blocked_requests": [asdict(item) for item in evidence.blocked_requests],
            "actions": evidence.actions,
            "limitations": evidence.limitations,
            "failure": {
                "class": evidence.failure_class,
                "message": evidence.failure_message,
            },
            "collectors": [
                {
                    "type": item.collector_type,
                    "version": item.collector_version,
                    "status": item.status,
                    "summary": item.summary,
                    "error_code": item.error_code,
                }
                for item in evidence.collectors
            ],
            "artifacts": [asdict(item) for item in artifacts],
        }
