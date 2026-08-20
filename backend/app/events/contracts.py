import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

ConfirmationMode = Literal[
    "SINGLE_STRONG_OBSERVATION",
    "TWO_CONSECUTIVE_CHECKPOINTS",
    "MULTI_URL_CORROBORATION",
]
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


@dataclass(frozen=True, slots=True)
class EvidencePointer:
    checkpoint_run_id: uuid.UUID
    relation: str


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
