import uuid

from app.events.contracts import EventRule

EVENT_RULE_BUNDLE_VERSION = "e1-v1"
EVENT_DEFINITION_NAMESPACE = uuid.UUID("61c5d280-7ae7-4c87-a722-649077277f42")

RULES = (
    EventRule(
        "THIRD_PARTY_DEPENDENCY_ADDED",
        "DEPENDENCY",
        "A third-party dependency appeared.",
        "LOW",
        "SINGLE_STRONG_OBSERVATION",
        ("CHECKPOINT_RUN", "ENTITY_OBSERVATION"),
    ),
    EventRule(
        "THIRD_PARTY_DEPENDENCY_REMOVED",
        "DEPENDENCY",
        "A third-party dependency disappeared.",
        "MEDIUM",
        "SINGLE_STRONG_OBSERVATION",
        ("CHECKPOINT_RUN", "ENTITY_OBSERVATION"),
    ),
    EventRule(
        "JS_ERROR_STARTED",
        "JAVASCRIPT",
        "A JavaScript error fingerprint appeared.",
        "MEDIUM",
        "REQUIRES_E2_CONFIRMATION",
        ("CHECKPOINT_RUN", "JS_ERROR_OBSERVATION"),
    ),
    EventRule(
        "NOINDEX_ADDED",
        "SEO",
        "A rendered noindex directive appeared.",
        "HIGH",
        "REQUIRES_E2_CONFIRMATION",
        ("CHECKPOINT_RUN", "SEO_OBSERVATION"),
    ),
    EventRule(
        "CANONICAL_CHANGED",
        "SEO",
        "The rendered canonical URL changed.",
        "MEDIUM",
        "SINGLE_STRONG_OBSERVATION",
        ("CHECKPOINT_RUN", "SEO_OBSERVATION"),
    ),
    EventRule(
        "GPT_EXPECTED_SLOT_MISSING",
        "MONETIZATION",
        "An expected GPT slot was not observed.",
        "HIGH",
        "REQUIRES_E2_CONFIRMATION",
        ("CHECKPOINT_RUN", "GPT_SLOT_OBSERVATION"),
    ),
)
RULES_BY_CODE = {rule.code: rule for rule in RULES}


def definition_id(code: str) -> uuid.UUID:
    if code not in RULES_BY_CODE:
        raise KeyError(code)
    return uuid.uuid5(EVENT_DEFINITION_NAMESPACE, code)
