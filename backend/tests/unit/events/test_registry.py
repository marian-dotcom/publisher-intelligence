import pytest

from app.events.registry import RULES, RULES_BY_CODE, definition_id


def test_registry_is_fixed_and_complete() -> None:
    assert len(RULES) == len(RULES_BY_CODE) == 6
    assert {rule.code for rule in RULES} == {
        "THIRD_PARTY_DEPENDENCY_ADDED",
        "THIRD_PARTY_DEPENDENCY_REMOVED",
        "JS_ERROR_STARTED",
        "NOINDEX_ADDED",
        "CANONICAL_CHANGED",
        "GPT_EXPECTED_SLOT_MISSING",
    }
    assert definition_id("CANONICAL_CHANGED") == definition_id("CANONICAL_CHANGED")


def test_unknown_definition_is_rejected() -> None:
    with pytest.raises(KeyError):
        definition_id("CALLER_SUPPLIED_EVENT")
