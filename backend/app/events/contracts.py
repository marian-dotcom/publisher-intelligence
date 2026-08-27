import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

ConfirmationMode = Literal[
    "SINGLE_STRONG_OBSERVATION",
    "TWO_CONSECUTIVE_CHECKPOINTS",
    "MULTI_URL_CORROBORATION",
    "IMMEDIATE_SECOND_CHECK",
]
EvidenceKind = Literal["CHECKPOINT_RUN", "PUBLIC_CONFIG_SNAPSHOT"]
EventKind = Literal["POINT", "CONDITION"]
EventAction = Literal[
    "RECORD",
    "UPSERT_CONDITION",
    "SUPPORT_CONDITION",
    "RESOLVE_CONDITION",
    "PENDING",
]
EventStatus = Literal["RECORDED", "ACTIVE", "RESOLVED", "SUPERSEDED"]


@dataclass(frozen=True, slots=True)
class EventRule:
    code: str
    family: str
    description: str
    kind: EventKind
    default_severity: str
    confirmation: ConfirmationMode
    evidence_kinds: tuple[str, ...]
    subject_kind: str
    diff_operator: str
    aggregation_scope: str
    severity_policy: str
    resolution_rule: str
    dedupe_strategy: str
    domain_refs: tuple[str, ...]
    noise_notes: str
    rule_version: str
    min_valid_urls: int = 1
    min_affected_urls: int = 1
    critical_min_affected_urls: int | None = None
    schema_version: int = 2


@dataclass(frozen=True, slots=True, init=False)
class EvidencePointer:
    source_id: uuid.UUID
    relation: str
    evidence_kind: EvidenceKind = "CHECKPOINT_RUN"

    def __init__(
        self,
        source_id: uuid.UUID | None = None,
        relation: str = "",
        evidence_kind: EvidenceKind = "CHECKPOINT_RUN",
        *,
        checkpoint_run_id: uuid.UUID | None = None,
    ) -> None:
        if source_id is not None and checkpoint_run_id is not None:
            raise TypeError("provide source_id or checkpoint_run_id, not both")
        resolved_source_id = source_id if source_id is not None else checkpoint_run_id
        if resolved_source_id is None:
            raise TypeError("evidence source ID is required")
        if not relation:
            raise ValueError("evidence relation is required")
        object.__setattr__(self, "source_id", resolved_source_id)
        object.__setattr__(self, "relation", relation)
        object.__setattr__(self, "evidence_kind", evidence_kind)

    @property
    def checkpoint_run_id(self) -> uuid.UUID:
        """Compatibility alias for the browser event path."""
        return self.source_id


@dataclass(frozen=True, slots=True)
class EventCandidate:
    code: str
    subject: str
    summary: str
    before: object
    after: object
    confirmation: ConfirmationMode
    action: EventAction = "RECORD"
    severity: str | None = None
    scope: dict[str, object] = field(default_factory=dict)
    occurred_after_at: datetime | None = None
    occurred_before_at: datetime | None = None
    detected_at: datetime | None = None
    evidence: tuple[EvidencePointer, ...] = ()
    affected_url_count: int = 1
    valid_url_count: int = 1


@dataclass(frozen=True, slots=True)
class DiagnosticInput:
    tenant_id: uuid.UUID
    site_id: uuid.UUID
    checkpoint_run_id: uuid.UUID
    checkpoint_window_id: uuid.UUID
    observed_at: datetime | None
    trigger_correlation_id: uuid.UUID | None
    status: str
    # EP-026 M2b-1a-2b: bounded {state, reason} access classification stored
    # on the DIAGNOSTIC run at finalize. None = not classified / malformed.
    browser_access_classification: dict[str, object] | None = None
    # EP-026 M2b-2: bounded context of the site's OPEN degradation episode
    # (latest reliability event is a degradation without later recovery).
    # Populated deterministically by the repository; all fields required for
    # recovery emission must be present, else no recovery is derived.
    open_degradation_event_id: uuid.UUID | None = None
    open_degradation_code: str | None = None
    open_degradation_detected_at: datetime | None = None
    open_degradation_checkpoint_run_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class EvaluationInput:
    tenant_id: uuid.UUID
    site_id: uuid.UUID
    monitored_url_id: uuid.UUID
    template_id: uuid.UUID
    scenario_id: uuid.UUID
    previous_checkpoint_run_id: uuid.UUID
    current_checkpoint_run_id: uuid.UUID
    previous_observed_at: datetime
    current_observed_at: datetime
    previous_status: str
    current_status: str
    selection_scope: str
    previous_state: dict[str, object]
    current_state: dict[str, object]
    previous_gpt: dict[str, object]
    current_gpt: dict[str, object]
    prior_checkpoint_run_id: uuid.UUID | None = None
    prior_observed_at: datetime | None = None
    prior_status: str | None = None
    prior_state: dict[str, object] = field(default_factory=dict)
    prior_gpt: dict[str, object] = field(default_factory=dict)
    checkpoint_window_id: uuid.UUID | None = None
    checkpoint_window_status: str | None = None


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    candidates: tuple[EventCandidate, ...]
    skip_reasons: tuple[str, ...]
