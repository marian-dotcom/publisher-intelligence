import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

# EP-026 M2: documented, stable, non-deceptive monitoring identity for
# publisher allowlisting. Not a consumer-browser impersonation string.
MONITORING_USER_AGENT = (
    "PublisherIntelligenceMonitoring/1.0 (+operational monitoring; "
    "allowlisting contact: operator runbook)"
)
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

# ADR-130 observation run taxonomy. Kinds and trigger provenance are
# creation-time evidence: they are assigned when the checkpoint run row is
# created and never mutated afterwards. SCHEDULED runs carry no provenance;
# every non-scheduled run records both a controlled trigger source and the
# concrete correlation identity of the invocation that produced it.
ObservationKind = Literal["SCHEDULED", "DIAGNOSTIC", "INCIDENT_DIAGNOSTIC"]
TriggerSource = Literal["OPERATOR_CLI", "LEGACY_CLI", "OPERATOR_UI", "INCIDENT"]

OBSERVATION_KINDS = frozenset({"SCHEDULED", "DIAGNOSTIC", "INCIDENT_DIAGNOSTIC"})
TRIGGER_SOURCES = frozenset({"OPERATOR_CLI", "LEGACY_CLI", "OPERATOR_UI", "INCIDENT"})


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
    request_started_at_ms: int | None = None
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
class PrebidAuctionObservation:
    auction_key: str
    started_at_ms: int | None
    ended_at_ms: int | None
    configured_timeout_ms: int | None
    ad_unit_count: int | None
    bidder_request_count: int
    bid_response_count: int
    no_bid_count: int
    timeout_count: int
    first_ad_server_request_at_ms: int | None = None


@dataclass(frozen=True, slots=True)
class PrebidBidderObservation:
    auction_key: str
    bidder_code: str
    request_count: int
    response_count: int
    no_bid_count: int
    timeout_count: int
    response_time_ms_min: float | None
    response_time_ms_max: float | None
    response_time_ms_avg: float | None
    winning_bid_count: int


@dataclass(frozen=True, slots=True)
class VideoPlayerObservation:
    stable_key: str
    present: bool
    visible: bool | None
    sticky: bool | None
    fixed: bool | None
    autoplay: bool | None
    muted: bool | None
    controls_present: bool | None
    dismiss_control_present: bool | None
    width_px: float | None
    height_px: float | None
    vast_request_count: int
    vast_error_count: int
    media_request_count: int
    playback_started: bool | None


@dataclass(frozen=True, slots=True)
class SyntheticPerformanceObservation:
    lcp_ms: float | None
    cls: float | None
    inp_ms: float | None
    inp_method: str | None
    ttfb_ms: float | None
    dom_content_loaded_ms: float | None
    load_event_ms: float | None
    long_task_count: int | None
    long_task_total_ms: float | None
    metadata: dict[str, object]


@dataclass(frozen=True, slots=True)
class SEOObservation:
    title_hash: str | None
    meta_robots: str | None
    canonical_url: str | None
    final_url: str | None
    http_status: int | None
    redirect_count: int
    collector_version: str


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
    prebid_present: bool = False
    prebid_version: str | None = None
    prebid_server_side_configured: bool = False
    prebid_targeting_keys: list[str] = field(default_factory=list)
    prebid_limitations: list[str] = field(default_factory=list)
    prebid_auctions: list[PrebidAuctionObservation] = field(default_factory=list)
    prebid_bidders: list[PrebidBidderObservation] = field(default_factory=list)
    video_present: bool = False
    video_limitations: list[str] = field(default_factory=list)
    video_players: list[VideoPlayerObservation] = field(default_factory=list)
    synthetic_performance: SyntheticPerformanceObservation | None = None
    seo_observation: SEOObservation | None = None
    failure_class: str | None = None
    failure_message: str | None = None
    # EP-026 M2b-1b: pre-reduced deterministic challenge signal from bounded
    # transient page text (detect_challenge_marker). Only the marker name is
    # carried; the source text is never persisted by this feature.
    challenge_marker: str | None = None


@dataclass(frozen=True, slots=True)
class StoredArtifactRecord:
    artifact_type: str
    object_key: str
    content_type: str
    byte_size: int
    sha256: str
    retention_class: str
