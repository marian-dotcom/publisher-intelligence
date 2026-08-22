"""Custom Inspect solver invoking the FoundationsEngine adapter.

No model is involved: the system under evaluation is deterministic code.
"""

import json

from inspect_ai.solver import Generate, Solver, TaskState, solver

from evals_runtime.adapter import lkg_eligible, pick_localization_anchor, within_budget


@solver
def foundations_solver() -> Solver:
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        payload = json.loads(state.user_prompt.text)
        state.store.set(
            "engine_output",
            {
                "anchor": pick_localization_anchor(payload["runs"], payload.get("onset")),
                "lkg_eligible": lkg_eligible(payload["candidate_run"], payload["fingerprints"]),
                "within_budget": within_budget(payload["resource_kind"], payload["used"]),
            },
        )
        return state

    return solve
