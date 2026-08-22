"""Local runner: python -m evals_runtime [--cases PATH]."""

import sys

from evals_runtime.task import DEFAULT_CASES_PATH


def main(argv: list[str]) -> int:
    cases_path = DEFAULT_CASES_PATH
    if "--cases" in argv:
        cases_path = argv[argv.index("--cases") + 1]
    from inspect_ai import eval as inspect_eval

    from evals_runtime.task import foundations_task

    logs = inspect_eval(foundations_task(cases_path), model="mockllm/it", display="none")
    ok = True
    for log in logs:
        for sample in log.samples or []:
            score_values = [
                getattr(score, "value", None) for score in (sample.scores or {}).values()
            ]
            if not any(value in (1, 1.0, "1", "1.0", "C", "PASS") for value in score_values):
                ok = False
    print("FOUNDATIONS EVAL:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
