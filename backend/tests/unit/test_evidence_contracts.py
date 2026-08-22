import pytest

from app.evidence.contracts import (
    MAX_PACK_BYTES,
    PACK_ENGINE_VERSION,
    canonical_pack_bytes,
    content_hash,
    validate_note_type,
    validate_relation_type,
)
from app.evidence.models import NOTE_TYPES, RELATION_TYPES


def test_relation_vocabulary_matches_data_model_and_reserved_causes() -> None:
    assert {
        "PRECEDES",
        "COINCIDES_WITH",
        "SAME_SEGMENT_AS",
        "MECHANISTICALLY_CAN_AFFECT",
        "METRIC_PARENT_OF",
        "METRIC_DESCENDANT_OF",
        "SUPPORTS",
        "CONTRADICTS",
        "INTRODUCED_BY",
        "RESOLVED_AFTER",
        "PERSISTED_AFTER_REMOVAL",
        "EXTERNAL_CONTEXT_FOR",
        "UNKNOWN_RELATION",
    } == RELATION_TYPES

    with pytest.raises(Exception, match="reserved"):
        validate_relation_type("CAUSES")
    with pytest.raises(Exception, match="unknown event relation"):
        validate_relation_type("TELEPATHY")


def test_note_type_vocabulary_is_bounded() -> None:
    assert NOTE_TYPES == {
        "DEPLOY",
        "ROLLBACK",
        "CONFIG_CHANGE",
        "OPERATOR_INTERVENTION",
        "EXTERNAL_COMMUNICATION",
        "OTHER",
    }
    with pytest.raises(Exception, match="unknown manual note type"):
        validate_note_type("GAM_CONFIGURATION_CHANGED_AUTOMATICALLY")


def test_pack_content_serialization_is_deterministic() -> None:
    content = {"b": 1, "a": ["x", "y"]}
    first = canonical_pack_bytes(content)
    second = canonical_pack_bytes({"a": ["x", "y"], "b": 1})
    assert first == second
    assert content_hash(content) == content_hash({"a": ["x", "y"], "b": 1})
    assert len(content_hash(content)) == 64


def test_pack_engine_version_and_bound_are_pinned() -> None:
    assert PACK_ENGINE_VERSION == "pack-v1"
    assert MAX_PACK_BYTES == 262_144
