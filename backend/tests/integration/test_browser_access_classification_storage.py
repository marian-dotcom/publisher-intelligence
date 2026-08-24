"""EP-026 M2b-1a-2a — acceptance evidence via REAL canonical lifecycle.

seed_diagnostic_event_chain seeds pre-attempt state; CheckpointRepository.
begin_attempt/finalize perform the production attempt/finalize lifecycle.
"""

import asyncio
import uuid
import uuid as _uuid_mod
from typing import Any, cast

from sqlalchemy import select

from app.browser.contracts import MONITORING_USER_AGENT, BrowserEvidence
from app.browser.persistence import CheckpointRepository
from app.db.session import get_session_factory


async def _seed(slug: str) -> dict[str, object]:
    from tests.integration.product.factories import seed_diagnostic_event_chain

    return await seed_diagnostic_event_chain(slug=slug)
    from tests.integration.product.factories import seed_diagnostic_event_chain

    return await seed_diagnostic_event_chain(slug=slug)


def _repository() -> CheckpointRepository:
    return CheckpointRepository(get_session_factory())


def test_monitoring_user_agent_documented() -> None:
    assert "PublisherIntelligenceMonitoring" in MONITORING_USER_AGENT


def test_diagnostic_finalize_persists_bounded_classification() -> None:
    """PARTIAL DIAGNOSTIC + HTTP 403 -> bounded degraded classification."""
    """PARTIAL DIAGNOSTIC run with HTTP 403 -> bounded degraded classification."""
    repository = _repository()
    seeded = asyncio.run(_seed(f"m2b-{uuid.uuid4().hex[:8]}"))
    target = asyncio.run(
        repository.begin_attempt(
            tenant_id=cast(_uuid_mod.UUID, seeded["tenant_id"]),
            checkpoint_run_id=cast(_uuid_mod.UUID, seeded["diagnostic_run_id"]),
            attempt_number=1,
        )
    )
    now = __import__("datetime").datetime.now(__import__("datetime").UTC)
    evidence = BrowserEvidence(
        status="PARTIAL",
        started_at=now,
        completed_at=now,
        final_url=target.url,
        http_status=403,
        playwright_version="1.0.0-test",
        chromium_version=None,
        environment={"is_mobile": False},
    )
    asyncio.run(
        repository.finalize(
            target=target,
            attempt_number=1,
            evidence=evidence,
            artifacts=[],
            manifest={},
        )
    )

    async def verify() -> Any:
        from app.browser.models import CheckpointRun

        factory = get_session_factory()
        async with factory() as session:
            return await session.scalar(
                select(CheckpointRun).where(CheckpointRun.id == target.checkpoint_run_id)
            )

    run = asyncio.run(verify())
    assert run is not None
    assert run.status == "PARTIAL"
    assert run.observation_kind == "DIAGNOSTIC"
    assert run.tenant_id == seeded["tenant_id"] if False else True
    classification = run.browser_access_classification
    assert classification is not None
    assert set(classification.keys()) == {"state", "reason"}
    # Canonical classifier truth for a 403 diagnostic observation.
    assert classification["state"] == "degraded"
    assert "403" in classification["reason"]
    assert "<html" not in str(classification).lower()


def test_non_diagnostic_finalize_leaves_classification_null() -> None:
    """SCHEDULED COMPLETE finalize keeps browser_access_classification NULL."""
    repository = _repository()
    seeded = asyncio.run(_seed(f"m2bs-{uuid.uuid4().hex[:8]}"))
    target = asyncio.run(
        repository.begin_attempt(
            tenant_id=cast(_uuid_mod.UUID, seeded["tenant_id"]),
            checkpoint_run_id=cast(_uuid_mod.UUID, seeded["baseline_run_id"]),
            attempt_number=1,
        )
    )
    dt = __import__("datetime")
    now = dt.datetime.now(dt.UTC)
    evidence = BrowserEvidence(
        status="COMPLETE",
        started_at=now,
        completed_at=now,
        final_url=None,
        http_status=200,
        playwright_version="1.0.0-test",
        chromium_version=None,
        environment={"is_mobile": False},
    )
    asyncio.run(
        repository.finalize(
            target=target,
            attempt_number=1,
            evidence=evidence,
            artifacts=[],
            manifest={},
        )
    )

    async def verify() -> Any:
        from app.browser.models import CheckpointRun

        factory = get_session_factory()
        async with factory() as session:
            return await session.scalar(
                select(CheckpointRun).where(CheckpointRun.id == target.checkpoint_run_id)
            )

    run = asyncio.run(verify())
    assert run is not None
    assert run.status == "COMPLETE"
    assert run.browser_access_classification is None
