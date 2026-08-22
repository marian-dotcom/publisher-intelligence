import pytest

from app.browser.contracts import OBSERVATION_KINDS, TRIGGER_SOURCES
from app.browser.service import CheckpointService


def _service() -> CheckpointService:
    return CheckpointService(None, None, None)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_registration_rejects_scheduled_kind_before_any_side_effect() -> None:
    service = _service()
    with pytest.raises(ValueError, match="non-scheduled"):
        await service.register_and_enqueue(
            tenant_slug="t",
            tenant_name="T",
            publisher_name="P",
            site_name="S",
            url="https://www.example.com/",
            observation_kind="SCHEDULED",
        )


@pytest.mark.asyncio
async def test_registration_rejects_unknown_observation_kind() -> None:
    service = _service()
    with pytest.raises(ValueError, match="non-scheduled"):
        await service.register_and_enqueue(
            tenant_slug="t",
            tenant_name="T",
            publisher_name="P",
            site_name="S",
            url="https://www.example.com/",
            observation_kind="MYSTERY",
        )


@pytest.mark.asyncio
async def test_registration_rejects_unknown_trigger_source() -> None:
    service = _service()
    with pytest.raises(ValueError, match="trigger source"):
        await service.register_and_enqueue(
            tenant_slug="t",
            tenant_name="T",
            publisher_name="P",
            site_name="S",
            url="https://www.example.com/",
            trigger_source="NOT_A_SOURCE",
        )


def test_vocabularies_match_adr_130() -> None:
    assert OBSERVATION_KINDS == {"SCHEDULED", "DIAGNOSTIC", "INCIDENT_DIAGNOSTIC"}
    assert TRIGGER_SOURCES == {"OPERATOR_CLI", "LEGACY_CLI", "INCIDENT"}
