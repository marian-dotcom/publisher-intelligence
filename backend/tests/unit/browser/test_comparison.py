from copy import deepcopy

from app.browser.comparison import compare_normalized_state


def _state() -> dict[str, object]:
    return {
        "dom": {"normalizer_version": "dom-v1", "sha256": "dom-a"},
        "scripts": {
            "normalizer_version": "dependency-v1",
            "identities": [{"stable_key": "cdn.example|/app.js|script"}],
        },
        "network": {
            "normalizer_version": "dependency-v1",
            "dependencies": [{"stable_key": "api.example|/data|xhr"}],
        },
        "javascript_errors": {
            "normalizer_version": "error-v1",
            "errors": [],
        },
    }


def test_identical_state_has_empty_explainable_diff() -> None:
    state = _state()
    result = compare_normalized_state(state, {"normalized_state": deepcopy(state)})

    assert result == {
        "status": "COMPARABLE",
        "reason": None,
        "change_count": 0,
        "changes": [],
        "truncated": False,
    }


def test_comparison_reports_structural_and_presence_changes() -> None:
    previous = _state()
    current = deepcopy(previous)
    current["dom"]["sha256"] = "dom-b"  # type: ignore[index]
    current["scripts"]["identities"] = [  # type: ignore[index]
        {"stable_key": "cdn.example|/replacement.js|script"}
    ]

    result = compare_normalized_state(current, {"normalized_state": previous})

    assert result["status"] == "COMPARABLE"
    assert result["change_count"] == 3
    assert {item["kind"] for item in result["changes"]} == {
        "STRUCTURAL_CHANGE",
        "PRESENCE_ADDED",
        "PRESENCE_REMOVED",
    }


def test_incompatible_normalizer_is_not_comparable() -> None:
    current = _state()
    previous = _state()
    previous["dom"]["normalizer_version"] = "dom-v0"  # type: ignore[index]

    result = compare_normalized_state(current, {"normalized_state": previous})

    assert result["status"] == "NOT_COMPARABLE"
    assert result["reason"] == "INCOMPATIBLE_DOM_NORMALIZER"
    assert result["changes"] == []


def test_network_failure_state_change_is_explainable() -> None:
    previous = _state()
    current = deepcopy(previous)
    previous_dependency = previous["network"]["dependencies"][0]  # type: ignore[index]
    current_dependency = current["network"]["dependencies"][0]  # type: ignore[index]
    previous_dependency.update({"failure_count": 0, "status_4xx": 0, "status_5xx": 0})
    current_dependency.update({"failure_count": 0, "status_4xx": 0, "status_5xx": 1})

    result = compare_normalized_state(current, {"normalized_state": previous})

    assert result["change_count"] == 1
    assert result["changes"][0]["kind"] == "STATUS_CHANGE"
