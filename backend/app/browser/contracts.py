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
InteractionStepType = Literal["WAIT", "SCROLL_PERCENT", "INSPECT"]


@dataclass(frozen=True, slots=True)
class InteractionStep:
    step_type: InteractionStepType
    duration_ms: int | None = None
    percent: int | None = None
    marker: str | None = None


@dataclass(frozen=True, slots=True)
class ExpectedGPTSlot:
    entity_id: uuid.UUID
    stable_key: str
    ad_unit_path: str | None = None
    dom_element_id: str | None = None
    sizes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ConsentAdapterConfig:
    vendor: str | None = None
    accept_selector: str | None = None
    reject_selector: str | None = None
    ready_selector: str | None = None


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
    scheduled_for: datetime | None = None
    device_scale_factor: float = 1.0
    user_agent: str | None = None
    is_mobile: bool = False
    has_touch: bool = False
    interaction_profile_id: uuid.UUID | None = None
    interaction_profile_code: str | None = None
    interaction_profile_version: int | None = None
    interaction_steps: tuple[InteractionStep, ...] = ()
    template_id: uuid.UUID | None = None
    template_code: str = "pilot"
    template_family: str = "CUSTOM"
    template_fingerprint_version: str | None = None
    template_expected_features: dict[str, object] = field(default_factory=dict)
    expected_gpt_slots: tuple[ExpectedGPTSlot, ...] = ()
    consent_path: str = "NONE"
    consent_adapter: ConsentAdapterConfig | None = None


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
class NetworkObservation:
    url: str
    method: str
    resource_type: str
    status: int | None = None
    error_text: str | None = None
    observed_at_ms: int | None = None


@dataclass(frozen=True, slots=True)
class NormalizedEntityObservation:
    entity_kind: str
    stable_key: str
    state_hash: str
    state: dict[str, object]


@dataclass(frozen=True, slots=True)
class GPTSlotObservation:
    stable_key: str
    ad_unit_path: str | None
    dom_element_id: str | None
    sizes: tuple[str, ...]
    expected: bool
    present: bool
    defined_at_ms: int | None = None
    requested_at_ms: int | None = None
    response_at_ms: int | None = None
    render_ended_at_ms: int | None = None
    onload_at_ms: int | None = None
    viewable_at_ms: int | None = None
    is_empty: bool | None = None
    creative_id: str | None = None
    line_item_id: str | None = None
    request_count: int = 0


@dataclass(frozen=True, slots=True)
class CMPObservation:
    cmp_detected: bool
    tcf_api_detected: bool
    consent_action: str
    consent_action_status: str
    ui_detected_at_ms: int | None = None
    api_ready_at_ms: int | None = None
    action_started_at_ms: int | None = None
    action_completed_at_ms: int | None = None
    tc_state_available_at_ms: int | None = None
    gdpr_applies: bool | None = None
    tc_string_hash: str | None = None
    tcf_error_codes: tuple[str, ...] = ()
    cmp_id: int | None = None
    cmp_version: int | None = None
    cmp_status: str | None = None
    event_status: str | None = None
    vendor: str | None = None


@dataclass(frozen=True, slots=True)
class ConsentPhaseDependencyObservation:
    phase: str
    stable_key: str
    host: str
    path_family: str
    resource_type: str
    category: str
    request_count: int
    error_count: int
    first_request_at_ms: int | None


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
    normalized_state: dict[str, object] = field(default_factory=dict)
    normalized_entities: list[NormalizedEntityObservation] = field(default_factory=list)
    gpt_present: bool = False
    gpt_version: str | None = None
    gpt_slots: list[GPTSlotObservation] = field(default_factory=list)
    cmp_observation: CMPObservation | None = None
    consent_phase_dependencies: list[ConsentPhaseDependencyObservation] = field(
        default_factory=list
    )
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
