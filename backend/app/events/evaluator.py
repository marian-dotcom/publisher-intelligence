import uuid
from collections import defaultdict
from dataclasses import replace

from app.events.contracts import (
    EvaluationInput,
    EvaluationResult,
    EventAction,
    EventCandidate,
    EvidencePointer,
)
from app.events.lifecycle import severity_for
from app.events.registry import RULES_BY_CODE

VALID_STATUSES = {"COMPLETE", "PARTIAL"}


def evaluate(value: EvaluationInput) -> EvaluationResult:
    reason = _invalid_reason(value)
    if reason:
        return EvaluationResult((), (reason,))
    skips = list(_component_skip_reasons(value))
    if skips:
        return EvaluationResult((), tuple(skips))

    candidates: list[EventCandidate] = []
    previous, current = value.previous_state, value.current_state
    _dependency_candidates(
        candidates, skips, value, previous.get("network"), current.get("network")
    )
    _js_candidates(
        candidates,
        value,
        previous.get("javascript_errors"),
        current.get("javascript_errors"),
    )
    _seo_candidates(candidates, value, previous.get("seo"), current.get("seo"))
    _gpt_pending_candidates(candidates, value)
    return EvaluationResult(tuple(candidates), tuple(dict.fromkeys(skips)))


def evaluate_window(values: tuple[EvaluationInput, ...]) -> EvaluationResult:
    if not values:
        return EvaluationResult((), ("EMPTY_CHECKPOINT_WINDOW",))
    if any(value.checkpoint_window_status != "COMPLETE" for value in values):
        return EvaluationResult((), ("INCOMPLETE_CHECKPOINT_WINDOW",))

    valid: list[EvaluationInput] = []
    skips: list[str] = []
    for value in values:
        reason = _invalid_reason(value)
        component_skips = _component_skip_reasons(value)
        if reason or component_skips:
            if reason:
                skips.append(reason)
            skips.extend(component_skips)
            continue
        valid.append(value)
    if not valid:
        return EvaluationResult((), tuple(dict.fromkeys(skips or ["NO_VALID_WINDOW_RUNS"])))

    candidates: list[EventCandidate] = []
    _noindex_window_candidates(candidates, valid)
    _gpt_window_candidates(candidates, valid)
    return EvaluationResult(tuple(candidates), tuple(dict.fromkeys(skips)))


def _invalid_reason(value: EvaluationInput) -> str | None:
    if value.selection_scope != "EXACT_MONITORED_URL":
        return "NON_EXACT_URL_LINEAGE"
    if value.previous_status not in VALID_STATUSES or value.current_status not in VALID_STATUSES:
        return "INVALID_CHECKPOINT_STATUS"
    if value.current_observed_at <= value.previous_observed_at:
        return "UNORDERED_OBSERVATION_TIME"
    return None


def _component_skip_reasons(value: EvaluationInput) -> tuple[str, ...]:
    skips: list[str] = []
    for component in ("scripts", "network", "javascript_errors", "seo"):
        before = value.previous_state.get(component)
        after = value.current_state.get(component)
        if not isinstance(before, dict) or not isinstance(after, dict):
            skips.append(f"MISSING_{component.upper()}_STATE")
            continue
        if before.get("normalizer_version") != after.get("normalizer_version"):
            skips.append(f"INCOMPATIBLE_{component.upper()}_NORMALIZER")
    return tuple(dict.fromkeys(skips))


def _items(state: object, key: str, identity: str) -> set[str]:
    if not isinstance(state, dict) or not isinstance(state.get(key), list):
        return set()
    return {
        str(item[identity])
        for item in state[key]
        if isinstance(item, dict) and isinstance(item.get(identity), str)
    }


def _scope(value: EvaluationInput, *, include_url: bool = True) -> dict[str, object]:
    scope: dict[str, object] = {
        "scenario_id": str(value.scenario_id),
        "template_id": str(value.template_id),
    }
    if include_url:
        scope["monitored_url_id"] = str(value.monitored_url_id)
    return scope


def _candidate(
    code: str,
    subject: str,
    before: object,
    after: object,
    value: EvaluationInput,
    *,
    action: EventAction = "RECORD",
) -> EventCandidate:
    rule = RULES_BY_CODE[code]
    verb = (
        "added"
        if code.endswith("ADDED")
        else "removed"
        if code.endswith("REMOVED")
        else "changed"
        if code.endswith("CHANGED")
        else "started"
        if code.endswith("STARTED")
        else "missing"
    )
    return EventCandidate(
        code=code,
        subject=subject,
        summary=f"{code}: {subject} {verb}",
        before=before,
        after=after,
        confirmation=rule.confirmation,
        action=action,
        severity=rule.default_severity,
        scope=_scope(value),
        occurred_after_at=value.previous_observed_at,
        occurred_before_at=value.current_observed_at,
        detected_at=value.current_observed_at,
        evidence=(
            EvidencePointer(value.previous_checkpoint_run_id, "BEFORE"),
            EvidencePointer(value.current_checkpoint_run_id, "AFTER"),
        ),
    )


def _dependency_candidates(
    out: list[EventCandidate],
    skips: list[str],
    value: EvaluationInput,
    before: object,
    after: object,
) -> None:
    old = _items(before, "dependencies", "stable_key")
    new = _items(after, "dependencies", "stable_key")
    for key in sorted(new - old):
        out.append(_candidate("THIRD_PARTY_DEPENDENCY_ADDED", key, False, True, value))
    truncated = (isinstance(before, dict) and before.get("truncated") is True) or (
        isinstance(after, dict) and after.get("truncated") is True
    )
    if truncated and old - new:
        skips.append("TRUNCATED_DEPENDENCY_ABSENCE")
    else:
        for key in sorted(old - new):
            out.append(_candidate("THIRD_PARTY_DEPENDENCY_REMOVED", key, True, False, value))


def _js_candidates(
    out: list[EventCandidate], value: EvaluationInput, before: object, after: object
) -> None:
    previous = _items(before, "errors", "fingerprint")
    current = _items(after, "errors", "fingerprint")
    prior_state = value.prior_state.get("javascript_errors")
    prior = _items(prior_state, "errors", "fingerprint")
    prior_is_comparable = (
        value.prior_checkpoint_run_id is not None
        and value.prior_observed_at is not None
        and value.prior_status in VALID_STATUSES
        and value.prior_observed_at < value.previous_observed_at
        and isinstance(prior_state, dict)
        and isinstance(before, dict)
        and prior_state.get("normalizer_version") == before.get("normalizer_version")
    )

    for fingerprint in sorted(current - previous):
        pending = _candidate("JS_ERROR_STARTED", fingerprint, False, True, value, action="PENDING")
        out.append(pending)

    for fingerprint in sorted(current & previous):
        scope = _scope(value)
        if prior_is_comparable and fingerprint not in prior:
            assert value.prior_checkpoint_run_id is not None
            assert value.prior_observed_at is not None
            out.append(
                EventCandidate(
                    code="JS_ERROR_STARTED",
                    subject=fingerprint,
                    summary=f"JS_ERROR_STARTED: {fingerprint} persisted",
                    before=False,
                    after=True,
                    confirmation="TWO_CONSECUTIVE_CHECKPOINTS",
                    action="UPSERT_CONDITION",
                    severity=RULES_BY_CODE["JS_ERROR_STARTED"].default_severity,
                    scope=scope,
                    occurred_after_at=value.prior_observed_at,
                    occurred_before_at=value.previous_observed_at,
                    detected_at=value.current_observed_at,
                    evidence=(
                        EvidencePointer(value.prior_checkpoint_run_id, "TRIGGER_BEFORE"),
                        EvidencePointer(value.previous_checkpoint_run_id, "TRIGGER_AFTER"),
                        EvidencePointer(value.current_checkpoint_run_id, "SUPPORTING"),
                    ),
                )
            )
        else:
            out.append(
                EventCandidate(
                    code="JS_ERROR_STARTED",
                    subject=fingerprint,
                    summary=f"JS_ERROR_STARTED: {fingerprint} still present",
                    before=True,
                    after=True,
                    confirmation="TWO_CONSECUTIVE_CHECKPOINTS",
                    action="SUPPORT_CONDITION",
                    severity=RULES_BY_CODE["JS_ERROR_STARTED"].default_severity,
                    scope=scope,
                    occurred_after_at=value.previous_observed_at,
                    occurred_before_at=value.current_observed_at,
                    detected_at=value.current_observed_at,
                    evidence=(EvidencePointer(value.current_checkpoint_run_id, "SUPPORTING"),),
                )
            )

    for fingerprint in sorted(previous - current):
        out.append(
            EventCandidate(
                code="JS_ERROR_STARTED",
                subject=fingerprint,
                summary=f"JS_ERROR_STARTED: {fingerprint} no longer observed",
                before=True,
                after=False,
                confirmation="TWO_CONSECUTIVE_CHECKPOINTS",
                action="RESOLVE_CONDITION",
                severity=RULES_BY_CODE["JS_ERROR_STARTED"].default_severity,
                scope=_scope(value),
                occurred_after_at=value.previous_observed_at,
                occurred_before_at=value.current_observed_at,
                detected_at=value.current_observed_at,
                evidence=(EvidencePointer(value.current_checkpoint_run_id, "RECOVERY"),),
            )
        )


def _seo_candidates(
    out: list[EventCandidate], value: EvaluationInput, before: object, after: object
) -> None:
    if not isinstance(before, dict) or not isinstance(after, dict):
        return
    old_robots = _robots(before)
    new_robots = _robots(after)
    if "noindex" in new_robots and "noindex" not in old_robots:
        out.append(
            _candidate(
                "NOINDEX_ADDED",
                "rendered-page",
                old_robots,
                new_robots,
                value,
                action="PENDING",
            )
        )
    old = before.get("canonical_url")
    new = after.get("canonical_url")
    if old != new and (old is not None or new is not None):
        out.append(_candidate("CANONICAL_CHANGED", "rendered-page", old, new, value))


def _gpt_pending_candidates(out: list[EventCandidate], value: EvaluationInput) -> None:
    previous = _gpt_slots(value.previous_gpt)
    current = _gpt_slots(value.current_gpt)
    for key in sorted(
        subject
        for subject, present in current.items()
        if present is False and previous.get(subject) is True
    ):
        out.append(
            _candidate("GPT_EXPECTED_SLOT_MISSING", key, True, False, value, action="PENDING")
        )


def _robots(state: dict[str, object]) -> list[str]:
    return sorted(
        part.strip().lower()
        for part in str(state.get("meta_robots") or "").split(",")
        if part.strip()
    )


def _gpt_slots(state: dict[str, object]) -> dict[str, bool]:
    slots = state.get("slots")
    if not isinstance(slots, list):
        return {}
    return {
        str(slot["stable_key"]): bool(slot["present"])
        for slot in slots
        if isinstance(slot, dict)
        and slot.get("expected") is True
        and isinstance(slot.get("present"), bool)
        and isinstance(slot.get("stable_key"), str)
    }


def _noindex_window_candidates(out: list[EventCandidate], values: list[EvaluationInput]) -> None:
    grouped: dict[tuple[uuid.UUID, uuid.UUID], list[EvaluationInput]] = defaultdict(list)
    valid_counts: dict[tuple[uuid.UUID, uuid.UUID], int] = defaultdict(int)
    for value in values:
        group_key = (value.template_id, value.scenario_id)
        valid_counts[group_key] += 1
        before = value.previous_state.get("seo")
        after = value.current_state.get("seo")
        if (
            isinstance(before, dict)
            and isinstance(after, dict)
            and "noindex" not in _robots(before)
            and "noindex" in _robots(after)
        ):
            grouped[group_key].append(value)

    rule = RULES_BY_CODE["NOINDEX_ADDED"]
    for group_key, affected in grouped.items():
        valid_count = valid_counts[group_key]
        if len(affected) >= rule.min_affected_urls and valid_count >= rule.min_valid_urls:
            first = affected[0]
            out.append(
                EventCandidate(
                    code=rule.code,
                    subject="rendered-template",
                    summary=f"NOINDEX_ADDED: {len(affected)} representative URLs affected",
                    before=False,
                    after=True,
                    confirmation=rule.confirmation,
                    action="RECORD",
                    severity=severity_for(
                        rule, affected_urls=len(affected), valid_urls=valid_count
                    ),
                    scope=_scope(first, include_url=False),
                    occurred_after_at=min(item.previous_observed_at for item in affected),
                    occurred_before_at=max(item.current_observed_at for item in affected),
                    detected_at=max(item.current_observed_at for item in affected),
                    evidence=tuple(
                        pointer
                        for item in affected
                        for pointer in (
                            EvidencePointer(item.previous_checkpoint_run_id, "BEFORE"),
                            EvidencePointer(item.current_checkpoint_run_id, "AFTER"),
                        )
                    ),
                    affected_url_count=len(affected),
                    valid_url_count=valid_count,
                )
            )
        else:
            for item in affected:
                candidate = _candidate(
                    rule.code,
                    "rendered-page",
                    False,
                    True,
                    item,
                    action="RECORD",
                )
                out.append(
                    replace(candidate, severity=severity_for(rule, affected_urls=1, valid_urls=1))
                )


def _gpt_window_candidates(out: list[EventCandidate], values: list[EvaluationInput]) -> None:
    grouped: dict[tuple[object, object, str], list[tuple[EvaluationInput, bool, bool | None]]] = (
        defaultdict(list)
    )
    for value in values:
        previous = _gpt_slots(value.previous_gpt)
        current = _gpt_slots(value.current_gpt)
        for subject, present in current.items():
            grouped[(value.template_id, value.scenario_id, subject)].append(
                (value, present, previous.get(subject))
            )

    rule = RULES_BY_CODE["GPT_EXPECTED_SLOT_MISSING"]
    for (_template_id, _scenario_id, subject), observations in grouped.items():
        valid_count = len({item.monitored_url_id for item, _, _ in observations})
        affected = [entry for entry in observations if entry[1] is False]
        healthy = [entry for entry in observations if entry[1] is True]
        transitions = [entry for entry in affected if entry[2] is True]
        first = observations[0][0]
        scope = _scope(first, include_url=False)

        if len(affected) >= rule.min_affected_urls and valid_count >= rule.min_valid_urls:
            action: EventAction = (
                "UPSERT_CONDITION"
                if len(transitions) >= rule.min_affected_urls
                else "SUPPORT_CONDITION"
            )
            trigger_runs = transitions if action == "UPSERT_CONDITION" else affected
            out.append(
                EventCandidate(
                    code=rule.code,
                    subject=subject,
                    summary=(
                        f"GPT_EXPECTED_SLOT_MISSING: {len(affected)} representative URLs affected"
                    ),
                    before=True,
                    after=False,
                    confirmation=rule.confirmation,
                    action=action,
                    severity=severity_for(
                        rule, affected_urls=len(affected), valid_urls=valid_count
                    ),
                    scope=scope,
                    occurred_after_at=min(entry[0].previous_observed_at for entry in trigger_runs),
                    occurred_before_at=max(entry[0].current_observed_at for entry in trigger_runs),
                    detected_at=max(entry[0].current_observed_at for entry in affected),
                    evidence=tuple(
                        pointer
                        for value, _present, previous_present in affected
                        for pointer in (
                            (
                                EvidencePointer(value.previous_checkpoint_run_id, "TRIGGER_BEFORE")
                                if action == "UPSERT_CONDITION" and previous_present is True
                                else None
                            ),
                            EvidencePointer(
                                value.current_checkpoint_run_id,
                                "TRIGGER_AFTER" if action == "UPSERT_CONDITION" else "SUPPORTING",
                            ),
                        )
                        if pointer is not None
                    ),
                    affected_url_count=len(affected),
                    valid_url_count=valid_count,
                )
            )
        elif (
            not affected
            and len(healthy) >= rule.min_valid_urls
            and valid_count >= rule.min_valid_urls
        ):
            out.append(
                EventCandidate(
                    code=rule.code,
                    subject=subject,
                    summary=(
                        f"GPT_EXPECTED_SLOT_MISSING: {len(healthy)} representative URLs recovered"
                    ),
                    before=False,
                    after=True,
                    confirmation=rule.confirmation,
                    action="RESOLVE_CONDITION",
                    severity=rule.default_severity,
                    scope=scope,
                    occurred_after_at=min(entry[0].previous_observed_at for entry in healthy),
                    occurred_before_at=max(entry[0].current_observed_at for entry in healthy),
                    detected_at=max(entry[0].current_observed_at for entry in healthy),
                    evidence=tuple(
                        EvidencePointer(entry[0].current_checkpoint_run_id, "RECOVERY")
                        for entry in healthy
                    ),
                    affected_url_count=0,
                    valid_url_count=valid_count,
                )
            )
