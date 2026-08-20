import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

ConfirmationMode = Literal["SINGLE_STRONG_OBSERVATION", "REQUIRES_E2_CONFIRMATION"]


@dataclass(frozen=True, slots=True)
class EventRule:
    code: str
    family: str
    description: str
    default_severity: str
    confirmation: ConfirmationMode
    evidence_kinds: tuple[str, ...]
    schema_version: int = 1


@dataclass(frozen=True, slots=True)
class EventCandidate:
    code: str
    subject: str
    summary: str
    before: object
    after: object
    confirmation: ConfirmationMode


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


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    candidates: tuple[EventCandidate, ...]
    skip_reasons: tuple[str, ...]
