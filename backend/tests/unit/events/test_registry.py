import uuid

import pytest

from app.events.contracts import EvidencePointer
from app.events.registry import RULES, RULES_BY_CODE, definition_id


def test_registry_is_fixed_and_complete() -> None:
    assert len(RULES) == len(RULES_BY_CODE) == 13
    assert {rule.code for rule in RULES} == {
        "THIRD_PARTY_DEPENDENCY_ADDED",
        "THIRD_PARTY_DEPENDENCY_REMOVED",
        "JS_ERROR_STARTED",
        "NOINDEX_ADDED",
        "CANONICAL_CHANGED",
        "GPT_EXPECTED_SLOT_MISSING",
        "ROBOTS_TXT_CHANGED",
        "ROBOTS_BROAD_BLOCK_ADDED",
        "ROBOTS_BROAD_BLOCK_REMOVED",
        "ADS_TXT_CHANGED",
        "ADS_TXT_MISSING",
        "ADS_TXT_EMPTY_200",
        "ADS_TXT_INVALID",
    }
    assert definition_id("CANONICAL_CHANGED") == definition_id("CANONICAL_CHANGED")
    assert all(rule.kind in {"POINT", "CONDITION"} for rule in RULES)
    assert all(rule.schema_version == 2 for rule in RULES)
    assert all(rule.rule_version in {"e1-v1", "e2-v1", "e3-v1"} for rule in RULES)
    assert all(rule.domain_refs and rule.dedupe_strategy for rule in RULES)
    assert RULES_BY_CODE["JS_ERROR_STARTED"].confirmation == "TWO_CONSECUTIVE_CHECKPOINTS"
    assert RULES_BY_CODE["GPT_EXPECTED_SLOT_MISSING"].confirmation == "MULTI_URL_CORROBORATION"
    assert RULES_BY_CODE["ROBOTS_BROAD_BLOCK_ADDED"].confirmation == "IMMEDIATE_SECOND_CHECK"


def test_unknown_definition_is_rejected() -> None:
    with pytest.raises(KeyError):
        definition_id("CALLER_SUPPLIED_EVENT")


def test_evidence_pointer_preserves_browser_constructor_and_exposes_typed_source() -> None:
    source_id = uuid.uuid4()
    browser = EvidencePointer(checkpoint_run_id=source_id, relation="AFTER")
    public = EvidencePointer(source_id, "VALIDATION", "PUBLIC_CONFIG_SNAPSHOT")

    assert browser.source_id == browser.checkpoint_run_id == source_id
    assert browser.evidence_kind == "CHECKPOINT_RUN"
    assert public.source_id == source_id
    assert public.evidence_kind == "PUBLIC_CONFIG_SNAPSHOT"
