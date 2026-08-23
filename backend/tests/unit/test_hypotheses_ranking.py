from app.hypotheses.ranking import build_candidates, rank


def _events(*pairs: tuple[str, bool]) -> list[dict[str, object]]:
    return [
        {"family": family, "supports": supports, "evidence_id": f"ev-{index}"}
        for index, (family, supports) in enumerate(pairs)
    ]


def test_ranking_orders_by_score_and_explains() -> None:
    candidates = build_candidates(
        families=("GAM_ADSERVING", "SEARCH_DISCOVER"),
        events=_events(
            ("GAM_ADSERVING", True),
            ("GAM_ADSERVING", True),
            ("SEARCH_DISCOVER", False),
        ),
        relations=[],
        degraded_observations=[],
        human_notes=[],
    )
    ranked = rank(candidates)
    view = {item.hypothesis_key: item for item in ranked}
    gam = view["GAM_ADSERVING:degradation"]
    search = view["SEARCH_DISCOVER:degradation"]
    assert gam.status == "LEADING"
    assert search.status == "WEAKENED"
    assert "rank 1" in gam.rationale
    assert "typed evidence items" in gam.rationale


def test_contradictions_demote_to_weakened() -> None:
    candidates = build_candidates(
        families=("GAM_ADSERVING",),
        events=[],
        relations=[
            {
                "from_family": "GAM_ADSERVING",
                "to_family": "GAM_ADSERVING",
                "relation_type": "CONTRADICTS",
            }
        ],
        degraded_observations=[],
        human_notes=[],
    )
    ranked = rank(candidates)
    assert ranked[0].status == "WEAKENED"


def test_observation_gaps_are_neutral_context() -> None:
    candidates = build_candidates(
        families=("VIDEO",),
        events=[],
        relations=[],
        degraded_observations=[{"description": "run SITE_ERROR"}],
        human_notes=[{"note_id": "n1"}],
    )
    ranked = rank(candidates)
    assert ranked[0].status == "UNRESOLVED"
    item = ranked[0]
    assert item.missing == ("observation_gap:run SITE_ERROR",)
    assert item.human_context == ("human_reported:n1",)
    assert item.score == 0


def test_determinism_for_identical_inputs() -> None:
    from typing import Any

    kwargs: dict[str, Any] = {
        "families": ("A", "B"),
        "events": _events(("A", True), ("B", True)),
        "relations": [],
        "degraded_observations": [{"description": "gap"}],
        "human_notes": [],
    }
    first = [(item.hypothesis_key, item.rank) for item in rank(build_candidates(**kwargs))]
    second = [(item.hypothesis_key, item.rank) for item in rank(build_candidates(**kwargs))]
    assert first == second
