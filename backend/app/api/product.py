"""Product read APIs: Home/status, source health, site health,
diagnostic results (EP-025a P2-A, EP-029 M2a)."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import ActorContext, get_current_actor
from app.browser.access_reliability import classification_from_storage
from app.browser.cost import breaker_open_for_usage, latest_site_window_usage
from app.browser.models import Artifact, CheckpointRun, Publisher, Site
from app.config.settings import Settings
from app.connectors.freshness import SOURCE_FRESHNESS_THRESHOLDS, freshness_state
from app.connectors.models import DataConnection
from app.db.session import get_session_factory
from app.events.source_health import browser_source_health
from app.incidents.models import Incident
from app.operations import operations_snapshot
from app.public_config.models import PublicConfigSnapshot
from app.storage.s3 import S3Storage

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


# EP-028 M2: a bounded initial-diagnostic projection for the operator's first
# controlled observation. Qualifying runs are limited to DIAGNOSTIC /
# OPERATOR_UI checkpoints owned by the authenticated actor's tenant and the
# selected site. This projection is deliberately separate from six-hour
# SCHEDULED source health and is never an LKG/comparison candidate.
_BROWSER_ACCESS_CLASSIFICATION_STATES = frozenset(("ok", "degraded", "challenge_suspected"))


async def _initial_diagnostic_projection(
    session: AsyncSession, *, tenant_id: uuid.UUID, site_id: uuid.UUID
) -> dict[str, object] | None:
    """Return a bounded {run_id, status, completed_at, classification} view of
    the latest qualifying OPERATOR_UI diagnostic, or None when absent.

    Deterministic latest selection uses the immutable creation timestamp plus
    the run id as a stable tie-breaker; a bare LIMIT 1 without ordering would be
    nondeterministic. Only canonical scalar fields are exposed.
    """
    run = await session.scalar(
        select(CheckpointRun)
        .where(
            CheckpointRun.tenant_id == tenant_id,
            CheckpointRun.site_id == site_id,
            CheckpointRun.observation_kind == "DIAGNOSTIC",
            CheckpointRun.trigger_source == "OPERATOR_UI",
        )
        .order_by(CheckpointRun.created_at.desc(), CheckpointRun.id.desc())
        .limit(1)
    )
    if run is None:
        return None
    classification = classification_from_storage(run.browser_access_classification)
    classification_state = classification.state if classification is not None else None
    if classification_state is not None and (
        classification_state not in _BROWSER_ACCESS_CLASSIFICATION_STATES
    ):
        classification_state = None
    return {
        "run_id": str(run.id),
        "status": run.status,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "browser_access_classification": classification_state,
    }


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
        initial_diagnostic: dict[str, object] | None = None
        if selected is not None:
            sources = await _source_health_rows(
                session,
                tenant_id=actor.tenant_id,
                site_id=selected.id,
            )
            initial_diagnostic = await _initial_diagnostic_projection(
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
        "initial_diagnostic": initial_diagnostic,
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


# EP-029 M2a: diagnostic-results read surface for initial DIAGNOSTIC/OPERATOR_UI runs.
# These endpoints expose the collected evidence through an authenticated API proxy.
# MinIO stays private; artifacts are proxied read-only with per-request
# tenant->site->run->artifact->kind allowlist enforcement.
# Allowed artifact kinds for diagnostic results:
_DIAGNOSTIC_ARTIFACT_KINDS = frozenset(
    {
        "SCREENSHOT_VIEWPORT",
        "SCREENSHOT_VIEWPORT_PRECONSENT",
        "SCREENSHOT_VIEWPORT_POSTCONSENT",
        "SCREENSHOT_FULL_PAGE",
        "RAW_DOM",
        "NORMALIZED_DOM",
        "MANIFEST",
    }
)

# Server-side MIME type and disposition mapping for allowed artifact kinds.
# This is the authoritative source for Content-Type and disposition; never trust stored metadata.
_ARTIFACT_KIND_META: dict[str, dict[str, str]] = {
    "SCREENSHOT_VIEWPORT": {"media_type": "image/png", "disposition": "inline", "extension": "png"},
    "SCREENSHOT_VIEWPORT_PRECONSENT": {
        "media_type": "image/png",
        "disposition": "inline",
        "extension": "png",
    },
    "SCREENSHOT_VIEWPORT_POSTCONSENT": {
        "media_type": "image/png",
        "disposition": "inline",
        "extension": "png",
    },
    "SCREENSHOT_FULL_PAGE": {
        "media_type": "image/png",
        "disposition": "inline",
        "extension": "png",
    },
    "RAW_DOM": {"media_type": "text/html", "disposition": "attachment", "extension": "html"},
    "NORMALIZED_DOM": {
        "media_type": "application/json",
        "disposition": "attachment",
        "extension": "json",
    },
    "MANIFEST": {
        "media_type": "application/json",
        "disposition": "attachment",
        "extension": "json",
    },
}


async def _get_latest_operator_diagnostic(
    session: AsyncSession, *, tenant_id: uuid.UUID, site_id: uuid.UUID
) -> CheckpointRun | None:
    """Return the latest DIAGNOSTIC/OPERATOR_UI checkpoint run for the site, or None."""
    result = await session.scalar(
        select(CheckpointRun)
        .where(
            CheckpointRun.tenant_id == tenant_id,
            CheckpointRun.site_id == site_id,
            CheckpointRun.observation_kind == "DIAGNOSTIC",
            CheckpointRun.trigger_source == "OPERATOR_UI",
        )
        .order_by(CheckpointRun.created_at.desc(), CheckpointRun.id.desc())
        .limit(1)
    )
    return result if isinstance(result, CheckpointRun) else None


def _classification_state(run: CheckpointRun) -> str | None:
    classification = classification_from_storage(run.browser_access_classification)
    state = classification.state if classification is not None else None
    if state is not None and state not in _BROWSER_ACCESS_CLASSIFICATION_STATES:
        return None
    return state


@router.get("/sites/{site_id}/diagnostic-results")
async def diagnostic_results(
    site_id: uuid.UUID,
    actor: ActorContext = Depends(get_current_actor),  # noqa: B008
) -> dict[str, object]:
    """Tenant-scoped summary of the latest DIAGNOSTIC/OPERATOR_UI run for the site."""
    factory = get_session_factory()
    async with factory() as session:
        # Verify site belongs to actor tenant
        site = await session.scalar(
            select(Site).where(Site.id == site_id, Site.tenant_id == actor.tenant_id)
        )
        if site is None:
            raise HTTPException(status_code=404, detail="resource not found")

        run = await _get_latest_operator_diagnostic(
            session, tenant_id=actor.tenant_id, site_id=site_id
        )
        if run is None:
            raise HTTPException(status_code=404, detail="no diagnostic run found")

        # Get artifacts for this run
        artifacts = list(
            (
                await session.scalars(
                    select(Artifact).where(
                        Artifact.tenant_id == actor.tenant_id,
                        Artifact.site_id == site_id,
                        Artifact.checkpoint_run_id == run.id,
                        Artifact.artifact_type.in_(_DIAGNOSTIC_ARTIFACT_KINDS),
                    )
                )
            ).all()
        )

        publisher = await session.scalar(select(Publisher).where(Publisher.id == site.publisher_id))

    # Build artifacts summary
    artifact_summaries = [
        {
            "artifact_id": str(a.id),
            "artifact_type": a.artifact_type,
            "content_type": a.content_type,
            "byte_size": a.byte_size,
            "sha256": a.sha256,
        }
        for a in artifacts
    ]

    return {
        "site_id": str(site.id),
        "site_name": site.name,
        "site_domain": site.canonical_domain,
        "publisher_name": publisher.name if publisher else None,
        "run": {
            "run_id": str(run.id),
            "observation_kind": run.observation_kind,
            "trigger_source": run.trigger_source,
            "trigger_correlation_id": str(run.trigger_correlation_id)
            if run.trigger_correlation_id
            else None,
            "status": run.status,
            "attempt_count": run.attempt_count,
            "final_url": run.final_url,
            "http_status": run.http_status,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "browser_access_classification": _classification_state(run),
            "scenario_id": str(run.scenario_id),
            "collector_bundle_version": run.collector_bundle_version,
            "limitations": run.limitations,
        },
        "artifacts": artifact_summaries,
    }


@router.get("/sites/{site_id}/diagnostic-artifacts/{artifact_id}")
async def diagnostic_artifact(
    site_id: uuid.UUID,
    artifact_id: uuid.UUID,
    actor: ActorContext = Depends(get_current_actor),  # noqa: B008
) -> Response:
    """Stream a single artifact for a DIAGNOSTIC/OPERATOR_UI run.
    Enforces tenant->site->run->artifact->kind allowlist (404 on foreign/nonexistent).
    """
    factory = get_session_factory()
    async with factory() as session:
        # Verify site belongs to actor tenant
        site = await session.scalar(
            select(Site).where(Site.id == site_id, Site.tenant_id == actor.tenant_id)
        )
        if site is None:
            raise HTTPException(status_code=404, detail="resource not found")

        artifact = await session.scalar(
            select(Artifact).where(
                Artifact.id == artifact_id,
                Artifact.tenant_id == actor.tenant_id,
                Artifact.site_id == site_id,
                Artifact.artifact_type.in_(_DIAGNOSTIC_ARTIFACT_KINDS),
            )
        )
        if artifact is None:
            raise HTTPException(status_code=404, detail="resource not found")

        # Verify artifact belongs to a DIAGNOSTIC/OPERATOR_UI run
        run = await session.scalar(
            select(CheckpointRun).where(
                CheckpointRun.id == artifact.checkpoint_run_id,
                CheckpointRun.tenant_id == actor.tenant_id,
                CheckpointRun.site_id == site_id,
                CheckpointRun.observation_kind == "DIAGNOSTIC",
                CheckpointRun.trigger_source == "OPERATOR_UI",
            )
        )
        if run is None:
            raise HTTPException(status_code=404, detail="resource not found")

        # Enforce per-artifact response size bound (SECURITY.md §75: 20 MB incident
        # attachment limit; climatologie.ro screenshot ~4.6 MB; cap at 20 MB).
        MAX_ARTIFACT_BYTES = 20 * 1024 * 1024
        if artifact.byte_size > MAX_ARTIFACT_BYTES:
            raise HTTPException(
                status_code=413, detail="artifact exceeds maximum allowed size"
            ) from None

        # Stream from MinIO through authenticated proxy
        settings = Settings()
        storage = S3Storage(settings)
        try:
            content = storage.get_bytes(key=artifact.object_key)
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            if error_code == "NoSuchKey":
                raise HTTPException(status_code=404, detail="resource not found") from None
            raise HTTPException(status_code=500, detail="storage read failed") from None

        # Enforce returned content length matches stored byte_size
        # (defense against corrupted reads)
        if len(content) != artifact.byte_size:
            raise HTTPException(status_code=500, detail="artifact size mismatch") from None

    # Server-side MIME and disposition from trusted artifact kind (never trust stored metadata)
    meta = _ARTIFACT_KIND_META[artifact.artifact_type]
    media_type = meta["media_type"]
    disposition = meta["disposition"]
    extension = meta["extension"]

    # Safe deterministic filename from trusted artifact type and ID (not raw object key)
    safe_filename = (
        f"diagnostic-{artifact.artifact_type.lower()}-{str(artifact.id)[:8]}.{extension}"
    )

    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'{disposition}; filename="{safe_filename}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Length": str(artifact.byte_size),
        },
    )
