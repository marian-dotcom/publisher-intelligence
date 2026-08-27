"""EP-026 M4: measured browser-workload cost telemetry + circuit breaker.

Extends the investigation budget-ledger pattern (DIAGNOSTIC_RUN) into the
scheduled browser workload. Cost is MEASURED at execution time — one ledger
entry per executed checkpoint run, amounting one run unit over a bounded
one-page set, with measured facts (status, attempt) in the audit detail.
Nothing is inferred or estimated.

The circuit breaker is a deterministic READ-TIME projection of the same
append-only ledger: for a site's checkpoint window, once recorded usage
reaches the per-site/per-window cap, further scheduling for that scope is
stopped until the window rolls over. There is no mutable breaker state and
no hidden global: the ledger rows are the auditable breaker evidence.

Bounded retries stay governed by existing job max_attempts semantics; retry
attempts of the same run are folded into the run's single idempotent cost
entry (usage_key uniqueness), so retries can never become an uncontrolled
spend loop.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.browser.models import CheckpointRun
from app.incidents.contracts import usage_key_for
from app.incidents.models import InvestigationUsageEntry

CHECKPOINT_RUN = "CHECKPOINT_RUN"

# Canonical cap source (SECURITY.md §55/§96: server-side configured limits).
DEFAULT_CHECKPOINTS_PER_SITE_WINDOW = 4


def site_window_scope(*, site_id: uuid.UUID, window_id: uuid.UUID) -> str:
    """Deterministic per-site/per-window budget scope key."""
    return f"site:{site_id}|window:{window_id}"


def _usage_key(*, site_id: uuid.UUID, window_id: uuid.UUID, checkpoint_run_id: uuid.UUID) -> str:
    return usage_key_for(
        investigation_key=site_window_scope(site_id=site_id, window_id=window_id),
        resource_kind=CHECKPOINT_RUN,
        correlation_id=checkpoint_run_id,
    )


async def record_checkpoint_cost(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    tenant_id: uuid.UUID,
    checkpoint_run_id: uuid.UUID,
    status: str,
    attempt_count: int,
    pages: int = 1,
    occurred_at: datetime | None = None,
) -> bool:
    """Record measured execution cost for one checkpoint run.

    Idempotent by usage_key (run-scoped): retries fold into the single entry,
    so bounded retries cannot inflate recorded spend. Returns True when this
    call created the entry. The run's site/window scope is resolved from the
    run row so telemetry scope always matches scheduling scope.
    """
    async with session_factory() as session, session.begin():
        row = await session.execute(
            select(CheckpointRun.site_id, CheckpointRun.checkpoint_window_id).where(
                CheckpointRun.id == checkpoint_run_id,
                CheckpointRun.tenant_id == tenant_id,
            )
        )
        scoped = row.one_or_none()
        if scoped is None:
            return False
        site_id, window_id = scoped
        key = _usage_key(site_id=site_id, window_id=window_id, checkpoint_run_id=checkpoint_run_id)
        existing = await session.scalar(
            select(InvestigationUsageEntry.id).where(InvestigationUsageEntry.usage_key == key)
        )
        if existing is not None:
            return False
        detail: dict[str, Any] = {
            "checkpoint_run_id": str(checkpoint_run_id),
            "window_id": str(window_id),
            "pages": pages,
            "status": status,
            "attempt_count": attempt_count,
        }
        session.add(
            InvestigationUsageEntry(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                incident_id=None,
                investigation_key=site_window_scope(site_id=site_id, window_id=window_id),
                resource_kind=CHECKPOINT_RUN,
                amount=1,
                usage_key=key,
                detail=detail,
                occurred_at=occurred_at or datetime.now(UTC),
            )
        )
        return True


def breaker_open_for_usage(*, used: int, limit: int = DEFAULT_CHECKPOINTS_PER_SITE_WINDOW) -> bool:
    """Deterministic breaker predicate: open once usage reaches the cap."""
    return used >= limit


class CheckpointCostRecorder:
    """Execution-boundary cost sink, injected into the browser job handler so
    the handler itself never depends on process-global engine state."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def record(
        self,
        *,
        tenant_id: uuid.UUID,
        checkpoint_run_id: uuid.UUID,
        status: str,
        attempt_count: int,
    ) -> bool:
        return await record_checkpoint_cost(
            self._session_factory,
            tenant_id=tenant_id,
            checkpoint_run_id=checkpoint_run_id,
            status=status,
            attempt_count=attempt_count,
        )


async def latest_site_window_usage(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    site_id: uuid.UUID,
) -> int:
    """Recorded checkpoint cost units for the site's most recent window."""
    from app.browser.models import CheckpointWindow

    window_id = await session.scalar(
        select(CheckpointWindow.id)
        .where(CheckpointWindow.tenant_id == tenant_id, CheckpointWindow.site_id == site_id)
        .order_by(CheckpointWindow.scheduled_for.desc())
        .limit(1)
    )
    if window_id is None:
        return 0
    return await current_window_usage(
        session,
        tenant_id=tenant_id,
        scope=site_window_scope(site_id=site_id, window_id=window_id),
    )


async def current_window_usage(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    scope: str,
) -> int:
    """Sum recorded CHECKPOINT_RUN cost units for one site/window scope."""
    total = await session.scalar(
        select(func.sum(InvestigationUsageEntry.amount)).where(
            InvestigationUsageEntry.tenant_id == tenant_id,
            InvestigationUsageEntry.investigation_key == scope,
            InvestigationUsageEntry.resource_kind == CHECKPOINT_RUN,
        )
    )
    return int(total or 0)
