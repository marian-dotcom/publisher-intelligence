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
    InteractionProfile,
    JavaScriptErrorObservation,
    MonitoredUrl,
    Site,
    Template,
)
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
        )

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
            return (
                self._target_from_row(
                    cast(
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
                )
                if row is not None
                else None
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
            return self._target_from_row(
                cast(
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
            "schema": "browser-checkpoint-manifest/v3",
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
