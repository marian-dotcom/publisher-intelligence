"""EP-026 M2b-2: deterministic browser-source health projection.

Derives the CURRENT health of our browser-monitoring source for a site from
immutable reliability events — no persistent source-health state exists.

Invariants:
- OBSERVATION FAILURE ≠ PUBLISHER FAILURE: this describes Publisher
  Intelligence's browser observation source only;
- reliability Events are immutable observation-level facts; "current health"
  is a deterministic read-time projection over them;
- a degradation/challenge Event opens an episode; a later qualifying healthy
  DIAGNOSTIC recheck emits BROWSER_SOURCE_RECOVERED, closing it;
- no reliability events ⇒ HEALTHY (quiet-by-default product semantics);
- GA4/GSC/GAM/public-config outcomes cannot influence this projection.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.models import Event, EventEvidenceRef
from app.events.registry import definition_id

DEGRADATION_CODES = (
    "BROWSER_SOURCE_DEGRADED",
    "BROWSER_ACCESS_CHALLENGE_SUSPECTED",
)
RECOVERY_CODE = "BROWSER_SOURCE_RECOVERED"


@dataclass(frozen=True, slots=True)
class BrowserSourceHealth:
    """Current deterministic health of OUR browser monitoring source."""

    state: str  # "HEALTHY" | "DEGRADED"
    reason: str | None
    detected_at: datetime | None
    source_event_id: uuid.UUID | None
    source_event_code: str | None
    evidence_checkpoint_run_id: uuid.UUID | None


def _code_for(event: Event) -> str:
    for code in (*DEGRADATION_CODES, RECOVERY_CODE):
        if event.event_definition_id == definition_id(code):
            return code
    raise ValueError("non-reliability event reached source-health projection")


def _reason_for(event: Event, code: str) -> str:
    details = event.details if isinstance(event.details, dict) else {}
    after = details.get("after")
    if isinstance(after, dict):
        reason = after.get("reason")
        if isinstance(reason, str) and reason:
            return reason[:200]
    return event.summary[:200]


async def _trigger_checkpoint_run_id(
    session: AsyncSession, event_id: uuid.UUID
) -> uuid.UUID | None:
    ref = await session.scalar(
        select(EventEvidenceRef)
        .where(
            EventEvidenceRef.event_id == event_id,
            EventEvidenceRef.evidence_kind == "CHECKPOINT_RUN",
            EventEvidenceRef.relation.in_(("TRIGGER_AFTER", "TRIGGER_BEFORE", "BEFORE")),
        )
        .order_by(EventEvidenceRef.id)
        .limit(1)
    )
    return ref.source_id if ref is not None else None


async def browser_source_health(
    session: AsyncSession, *, tenant_id: uuid.UUID, site_id: uuid.UUID
) -> BrowserSourceHealth:
    """Resolve current browser-monitoring source health deterministically."""
    latest = await session.scalar(
        select(Event)
        .where(
            Event.tenant_id == tenant_id,
            Event.site_id == site_id,
            Event.event_definition_id.in_(
                [definition_id(code) for code in (*DEGRADATION_CODES, RECOVERY_CODE)]
            ),
            Event.status.in_(("RECORDED", "ACTIVE")),
        )
        .order_by(Event.detected_at.desc(), Event.created_at.desc(), Event.id.desc())
        .limit(1)
    )
    if latest is None:
        return BrowserSourceHealth(
            state="HEALTHY",
            reason=None,
            detected_at=None,
            source_event_id=None,
            source_event_code=None,
            evidence_checkpoint_run_id=None,
        )
    code = _code_for(latest)
    trigger_run_id = await _trigger_checkpoint_run_id(session, latest.id)
    if code in DEGRADATION_CODES:
        return BrowserSourceHealth(
            state="DEGRADED",
            reason=_reason_for(latest, code),
            detected_at=latest.detected_at,
            source_event_id=latest.id,
            source_event_code=code,
            evidence_checkpoint_run_id=trigger_run_id,
        )
    return BrowserSourceHealth(
        state="HEALTHY",
        reason=_reason_for(latest, code),
        detected_at=latest.detected_at,
        source_event_id=latest.id,
        source_event_code=code,
        evidence_checkpoint_run_id=trigger_run_id,
    )


async def open_degradation_episode(
    session: AsyncSession, *, tenant_id: uuid.UUID, site_id: uuid.UUID
) -> dict[str, object] | None:
    """Return the open degradation episode for the site, if any.

    An episode is OPEN when the most recent reliability event is a degradation
    (not yet followed by BROWSER_SOURCE_RECOVERED). Returns bounded context:
    event id/code/detected_at plus its triggering checkpoint run.
    """
    latest = await session.scalar(
        select(Event)
        .where(
            Event.tenant_id == tenant_id,
            Event.site_id == site_id,
            Event.event_definition_id.in_(
                [definition_id(code) for code in (*DEGRADATION_CODES, RECOVERY_CODE)]
            ),
            Event.status.in_(("RECORDED", "ACTIVE")),
        )
        .order_by(Event.detected_at.desc(), Event.created_at.desc(), Event.id.desc())
        .limit(1)
    )
    if latest is None or _code_for(latest) == RECOVERY_CODE:
        return None
    return {
        "event_id": latest.id,
        "code": _code_for(latest),
        "detected_at": latest.detected_at,
        "checkpoint_run_id": await _trigger_checkpoint_run_id(session, latest.id),
    }
