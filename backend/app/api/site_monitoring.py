"""EP-030 M1: authenticated per-site monitoring-control endpoint.

One idempotent command — PUT /product/sites/{site_id}/monitoring — gated on
ADMIN + valid CSRF, with the tenant derived exclusively from the authenticated
actor. Missing/foreign sites return a non-disclosing 404. The endpoint only
persists the monitoring authorization state; it starts no runs, enqueues no
work, and does not contact the publisher. Scheduler/worker enforcement is M2.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from app.auth.dependencies import ActorContext, get_current_actor_with_csrf
from app.browser.monitoring_control import (
    SiteMonitoringNotFoundError,
    monitoring_control_result,
    set_monitoring_state,
)
from app.db.session import get_session_factory

router = APIRouter(prefix="/product", tags=["product"])

MONITORING_CADENCE = {
    "identifier": "six-hour",
    "hours": 6,
}


class UpdateMonitoringRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


@router.put("/sites/{site_id}/monitoring")
async def update_site_monitoring(
    site_id: uuid.UUID,
    payload: UpdateMonitoringRequest,
    actor: ActorContext = Depends(get_current_actor_with_csrf),  # noqa: B008
) -> dict[str, object]:
    if actor.role != "ADMIN":
        raise HTTPException(status_code=403, detail="insufficient permissions")

    factory = get_session_factory()
    try:
        await set_monitoring_state(
            factory,
            tenant_id=actor.tenant_id,
            site_id=site_id,
            enabled=payload.enabled,
            actor_id=actor.actor_subject_id,
        )
    except SiteMonitoringNotFoundError as error:
        raise HTTPException(status_code=404, detail="resource not found") from error

    async with factory() as session:
        result = await monitoring_control_result(
            session,
            tenant_id=actor.tenant_id,
            site_id=site_id,
        )

    return {
        "site_id": str(result.site_id),
        "enabled": result.enabled,
        "monitoring_state_updated_at": result.monitoring_state_updated_at.isoformat(),
        "cadence": MONITORING_CADENCE,
        "next_scheduled_for": (
            result.next_scheduled_for.isoformat() if result.next_scheduled_for else None
        ),
        "in_flight_scheduled_run_status": result.in_flight_scheduled_run_status,
    }
