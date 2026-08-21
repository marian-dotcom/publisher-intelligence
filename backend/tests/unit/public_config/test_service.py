import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest

from app.public_config.client import (
    PublicConfigFetchError,
    PublicConfigFetchResult,
)
from app.public_config.contracts import (
    PUBLIC_CONFIG_RULE_VERSION,
    PublicConfigSiteTarget,
    PublicConfigSnapshotInput,
    SnapshotWriteResult,
    StoredPublicConfigSnapshot,
)
from app.public_config.persistence import PublicConfigStateError
from app.public_config.service import PublicConfigRunError, PublicConfigService

TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
SITE_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


class Repository:
    def __init__(self) -> None:
        self.snapshots: list[StoredPublicConfigSnapshot] = []
        self.records: dict[uuid.UUID, tuple[Any, ...]] = {}

    async def load_active_site(
        self, *, tenant_id: uuid.UUID, site_id: uuid.UUID
    ) -> PublicConfigSiteTarget:
        if tenant_id != TENANT_ID or site_id != SITE_ID:
            raise PublicConfigStateError("site is not owned")
        return PublicConfigSiteTarget(
            tenant_id=TENANT_ID,
            site_id=SITE_ID,
            canonical_domain="example.com",
            canonical_scheme="https",
            timezone="UTC",
        )

    async def persist_snapshot(
        self,
        *,
        tenant_id: uuid.UUID,
        site_id: uuid.UUID,
        snapshot: PublicConfigSnapshotInput,
        records: tuple[Any, ...] = (),
    ) -> SnapshotWriteResult:
        await self.load_active_site(tenant_id=tenant_id, site_id=site_id)
        for existing in self.snapshots:
            if existing.observation_key == snapshot.observation_key:
                return SnapshotWriteResult(existing.id, False)
        snapshot_id = uuid.uuid4()
        stored = StoredPublicConfigSnapshot(
            id=snapshot_id,
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
        self.snapshots.append(stored)
        self.records[snapshot_id] = records
        return SnapshotWriteResult(snapshot_id, True)

    async def load_snapshot(
        self,
        *,
        tenant_id: uuid.UUID,
        site_id: uuid.UUID,
        snapshot_id: uuid.UUID,
    ) -> StoredPublicConfigSnapshot:
        for snapshot in self.snapshots:
            if (
                snapshot.id == snapshot_id
                and snapshot.tenant_id == tenant_id
                and snapshot.site_id == site_id
            ):
                return snapshot
        raise PublicConfigStateError("snapshot is not owned")

    async def previous_healthy_scheduled_snapshot(
        self,
        *,
        tenant_id: uuid.UUID,
        site_id: uuid.UUID,
        config_type: str,
        observed_before: datetime,
        normalizer_version: str,
    ) -> StoredPublicConfigSnapshot | None:
        candidates = [
            snapshot
            for snapshot in self.snapshots
            if snapshot.tenant_id == tenant_id
            and snapshot.site_id == site_id
            and snapshot.config_type == config_type
            and snapshot.fetch_kind == "SCHEDULED"
            and snapshot.normalizer_version == normalizer_version
            and snapshot.parse_status in {"VALID", "VALID_WITH_WARNINGS"}
            and snapshot.observed_at < observed_before
        ]
        return max(candidates, key=lambda item: item.observed_at) if candidates else None

    async def previous_scheduled_snapshot(
        self,
        *,
        tenant_id: uuid.UUID,
        site_id: uuid.UUID,
        config_type: str,
        observed_before: datetime,
        normalizer_version: str,
    ) -> StoredPublicConfigSnapshot | None:
        candidates = [
            snapshot
            for snapshot in self.snapshots
            if snapshot.tenant_id == tenant_id
            and snapshot.site_id == site_id
            and snapshot.config_type == config_type
            and snapshot.fetch_kind == "SCHEDULED"
            and snapshot.normalizer_version == normalizer_version
            and snapshot.observed_at < observed_before
        ]
        return max(candidates, key=lambda item: item.observed_at) if candidates else None

    async def previous_ads_condition_snapshot(
        self,
        *,
        tenant_id: uuid.UUID,
        site_id: uuid.UUID,
        observed_before: datetime,
        normalizer_version: str,
    ) -> StoredPublicConfigSnapshot | None:
        candidates = [
            snapshot
            for snapshot in self.snapshots
            if snapshot.tenant_id == tenant_id
            and snapshot.site_id == site_id
            and snapshot.config_type == "ADS_TXT"
            and snapshot.fetch_kind == "SCHEDULED"
            and snapshot.normalizer_version == normalizer_version
            and snapshot.parse_status in {"MISSING", "EMPTY", "INVALID"}
            and snapshot.observed_at < observed_before
        ]
        return max(candidates, key=lambda item: item.observed_at) if candidates else None


class Queue:
    def __init__(self) -> None:
        self.jobs: dict[str, dict[str, Any]] = {}

    async def enqueue(self, **kwargs: Any) -> uuid.UUID:
        key = cast(str, kwargs["idempotency_key"])
        self.jobs.setdefault(key, kwargs)
        return uuid.uuid5(uuid.NAMESPACE_URL, key)


class Client:
    def __init__(self, responses: list[PublicConfigFetchResult | Exception]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    async def fetch(self, **kwargs: Any) -> PublicConfigFetchResult:
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class Clock:
    def __init__(self, start: datetime) -> None:
        self.current = start

    def __call__(self) -> datetime:
        current = self.current
        self.current += timedelta(minutes=1)
        return current


def response(status: int, content: bytes = b"") -> PublicConfigFetchResult:
    return PublicConfigFetchResult(
        url="https://example.com/robots.txt",
        http_status=status,
        content=content,
        content_hash=hashlib.sha256(content).hexdigest(),
        content_type="text/plain",
        redirect_count=0,
    )


def service(
    repository: Repository,
    queue: Queue,
    client: Client,
) -> PublicConfigService:
    return PublicConfigService(
        cast(Any, repository),
        cast(Any, queue),
        cast(Any, client),
        clock=Clock(datetime(2026, 8, 21, tzinfo=UTC)),
    )


async def test_first_baseline_does_not_request_validation() -> None:
    repository, queue = Repository(), Queue()
    subject = service(
        repository,
        queue,
        Client([response(200, b"User-agent: *\nDisallow: /private\n")]),
    )

    result = await subject.run_scheduled(
        tenant_id=TENANT_ID,
        site_id=SITE_ID,
        config_type="ROBOTS_TXT",
        scheduled_for=datetime(2026, 8, 21, tzinfo=UTC),
        attempt=1,
        rule_version=PUBLIC_CONFIG_RULE_VERSION,
    )

    assert result.parse_status == "VALID"
    assert result.validation_requested is False
    assert queue.jobs == {}


async def test_broad_robots_transition_requests_one_independent_validation() -> None:
    repository, queue = Repository(), Queue()
    client = Client(
        [
            response(200, b"User-agent: *\nDisallow: /private\n"),
            response(200, b"User-agent: *\nDisallow: /\n"),
            response(200, b"User-agent: *\nDisallow: /\n"),
        ]
    )
    subject = service(repository, queue, client)
    await subject.run_scheduled(
        tenant_id=TENANT_ID,
        site_id=SITE_ID,
        config_type="ROBOTS_TXT",
        scheduled_for=datetime(2026, 8, 21, tzinfo=UTC),
        attempt=1,
        rule_version=PUBLIC_CONFIG_RULE_VERSION,
    )
    primary = await subject.run_scheduled(
        tenant_id=TENANT_ID,
        site_id=SITE_ID,
        config_type="ROBOTS_TXT",
        scheduled_for=datetime(2026, 8, 21, 6, tzinfo=UTC),
        attempt=1,
        rule_version=PUBLIC_CONFIG_RULE_VERSION,
    )

    assert primary.validation_requested is True
    assert len(queue.jobs) == 1
    validation_job = next(iter(queue.jobs.values()))
    assert validation_job["job_type"] == "VALIDATE_PUBLIC_CONFIG"
    assert validation_job["payload"]["primary_snapshot_id"] == str(primary.snapshot_id)

    validation = await subject.run_validation(
        tenant_id=TENANT_ID,
        site_id=SITE_ID,
        config_type="ROBOTS_TXT",
        primary_snapshot_id=primary.snapshot_id,
        attempt=1,
        rule_version=PUBLIC_CONFIG_RULE_VERSION,
    )

    stored = await repository.load_snapshot(
        tenant_id=TENANT_ID,
        site_id=SITE_ID,
        snapshot_id=validation.snapshot_id,
    )
    assert stored.fetch_kind == "VALIDATION"
    assert stored.validation_of_snapshot_id == primary.snapshot_id
    assert len(queue.jobs) == 1


async def test_previously_valid_ads_missing_requests_validation() -> None:
    repository, queue = Repository(), Queue()
    subject = service(
        repository,
        queue,
        Client(
            [
                response(200, b"example.net, account-1, DIRECT\n"),
                response(404),
            ]
        ),
    )
    await subject.run_scheduled(
        tenant_id=TENANT_ID,
        site_id=SITE_ID,
        config_type="ADS_TXT",
        scheduled_for=datetime(2026, 8, 21, tzinfo=UTC),
        attempt=1,
        rule_version=PUBLIC_CONFIG_RULE_VERSION,
    )
    result = await subject.run_scheduled(
        tenant_id=TENANT_ID,
        site_id=SITE_ID,
        config_type="ADS_TXT",
        scheduled_for=datetime(2026, 8, 21, 6, tzinfo=UTC),
        attempt=1,
        rule_version=PUBLIC_CONFIG_RULE_VERSION,
    )

    assert result.parse_status == "MISSING"
    assert result.validation_requested is True
    assert len(queue.jobs) == 1


async def test_ads_recovery_requests_independent_validation() -> None:
    repository, queue = Repository(), Queue()
    subject = service(
        repository,
        queue,
        Client(
            [
                response(200, b"example.net, account-1, DIRECT\n"),
                response(404),
                response(404),
                response(200, b"example.net, account-1, DIRECT\n"),
            ]
        ),
    )
    await subject.run_scheduled(
        tenant_id=TENANT_ID,
        site_id=SITE_ID,
        config_type="ADS_TXT",
        scheduled_for=datetime(2026, 8, 21, tzinfo=UTC),
        attempt=1,
        rule_version=PUBLIC_CONFIG_RULE_VERSION,
    )
    missing = await subject.run_scheduled(
        tenant_id=TENANT_ID,
        site_id=SITE_ID,
        config_type="ADS_TXT",
        scheduled_for=datetime(2026, 8, 21, 6, tzinfo=UTC),
        attempt=1,
        rule_version=PUBLIC_CONFIG_RULE_VERSION,
    )
    await subject.run_validation(
        tenant_id=TENANT_ID,
        site_id=SITE_ID,
        config_type="ADS_TXT",
        primary_snapshot_id=missing.snapshot_id,
        attempt=1,
        rule_version=PUBLIC_CONFIG_RULE_VERSION,
    )

    recovery = await subject.run_scheduled(
        tenant_id=TENANT_ID,
        site_id=SITE_ID,
        config_type="ADS_TXT",
        scheduled_for=datetime(2026, 8, 21, 12, tzinfo=UTC),
        attempt=1,
        rule_version=PUBLIC_CONFIG_RULE_VERSION,
    )

    assert recovery.parse_status == "VALID"
    assert recovery.validation_requested is True
    assert len(queue.jobs) == 2


async def test_ads_recovery_validation_survives_intervening_http_error() -> None:
    repository, queue = Repository(), Queue()
    subject = service(
        repository,
        queue,
        Client(
            [
                response(200, b"example.net, account-1, DIRECT\n"),
                response(404),
                response(404),
                response(403),
                response(200, b"example.net, account-1, DIRECT\n"),
            ]
        ),
    )
    await subject.run_scheduled(
        tenant_id=TENANT_ID,
        site_id=SITE_ID,
        config_type="ADS_TXT",
        scheduled_for=datetime(2026, 8, 21, tzinfo=UTC),
        attempt=1,
        rule_version=PUBLIC_CONFIG_RULE_VERSION,
    )
    missing = await subject.run_scheduled(
        tenant_id=TENANT_ID,
        site_id=SITE_ID,
        config_type="ADS_TXT",
        scheduled_for=datetime(2026, 8, 21, 6, tzinfo=UTC),
        attempt=1,
        rule_version=PUBLIC_CONFIG_RULE_VERSION,
    )
    await subject.run_validation(
        tenant_id=TENANT_ID,
        site_id=SITE_ID,
        config_type="ADS_TXT",
        primary_snapshot_id=missing.snapshot_id,
        attempt=1,
        rule_version=PUBLIC_CONFIG_RULE_VERSION,
    )
    intermediate = await subject.run_scheduled(
        tenant_id=TENANT_ID,
        site_id=SITE_ID,
        config_type="ADS_TXT",
        scheduled_for=datetime(2026, 8, 21, 12, tzinfo=UTC),
        attempt=1,
        rule_version=PUBLIC_CONFIG_RULE_VERSION,
    )
    recovery = await subject.run_scheduled(
        tenant_id=TENANT_ID,
        site_id=SITE_ID,
        config_type="ADS_TXT",
        scheduled_for=datetime(2026, 8, 21, 18, tzinfo=UTC),
        attempt=1,
        rule_version=PUBLIC_CONFIG_RULE_VERSION,
    )

    assert intermediate.parse_status == "HTTP_ERROR"
    assert intermediate.validation_requested is False
    assert recovery.parse_status == "VALID"
    assert recovery.validation_requested is True
    assert len(queue.jobs) == 2


async def test_transport_failure_is_persisted_before_retry_signal() -> None:
    repository, queue = Repository(), Queue()
    subject = service(
        repository,
        queue,
        Client([PublicConfigFetchError("PUBLIC_CONFIG_TIMEOUT", "timed out", retryable=True)]),
    )

    with pytest.raises(PublicConfigRunError) as raised:
        await subject.run_scheduled(
            tenant_id=TENANT_ID,
            site_id=SITE_ID,
            config_type="ADS_TXT",
            scheduled_for=datetime(2026, 8, 21, tzinfo=UTC),
            attempt=1,
            rule_version=PUBLIC_CONFIG_RULE_VERSION,
        )

    assert raised.value.retryable is True
    assert len(repository.snapshots) == 1
    assert repository.snapshots[0].parse_status == "UNREACHABLE"
    assert queue.jobs == {}


async def test_security_failure_is_persisted_and_terminal() -> None:
    repository, queue = Repository(), Queue()
    subject = service(
        repository,
        queue,
        Client(
            [PublicConfigFetchError("PUBLIC_CONFIG_SECURITY_ERROR", "blocked", retryable=False)]
        ),
    )

    with pytest.raises(PublicConfigRunError) as raised:
        await subject.run_scheduled(
            tenant_id=TENANT_ID,
            site_id=SITE_ID,
            config_type="ROBOTS_TXT",
            scheduled_for=datetime(2026, 8, 21, tzinfo=UTC),
            attempt=1,
            rule_version=PUBLIC_CONFIG_RULE_VERSION,
        )

    assert raised.value.retryable is False
    assert len(repository.snapshots) == 1
    assert repository.snapshots[0].parse_status == "BLOCKED"


async def test_wrong_tenant_is_rejected_before_network() -> None:
    repository, queue = Repository(), Queue()
    client = Client([response(200, b"User-agent: *\nDisallow:\n")])
    subject = service(repository, queue, client)

    with pytest.raises(PublicConfigStateError):
        await subject.run_scheduled(
            tenant_id=uuid.uuid4(),
            site_id=SITE_ID,
            config_type="ROBOTS_TXT",
            scheduled_for=datetime(2026, 8, 21, tzinfo=UTC),
            attempt=1,
            rule_version=PUBLIC_CONFIG_RULE_VERSION,
        )

    assert client.calls == []
