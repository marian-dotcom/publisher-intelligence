import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import cast

from app.jobs.queue import JobQueue
from app.public_config.ads_txt import ADS_TXT_NORMALIZER_VERSION, parse_ads_txt
from app.public_config.client import PublicConfigClient, PublicConfigFetchError
from app.public_config.contracts import (
    PUBLIC_CONFIG_RULE_VERSION,
    AdsTxtRecordInput,
    ConfigType,
    FetchKind,
    ParseStatus,
    PublicConfigRunResult,
    PublicConfigSnapshotInput,
    StoredPublicConfigSnapshot,
    public_config_observation_key,
)
from app.public_config.persistence import PublicConfigRepository, PublicConfigStateError
from app.public_config.robots import ROBOTS_NORMALIZER_VERSION, parse_robots_txt


class PublicConfigRunError(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        retryable: bool,
        snapshot_id: uuid.UUID | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable
        self.snapshot_id = snapshot_id


class PublicConfigService:
    def __init__(
        self,
        repository: PublicConfigRepository,
        queue: JobQueue,
        client: PublicConfigClient,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._queue = queue
        self._client = client
        self._clock = clock or (lambda: datetime.now(UTC))

    async def run_scheduled(
        self,
        *,
        tenant_id: uuid.UUID,
        site_id: uuid.UUID,
        config_type: ConfigType,
        scheduled_for: datetime,
        attempt: int,
        rule_version: str,
    ) -> PublicConfigRunResult:
        _validate_run_inputs(scheduled_for, attempt, rule_version)
        target = await self._repository.load_active_site(tenant_id=tenant_id, site_id=site_id)
        observed_at = _aware_now(self._clock())
        normalizer_version = _normalizer_version(config_type)
        predecessor = await self._repository.previous_healthy_scheduled_snapshot(
            tenant_id=tenant_id,
            site_id=site_id,
            config_type=config_type,
            observed_before=observed_at,
            normalizer_version=normalizer_version,
        )
        result = await self._observe(
            tenant_id=tenant_id,
            site_id=site_id,
            canonical_scheme=target.canonical_scheme,
            canonical_domain=target.canonical_domain,
            config_type=config_type,
            fetch_kind="SCHEDULED",
            validation_of_snapshot_id=None,
            source_key=f"{scheduled_for.isoformat()}:attempt:{attempt}",
            observed_at=observed_at,
        )
        current = await self._repository.load_snapshot(
            tenant_id=tenant_id,
            site_id=site_id,
            snapshot_id=result.snapshot_id,
        )
        if not _requires_validation(
            result,
            predecessor=predecessor,
            config_type=config_type,
            summary=current.summary,
        ):
            return result
        await self._queue.enqueue(
            tenant_id=tenant_id,
            job_type="VALIDATE_PUBLIC_CONFIG",
            payload={
                "site_id": str(site_id),
                "config_type": config_type,
                "primary_snapshot_id": str(result.snapshot_id),
                "rule_version": PUBLIC_CONFIG_RULE_VERSION,
            },
            idempotency_key=(
                f"public-config-validation:{result.snapshot_id}:{PUBLIC_CONFIG_RULE_VERSION}"
            ),
            priority=10,
            max_attempts=3,
        )
        return PublicConfigRunResult(
            snapshot_id=result.snapshot_id,
            created=result.created,
            parse_status=result.parse_status,
            validation_requested=True,
        )

    async def run_validation(
        self,
        *,
        tenant_id: uuid.UUID,
        site_id: uuid.UUID,
        config_type: ConfigType,
        primary_snapshot_id: uuid.UUID,
        attempt: int,
        rule_version: str,
    ) -> PublicConfigRunResult:
        if attempt < 1 or rule_version != PUBLIC_CONFIG_RULE_VERSION:
            raise PublicConfigStateError("public configuration validation contract is invalid")
        target = await self._repository.load_active_site(tenant_id=tenant_id, site_id=site_id)
        primary = await self._repository.load_snapshot(
            tenant_id=tenant_id,
            site_id=site_id,
            snapshot_id=primary_snapshot_id,
        )
        if (
            primary.fetch_kind != "SCHEDULED"
            or primary.config_type != config_type
            or primary.normalizer_version != _normalizer_version(config_type)
        ):
            raise PublicConfigStateError("validation primary is not eligible")
        predecessor = await self._repository.previous_healthy_scheduled_snapshot(
            tenant_id=tenant_id,
            site_id=site_id,
            config_type=config_type,
            observed_before=primary.observed_at,
            normalizer_version=primary.normalizer_version,
        )
        primary_result = PublicConfigRunResult(
            snapshot_id=primary.id,
            created=False,
            parse_status=_parse_status(primary.parse_status),
            validation_requested=False,
        )
        if not _requires_validation(
            primary_result,
            predecessor=predecessor,
            config_type=config_type,
            summary=primary.summary,
        ):
            raise PublicConfigStateError("validation primary is not a high-risk transition")
        observed_at = _aware_now(self._clock())
        if observed_at <= primary.observed_at:
            observed_at = primary.observed_at + timedelta(microseconds=1)
        return await self._observe(
            tenant_id=tenant_id,
            site_id=site_id,
            canonical_scheme=target.canonical_scheme,
            canonical_domain=target.canonical_domain,
            config_type=config_type,
            fetch_kind="VALIDATION",
            validation_of_snapshot_id=primary.id,
            source_key=(f"primary:{primary.id}:{rule_version}:attempt:{attempt}"),
            observed_at=observed_at,
        )

    async def _observe(
        self,
        *,
        tenant_id: uuid.UUID,
        site_id: uuid.UUID,
        canonical_scheme: str,
        canonical_domain: str,
        config_type: ConfigType,
        fetch_kind: FetchKind,
        validation_of_snapshot_id: uuid.UUID | None,
        source_key: str,
        observed_at: datetime,
    ) -> PublicConfigRunResult:
        normalizer_version = _normalizer_version(config_type)
        observation_key = public_config_observation_key(
            tenant_id=tenant_id,
            site_id=site_id,
            config_type=config_type,
            fetch_kind=fetch_kind,
            source_key=source_key,
        )
        try:
            fetched = await self._client.fetch(
                canonical_scheme=canonical_scheme,
                canonical_domain=canonical_domain,
                config_type=config_type,
            )
        except PublicConfigFetchError as error:
            parse_status = _fetch_error_status(error.code)
            write = await self._repository.persist_snapshot(
                tenant_id=tenant_id,
                site_id=site_id,
                snapshot=PublicConfigSnapshotInput(
                    observation_key=observation_key,
                    config_type=config_type,
                    observed_at=observed_at,
                    http_status=None,
                    content_hash=None,
                    parse_status=parse_status,
                    normalizer_version=normalizer_version,
                    summary={
                        "normalizer_version": normalizer_version,
                        "error_code": error.code,
                    },
                    fetch_kind=fetch_kind,
                    validation_of_snapshot_id=validation_of_snapshot_id,
                ),
            )
            raise PublicConfigRunError(
                error.code,
                retryable=error.retryable,
                snapshot_id=write.snapshot_id,
            ) from error

        parse_status, summary, records = _normalize_response(
            config_type=config_type,
            http_status=fetched.http_status,
            content=fetched.content,
            url=fetched.url,
            content_type=fetched.content_type,
            redirect_count=fetched.redirect_count,
        )
        write = await self._repository.persist_snapshot(
            tenant_id=tenant_id,
            site_id=site_id,
            snapshot=PublicConfigSnapshotInput(
                observation_key=observation_key,
                config_type=config_type,
                observed_at=observed_at,
                http_status=fetched.http_status,
                content_hash=fetched.content_hash,
                parse_status=parse_status,
                normalizer_version=normalizer_version,
                summary=summary,
                fetch_kind=fetch_kind,
                validation_of_snapshot_id=validation_of_snapshot_id,
            ),
            records=records,
        )
        if fetched.http_status == 429 or fetched.http_status >= 500:
            raise PublicConfigRunError(
                "PUBLIC_CONFIG_HTTP_ERROR",
                retryable=True,
                snapshot_id=write.snapshot_id,
            )
        return PublicConfigRunResult(
            snapshot_id=write.snapshot_id,
            created=write.created,
            parse_status=parse_status,
            validation_requested=False,
        )


def _normalize_response(
    *,
    config_type: ConfigType,
    http_status: int,
    content: bytes,
    url: str,
    content_type: str | None,
    redirect_count: int,
) -> tuple[ParseStatus, dict[str, object], tuple[AdsTxtRecordInput, ...]]:
    normalizer_version = _normalizer_version(config_type)
    metadata: dict[str, object] = {
        "normalizer_version": normalizer_version,
        "byte_count": len(content),
        "redirect_count": redirect_count,
        "final_url": url,
        "content_type": content_type,
    }
    if http_status != 200:
        if http_status in {404, 410}:
            parse_status: ParseStatus = "MISSING"
        elif config_type == "ROBOTS_TXT" and http_status >= 500:
            parse_status = "UNREACHABLE"
        else:
            parse_status = "HTTP_ERROR"
        metadata["http_outcome"] = parse_status
        return parse_status, metadata, ()
    if config_type == "ROBOTS_TXT":
        parsed = parse_robots_txt(content)
        return parsed.parse_status, {**parsed.summary, **metadata}, ()
    parsed_ads = parse_ads_txt(content)
    return parsed_ads.parse_status, {**parsed_ads.summary, **metadata}, parsed_ads.records


def _requires_validation(
    current: PublicConfigRunResult,
    *,
    predecessor: StoredPublicConfigSnapshot | None,
    config_type: ConfigType,
    summary: dict[str, object] | None = None,
) -> bool:
    if predecessor is None:
        return False
    current_summary = summary or {}
    if config_type == "ROBOTS_TXT":
        return bool(current_summary.get("broad_blocked")) and not bool(
            predecessor.summary.get("broad_blocked")
        )
    return current.parse_status in {"MISSING", "EMPTY", "INVALID"}


def _normalizer_version(config_type: ConfigType) -> str:
    return ROBOTS_NORMALIZER_VERSION if config_type == "ROBOTS_TXT" else ADS_TXT_NORMALIZER_VERSION


def _fetch_error_status(code: str) -> ParseStatus:
    if code == "PUBLIC_CONFIG_TOO_LARGE":
        return "TOO_LARGE"
    if code == "PUBLIC_CONFIG_SECURITY_ERROR":
        return "BLOCKED"
    return "UNREACHABLE"


def _parse_status(value: str) -> ParseStatus:
    allowed: set[str] = {
        "VALID",
        "VALID_WITH_WARNINGS",
        "EMPTY",
        "INVALID",
        "MISSING",
        "HTTP_ERROR",
        "UNREACHABLE",
        "TOO_LARGE",
        "BLOCKED",
    }
    if value not in allowed:
        raise PublicConfigStateError("stored public configuration status is invalid")
    return cast(ParseStatus, value)


def _validate_run_inputs(scheduled_for: datetime, attempt: int, rule_version: str) -> None:
    if scheduled_for.tzinfo is None or scheduled_for.utcoffset() is None:
        raise PublicConfigStateError(
            "scheduled public configuration instant must be timezone-aware"
        )
    if attempt < 1 or rule_version != PUBLIC_CONFIG_RULE_VERSION:
        raise PublicConfigStateError("scheduled public configuration contract is invalid")


def _aware_now(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise PublicConfigStateError("public configuration clock must be timezone-aware")
    return value.astimezone(UTC)
