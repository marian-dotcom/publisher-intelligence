"""Deterministic scorers — repository-owned gold, no model grading."""

from inspect_ai.scorer import Score, Scorer, Target, accuracy, scorer
from inspect_ai.solver import TaskState


@scorer(metrics=[accuracy()])
def foundations_exact_match() -> Scorer:
    async def score(state: TaskState, target: Target) -> Score:
        import json

        expected = json.loads(target.text)
        actual = state.store.get("engine_output")
        passed = actual == expected
        return Score(
            value=1.0 if passed else 0.0,
            answer=str(actual),
            explanation=f"expected={expected} actual={actual}",
        )

    return score
