import asyncio
import json
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.browser.contracts import (
    BrowserEvidence,
    BrowserTarget,
    StoredArtifactRecord,
)
from app.browser.models import (
    FINAL_CHECKPOINT_STATUSES,
    Artifact,
    BrowserScenario,
    CheckpointAttempt,
    CheckpointRun,
    CheckpointWindow,
    CollectorRun,
    MonitoredUrl,
    Site,
    Template,
)
from app.storage.s3 import S3Storage


class CheckpointStateError(RuntimeError):
    pass


class CheckpointRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    @staticmethod
    def _target_from_row(
        row: tuple[CheckpointRun, MonitoredUrl, Site, BrowserScenario],
    ) -> BrowserTarget:
        run, monitored_url, site, scenario = row
        viewport = scenario.device_profile.get("viewport", {})
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
        )

    @staticmethod
    def _target_statement(tenant_id: uuid.UUID, checkpoint_run_id: uuid.UUID) -> Any:
        return (
            select(CheckpointRun, MonitoredUrl, Site, BrowserScenario)
            .join(MonitoredUrl, MonitoredUrl.id == CheckpointRun.monitored_url_id)
            .join(Site, Site.id == CheckpointRun.site_id)
            .join(BrowserScenario, BrowserScenario.id == CheckpointRun.scenario_id)
            .join(Template, Template.id == CheckpointRun.template_id)
            .where(
                CheckpointRun.id == checkpoint_run_id,
                CheckpointRun.tenant_id == tenant_id,
                MonitoredUrl.tenant_id == tenant_id,
                MonitoredUrl.site_id == CheckpointRun.site_id,
                Site.tenant_id == tenant_id,
                BrowserScenario.tenant_id == tenant_id,
                BrowserScenario.site_id == CheckpointRun.site_id,
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
                    cast(tuple[CheckpointRun, MonitoredUrl, Site, BrowserScenario], row._tuple())
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
            statement = self._target_statement(tenant_id, checkpoint_run_id).with_for_update()
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
                cast(tuple[CheckpointRun, MonitoredUrl, Site, BrowserScenario], row._tuple())
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
            window = await session.scalar(
                select(CheckpointWindow).where(
                    CheckpointWindow.id == run.checkpoint_window_id,
                    CheckpointWindow.tenant_id == target.tenant_id,
                )
            )
            if window is not None:
                window.status = "COMPLETE"
                window.completed_at = evidence.completed_at

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
        manifest = self._manifest(target, evidence, stored)
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
    ) -> dict[str, Any]:
        return {
            "schema": "browser-checkpoint-manifest/v1",
            "checkpoint_run_id": str(target.checkpoint_run_id),
            "tenant_id": str(target.tenant_id),
            "site_id": str(target.site_id),
            "monitored_url_id": str(target.monitored_url_id),
            "scenario_id": str(target.scenario_id),
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
