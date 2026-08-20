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
    assert all(rule.kind in {"POINT", "CONDITION"} for rule in RULES)
    assert all(rule.schema_version == 2 for rule in RULES)
    assert all(rule.rule_version in {"e1-v1", "e2-v1"} for rule in RULES)
    assert all(rule.domain_refs and rule.dedupe_strategy for rule in RULES)
    assert RULES_BY_CODE["JS_ERROR_STARTED"].confirmation == "TWO_CONSECUTIVE_CHECKPOINTS"
    assert RULES_BY_CODE["GPT_EXPECTED_SLOT_MISSING"].confirmation == "MULTI_URL_CORROBORATION"


def test_unknown_definition_is_rejected() -> None:
    with pytest.raises(KeyError):
        definition_id("CALLER_SUPPLIED_EVENT")
