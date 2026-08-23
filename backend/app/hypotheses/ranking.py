"""Deterministic hypothesis candidate generation, scoring, and ranking.

Pure functions over plain dictionaries — no database, no inspect_ai, no LLM.
The same stored evidence always produces the same ranked output.

Load-bearing semantics:
- observation failures are MISSING context, never publisher-failure evidence;
- manual notes are human_reported CONTEXT with zero score weight;
- temporal correlation alone yields at most CONTENDER wording; nothing here
  asserts CAUSES.
"""

from dataclasses import dataclass
from typing import Any

SUPPORT_WEIGHT = 2
CONTRADICT_WEIGHT = 1


@dataclass(frozen=True, slots=True)
class RankedHypothesis:
    hypothesis_key: str
    family: str
    statement: str
    status: str
    confidence: str
    rank: int
    score: int
    supporting_count: int
    contradicting_count: int
    supporting: tuple[str, ...]
    contradicting: tuple[str, ...]
    missing: tuple[str, ...]
    human_context: tuple[str, ...]
    rationale: str


def build_candidates(
    *,
    families: tuple[str, ...],
    events: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    degraded_observations: list[dict[str, Any]],
    human_notes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Aggregate typed evidence into per-family candidates.

    events: observed positive/negative machine evidence with a "family" key and
        "supports" bool plus a stable "evidence_id";
    relations: explicitly typed CONTRADICTS/SUPPORTS edges between families
        (from_event family → to_event family);
    degraded_observations: unavailable/unreliable observations — recorded as
        missing-evidence context only;
    human_notes: operator/manual statements — zero weight, tagged human_reported.
    """
    candidates: dict[str, dict[str, Any]] = {}
    ordered_families: list[str] = []
    for family in (*families, *(item["family"] for item in events)):
        if family not in candidates:
            candidates[family] = {
                "hypothesis_key": f"{family}:degradation",
                "family": family,
                "supporting": [],
                "contradicting": [],
                "missing": [],
                "human_context": [],
            }
            ordered_families.append(family)

    for item in events:
        family = item["family"]
        bucket = (
            candidates[family]["supporting"]
            if item.get("supports")
            else candidates[family]["contradicting"]
        )
        label = f"machine_observed:{item['evidence_id']}"
        if label not in bucket:
            bucket.append(label)

    for relation in relations:
        target_family = relation["to_family"]
        source_family = relation["from_family"]
        if target_family not in candidates:
            continue
        kind = "supporting" if relation["relation_type"] == "SUPPORTS" else "contradicting"
        label = f"typed_relation:{source_family}->{target_family}:{relation['relation_type']}"
        bucket = candidates[target_family][kind]
        if label not in bucket:
            bucket.append(label)
        if (
            relation["relation_type"] == "CONTRADICTS"
            and source_family != target_family
            and source_family in candidates
        ):
            opposite = "contradicting" if kind == "supporting" else "supporting"
            mirror = f"typed_relation:{source_family}->{target_family}:CONTRADICTS"
            if mirror not in candidates[source_family][opposite]:
                candidates[source_family][opposite].append(mirror)

    for gap in degraded_observations:
        for family in candidates:
            label = f"observation_gap:{gap['description']}"
            if label not in candidates[family]["missing"]:
                candidates[family]["missing"].append(label)

    for note in human_notes:
        for family in candidates:
            label = f"human_reported:{note['note_id']}"
            if label not in candidates[family]["human_context"]:
                candidates[family]["human_context"].append(label)

    return [candidates[family] for family in ordered_families]


def score_candidate(candidate: dict[str, Any]) -> int:
    return (
        len(candidate["supporting"]) * SUPPORT_WEIGHT
        - len(candidate["contradicting"]) * CONTRADICT_WEIGHT
    )


def status_for(*, supports: int, contradicts: int, is_leading: bool) -> str:
    if supports == 0 and contradicts == 0:
        return "UNRESOLVED"
    if contradicts > supports:
        return "WEAKENED"
    if is_leading and supports > 0:
        return "LEADING"
    return "CONTENDER"


def confidence_for(score: int) -> str:
    if score >= 4:
        return "HIGH"
    if score >= 2:
        return "MEDIUM"
    return "LOW"


def rank(candidates: list[dict[str, Any]]) -> list[RankedHypothesis]:
    scored: list[tuple[int, str, dict[str, Any]]] = []
    for candidate in candidates:
        score = score_candidate(candidate)
        scored.append((score, candidate["hypothesis_key"], candidate))
    scored.sort(key=lambda item: (-item[0], item[1]))

    ranked: list[RankedHypothesis] = []
    leading_assigned = False
    for position, (score, key, candidate) in enumerate(scored, start=1):
        supports = len(candidate["supporting"])
        contradicts = len(candidate["contradicting"])
        is_leading = not leading_assigned and score > 0 and contradicts == 0
        if is_leading:
            leading_assigned = True
        status = status_for(
            supports=supports, contradicts=contradicts, is_leading=is_leading and position == 1
        )
        rationale = (
            f"rank {position}: {supports} supporting vs {contradicts} contradicting "
            f"typed evidence items (score {score}); "
            f"{len(candidate['missing'])} unavailable/degraded observations recorded as "
            f"missing context; {len(candidate['human_context'])} human_reported notes "
            f"(zero weight). Temporal correlation alone never implies causation."
        )
        ranked.append(
            RankedHypothesis(
                hypothesis_key=key,
                family=candidate["family"],
                statement=f"{candidate['family']} degradation explains the reported symptom",
                status=status,
                confidence=confidence_for(score),
                rank=position,
                score=score,
                supporting_count=supports,
                contradicting_count=contradicts,
                supporting=tuple(candidate["supporting"]),
                contradicting=tuple(candidate["contradicting"]),
                missing=tuple(candidate["missing"]),
                human_context=tuple(candidate["human_context"]),
                rationale=rationale,
            )
        )
    return ranked
