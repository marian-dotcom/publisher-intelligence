import uuid
from datetime import UTC, datetime, timedelta

from app.events.contracts import EvaluationInput
from app.events.evaluator import evaluate, evaluate_window


def state(
    network: list[str],
    *,
    canonical: str | None = "https://example.com/a",
    truncated: bool = False,
    errors: tuple[str, ...] = (),
    noindex: bool = False,
) -> dict[str, object]:
    return {
        "scripts": {"normalizer_version": "v1", "identities": [], "truncated": False},
        "network": {
            "normalizer_version": "v1",
            "dependencies": [{"stable_key": key} for key in network],
            "truncated": truncated,
        },
        "javascript_errors": {
            "normalizer_version": "v1",
            "errors": [{"fingerprint": item} for item in errors],
        },
        "seo": {
            "normalizer_version": "seo-e1-v1",
            "meta_robots": "noindex" if noindex else None,
            "canonical_url": canonical,
        },
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


def test_noindex_transition_waits_for_complete_window_evaluation() -> None:
    before = state([])
    after = state([])
    after["seo"] = {
        "normalizer_version": "seo-e1-v1",
        "meta_robots": "noindex",
        "canonical_url": "https://example.com/a",
    }
    result = evaluate(input_value(before, after))
    noindex = next(item for item in result.candidates if item.code == "NOINDEX_ADDED")
    assert noindex.confirmation == "SINGLE_STRONG_OBSERVATION"
    assert noindex.action == "PENDING"


def test_js_requires_two_consecutive_checkpoints_and_preserves_first_window() -> None:
    value = input_value(state([], errors=("error",)), state([], errors=("error",)))
    value = EvaluationInput(
        **{
            field: getattr(value, field)
            for field in value.__dataclass_fields__
            if field
            not in {"prior_checkpoint_run_id", "prior_observed_at", "prior_status", "prior_state"}
        },
        prior_checkpoint_run_id=uuid.uuid4(),
        prior_observed_at=value.previous_observed_at - timedelta(hours=6),
        prior_status="COMPLETE",
        prior_state=state([]),
    )
    candidate = next(item for item in evaluate(value).candidates if item.code == "JS_ERROR_STARTED")
    assert candidate.action == "UPSERT_CONDITION"
    assert candidate.occurred_after_at == value.prior_observed_at
    assert candidate.occurred_before_at == value.previous_observed_at
    assert candidate.detected_at == value.current_observed_at


def test_incompatible_prior_observer_cannot_create_js_condition() -> None:
    value = input_value(state([], errors=("error",)), state([], errors=("error",)))
    incompatible_prior = state([])
    incompatible_prior["javascript_errors"] = {
        "normalizer_version": "legacy",
        "errors": [],
    }
    value = EvaluationInput(
        **{
            field: getattr(value, field)
            for field in value.__dataclass_fields__
            if field
            not in {
                "prior_checkpoint_run_id",
                "prior_observed_at",
                "prior_status",
                "prior_state",
            }
        },
        prior_checkpoint_run_id=uuid.uuid4(),
        prior_observed_at=value.previous_observed_at - timedelta(hours=6),
        prior_status="COMPLETE",
        prior_state=incompatible_prior,
    )
    candidate = next(item for item in evaluate(value).candidates if item.code == "JS_ERROR_STARTED")
    assert candidate.action == "SUPPORT_CONDITION"


def test_window_aggregates_expected_slot_and_noindex_by_template_scenario() -> None:
    first = input_value(state([]), state([], noindex=True))
    second = input_value(state([]), state([], noindex=True))
    common_template, common_scenario, window_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    def window_value(value: EvaluationInput) -> EvaluationInput:
        return EvaluationInput(
            **{
                field: getattr(value, field)
                for field in value.__dataclass_fields__
                if field
                not in {
                    "template_id",
                    "scenario_id",
                    "checkpoint_window_id",
                    "checkpoint_window_status",
                    "previous_gpt",
                    "current_gpt",
                }
            },
            template_id=common_template,
            scenario_id=common_scenario,
            checkpoint_window_id=window_id,
            checkpoint_window_status="COMPLETE",
            previous_gpt={"slots": [{"stable_key": "slot", "expected": True, "present": True}]},
            current_gpt={"slots": [{"stable_key": "slot", "expected": True, "present": False}]},
        )

    result = evaluate_window((window_value(first), window_value(second)))
    by_code = {item.code: item for item in result.candidates}
    assert by_code["NOINDEX_ADDED"].affected_url_count == 2
    assert by_code["NOINDEX_ADDED"].severity == "CRITICAL"
    assert by_code["GPT_EXPECTED_SLOT_MISSING"].action == "UPSERT_CONDITION"
    assert by_code["GPT_EXPECTED_SLOT_MISSING"].valid_url_count == 2


def test_one_healthy_gpt_url_cannot_resolve_aggregate_condition() -> None:
    first = input_value(state([]), state([]))
    second = input_value(state([]), state([]))
    common_template, common_scenario, window_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    def window_value(
        value: EvaluationInput, *, previous_present: bool, current_present: bool
    ) -> EvaluationInput:
        return EvaluationInput(
            **{
                field: getattr(value, field)
                for field in value.__dataclass_fields__
                if field
                not in {
                    "template_id",
                    "scenario_id",
                    "checkpoint_window_id",
                    "checkpoint_window_status",
                    "previous_gpt",
                    "current_gpt",
                }
            },
            template_id=common_template,
            scenario_id=common_scenario,
            checkpoint_window_id=window_id,
            checkpoint_window_status="COMPLETE",
            previous_gpt={
                "slots": [
                    {
                        "stable_key": "slot",
                        "expected": True,
                        "present": previous_present,
                    }
                ]
            },
            current_gpt={
                "slots": [
                    {
                        "stable_key": "slot",
                        "expected": True,
                        "present": current_present,
                    }
                ]
            },
        )

    result = evaluate_window(
        (
            window_value(first, previous_present=False, current_present=True),
            window_value(second, previous_present=False, current_present=False),
        )
    )
    assert not any(
        item.code == "GPT_EXPECTED_SLOT_MISSING" and item.action == "RESOLVE_CONDITION"
        for item in result.candidates
    )
