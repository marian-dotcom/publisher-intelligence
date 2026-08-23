from typing import Any

from app.hypotheses.ranking import build_candidates, rank
from evals_runtime.adapter import build_ranking_inputs

DEFAULT_PATH = "evals/ranking_cases_v0.yaml"


def evaluate_ranking_cases(path: str = DEFAULT_PATH) -> tuple[bool, list[dict[str, Any]]]:
    document: dict[str, Any] = _load_yaml(path)
    assert document["kind"] == "ranking_smoke_v0"
    results = []
    ok = True
    for case in document["cases"]:
        inputs = build_ranking_inputs(case["input"])
        ranked = rank(build_candidates(**inputs))
        leading = next((item for item in ranked if item.status == "LEADING"), None)
        actual_leading = leading.family if leading else None
        expected_leading = (case["expected"] or {}).get("leading_family")
        weakened = sorted(item.family for item in ranked if item.status == "WEAKENED")
        expected_weakened = sorted(case["expected"].get("weakened_families", []))
        passed = expected_leading in (None, actual_leading) and weakened == expected_weakened
        ok = ok and passed
        results.append(
            {
                "case_id": case["case_id"],
                "passed": passed,
                "leading": actual_leading,
                "weakened": weakened,
            }
        )
    return ok, results


def _load_yaml(path: str) -> dict[str, Any]:
    import yaml

    document: dict[str, Any] = yaml.safe_load(handle) if (handle := open(path)) else {}
    return document
