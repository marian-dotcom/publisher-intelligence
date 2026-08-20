import asyncio
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select

from app.browser.models import Publisher, Site
from app.db.models import Tenant
from app.db.session import get_session_factory
from app.public_config.contracts import (
    AdsTxtRecordInput,
    PublicConfigSnapshotInput,
    ads_txt_record_hash,
    public_config_observation_key,
)
from app.public_config.models import AdsTxtRecord, PublicConfigSnapshot
from app.public_config.persistence import PublicConfigRepository, PublicConfigStateError

pytestmark = pytest.mark.integration


@dataclass(frozen=True, slots=True)
class PublicConfigFixture:
    tenant_id: uuid.UUID
    other_tenant_id: uuid.UUID
    site_id: uuid.UUID


@pytest.fixture
async def public_config_fixture() -> AsyncIterator[PublicConfigFixture]:
    tenant_id, other_tenant_id = uuid.uuid4(), uuid.uuid4()
    publisher_id, site_id = uuid.uuid4(), uuid.uuid4()
    factory = get_session_factory()
    async with factory() as session, session.begin():
        session.add_all(
            [
                Tenant(id=tenant_id, slug=f"public-{tenant_id.hex[:10]}", name="Public Tenant"),
                Tenant(
                    id=other_tenant_id,
                    slug=f"public-other-{other_tenant_id.hex[:10]}",
                    name="Other Public Tenant",
                ),
            ]
        )
        await session.flush()
        session.add(
            Publisher(
                id=publisher_id,
                tenant_id=tenant_id,
                name="Public Publisher",
                slug=f"publisher-{publisher_id.hex[:10]}",
                default_timezone="UTC",
                status="ACTIVE",
            )
        )
        await session.flush()
        session.add(
            Site(
                id=site_id,
                tenant_id=tenant_id,
                publisher_id=publisher_id,
                name="Public Site",
                canonical_domain=f"{site_id.hex}.example.com",
                canonical_scheme="https",
                timezone="UTC",
                status="ACTIVE",
            )
        )

    yield PublicConfigFixture(tenant_id, other_tenant_id, site_id)

    async with factory() as session, session.begin():
        await session.execute(delete(AdsTxtRecord).where(AdsTxtRecord.tenant_id == tenant_id))
        await session.execute(
            delete(PublicConfigSnapshot).where(PublicConfigSnapshot.tenant_id == tenant_id)
        )
        await session.execute(delete(Site).where(Site.tenant_id == tenant_id))
        await session.execute(delete(Publisher).where(Publisher.tenant_id == tenant_id))
        await session.execute(delete(Tenant).where(Tenant.id.in_([tenant_id, other_tenant_id])))


async def test_persistence_is_idempotent_and_keeps_immutable_records(
    public_config_fixture: PublicConfigFixture,
) -> None:
    fixture = public_config_fixture
    observed_at = datetime(2026, 8, 21, 12, tzinfo=UTC)
    key = public_config_observation_key(
        tenant_id=fixture.tenant_id,
        site_id=fixture.site_id,
        config_type="ADS_TXT",
        fetch_kind="SCHEDULED",
        source_key=observed_at.isoformat(),
    )
    record = AdsTxtRecordInput(
        advertising_system_domain="example.com",
        publisher_account_id="account-1",
        relationship="DIRECT",
        cert_authority_id=None,
        record_hash=ads_txt_record_hash(
            advertising_system_domain="example.com",
            publisher_account_id="account-1",
            relationship="DIRECT",
            cert_authority_id=None,
        ),
    )
    snapshot = PublicConfigSnapshotInput(
        observation_key=key,
        config_type="ADS_TXT",
        observed_at=observed_at,
        http_status=200,
        content_hash="a" * 64,
        parse_status="VALID",
        normalizer_version="ads-txt-v1",
        summary={"valid_record_count": 1},
    )
    repository = PublicConfigRepository(get_session_factory())

    first, repeated = await asyncio.gather(
        repository.persist_snapshot(
            tenant_id=fixture.tenant_id,
            site_id=fixture.site_id,
            snapshot=snapshot,
            records=(record,),
        ),
        repository.persist_snapshot(
            tenant_id=fixture.tenant_id,
            site_id=fixture.site_id,
            snapshot=snapshot,
            records=(record,),
        ),
    )

    assert first.snapshot_id == repeated.snapshot_id
    assert first.created != repeated.created
    loaded = await repository.load_snapshot(
        tenant_id=fixture.tenant_id,
        site_id=fixture.site_id,
        snapshot_id=first.snapshot_id,
    )
    assert loaded.parse_status == "VALID"
    assert loaded.summary == {"valid_record_count": 1}
    async with get_session_factory()() as session:
        snapshot_count = await session.scalar(
            select(func.count())
            .select_from(PublicConfigSnapshot)
            .where(PublicConfigSnapshot.observation_key == key)
        )
        record_count = await session.scalar(
            select(func.count())
            .select_from(AdsTxtRecord)
            .where(AdsTxtRecord.snapshot_id == first.snapshot_id)
        )
    assert snapshot_count == 1
    assert record_count == 1


async def test_persistence_enforces_ownership_and_validation_lineage(
    public_config_fixture: PublicConfigFixture,
) -> None:
    fixture = public_config_fixture
    repository = PublicConfigRepository(get_session_factory())
    observed_at = datetime(2026, 8, 21, 12, tzinfo=UTC)
    primary = PublicConfigSnapshotInput(
        observation_key=public_config_observation_key(
            tenant_id=fixture.tenant_id,
            site_id=fixture.site_id,
            config_type="ROBOTS_TXT",
            fetch_kind="SCHEDULED",
            source_key=observed_at.isoformat(),
        ),
        config_type="ROBOTS_TXT",
        observed_at=observed_at,
        http_status=200,
        content_hash="b" * 64,
        parse_status="VALID",
        normalizer_version="robots-v1",
        summary={"group_count": 1},
    )
    with pytest.raises(PublicConfigStateError, match="does not belong"):
        await repository.persist_snapshot(
            tenant_id=fixture.other_tenant_id,
            site_id=fixture.site_id,
            snapshot=primary,
        )

    persisted_primary = await repository.persist_snapshot(
        tenant_id=fixture.tenant_id,
        site_id=fixture.site_id,
        snapshot=primary,
    )
    validation = PublicConfigSnapshotInput(
        observation_key=public_config_observation_key(
            tenant_id=fixture.tenant_id,
            site_id=fixture.site_id,
            config_type="ROBOTS_TXT",
            fetch_kind="VALIDATION",
            source_key=str(persisted_primary.snapshot_id),
        ),
        config_type="ROBOTS_TXT",
        observed_at=observed_at + timedelta(seconds=30),
        http_status=200,
        content_hash="b" * 64,
        parse_status="VALID",
        normalizer_version="robots-v1",
        summary={"group_count": 1},
        fetch_kind="VALIDATION",
        validation_of_snapshot_id=persisted_primary.snapshot_id,
    )
    persisted_validation = await repository.persist_snapshot(
        tenant_id=fixture.tenant_id,
        site_id=fixture.site_id,
        snapshot=validation,
    )
    loaded = await repository.load_snapshot(
        tenant_id=fixture.tenant_id,
        site_id=fixture.site_id,
        snapshot_id=persisted_validation.snapshot_id,
    )

    assert loaded.fetch_kind == "VALIDATION"
    assert loaded.validation_of_snapshot_id == persisted_primary.snapshot_id


async def test_previous_snapshot_ignores_validation_and_incompatible_versions(
    public_config_fixture: PublicConfigFixture,
) -> None:
    fixture = public_config_fixture
    repository = PublicConfigRepository(get_session_factory())
    observed_at = datetime(2026, 8, 21, 12, tzinfo=UTC)
    scheduled_ids: list[uuid.UUID] = []
    for index, version in enumerate(("robots-v1", "robots-v2", "robots-v1")):
        timestamp = observed_at + timedelta(hours=index)
        snapshot = PublicConfigSnapshotInput(
            observation_key=public_config_observation_key(
                tenant_id=fixture.tenant_id,
                site_id=fixture.site_id,
                config_type="ROBOTS_TXT",
                fetch_kind="SCHEDULED",
                source_key=timestamp.isoformat(),
            ),
            config_type="ROBOTS_TXT",
            observed_at=timestamp,
            http_status=200,
            content_hash=f"{index + 1}" * 64,
            parse_status="VALID",
            normalizer_version=version,
            summary={"group_count": index + 1},
        )
        result = await repository.persist_snapshot(
            tenant_id=fixture.tenant_id,
            site_id=fixture.site_id,
            snapshot=snapshot,
        )
        scheduled_ids.append(result.snapshot_id)

    previous = await repository.previous_scheduled_snapshot(
        tenant_id=fixture.tenant_id,
        site_id=fixture.site_id,
        config_type="ROBOTS_TXT",
        observed_before=observed_at + timedelta(hours=3),
        normalizer_version="robots-v1",
    )

    assert previous is not None
    assert previous.id == scheduled_ids[2]
