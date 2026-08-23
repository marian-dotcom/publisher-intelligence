"""Minimal authenticated Investigate intake endpoint (EP-020 semantics)."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.auth.dependencies import ActorContext, get_current_actor_with_csrf
from app.browser.models import Site
from app.browser.service import CheckpointService
from app.config.settings import get_settings
from app.db.session import get_session_factory
from app.incidents.intake import IncidentIntakeService
from app.incidents.persistence import InvestigationRepository
from app.jobs.queue import JobQueue

router = APIRouter(prefix="/investigations", tags=["investigations"])


class InvestigateRequest(BaseModel):
    site_id: str
    title: str
    symptom_family: str = "OTHER"
    description: str
    reported_start_at: str | None = None
    reported_end_at: str | None = None


def _intake_service() -> IncidentIntakeService:
    factory = get_session_factory()
    return IncidentIntakeService(
        repository=InvestigationRepository(factory),
        checkpoint_service=CheckpointService(factory, JobQueue(factory), get_settings()),
        session_factory=factory,
    )


def _parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


@router.post("")
async def open_investigation(
    payload: InvestigateRequest,
    actor: ActorContext = Depends(get_current_actor_with_csrf),  # noqa: B008
) -> dict[str, str]:
    try:
        site_uuid = uuid.UUID(payload.site_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail="resource not found") from error

    factory = get_session_factory()
    async with factory() as session:
        site = await session.scalar(select(Site).where(Site.id == site_uuid))
    if site is None or site.tenant_id != actor.tenant_id:
        raise HTTPException(status_code=404, detail="resource not found")

    incident, investigation_key = await _intake_service().open_investigation(
        tenant_id=actor.tenant_id,
        publisher_id=site.publisher_id,
        site_id=site.id,
        title=payload.title,
        symptom_family=payload.symptom_family,
        description=payload.description,
        reported_start_at=_parse(payload.reported_start_at),
        reported_end_at=_parse(payload.reported_end_at),
    )
    del actor  # actor provenance flows through authenticated boundary; created_by pending OPEN-003
    return {
        "incident_id": str(incident.id),
        "investigation_key": investigation_key,
        "status": incident.status,
    }
