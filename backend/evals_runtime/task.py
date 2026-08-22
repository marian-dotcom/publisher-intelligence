"""Inspect task wiring the foundations SUT to repository-owned gold cases."""

import json
from typing import Any

from inspect_ai import Task
from inspect_ai.dataset import Sample

from evals_runtime.scorers import foundations_exact_match
from evals_runtime.solver import foundations_solver

DEFAULT_CASES_PATH = "evals/foundations_cases_v0.yaml"


def load_cases(path: str = DEFAULT_CASES_PATH) -> list[dict[str, Any]]:
    import yaml

    with open(path) as handle:
        document = yaml.safe_load(handle)
    assert document["kind"] == "foundations_smoke_v0"
    return list(document["cases"])


def foundations_samples(cases_path: str = DEFAULT_CASES_PATH) -> list[Sample]:
    samples = []
    for case in load_cases(cases_path):
        engine_input = {
            "runs": case["input"]["runs"],
            "onset": case["input"].get("onset"),
            "candidate_run": case["input"]["candidate_run"],
            "fingerprints": case["input"]["fingerprints"],
            "resource_kind": case["input"]["resource_kind"],
            "used": case["input"]["used"],
        }
        samples.append(
            Sample(
                id=case["case_id"],
                input=json.dumps(engine_input),
                target=json.dumps(case["expected"]),
            )
        )
    return samples


def foundations_task(cases_path: str = DEFAULT_CASES_PATH) -> Task:
    return Task(
        dataset=foundations_samples(cases_path),
        solver=[foundations_solver()],
        scorer=foundations_exact_match(),
    )
