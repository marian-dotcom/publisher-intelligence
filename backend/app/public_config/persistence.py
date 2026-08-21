import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.browser.models import Artifact, Site
from app.public_config.contracts import (
    MAX_ADS_TXT_RECORDS,
    AdsTxtRecordInput,
    ConfigType,
    PublicConfigSiteTarget,
    PublicConfigSnapshotInput,
    SnapshotWriteResult,
    StoredPublicConfigSnapshot,
)
from app.public_config.models import AdsTxtRecord, PublicConfigSnapshot


class PublicConfigStateError(RuntimeError):
    pass


class PublicConfigRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def schedulable_sites(self) -> tuple[PublicConfigSiteTarget, ...]:
        async with self._session_factory() as session:
            sites = list(
                (
                    await session.scalars(
                        select(Site).where(Site.status == "ACTIVE").order_by(Site.id)
                    )
                ).all()
            )
        return tuple(_site_target(site) for site in sites)

    async def load_active_site(
        self, *, tenant_id: uuid.UUID, site_id: uuid.UUID
    ) -> PublicConfigSiteTarget:
        async with self._session_factory() as session:
            site = await session.scalar(
                select(Site).where(
                    Site.id == site_id,
                    Site.tenant_id == tenant_id,
                    Site.status == "ACTIVE",
                )
            )
        if site is None:
            raise PublicConfigStateError(
                "active site does not belong to public configuration tenant"
            )
        return _site_target(site)

    async def persist_snapshot(
        self,
        *,
        tenant_id: uuid.UUID,
        site_id: uuid.UUID,
        snapshot: PublicConfigSnapshotInput,
        records: tuple[AdsTxtRecordInput, ...] = (),
    ) -> SnapshotWriteResult:
        _validate_records(snapshot, records)
        proposed_id = uuid.uuid4()
        async with self._session_factory() as session, session.begin():
            await self._validate_site(session, tenant_id=tenant_id, site_id=site_id)
            await self._validate_artifact(
                session,
                tenant_id=tenant_id,
                site_id=site_id,
                artifact_id=snapshot.artifact_id,
            )
            await self._validate_primary(
                session,
                tenant_id=tenant_id,
                site_id=site_id,
                snapshot=snapshot,
            )
            created_id = await session.scalar(
                insert(PublicConfigSnapshot)
                .values(
                    id=proposed_id,
                    tenant_id=tenant_id,
                    site_id=site_id,
                    config_type=snapshot.config_type,
                    observed_at=snapshot.observed_at,
                    http_status=snapshot.http_status,
                    content_hash=snapshot.content_hash,
                    parse_status=snapshot.parse_status,
                    artifact_id=snapshot.artifact_id,
                    normalizer_version=snapshot.normalizer_version,
                    summary=snapshot.summary,
                    fetch_kind=snapshot.fetch_kind,
                    validation_of_snapshot_id=snapshot.validation_of_snapshot_id,
                    observation_key=snapshot.observation_key,
                )
                .on_conflict_do_nothing(constraint="uq_public_config_snapshot_observation_key")
                .returning(PublicConfigSnapshot.id)
            )
            if created_id is None:
                existing = await session.scalar(
                    select(PublicConfigSnapshot).where(
                        PublicConfigSnapshot.observation_key == snapshot.observation_key
                    )
                )
                if existing is None or not _same_observation(
                    existing, tenant_id=tenant_id, site_id=site_id, snapshot=snapshot
                ):
                    raise PublicConfigStateError("public configuration observation key conflict")
                return SnapshotWriteResult(snapshot_id=existing.id, created=False)

            if records:
                await session.execute(
                    insert(AdsTxtRecord),
                    [
                        {
                            "id": uuid.uuid4(),
                            "tenant_id": tenant_id,
                            "site_id": site_id,
                            "snapshot_id": created_id,
                            "advertising_system_domain": record.advertising_system_domain,
                            "publisher_account_id": record.publisher_account_id,
                            "relationship": record.relationship,
                            "cert_authority_id": record.cert_authority_id,
                            "record_hash": record.record_hash,
                            "is_valid": record.is_valid,
                            "validation_errors": list(record.validation_errors),
                        }
                        for record in records
                    ],
                )
        return SnapshotWriteResult(snapshot_id=created_id, created=True)

    async def load_snapshot(
        self,
        *,
        tenant_id: uuid.UUID,
        site_id: uuid.UUID,
        snapshot_id: uuid.UUID,
    ) -> StoredPublicConfigSnapshot:
        async with self._session_factory() as session:
            snapshot = await session.scalar(
                select(PublicConfigSnapshot).where(
                    PublicConfigSnapshot.id == snapshot_id,
                    PublicConfigSnapshot.tenant_id == tenant_id,
                    PublicConfigSnapshot.site_id == site_id,
                )
            )
        if snapshot is None:
            raise PublicConfigStateError("public configuration snapshot does not belong to site")
        return _stored_snapshot(snapshot)

    async def previous_scheduled_snapshot(
        self,
        *,
        tenant_id: uuid.UUID,
        site_id: uuid.UUID,
        config_type: ConfigType,
        observed_before: datetime,
        normalizer_version: str,
    ) -> StoredPublicConfigSnapshot | None:
        async with self._session_factory() as session:
            snapshot = await session.scalar(
                select(PublicConfigSnapshot)
                .where(
                    PublicConfigSnapshot.tenant_id == tenant_id,
                    PublicConfigSnapshot.site_id == site_id,
                    PublicConfigSnapshot.config_type == config_type,
                    PublicConfigSnapshot.fetch_kind == "SCHEDULED",
                    PublicConfigSnapshot.normalizer_version == normalizer_version,
                    PublicConfigSnapshot.observed_at < observed_before,
                )
                .order_by(
                    PublicConfigSnapshot.observed_at.desc(),
                    PublicConfigSnapshot.created_at.desc(),
                )
                .limit(1)
            )
        return _stored_snapshot(snapshot) if snapshot is not None else None

    async def previous_healthy_scheduled_snapshot(
        self,
        *,
        tenant_id: uuid.UUID,
        site_id: uuid.UUID,
        config_type: ConfigType,
        observed_before: datetime,
        normalizer_version: str,
    ) -> StoredPublicConfigSnapshot | None:
        async with self._session_factory() as session:
            snapshot = await session.scalar(
                select(PublicConfigSnapshot)
                .where(
                    PublicConfigSnapshot.tenant_id == tenant_id,
                    PublicConfigSnapshot.site_id == site_id,
                    PublicConfigSnapshot.config_type == config_type,
                    PublicConfigSnapshot.fetch_kind == "SCHEDULED",
                    PublicConfigSnapshot.parse_status.in_(("VALID", "VALID_WITH_WARNINGS")),
                    PublicConfigSnapshot.normalizer_version == normalizer_version,
                    PublicConfigSnapshot.observed_at < observed_before,
                )
                .order_by(
                    PublicConfigSnapshot.observed_at.desc(),
                    PublicConfigSnapshot.created_at.desc(),
                )
                .limit(1)
            )
        return _stored_snapshot(snapshot) if snapshot is not None else None

    @staticmethod
    async def _validate_site(
        session: AsyncSession, *, tenant_id: uuid.UUID, site_id: uuid.UUID
    ) -> None:
        owned_site = await session.scalar(
            select(Site.id).where(Site.id == site_id, Site.tenant_id == tenant_id)
        )
        if owned_site is None:
            raise PublicConfigStateError("site does not belong to public configuration tenant")

    @staticmethod
    async def _validate_artifact(
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        site_id: uuid.UUID,
        artifact_id: uuid.UUID | None,
    ) -> None:
        if artifact_id is None:
            return
        owned_artifact = await session.scalar(
            select(Artifact.id).where(
                Artifact.id == artifact_id,
                Artifact.tenant_id == tenant_id,
                Artifact.site_id == site_id,
            )
        )
        if owned_artifact is None:
            raise PublicConfigStateError("artifact does not belong to public configuration site")

    @staticmethod
    async def _validate_primary(
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        site_id: uuid.UUID,
        snapshot: PublicConfigSnapshotInput,
    ) -> None:
        if snapshot.validation_of_snapshot_id is None:
            return
        primary = await session.scalar(
            select(PublicConfigSnapshot).where(
                PublicConfigSnapshot.id == snapshot.validation_of_snapshot_id,
                PublicConfigSnapshot.tenant_id == tenant_id,
                PublicConfigSnapshot.site_id == site_id,
                PublicConfigSnapshot.config_type == snapshot.config_type,
                PublicConfigSnapshot.fetch_kind == "SCHEDULED",
            )
        )
        if primary is None:
            raise PublicConfigStateError("validation primary is not an owned scheduled snapshot")
        if snapshot.observed_at < primary.observed_at:
            raise PublicConfigStateError("validation cannot predate its primary snapshot")


def _validate_records(
    snapshot: PublicConfigSnapshotInput, records: tuple[AdsTxtRecordInput, ...]
) -> None:
    if snapshot.config_type != "ADS_TXT" and records:
        raise PublicConfigStateError("only ads.txt snapshots can contain seller records")
    if len(records) > MAX_ADS_TXT_RECORDS:
        raise PublicConfigStateError("ads.txt snapshot exceeds the record limit")
    hashes = {record.record_hash for record in records}
    if len(hashes) != len(records):
        raise PublicConfigStateError("ads.txt snapshot contains duplicate semantic records")
    valid_record_count = sum(record.is_valid for record in records)
    if snapshot.config_type == "ADS_TXT" and snapshot.parse_status in {
        "VALID",
        "VALID_WITH_WARNINGS",
    }:
        if valid_record_count < 1:
            raise PublicConfigStateError("healthy ads.txt snapshot requires a valid record")
        if snapshot.summary.get("valid_record_count") != valid_record_count:
            raise PublicConfigStateError("ads.txt summary record count does not match records")


def _same_observation(
    existing: PublicConfigSnapshot,
    *,
    tenant_id: uuid.UUID,
    site_id: uuid.UUID,
    snapshot: PublicConfigSnapshotInput,
) -> bool:
    return (
        existing.tenant_id == tenant_id
        and existing.site_id == site_id
        and existing.config_type == snapshot.config_type
        and existing.observed_at == snapshot.observed_at
        and existing.http_status == snapshot.http_status
        and existing.content_hash == snapshot.content_hash
        and existing.parse_status == snapshot.parse_status
        and existing.artifact_id == snapshot.artifact_id
        and existing.normalizer_version == snapshot.normalizer_version
        and existing.summary == snapshot.summary
        and existing.fetch_kind == snapshot.fetch_kind
        and existing.validation_of_snapshot_id == snapshot.validation_of_snapshot_id
    )


def _stored_snapshot(snapshot: PublicConfigSnapshot) -> StoredPublicConfigSnapshot:
    return StoredPublicConfigSnapshot(
        id=snapshot.id,
        tenant_id=snapshot.tenant_id,
        site_id=snapshot.site_id,
        config_type=snapshot.config_type,
        observed_at=snapshot.observed_at,
        http_status=snapshot.http_status,
        content_hash=snapshot.content_hash,
        parse_status=snapshot.parse_status,
        artifact_id=snapshot.artifact_id,
        normalizer_version=snapshot.normalizer_version,
        summary=snapshot.summary,
        fetch_kind=snapshot.fetch_kind,
        validation_of_snapshot_id=snapshot.validation_of_snapshot_id,
        observation_key=snapshot.observation_key,
    )


def _site_target(site: Site) -> PublicConfigSiteTarget:
    return PublicConfigSiteTarget(
        tenant_id=site.tenant_id,
        site_id=site.id,
        canonical_domain=site.canonical_domain,
        canonical_scheme=site.canonical_scheme,
        timezone=site.timezone,
    )
