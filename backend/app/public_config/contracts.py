import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

ConfigType = Literal["ROBOTS_TXT", "ADS_TXT"]
FetchKind = Literal["SCHEDULED", "VALIDATION"]
ParseStatus = Literal[
    "VALID",
    "VALID_WITH_WARNINGS",
    "EMPTY",
    "INVALID",
    "MISSING",
    "HTTP_ERROR",
    "UNREACHABLE",
    "TOO_LARGE",
    "BLOCKED",
]
AdsTxtRelationship = Literal["DIRECT", "RESELLER"]

CONFIG_TYPES = frozenset({"ROBOTS_TXT", "ADS_TXT"})
FETCH_KINDS = frozenset({"SCHEDULED", "VALIDATION"})
PARSE_STATUSES = frozenset(
    {
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
)
ADS_TXT_RELATIONSHIPS = frozenset({"DIRECT", "RESELLER"})

MAX_SUMMARY_BYTES = 65_536
MAX_ADS_TXT_RECORDS = 100_000
MAX_VALIDATION_ERRORS = 20
MAX_VALIDATION_ERROR_LENGTH = 200
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class PublicConfigSnapshotInput:
    observation_key: str
    config_type: ConfigType
    observed_at: datetime
    http_status: int | None
    content_hash: str | None
    parse_status: ParseStatus
    normalizer_version: str
    summary: dict[str, Any] = field(default_factory=dict)
    fetch_kind: FetchKind = "SCHEDULED"
    validation_of_snapshot_id: uuid.UUID | None = None
    artifact_id: uuid.UUID | None = None

    def __post_init__(self) -> None:
        if not _SHA256_PATTERN.fullmatch(self.observation_key):
            raise ValueError("observation_key must be a lowercase SHA-256 digest")
        if self.config_type not in CONFIG_TYPES:
            raise ValueError("unsupported public configuration type")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        if self.http_status is not None and not 100 <= self.http_status <= 599:
            raise ValueError("http_status must be between 100 and 599")
        if self.content_hash is not None and not _SHA256_PATTERN.fullmatch(self.content_hash):
            raise ValueError("content_hash must be a lowercase SHA-256 digest")
        if self.parse_status not in PARSE_STATUSES:
            raise ValueError("unsupported public configuration parse status")
        if not self.normalizer_version or len(self.normalizer_version) > 50:
            raise ValueError("normalizer_version must contain at most 50 characters")
        if self.fetch_kind not in FETCH_KINDS:
            raise ValueError("unsupported public configuration fetch kind")
        if self.fetch_kind == "SCHEDULED" and self.validation_of_snapshot_id is not None:
            raise ValueError("scheduled snapshots cannot reference a validation primary")
        if self.fetch_kind == "VALIDATION" and self.validation_of_snapshot_id is None:
            raise ValueError("validation snapshots require a primary snapshot")
        if self.parse_status == "EMPTY" and self.http_status != 200:
            raise ValueError("EMPTY is reserved for HTTP 200 observations")
        _validate_summary(self.summary)
        if (
            self.config_type == "ADS_TXT"
            and self.http_status == 200
            and self.parse_status in {"VALID", "VALID_WITH_WARNINGS"}
        ):
            valid_record_count = self.summary.get("valid_record_count")
            if not isinstance(valid_record_count, int) or valid_record_count < 1:
                raise ValueError("HTTP 200 ads.txt without valid records cannot be healthy")


@dataclass(frozen=True, slots=True)
class AdsTxtRecordInput:
    advertising_system_domain: str
    publisher_account_id: str
    relationship: AdsTxtRelationship
    cert_authority_id: str | None
    record_hash: str
    is_valid: bool = True
    validation_errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (
            not self.advertising_system_domain
            or self.advertising_system_domain != self.advertising_system_domain.strip().lower()
            or len(self.advertising_system_domain) > 253
        ):
            raise ValueError("advertising system domain must be normalized lowercase")
        if (
            not self.publisher_account_id
            or self.publisher_account_id != self.publisher_account_id.strip()
            or len(self.publisher_account_id) > 500
        ):
            raise ValueError("publisher account ID must be non-empty and normalized")
        if self.relationship not in ADS_TXT_RELATIONSHIPS:
            raise ValueError("unsupported ads.txt relationship")
        if self.cert_authority_id is not None and (
            not self.cert_authority_id
            or self.cert_authority_id != self.cert_authority_id.strip()
            or len(self.cert_authority_id) > 255
        ):
            raise ValueError("certification authority ID must be normalized")
        if not _SHA256_PATTERN.fullmatch(self.record_hash):
            raise ValueError("record_hash must be a lowercase SHA-256 digest")
        if len(self.validation_errors) > MAX_VALIDATION_ERRORS:
            raise ValueError("too many ads.txt validation errors")
        if any(
            not error or len(error) > MAX_VALIDATION_ERROR_LENGTH
            for error in self.validation_errors
        ):
            raise ValueError("ads.txt validation errors must be non-empty and bounded")
        if self.is_valid and self.validation_errors:
            raise ValueError("valid ads.txt records cannot carry validation errors")
        if not self.is_valid and not self.validation_errors:
            raise ValueError("invalid ads.txt records require a validation error")


@dataclass(frozen=True, slots=True)
class SnapshotWriteResult:
    snapshot_id: uuid.UUID
    created: bool


@dataclass(frozen=True, slots=True)
class StoredPublicConfigSnapshot:
    id: uuid.UUID
    tenant_id: uuid.UUID
    site_id: uuid.UUID
    config_type: str
    observed_at: datetime
    http_status: int | None
    content_hash: str | None
    parse_status: str
    artifact_id: uuid.UUID | None
    normalizer_version: str
    summary: dict[str, Any]
    fetch_kind: str
    validation_of_snapshot_id: uuid.UUID | None
    observation_key: str


def public_config_observation_key(
    *,
    tenant_id: uuid.UUID,
    site_id: uuid.UUID,
    config_type: ConfigType,
    fetch_kind: FetchKind,
    source_key: str,
) -> str:
    if config_type not in CONFIG_TYPES or fetch_kind not in FETCH_KINDS:
        raise ValueError("unsupported public configuration key component")
    normalized_source_key = source_key.strip()
    if not normalized_source_key or len(normalized_source_key) > 500:
        raise ValueError("public configuration source key must be non-empty and bounded")
    payload = json.dumps(
        {
            "config_type": config_type,
            "fetch_kind": fetch_kind,
            "site_id": str(site_id),
            "source_key": normalized_source_key,
            "tenant_id": str(tenant_id),
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def ads_txt_record_hash(
    *,
    advertising_system_domain: str,
    publisher_account_id: str,
    relationship: AdsTxtRelationship,
    cert_authority_id: str | None,
) -> str:
    payload = "\x1f".join(
        (
            advertising_system_domain,
            publisher_account_id,
            relationship,
            cert_authority_id or "",
        )
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _validate_summary(summary: dict[str, Any]) -> None:
    try:
        encoded = json.dumps(summary, separators=(",", ":"), sort_keys=True).encode()
    except (TypeError, ValueError) as error:
        raise ValueError("public configuration summary must be JSON serializable") from error
    if len(encoded) > MAX_SUMMARY_BYTES:
        raise ValueError("public configuration summary exceeds the byte limit")
