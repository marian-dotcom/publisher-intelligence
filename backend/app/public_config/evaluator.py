from dataclasses import dataclass

from app.events.contracts import EvaluationResult, EventAction, EventCandidate, EvidencePointer
from app.events.registry import RULES_BY_CODE
from app.public_config.contracts import StoredPublicConfigSnapshot

HEALTHY_STATUSES = {"VALID", "VALID_WITH_WARNINGS"}
ADS_CONDITION_CODES = {
    "MISSING": "ADS_TXT_MISSING",
    "EMPTY": "ADS_TXT_EMPTY_200",
    "INVALID": "ADS_TXT_INVALID",
}


@dataclass(frozen=True, slots=True)
class PublicConfigEvaluationInput:
    previous: StoredPublicConfigSnapshot | None
    primary: StoredPublicConfigSnapshot
    validation: StoredPublicConfigSnapshot | None = None


def evaluate(value: PublicConfigEvaluationInput) -> EvaluationResult:
    reason = _invalid_reason(value)
    if reason is not None:
        return EvaluationResult((), (reason,))
    if value.previous is None:
        return EvaluationResult((), ("FIRST_SEMANTIC_BASELINE",))
    if value.primary.config_type == "ROBOTS_TXT":
        return _evaluate_robots(value)
    return _evaluate_ads(value)


def _invalid_reason(value: PublicConfigEvaluationInput) -> str | None:
    primary = value.primary
    if primary.fetch_kind != "SCHEDULED":
        return "PRIMARY_NOT_SCHEDULED"
    for snapshot in (value.previous, value.validation):
        if snapshot is None:
            continue
        if (
            snapshot.tenant_id != primary.tenant_id
            or snapshot.site_id != primary.site_id
            or snapshot.config_type != primary.config_type
        ):
            return "INCOMPATIBLE_SNAPSHOT_OWNERSHIP"
        if snapshot.normalizer_version != primary.normalizer_version:
            return "INCOMPATIBLE_PUBLIC_CONFIG_NORMALIZER"
    if value.previous is not None:
        if value.previous.fetch_kind != "SCHEDULED":
            return "PREDECESSOR_NOT_SCHEDULED"
        if value.previous.observed_at >= primary.observed_at:
            return "UNORDERED_OBSERVATION_TIME"
    if value.validation is not None:
        if (
            value.validation.fetch_kind != "VALIDATION"
            or value.validation.validation_of_snapshot_id != primary.id
        ):
            return "INVALID_VALIDATION_LINEAGE"
        if value.validation.observed_at < primary.observed_at:
            return "UNORDERED_VALIDATION_TIME"
    return None


def _evaluate_robots(value: PublicConfigEvaluationInput) -> EvaluationResult:
    assert value.previous is not None
    previous, primary = value.previous, value.primary
    if (
        previous.parse_status not in HEALTHY_STATUSES
        or primary.parse_status not in HEALTHY_STATUSES
    ):
        return EvaluationResult((), ("NON_SEMANTIC_ROBOTS_STATE",))
    before_hash, after_hash = _semantic_hash(previous), _semantic_hash(primary)
    if before_hash is None or after_hash is None:
        return EvaluationResult((), ("MISSING_SEMANTIC_HASH",))
    if before_hash == after_hash:
        return EvaluationResult((), ("UNCHANGED_SEMANTIC_STATE",))

    before_broad = previous.summary.get("broad_blocked") is True
    after_broad = primary.summary.get("broad_blocked") is True
    if not before_broad and after_broad:
        if not _validation_agrees(primary, value.validation):
            return EvaluationResult((), ("AWAITING_OR_DISAGREEING_VALIDATION",))
        return EvaluationResult((_point_candidate("ROBOTS_BROAD_BLOCK_ADDED", value),), ())
    if before_broad and not after_broad:
        return EvaluationResult((_point_candidate("ROBOTS_BROAD_BLOCK_REMOVED", value),), ())
    return EvaluationResult((_point_candidate("ROBOTS_TXT_CHANGED", value),), ())


def _evaluate_ads(value: PublicConfigEvaluationInput) -> EvaluationResult:
    assert value.previous is not None
    previous, primary = value.previous, value.primary
    if primary.parse_status in ADS_CONDITION_CODES:
        if not _validation_agrees(primary, value.validation):
            return EvaluationResult((), ("AWAITING_OR_DISAGREEING_VALIDATION",))
        code = ADS_CONDITION_CODES[primary.parse_status]
        action: EventAction = (
            "SUPPORT_CONDITION"
            if previous.parse_status == primary.parse_status
            else "UPSERT_CONDITION"
        )
        return EvaluationResult((_ads_condition_candidate(code, action, value),), ())

    if primary.parse_status in HEALTHY_STATUSES:
        if previous.parse_status in ADS_CONDITION_CODES:
            if not _validation_agrees(primary, value.validation):
                return EvaluationResult((), ("AWAITING_OR_DISAGREEING_RECOVERY_VALIDATION",))
            candidates = tuple(
                _ads_recovery_candidate(code, value) for code in ADS_CONDITION_CODES.values()
            )
            return EvaluationResult(candidates, ())
        if previous.parse_status not in HEALTHY_STATUSES:
            return EvaluationResult((), ("NON_COMPARABLE_ADS_STATE",))
        before_hash, after_hash = _semantic_hash(previous), _semantic_hash(primary)
        if before_hash is None or after_hash is None:
            return EvaluationResult((), ("MISSING_SEMANTIC_HASH",))
        if before_hash != after_hash:
            return EvaluationResult((_point_candidate("ADS_TXT_CHANGED", value),), ())
        return EvaluationResult((), ("UNCHANGED_SEMANTIC_STATE",))

    return EvaluationResult((), ("NON_SEMANTIC_ADS_STATE",))


def _point_candidate(code: str, value: PublicConfigEvaluationInput) -> EventCandidate:
    assert value.previous is not None
    rule = RULES_BY_CODE[code]
    primary = value.primary
    summaries = {
        "ROBOTS_TXT_CHANGED": "robots.txt normalized rule set changed for the site",
        "ROBOTS_BROAD_BLOCK_ADDED": (
            "robots.txt added a confirmed broad crawl block for the site rule scope"
        ),
        "ROBOTS_BROAD_BLOCK_REMOVED": (
            "robots.txt removed a broad crawl block from the site rule scope"
        ),
        "ADS_TXT_CHANGED": "ads.txt normalized seller-record set changed for the site",
    }
    evidence = [
        _evidence(value.previous, "BEFORE"),
        _evidence(primary, "AFTER"),
    ]
    if value.validation is not None and code == "ROBOTS_BROAD_BLOCK_ADDED":
        evidence.append(_evidence(value.validation, "VALIDATION"))
    return EventCandidate(
        code=code,
        subject=_subject(primary),
        summary=summaries[code],
        before=_state_details(value.previous),
        after=_state_details(primary),
        confirmation=rule.confirmation,
        severity=rule.default_severity,
        scope=_scope(primary),
        occurred_after_at=value.previous.observed_at,
        occurred_before_at=primary.observed_at,
        detected_at=(value.validation or primary).observed_at,
        evidence=tuple(evidence),
    )


def _ads_condition_candidate(
    code: str, action: EventAction, value: PublicConfigEvaluationInput
) -> EventCandidate:
    assert value.previous is not None
    assert value.validation is not None
    rule = RULES_BY_CODE[code]
    state_label = {
        "ADS_TXT_MISSING": "missing response",
        "ADS_TXT_EMPTY_200": "HTTP 200 response with no seller records",
        "ADS_TXT_INVALID": "response with no valid seller records",
    }[code]
    primary_relation = "SUPPORTING" if action == "SUPPORT_CONDITION" else "TRIGGER_AFTER"
    evidence = [
        _evidence(value.primary, primary_relation),
        _evidence(value.validation, "VALIDATION"),
    ]
    if action == "UPSERT_CONDITION":
        evidence.insert(0, _evidence(value.previous, "TRIGGER_BEFORE"))
    return EventCandidate(
        code=code,
        subject=_subject(value.primary),
        summary=f"ads.txt confirmed {state_label} for the site record scope",
        before=_state_details(value.previous),
        after=_state_details(value.primary),
        confirmation=rule.confirmation,
        action=action,
        severity=rule.default_severity,
        scope=_scope(value.primary),
        occurred_after_at=value.previous.observed_at,
        occurred_before_at=value.primary.observed_at,
        detected_at=value.validation.observed_at,
        evidence=tuple(evidence),
    )


def _ads_recovery_candidate(code: str, value: PublicConfigEvaluationInput) -> EventCandidate:
    assert value.previous is not None
    assert value.validation is not None
    rule = RULES_BY_CODE[code]
    return EventCandidate(
        code=code,
        subject=_subject(value.primary),
        summary="ads.txt returned to a confirmed valid seller-record state for the site",
        before=_state_details(value.previous),
        after=_state_details(value.primary),
        confirmation=rule.confirmation,
        action="RESOLVE_CONDITION",
        severity=rule.default_severity,
        scope=_scope(value.primary),
        occurred_after_at=value.previous.observed_at,
        occurred_before_at=value.primary.observed_at,
        detected_at=value.validation.observed_at,
        evidence=(
            _evidence(value.primary, "RECOVERY"),
            _evidence(value.validation, "VALIDATION"),
        ),
    )


def _validation_agrees(
    primary: StoredPublicConfigSnapshot,
    validation: StoredPublicConfigSnapshot | None,
) -> bool:
    if validation is None or validation.parse_status != primary.parse_status:
        return False
    primary_hash, validation_hash = _semantic_hash(primary), _semantic_hash(validation)
    if primary_hash is not None or validation_hash is not None:
        return primary_hash == validation_hash
    return True


def _semantic_hash(snapshot: StoredPublicConfigSnapshot) -> str | None:
    value = snapshot.summary.get("semantic_hash")
    return value if isinstance(value, str) else None


def _state_details(snapshot: StoredPublicConfigSnapshot) -> dict[str, object]:
    details: dict[str, object] = {"parse_status": snapshot.parse_status}
    semantic_hash = _semantic_hash(snapshot)
    if semantic_hash is not None:
        details["semantic_hash"] = semantic_hash
    if snapshot.config_type == "ROBOTS_TXT":
        details["broad_blocked"] = snapshot.summary.get("broad_blocked") is True
        rule_count = snapshot.summary.get("rule_count")
        if isinstance(rule_count, int):
            details["rule_count"] = rule_count
    else:
        record_count = snapshot.summary.get("valid_record_count")
        if isinstance(record_count, int):
            details["valid_record_count"] = record_count
    return details


def _scope(snapshot: StoredPublicConfigSnapshot) -> dict[str, object]:
    return {"config_type": snapshot.config_type}


def _subject(snapshot: StoredPublicConfigSnapshot) -> str:
    return "robots.txt" if snapshot.config_type == "ROBOTS_TXT" else "ads.txt"


def _evidence(snapshot: StoredPublicConfigSnapshot, relation: str) -> EvidencePointer:
    return EvidencePointer(snapshot.id, relation, "PUBLIC_CONFIG_SNAPSHOT")
