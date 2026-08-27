from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.auth.dependencies import ActorContext, get_current_actor_with_csrf
from app.browser.operator_registration import (
    DuplicateSiteRegistrationError,
    OperatorSiteRegistrationService,
)
from app.browser.security import BrowserBlockedError
from app.config.settings import get_settings
from app.db.session import get_session_factory
from app.jobs.queue import JobQueue

router = APIRouter(prefix="/product", tags=["product"])


class RegisterSiteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    publisher_name: str = Field(min_length=1, max_length=200)
    site_name: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=2048)


def _registration_service() -> OperatorSiteRegistrationService:
    factory = get_session_factory()
    return OperatorSiteRegistrationService(factory, JobQueue(factory), get_settings())


@router.post("/sites", status_code=status.HTTP_201_CREATED)
async def register_site(
    payload: RegisterSiteRequest,
    actor: ActorContext = Depends(get_current_actor_with_csrf),  # noqa: B008
) -> dict[str, str]:
    try:
        registered = await _registration_service().register_for_tenant(
            tenant_id=actor.tenant_id,
            publisher_name=payload.publisher_name,
            site_name=payload.site_name,
            url=payload.url,
        )
    except DuplicateSiteRegistrationError as error:
        raise HTTPException(status_code=409, detail="site already registered") from error
    except BrowserBlockedError as error:
        raise HTTPException(status_code=400, detail="site URL is not an allowed public target") from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail="invalid site registration") from error

    return {
        "site_id": str(registered.site_id),
        "canonical_domain": registered.canonical_domain,
        "checkpoint_run_id": str(registered.checkpoint_run_id),
        "diagnostic_status": "PENDING",
    }
