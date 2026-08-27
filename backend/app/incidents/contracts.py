import uuid
from datetime import datetime
from typing import Any, Literal

IncidentStatus = Literal["OPEN", "INVESTIGATING", "RESOLVED", "CLOSED_UNRESOLVED"]
SymptomFamily = Literal[
    "GAM_ADSERVING",
    "SEARCH_DISCOVER",
    "CONSENT_CMP",
    "PREBID_HEADER_BIDDING",
    "VIDEO",
    "BROWSER_PERFORMANCE",
    "ANALYTICS_MEASUREMENT",
    "EXTERNAL_INFRASTRUCTURE",
    "REPORTING_DISCREPANCY",
    "POLICY_COMPLIANCE",
    "PROGRAMMATIC_MARKET",
    "OTHER",
]
ResourceKind = Literal["DRILLDOWN", "LLM_PASS", "DIAGNOSTIC_RUN", "CHECKPOINT_RUN"]

INCIDENT_STATUSES = frozenset({"OPEN", "INVESTIGATING", "RESOLVED", "CLOSED_UNRESOLVED"})
SYMPTOM_FAMILIES = frozenset(
    {
        "GAM_ADSERVING",
        "SEARCH_DISCOVER",
        "CONSENT_CMP",
        "PREBID_HEADER_BIDDING",
        "VIDEO",
        "BROWSER_PERFORMANCE",
        "ANALYTICS_MEASUREMENT",
        "EXTERNAL_INFRASTRUCTURE",
        "REPORTING_DISCREPANCY",
        "POLICY_COMPLIANCE",
        "PROGRAMMATIC_MARKET",
        "OTHER",
    }
)
RESOURCE_KINDS = frozenset({"DRILLDOWN", "LLM_PASS", "DIAGNOSTIC_RUN", "CHECKPOINT_RUN"})

MAX_TITLE_LENGTH = 300
MAX_SEGMENT_LENGTH = 200
MAX_USAGE_KEY_LENGTH = 300

DEFAULT_RESOURCE_LIMITS: dict[str, int] = {
    "DRILLDOWN": 4,
    "DIAGNOSTIC_RUN": 8,
    # Reserved until the LLM milestone; no runtime consumer exists yet.
    "LLM_PASS": 20,
    # EP-026 M4: per-site/per-window scheduled checkpoint budget. Normal
    # cadence schedules two runs (desktop + mobile) per site per six-hour
    # window; the cap tolerates headroom while tripping the circuit breaker
    # on runaway scheduling.
    "CHECKPOINT_RUN": 4,
}


class InvestigationStateError(RuntimeError):
    pass


def validate_incident_fields(
    *,
    title: str,
    symptom_family: str,
    description: str,
    status: str = "OPEN",
    severity: str | None = None,
) -> None:
    if not title.strip() or len(title) > MAX_TITLE_LENGTH:
        raise InvestigationStateError("incident title is required and bounded")
    if symptom_family not in SYMPTOM_FAMILIES:
        raise InvestigationStateError("unknown incident symptom family")
    if not description.strip():
        raise InvestigationStateError("incident description is required")
    if status not in INCIDENT_STATUSES:
        raise InvestigationStateError("unknown incident status")
    if severity is not None and severity not in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
        raise InvestigationStateError("unknown incident severity")


def validate_symptom_segment(*, dimension: str, operator: str, value: str, source: str) -> None:
    for name, item in (
        ("dimension", dimension),
        ("operator", operator),
        ("value", value),
        ("source", source),
    ):
        if not item.strip() or len(item) > MAX_SEGMENT_LENGTH:
            raise InvestigationStateError(f"symptom segment {name} is required and bounded")


def validate_resource_kind(resource_kind: str) -> None:
    if resource_kind not in RESOURCE_KINDS:
        raise InvestigationStateError("unknown investigation resource kind")


def usage_key_for(
    *,
    investigation_key: str,
    resource_kind: str,
    correlation_id: uuid.UUID | str,
) -> str:
    normalized = investigation_key.strip()
    if not normalized or len(normalized) > MAX_USAGE_KEY_LENGTH:
        raise InvestigationStateError("investigation key is required and bounded")
    validate_resource_kind(resource_kind)
    return f"{normalized}|{resource_kind}|{correlation_id}"


def fingerprint_snapshot(values: dict[str, Any]) -> dict[str, str]:
    """Build a stable, ordered version-fingerprint snapshot.

    Values are stringified and sorted by key so identical inputs always
    serialize identically; fingerprints_comparable treats two snapshots as
    comparable only when every entry matches.
    """
    cleaned = {str(key): str(item) for key, item in values.items()}
    return {key: cleaned[key] for key in sorted(cleaned)}


def fingerprints_comparable(a: dict[str, str], b: dict[str, str]) -> bool:
    return a == b


def assert_time_window_valid(
    reported_start_at: datetime | None, reported_end_at: datetime | None
) -> None:
    if (
        reported_start_at is not None
        and reported_end_at is not None
        and reported_end_at < reported_start_at
    ):
        raise InvestigationStateError("reported window end precedes start")
