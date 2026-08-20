from app.events.contracts import EvaluationInput, EvaluationResult, EventCandidate
from app.events.registry import RULES_BY_CODE

VALID_STATUSES = {"COMPLETE", "PARTIAL"}


def evaluate(value: EvaluationInput) -> EvaluationResult:
    reason = _invalid_reason(value)
    if reason:
        return EvaluationResult((), (reason,))
    candidates: list[EventCandidate] = []
    skips: list[str] = []
    previous, current = value.previous_state, value.current_state
    for component in ("scripts", "network", "javascript_errors", "seo"):
        before = previous.get(component)
        after = current.get(component)
        if not isinstance(before, dict) or not isinstance(after, dict):
            skips.append(f"MISSING_{component.upper()}_STATE")
            continue
        if before.get("normalizer_version") != after.get("normalizer_version"):
            skips.append(f"INCOMPATIBLE_{component.upper()}_NORMALIZER")

    if skips:
        return EvaluationResult((), tuple(dict.fromkeys(skips)))

    _dependency_candidates(candidates, skips, previous.get("network"), current.get("network"))
    _js_candidates(candidates, previous.get("javascript_errors"), current.get("javascript_errors"))
    _seo_candidates(candidates, previous.get("seo"), current.get("seo"))
    _gpt_candidates(candidates, value.previous_gpt, value.current_gpt)
    return EvaluationResult(tuple(candidates), tuple(dict.fromkeys(skips)))


def _invalid_reason(value: EvaluationInput) -> str | None:
    if value.selection_scope != "EXACT_MONITORED_URL":
        return "NON_EXACT_URL_LINEAGE"
    if value.previous_status not in VALID_STATUSES or value.current_status not in VALID_STATUSES:
        return "INVALID_CHECKPOINT_STATUS"
    if value.current_observed_at <= value.previous_observed_at:
        return "UNORDERED_OBSERVATION_TIME"
    return None


def _items(state: object, key: str, identity: str) -> set[str]:
    if not isinstance(state, dict) or not isinstance(state.get(key), list):
        return set()
    return {
        str(item[identity])
        for item in state[key]
        if isinstance(item, dict) and isinstance(item.get(identity), str)
    }


def _candidate(code: str, subject: str, before: object, after: object) -> EventCandidate:
    rule = RULES_BY_CODE[code]
    action = (
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
        code, subject, f"{code}: {subject} {action}", before, after, rule.confirmation
    )


def _dependency_candidates(
    out: list[EventCandidate], skips: list[str], before: object, after: object
) -> None:
    old = _items(before, "dependencies", "stable_key")
    new = _items(after, "dependencies", "stable_key")
    for key in sorted(new - old):
        out.append(_candidate("THIRD_PARTY_DEPENDENCY_ADDED", key, False, True))
    truncated = (isinstance(before, dict) and before.get("truncated") is True) or (
        isinstance(after, dict) and after.get("truncated") is True
    )
    if truncated and old - new:
        skips.append("TRUNCATED_DEPENDENCY_ABSENCE")
    else:
        for key in sorted(old - new):
            out.append(_candidate("THIRD_PARTY_DEPENDENCY_REMOVED", key, True, False))


def _js_candidates(out: list[EventCandidate], before: object, after: object) -> None:
    for key in sorted(
        _items(after, "errors", "fingerprint") - _items(before, "errors", "fingerprint")
    ):
        out.append(_candidate("JS_ERROR_STARTED", key, False, True))


def _seo_candidates(out: list[EventCandidate], before: object, after: object) -> None:
    if not isinstance(before, dict) or not isinstance(after, dict):
        return
    old_robots = {part.strip() for part in str(before.get("meta_robots") or "").split(",")}
    new_robots = {part.strip() for part in str(after.get("meta_robots") or "").split(",")}
    if "noindex" in new_robots and "noindex" not in old_robots:
        out.append(
            _candidate("NOINDEX_ADDED", "rendered-page", sorted(old_robots), sorted(new_robots))
        )
    old = before.get("canonical_url")
    new = after.get("canonical_url")
    if old != new and (old is not None or new is not None):
        out.append(_candidate("CANONICAL_CHANGED", "rendered-page", old, new))


def _gpt_candidates(
    out: list[EventCandidate], before: dict[str, object], after: dict[str, object]
) -> None:
    def present_expected(value: dict[str, object]) -> set[str]:
        slots = value.get("slots")
        if not isinstance(slots, list):
            return set()
        return {
            str(slot["stable_key"])
            for slot in slots
            if isinstance(slot, dict)
            and slot.get("expected") is True
            and slot.get("present") is True
            and isinstance(slot.get("stable_key"), str)
        }

    def missing_expected(value: dict[str, object]) -> set[str]:
        slots = value.get("slots")
        if not isinstance(slots, list):
            return set()
        return {
            str(slot["stable_key"])
            for slot in slots
            if isinstance(slot, dict)
            and slot.get("expected") is True
            and slot.get("present") is False
            and isinstance(slot.get("stable_key"), str)
        }

    for key in sorted(present_expected(before) & missing_expected(after)):
        out.append(_candidate("GPT_EXPECTED_SLOT_MISSING", key, True, False))
