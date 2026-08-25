"""Product read APIs: Home/status, source health, site health (EP-025a P2-A)."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import ActorContext, get_current_actor
from app.browser.cost import breaker_open_for_usage, latest_site_window_usage
from app.browser.models import CheckpointRun, Publisher, Site
from app.connectors.freshness import SOURCE_FRESHNESS_THRESHOLDS, freshness_state
from app.connectors.models import DataConnection
from app.db.session import get_session_factory
from app.events.source_health import browser_source_health
from app.incidents.models import Incident
from app.operations import operations_snapshot
from app.public_config.models import PublicConfigSnapshot

router = APIRouter(prefix="/product", tags=["product"])


@router.get("/operations")
async def operations(
    actor: ActorContext = Depends(get_current_actor),  # noqa: B008
) -> dict[str, Any]:
    """EP-026 M6 minimal self-observability for the caller's tenant.

    PI-infrastructure signals are global by nature (one shared queue/scheduler
    fleet); per-site source-health rows remain strictly tenant-scoped and keep
    their EP-025a semantics. This endpoint never asserts publisher/site
    failure."""
    factory = get_session_factory()

    async def per_site_source_health() -> list[tuple[str, str, dict[str, str]]]:
        async with factory() as session:
            sites = list(
                (
                    await session.scalars(
                        select(Site).where(Site.tenant_id == actor.tenant_id).order_by(Site.name)
                    )
                ).all()
            )
            return [
                (
                    str(site.id),
                    site.name,
                    await _source_health_rows(session, tenant_id=actor.tenant_id, site_id=site.id),
                )
                for site in sites
            ]

    snapshot = await operations_snapshot(
        factory,
        tenant_id=actor.tenant_id,
        source_health_for_site=per_site_source_health,
    )
    return {"tenant_id": str(actor.tenant_id), **snapshot}


# Canonical source/product health vocabulary (EP-025a contract; STALE added
# by EP-026 M3b for derived connector freshness).
SOURCE_HEALTH_STATES = (
    "HEALTHY",
    "STALE",
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
    reported at source level (UNAVAILABLE), never as site failure. Evidence
    older than the freshness window is STALE (EP-026 M3b): the observation
    source itself stopped delivering trustworthy evidence.
    """
    if latest_status is None or completed_at is None:
        return "UNKNOWN"
    if datetime.now(UTC) - completed_at > _STALENESS:
        return "STALE"
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


def _connector_health_with_freshness(
    status: str | None, last_success_at: datetime | None, *, now: datetime, key: str
) -> str:
    """EP-026 M3b precedence: explicit connection-path states (DEGRADED,
    ACTION_REQUIRED, BLOCKED) are stronger than derived staleness and are
    preserved as-is. Only an otherwise-HEALTHY CONNECTED connection is
    subject to the freshness projection."""
    mapped = _connector_health(status)
    if mapped != "HEALTHY":
        return mapped
    return freshness_state(last_success_at, now=now, threshold=SOURCE_FRESHNESS_THRESHOLDS[key])


async def _source_health_rows(
    session: AsyncSession, *, tenant_id: uuid.UUID, site_id: uuid.UUID
) -> dict[str, str]:
    health: dict[str, str] = {
        "BROWSER_MONITORING": "UNKNOWN",
        "GA4": "UNKNOWN",
        "GSC": "UNKNOWN",
        "GAM": "UNKNOWN",
        "PUBLIC_CONFIG": "UNKNOWN",
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
    # EP-026 M2b-2: an OPEN browser-source degradation episode (deterministic
    # reliability evidence) overrides the run-status heuristic. This describes
    # OUR observation source only — never publisher/site health.
    reliability = await browser_source_health(session, tenant_id=tenant_id, site_id=site_id)
    if reliability.state == "DEGRADED":
        health["BROWSER_MONITORING"] = "DEGRADED"
    else:
        # EP-026 M4: an open checkpoint budget circuit breaker (cost ledger
        # usage at/over the per-site/per-window cap) surfaces as BLOCKED —
        # monitoring is deliberately stopped, never silently missing.
        # Precedence: active DEGRADED episode > breaker BLOCKED > heuristic.
        used = await latest_site_window_usage(session, tenant_id=tenant_id, site_id=site_id)
        if breaker_open_for_usage(used=used):
            health["BROWSER_MONITORING"] = "BLOCKED"
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
            # EP-026 M3b: freshness is derived from the last trustworthy
            # success (last_success_at), never from attempts/updated_at.
            health[key] = _connector_health_with_freshness(
                connection.status,
                connection.last_success_at,
                now=datetime.now(UTC),
                key=key,
            )
    # EP-026 M3b: PUBLIC_CONFIG freshness derives from the latest successful
    # SCHEDULED snapshot (parse_status VALID / VALID_WITH_WARNINGS) using its
    # observed_at. Validation follow-ups and failed fetches are never a
    # success heartbeat.
    latest_good_snapshot = await session.scalar(
        select(PublicConfigSnapshot.observed_at)
        .where(
            PublicConfigSnapshot.tenant_id == tenant_id,
            PublicConfigSnapshot.site_id == site_id,
            PublicConfigSnapshot.fetch_kind == "SCHEDULED",
            PublicConfigSnapshot.parse_status.in_(("VALID", "VALID_WITH_WARNINGS")),
        )
        .order_by(PublicConfigSnapshot.observed_at.desc())
        .limit(1)
    )
    health["PUBLIC_CONFIG"] = freshness_state(
        latest_good_snapshot,
        now=datetime.now(UTC),
        threshold=SOURCE_FRESHNESS_THRESHOLDS["PUBLIC_CONFIG"],
    )
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
                    DataConnection.site_id == selected.id,
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
        reliability = await browser_source_health(
            session, tenant_id=actor.tenant_id, site_id=site_id
        )
    response: dict[str, object] = {"site_id": str(site_id), "sources": health}
    if reliability.source_event_id is not None:
        # Machine-readable explanation of current browser-source health.
        response["browser_monitoring_detail"] = {
            "source": "BROWSER_MONITORING",
            "state": reliability.state,
            "reason": reliability.reason,
            "detected_at": (
                reliability.detected_at.isoformat() if reliability.detected_at else None
            ),
            "source_event_id": (
                str(reliability.source_event_id) if reliability.source_event_id else None
            ),
            "source_event_code": reliability.source_event_code,
            "evidence_checkpoint_run_id": (
                str(reliability.evidence_checkpoint_run_id)
                if reliability.evidence_checkpoint_run_id
                else None
            ),
            "boundary": (
                "Describes Publisher Intelligence's browser observation source, "
                "not the publisher/site health."
            ),
        }
    return response
