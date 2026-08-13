import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

CheckpointStatus = Literal[
    "COMPLETE",
    "PARTIAL",
    "SITE_ERROR",
    "BROWSER_ERROR",
    "TIMEOUT",
    "BLOCKED",
]
CollectorStatus = Literal["OK", "NOT_PRESENT", "NOT_OBSERVABLE", "ERROR", "TIMEOUT"]


@dataclass(frozen=True, slots=True)
class BrowserTarget:
    checkpoint_run_id: uuid.UUID
    tenant_id: uuid.UUID
    site_id: uuid.UUID
    monitored_url_id: uuid.UUID
    scenario_id: uuid.UUID
    url: str
    canonical_domain: str
    scenario_code: str
    scenario_version: int
    locale: str
    timezone: str
    viewport_width: int
    viewport_height: int


@dataclass(frozen=True, slots=True)
class RequestFailure:
    url: str
    resource_type: str
    error_text: str


@dataclass(frozen=True, slots=True)
class JavaScriptError:
    message: str
    source: str | None = None
    line: int | None = None
    column: int | None = None


@dataclass(frozen=True, slots=True)
class CollectorResult:
    collector_type: str
    collector_version: str
    status: CollectorStatus
    started_at: datetime
    completed_at: datetime
    summary: dict[str, object]
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class ArtifactContent:
    artifact_type: str
    filename: str
    content_type: str
    retention_class: str
    content: bytes


@dataclass(slots=True)
class BrowserEvidence:
    status: CheckpointStatus
    started_at: datetime
    completed_at: datetime
    final_url: str | None
    http_status: int | None
    playwright_version: str
    chromium_version: str | None
    environment: dict[str, object]
    redirect_chain: list[str] = field(default_factory=list)
    scripts: list[str] = field(default_factory=list)
    network_hosts: list[str] = field(default_factory=list)
    third_party_hosts: list[str] = field(default_factory=list)
    request_count: int = 0
    request_failures: list[RequestFailure] = field(default_factory=list)
    javascript_errors: list[JavaScriptError] = field(default_factory=list)
    console_errors: list[JavaScriptError] = field(default_factory=list)
    blocked_requests: list[RequestFailure] = field(default_factory=list)
    actions: list[dict[str, object]] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    artifacts: list[ArtifactContent] = field(default_factory=list)
    collectors: list[CollectorResult] = field(default_factory=list)
    failure_class: str | None = None
    failure_message: str | None = None


@dataclass(frozen=True, slots=True)
class StoredArtifactRecord:
    artifact_type: str
    object_key: str
    content_type: str
    byte_size: int
    sha256: str
    retention_class: str
