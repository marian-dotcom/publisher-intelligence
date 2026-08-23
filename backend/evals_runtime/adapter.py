"""Adapter boundary: pure foundations SUT over plain dicts.

No inspect_ai imports may appear in this module (or anywhere under app/).
The SUT delegates to the same decision logic the application uses so eval
results reflect real behavior.
"""

from typing import Any

from app.common.comparability import fingerprints_comparable
from app.incidents.contracts import DEFAULT_RESOURCE_LIMITS


def pick_localization_anchor(runs: list[dict[str, Any]], onset_iso: str | None) -> str | None:
    """Latest healthy scheduled run at/before onset; None when unavailable."""
    from datetime import datetime

    onset = datetime.fromisoformat(onset_iso) if onset_iso else None
    candidates = [
        run
        for run in runs
        if run.get("observation_kind") == "SCHEDULED"
        and run.get("status") == "COMPLETE"
        and run.get("completed_at") is not None
        and (onset is None or datetime.fromisoformat(str(run["completed_at"])) <= onset)
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda run: str(run["completed_at"]), reverse=True)
    return str(candidates[0]["run_id"])


def lkg_eligible(run: dict[str, Any], fingerprints: dict[str, str]) -> bool:
    """Eligibility = scheduled + healthy + fingerprint comparability (ADR-130)."""
    if run.get("observation_kind") != "SCHEDULED":
        return False
    if run.get("status") != "COMPLETE":
        return False
    return fingerprints_comparable(dict(run.get("fingerprints", {})), fingerprints)


def within_budget(resource_kind: str, used: int) -> bool:
    return used < DEFAULT_RESOURCE_LIMITS.get(resource_kind, 0)


def build_ranking_inputs(candidates: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in candidates.items()
        if key in {"families", "events", "relations", "degraded_observations", "human_notes"}
    }


def rank_candidates(candidates: dict[str, Any]) -> list[dict[str, Any]]:
    """Delegate deterministic ranking to the application core (EP-023)."""
    from app.hypotheses.ranking import build_candidates, rank

    inputs = {
        key: value
        for key, value in candidates.items()
        if key in {"families", "events", "relations", "degraded_observations", "human_notes"}
    }
    ranked = rank(build_candidates(**inputs))
    return [
        {
            "hypothesis_key": item.hypothesis_key,
            "status": item.status,
            "confidence": item.confidence,
            "rank": item.rank,
        }
        for item in ranked
    ]
