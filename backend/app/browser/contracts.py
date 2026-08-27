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
class CollectorResult:
    collector_name: str
    collector_version: str
    status: CollectorStatus
    summary: dict[str, object] = field(default_factory=dict)
    artifact_refs: tuple[uuid.UUID, ...] = ()
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class BrowserRunResult:
    checkpoint_run_id: uuid.UUID
    tenant_id: uuid.UUID
    site_id: uuid.UUID
    monitored_url_id: uuid.UUID
    scenario_id: uuid.UUID
    status: CheckpointStatus
    started_at: datetime
    completed_at: datetime
    requested_url: str
    final_url: str | None
    response_status: int | None
    page_title: str | None
    environment: dict[str, object]
    request_failures: tuple[RequestFailure, ...] = ()
    js_errors: tuple[JavaScriptError, ...] = ()
    network_observations: tuple[NetworkObservation, ...] = ()
    collector_results: tuple[CollectorResult, ...] = ()
    limitations: tuple[str, ...] = ()
    manifest: dict[str, object] = field(default_factory=dict)
