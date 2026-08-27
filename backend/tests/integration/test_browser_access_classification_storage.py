"""EP-026 M2b-1a-2a — acceptance evidence via REAL canonical lifecycle.

seed_diagnostic_event_chain seeds pre-attempt state; CheckpointRepository.
begin_attempt/finalize perform the production attempt/finalize lifecycle.
"""

import asyncio
import uuid
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import select

from app.browser.contracts import MONITORING_USER_AGENT, BrowserEvidence
from app.browser.persistence import CheckpointRepository
from app.db.session import get_session_factory


async def _seed(slug: str) -> dict[str, object]:
    from tests.integration.product.factories import seed_diagnostic_event_chain

    return await seed_diagnostic_event_chain(slug=slug)


def _repository() -> CheckpointRepository:
    return CheckpointRepository(get_session_factory())


def test_monitoring_user_agent_documented() -> None:
    assert "PublisherIntelligenceMonitoring" in MONITORING_USER_AGENT


def test_diagnostic_finalize_persists_bounded_classification() -> None:
    """PARTIAL DIAGNOSTIC + HTTP 403 -> bounded degraded classification."""
    repository = _repository()
    seeded = asyncio.run(_seed(f"m2b-{uuid.uuid4().hex[:8]}"))
    tenant_id = seeded["tenant_id"]
    diagnostic_run_id = seeded["diagnostic_run_id"]
    site_id = seeded["site_id"]

    target = asyncio.run(
        repository.begin_attempt(
            tenant_id=cast(uuid.UUID, tenant_id),
            checkpoint_run_id=cast(uuid.UUID, diagnostic_run_id),
            attempt_number=1,
        )
    )
    now = datetime.now(UTC)
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

    async def verify() -> tuple[str, str, str, str, str, str]:
        from app.browser.models import CheckpointRun

        factory = get_session_factory()
        async with factory() as session:
            run = await session.scalar(
                select(CheckpointRun).where(CheckpointRun.id == diagnostic_run_id)
            )
            assert run is not None
            classification = run.browser_access_classification or {}
            return (
                run.status,
                run.observation_kind,
                str(classification.get("state", "")),
                " ".join(str(classification.get("reason", "")).split()),
                str(run.tenant_id),
                str(run.site_id),
            )

    status, observation_kind, state, reason, persisted_tenant, persisted_site = asyncio.run(
        verify()
    )
    classification = {"state": state, "reason": reason}

    assert status == "PARTIAL"
    assert observation_kind == "DIAGNOSTIC"
    # Real ownership evidence (values compared, not tautologies).
    assert persisted_tenant == str(tenant_id)
    assert persisted_site == str(site_id)
    assert set(classification.keys()) == {"state", "reason"}
    assert state == "degraded"
    assert "403" in reason
    assert "<html" not in (classification.get("reason") or "").lower()


def test_non_diagnostic_finalize_leaves_classification_null() -> None:
    """SCHEDULED COMPLETE finalize keeps browser_access_classification NULL."""
    repository = _repository()
    seeded = asyncio.run(_seed(f"m2bs-{uuid.uuid4().hex[:8]}"))
    tenant_id = seeded["tenant_id"]
    baseline_run_id = seeded["baseline_run_id"]
    site_id = seeded["site_id"]

    target = asyncio.run(
        repository.begin_attempt(
            tenant_id=cast(uuid.UUID, tenant_id),
            checkpoint_run_id=cast(uuid.UUID, baseline_run_id),
            attempt_number=1,
        )
    )
    now = datetime.now(UTC)
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

    async def verify() -> tuple[dict[str, object] | None, str, str, str]:
        from app.browser.models import CheckpointRun

        factory = get_session_factory()
        async with factory() as session:
            run = await session.scalar(
                select(CheckpointRun).where(CheckpointRun.id == baseline_run_id)
            )
            assert run is not None
            return (
                run.browser_access_classification,
                run.status,
                str(run.tenant_id),
                str(run.site_id),
            )

    classification, status, persisted_tenant, persisted_site = asyncio.run(verify())
    assert classification is None
    assert status == "COMPLETE"
    # Real ownership evidence for the scheduled path as well.
    assert persisted_tenant == str(tenant_id)
    assert persisted_site == str(site_id)
