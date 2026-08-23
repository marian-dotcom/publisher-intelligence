"""Product read APIs: Home/status, source health, site health (EP-025a P2-A)."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.auth.dependencies import ActorContext, get_current_actor
from app.browser.models import CheckpointRun, Publisher, Site
from app.connectors.models import DataConnection
from app.db.session import get_session_factory
from app.incidents.models import Incident

router = APIRouter(prefix="/product", tags=["product"])

# Canonical source/product health vocabulary (EP-025a contract).
SOURCE_HEALTH_STATES = (
    "HEALTHY",
    "DEGRADED",
    "BLOCKED",
    "ACTION_REQUIRED",
    "UNKNOWN",
    "UNAVAILABLE",
)

_BROWSER_BAD_STATUSES = {"SITE_ERROR", "BROWSER_ERROR", "TIMEOUT", "BLOCKED"}
_STALENESS = timedelta(hours=7)  # slightly more than the six-hour cadence


def _browser_source_health(latest_status: str | None, completed_at: datetime | None) -> str:
    """Deterministic mapping from observation state to source health.

    Observation failure is not evidence of publisher failure: a failed run is
    reported at source level (UNAVAILABLE), never as site failure.
    """
    if latest_status is None or completed_at is None:
        return "UNKNOWN"
    if datetime.now(UTC) - completed_at > _STALENESS:
        return "UNAVAILABLE"
    if latest_status == "COMPLETE":
        return "HEALTHY"
    if latest_status == "PARTIAL":
        return "DEGRADED"
    return "UNAVAILABLE"


def _connector_health(status: str | None) -> str:
    if status is None:
        return "UNKNOWN"
    return {
        "CONNECTED": "HEALTHY",
        "DEGRADED": "DEGRADED",
        "AUTH_EXPIRED": "ACTION_REQUIRED",
        "PERMISSION_ERROR": "BLOCKED",
    }.get(status, "UNKNOWN")


from sqlalchemy.ext.asyncio import AsyncSession


async def _source_health_rows(
    session: AsyncSession, *, tenant_id: uuid.UUID, site_id: uuid.UUID
) -> dict[str, str]:
    health: dict[str, str] = {
        "BROWSER_MONITORING": "UNKNOWN",
        "GA4": "UNKNOWN",
        "GSC": "UNKNOWN",
        "GAM": "UNKNOWN",
    }
    run = await session.scalar(
        select(CheckpointRun)
        .where(
            CheckpointRun.tenant_id == tenant_id,
            CheckpointRun.site_id == site_id,
            CheckpointRun.observation_kind == "SCHEDULED",
        )
        .order_by(CheckpointRun.started_at.desc())
        .limit(1)
    )
    if run is not None:
        health["BROWSER_MONITORING"] = _browser_source_health(run.status, run.completed_at)
    connections = list(
        (
            await session.scalars(
                select(DataConnection).where(
                    DataConnection.tenant_id == tenant_id,
                    DataConnection.site_id == site_id,
                )
            )
        ).all()
    )
    provider_by_connection: dict[uuid.UUID, str] = {}
    for connection in connections:
        provider_by_connection[connection.id] = getattr(connection, "provider", "UNKNOWN")
    for connection in connections:
        provider = provider_by_connection.get(connection.id, "")
        key = {"ga4": "GA4", "gsc": "GSC", "gam": "GAM"}.get(provider.lower())
        if key:
            health[key] = _connector_health(connection.status)
    return health


@router.get("/home/status")
async def home_status(
    actor: ActorContext = Depends(get_current_actor),  # noqa: B008
    site_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    factory = get_session_factory()
    async with factory() as session:
        sites = list(
            (
                await session.scalars(
                    select(Site).where(Site.tenant_id == actor.tenant_id).order_by(Site.name)
                )
            ).all()
        )
        selected = (
            next((s for s in sites if s.id == site_id), None)
            if site_id
            else (sites[0] if sites else None)
        )
        sources: dict[str, str] = {}
        if selected is not None:
            sources = await _source_health_rows(
                session,
                tenant_id=actor.tenant_id,
                site_id=selected.id,
            )
        open_incidents = list(
            (
                await session.scalars(
                    select(Incident).where(
                        Incident.tenant_id == actor.tenant_id,
                        Incident.status.in_(("OPEN", "INVESTIGATING")),
                    )
                )
            ).all()
        )
        monetization_capability = "UNKNOWN"
        if selected is not None:
            connection = await session.scalar(
                select(DataConnection).where(
                    DataConnection.tenant_id == actor.tenant_id,
                    DataConnection.site_id == site_id,
                    DataConnection.provider.in_(("ga4", "gam")),
                )
            )
            if connection is not None:
                monetization_capability = connection.monetization_capability
    return {
        "sites": [{"site_id": str(s.id), "name": s.name} for s in sites],
        "selected_site_id": str(selected.id) if selected else None,
        "publisher_site_condition": (
            "UNKNOWN" if selected is None else getattr(selected, "status", "UNKNOWN")
        ),
        "source_health": sources,
        "open_incident_count": len(open_incidents),
        "monetization_capability": monetization_capability,
    }


@router.get("/source-health")
async def source_health(
    actor: ActorContext = Depends(get_current_actor),  # noqa: B008
    *,
    site_id: uuid.UUID,
) -> dict[str, object]:
    factory = get_session_factory()
    async with factory() as session:
        owned = await session.scalar(
            select(Publisher.id)
            .join(Site, Site.publisher_id == Publisher.id)
            .where(Site.id == site_id, Site.tenant_id == actor.tenant_id)
        )
    if owned is None:
        raise HTTPException(status_code=404, detail="resource not found")
    factory = get_session_factory()
    async with factory() as session:
        health = await _source_health_rows(session, tenant_id=actor.tenant_id, site_id=site_id)
    return {"site_id": str(site_id), "sources": health}
