import pytest

from app.incidents.contracts import (
    DEFAULT_RESOURCE_LIMITS,
    InvestigationStateError,
    usage_key_for,
    validate_incident_fields,
    validate_resource_kind,
    validate_symptom_segment,
)


def test_incident_field_validation_rejects_unknown_vocabularies() -> None:
    with pytest.raises(InvestigationStateError, match="symptom family"):
        validate_incident_fields(title="t", symptom_family="NOPE", description="d")
    with pytest.raises(InvestigationStateError, match="status"):
        validate_incident_fields(title="t", symptom_family="OTHER", description="d", status="MAGIC")
    with pytest.raises(InvestigationStateError, match="severity"):
        validate_incident_fields(
            title="t", symptom_family="OTHER", description="d", severity="EXTREME"
        )
    with pytest.raises(InvestigationStateError, match="title"):
        validate_incident_fields(title="  ", symptom_family="OTHER", description="d")
    with pytest.raises(InvestigationStateError, match="description"):
        validate_incident_fields(title="t", symptom_family="OTHER", description="")


def test_symptom_segment_validation_bounds_entries() -> None:
    with pytest.raises(InvestigationStateError, match="dimension"):
        validate_symptom_segment(dimension="", operator="=", value="v", source="s")
    long = "x" * 201
    with pytest.raises(InvestigationStateError, match="bounded"):
        validate_symptom_segment(dimension=long, operator="=", value="v", source="s")


def test_unknown_resource_kind_is_rejected() -> None:
    with pytest.raises(InvestigationStateError, match="resource kind"):
        validate_resource_kind("INFINITE_LLM")


def test_usage_key_combines_investigation_kind_and_correlation() -> None:
    key = usage_key_for(investigation_key="inv-1", resource_kind="DRILLDOWN", correlation_id="abc")
    assert key == "inv-1|DRILLDOWN|abc"
    with pytest.raises(InvestigationStateError, match="investigation key"):
        usage_key_for(investigation_key=" ", resource_kind="DRILLDOWN", correlation_id="abc")


def test_default_limits_cover_the_registry() -> None:
    for kind in ("DRILLDOWN", "LLM_PASS", "DIAGNOSTIC_RUN"):
        assert DEFAULT_RESOURCE_LIMITS[kind] > 0
