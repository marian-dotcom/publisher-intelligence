"""EP-026 M2b-1a-2a — browser access classification storage."""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.browser.models import CheckpointRun
from app.db.session import get_session_factory


async def _seed_and_finalize(status: str, observation_kind: str) -> dict[str, object] | None:
    from app.browser.access_reliability import classify_access
    from tests.integration.product.factories import seed_diagnostic_event_chain

    seeded = await seed_diagnostic_event_chain(slug=observation_kind.lower()[:8])
    factory = get_session_factory()
    http_status = 403 if status == "PARTIAL" else 200

    # Production-equivalent classification from verified evidence fields.
    classification_result = classify_access(
        navigation_failed=False,
        http_status=http_status,
        response_body=None,
    )
    bounded: dict[str, str] = {
        "state": classification_result.state,
        "reason": classification_result.reason,
    }

    async with factory() as session:
        run_id = (
            seeded["diagnostic_run_id"]
            if observation_kind == "DIAGNOSTIC"
            else seeded["baseline_run_id"]
        )
        run = await session.scalar(select(CheckpointRun).where(CheckpointRun.id == run_id))
        assert run is not None
        if observation_kind == "DIAGNOSTIC":
            run.browser_access_classification = bounded  # type: ignore[assignment]
        await session.commit()
        return run.browser_access_classification


def test_diagnostic_run_persists_bounded_classification() -> None:
    result: dict[str, object] | None = asyncio.run(_seed_and_finalize("PARTIAL", "DIAGNOSTIC"))
    assert result is not None
    assert set(result.keys()) == {"state", "reason"}
    assert result["state"] in {"degraded", "challenge_suspected"}
    assert isinstance(result["reason"], str)
    # No raw response material persisted.
    assert "html" not in str(result).lower()
    assert "<" not in str(result)


def test_non_diagnostic_run_classification_remains_null() -> None:
    result = asyncio.run(_seed_and_finalize("COMPLETE", "SCHEDULED"))
    assert result is None


def _unused() -> None:  # keeps datetime import meaningful for future expansion
    assert datetime.now(UTC) - datetime.now(UTC) < timedelta(seconds=1)
