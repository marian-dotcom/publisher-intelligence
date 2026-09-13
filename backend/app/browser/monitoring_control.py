"""EP-030 M1: per-site scheduled-monitoring control service.

Provides the smallest bounded boundary for enabling/disabling the six-hour
SCHEDULED browser monitoring authorization and for reading the current state.
A single transaction resolves and locks the tenant-owned site row and, only on
a real OFF<->ON transition, commits the state change and the watermark together
with exactly one append-only audit row.

M1 stores state and exposes the control read/write contract only. Scheduler
(GATE-1/2) and worker (GATE-3) enforcement, and the administrative SKIPPED
runtime behavior, land in M2.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.browser.models import CheckpointRun, Site, SiteMonitoringStateChange
from app.browser.scheduling import resolve_six_hour_window

MonitoringStateConstant = Literal["ON", "OFF"]


class SiteMonitoringNotFoundError(Exception):
    """Missing or not owned by the caller's tenant.

    Deliberately carries no distinguishing detail so a caller cannot infer
    whether a site exists in another tenant.
    """


@dataclass(frozen=True, slots=True)
class SiteMonitoringState:
    site_id: uuid.UUID
    enabled: bool
    monitoring_state_updated_at: datetime


@dataclass(frozen=True, slots=True)
class MonitoringControlResult:
    site_id: uuid.UUID
    enabled: bool
    monitoring_state_updated_at: datetime
    next_scheduled_for: datetime | None
    in_flight_scheduled_run_status: str | None


def _state_of(enabled: bool) -> MonitoringStateConstant:
    return "ON" if enabled else "OFF"


def _enabled(monitoring_state: str) -> bool:
    return monitoring_state == "ON"


def _resolve_next_boundary(
    monitoring_state: str, monitoring_state_updated_at: datetime, timezone: str
) -> datetime | None:
    """Next strictly-future six-hour boundary after the enable watermark.

    The watermark local instant always lies within its resolved window, so the
    window end is always strictly greater than the watermark. Enabling exactly
    at a boundary defers to the following boundary, as accepted.
    """
    if monitoring_state != "ON":
        return None
    try:
        bounds = resolve_six_hour_window(monitoring_state_updated_at, timezone)
    except ValueError:
        return None
    return bounds.window_end


async def set_monitoring_state(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    tenant_id: uuid.UUID,
    site_id: uuid.UUID,
    enabled: bool,
    actor_id: uuid.UUID,
) -> SiteMonitoringState:
    """Enable or disable monitoring for a tenant-owned site, atomically.

    A conditional UPDATE on the current state is the concurrency guard: the
    winner (rowcount == 1) appends exactly one audit row and commits state +
    audit together; a loser or an already-desired request (rowcount == 0)
    leaves state and watermark untouched and appends no audit row. Missing or
    foreign sites raise SiteMonitoringNotFoundError (discloses nothing).
    """
    desired = _state_of(enabled)
    updated_at = datetime.now(UTC)
    async with session_factory() as session, session.begin():
        row = await session.execute(
            select(Site).where(Site.tenant_id == tenant_id, Site.id == site_id).with_for_update()
        )
        site = row.scalar_one_or_none()
        if site is None:
            raise SiteMonitoringNotFoundError()

        original = site.monitoring_state
        if original == desired:
            return SiteMonitoringState(
                site_id=site_id,
                enabled=_enabled(original),
                monitoring_state_updated_at=site.monitoring_state_updated_at,
            )

        updated_id = (
            await session.execute(
                update(Site)
                .where(
                    Site.tenant_id == tenant_id,
                    Site.id == site_id,
                    Site.monitoring_state == original,
                )
                .values(
                    monitoring_state=desired,
                    monitoring_state_updated_at=updated_at,
                )
                .returning(Site.id)
            )
        ).scalar_one_or_none()
        if updated_id is None:
            # A concurrent transition completed first; reflect the winner's
            # state without moving the watermark or duplicating its audit row.
            winner_row = await session.execute(
                select(Site)
                .where(Site.tenant_id == tenant_id, Site.id == site_id)
                .with_for_update()
            )
            winner = winner_row.scalar_one_or_none()
            if winner is None:
                raise SiteMonitoringNotFoundError()
            return SiteMonitoringState(
                site_id=site_id,
                enabled=_enabled(winner.monitoring_state),
                monitoring_state_updated_at=winner.monitoring_state_updated_at,
            )

        session.add(
            SiteMonitoringStateChange(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                site_id=site_id,
                from_state=original,
                to_state=desired,
                actor_id=actor_id,
            )
        )
        return SiteMonitoringState(
            site_id=site_id,
            enabled=_enabled(desired),
            monitoring_state_updated_at=updated_at,
        )


async def read_monitoring_state(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    site_id: uuid.UUID,
) -> SiteMonitoringState:
    """Read the current monitoring state for a tenant-owned site, or fail closed."""
    site = await session.scalar(select(Site).where(Site.tenant_id == tenant_id, Site.id == site_id))
    if site is None:
        raise SiteMonitoringNotFoundError()
    return SiteMonitoringState(
        site_id=site.id,
        enabled=_enabled(site.monitoring_state),
        monitoring_state_updated_at=site.monitoring_state_updated_at,
    )


async def _in_flight_scheduled_run_status(
    session: AsyncSession, *, tenant_id: uuid.UUID, site_id: uuid.UUID
) -> str | None:
    """Read-only projection of the latest non-terminal SCHEDULED run, if any.

    M1 exposes already-materialized non-terminal SCHEDULED work truthfully;
    scheduler/worker gating on monitoring state is M2.
    """
    run = await session.scalar(
        select(CheckpointRun)
        .where(
            CheckpointRun.tenant_id == tenant_id,
            CheckpointRun.site_id == site_id,
            CheckpointRun.observation_kind == "SCHEDULED",
            CheckpointRun.status.in_(("PENDING", "RUNNING")),
        )
        .order_by(CheckpointRun.created_at.desc(), CheckpointRun.id.desc())
        .limit(1)
    )
    return run.status if run is not None else None


async def monitoring_control_result(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    site_id: uuid.UUID,
) -> MonitoringControlResult:
    """Compose the full M1 monitoring-control response for a site."""
    state = await read_monitoring_state(session, tenant_id=tenant_id, site_id=site_id)
    site = await session.scalar(select(Site).where(Site.tenant_id == tenant_id, Site.id == site_id))
    if site is None:
        raise SiteMonitoringNotFoundError()
    return MonitoringControlResult(
        site_id=site_id,
        enabled=state.enabled,
        monitoring_state_updated_at=state.monitoring_state_updated_at,
        next_scheduled_for=_resolve_next_boundary(
            site.monitoring_state,
            site.monitoring_state_updated_at,
            site.timezone,
        ),
        in_flight_scheduled_run_status=await _in_flight_scheduled_run_status(
            session, tenant_id=tenant_id, site_id=site_id
        ),
    )
