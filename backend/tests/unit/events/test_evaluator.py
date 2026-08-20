import uuid
from datetime import UTC, datetime, timedelta

from app.events.contracts import EvaluationInput
from app.events.evaluator import evaluate


def state(
    network: list[str], *, canonical: str | None = "https://example.com/a", truncated: bool = False
) -> dict[str, object]:
    return {
        "scripts": {"normalizer_version": "v1", "identities": [], "truncated": False},
        "network": {
            "normalizer_version": "v1",
            "dependencies": [{"stable_key": key} for key in network],
            "truncated": truncated,
        },
        "javascript_errors": {"normalizer_version": "v1", "errors": []},
        "seo": {"normalizer_version": "seo-e1-v1", "meta_robots": None, "canonical_url": canonical},
    }


def input_value(
    before: dict[str, object], after: dict[str, object], *, scope: str = "EXACT_MONITORED_URL"
) -> EvaluationInput:
    now = datetime(2026, 8, 20, tzinfo=UTC)
    ids = [uuid.uuid4() for _ in range(7)]
    return EvaluationInput(
        ids[0],
        ids[1],
        ids[2],
        ids[3],
        ids[4],
        ids[5],
        ids[6],
        now,
        now + timedelta(hours=6),
        "COMPLETE",
        "COMPLETE",
        scope,
        before,
        after,
        {"slots": []},
        {"slots": []},
    )


def test_evaluates_confirmed_point_changes() -> None:
    result = evaluate(
        input_value(state(["old"], canonical="/old"), state(["new"], canonical="/new"))
    )
    assert [item.code for item in result.candidates] == [
        "THIRD_PARTY_DEPENDENCY_ADDED",
        "THIRD_PARTY_DEPENDENCY_REMOVED",
        "CANONICAL_CHANGED",
    ]
    assert all(item.confirmation == "SINGLE_STRONG_OBSERVATION" for item in result.candidates)


def test_truncation_blocks_removal_and_template_fallback_blocks_all() -> None:
    truncated = evaluate(input_value(state(["old"]), state([], truncated=True)))
    assert truncated.candidates == ()
    assert "TRUNCATED_DEPENDENCY_ABSENCE" in truncated.skip_reasons
    fallback = evaluate(input_value(state([]), state(["new"]), scope="SAME_TEMPLATE_URL_ROTATION"))
    assert fallback.candidates == ()
    assert fallback.skip_reasons == ("NON_EXACT_URL_LINEAGE",)


def test_noisy_condition_is_candidate_but_not_confirmed() -> None:
    before = state([])
    after = state([])
    after["seo"] = {
        "normalizer_version": "seo-e1-v1",
        "meta_robots": "noindex",
        "canonical_url": "https://example.com/a",
    }
    result = evaluate(input_value(before, after))
    noindex = next(item for item in result.candidates if item.code == "NOINDEX_ADDED")
    assert noindex.confirmation == "REQUIRES_E2_CONFIRMATION"
