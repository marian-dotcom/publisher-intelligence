import uuid

import pytest

from app.events.lifecycle import condition_key, higher_severity, normalized_scope, severity_for
from app.events.registry import RULES_BY_CODE


def test_condition_key_is_stable_and_scope_order_independent() -> None:
    tenant_id, site_id = uuid.uuid4(), uuid.uuid4()
    first = condition_key(
        tenant_id=tenant_id,
        site_id=site_id,
        event_code="JS_ERROR_STARTED",
        subject="fingerprint",
        scope={"scenario_id": "2", "template_id": "1", "unused": None},
    )
    second = condition_key(
        tenant_id=tenant_id,
        site_id=site_id,
        event_code="JS_ERROR_STARTED",
        subject="fingerprint",
        scope={"template_id": "1", "scenario_id": "2"},
    )
    assert first == second
    assert len(first) == 64
    assert normalized_scope({"b": 2, "a": 1, "none": None}) == {"a": 1, "b": 2}


def test_condition_key_separates_tenant_subject_and_scope() -> None:
    tenant_id, site_id = uuid.uuid4(), uuid.uuid4()
    values = {
        condition_key(
            tenant_id=tenant_id,
            site_id=site_id,
            event_code="JS_ERROR_STARTED",
            subject=subject,
            scope={"template_id": scope},
        )
        for subject, scope in (("a", "1"), ("a", "2"), ("b", "1"))
    }
    assert len(values) == 3


def test_severity_is_rule_owned_and_monotonic() -> None:
    gpt = RULES_BY_CODE["GPT_EXPECTED_SLOT_MISSING"]
    noindex = RULES_BY_CODE["NOINDEX_ADDED"]
    assert severity_for(gpt, affected_urls=2, valid_urls=3) == "HIGH"
    assert severity_for(gpt, affected_urls=3, valid_urls=3) == "CRITICAL"
    assert severity_for(noindex, affected_urls=1, valid_urls=1) == "MEDIUM"
    assert severity_for(noindex, affected_urls=2, valid_urls=2) == "CRITICAL"
    assert higher_severity("HIGH", "MEDIUM") == "HIGH"
    assert higher_severity("MEDIUM", "CRITICAL") == "CRITICAL"


def test_invalid_counts_fail_closed() -> None:
    with pytest.raises(ValueError):
        severity_for(RULES_BY_CODE["GPT_EXPECTED_SLOT_MISSING"], affected_urls=2, valid_urls=1)
