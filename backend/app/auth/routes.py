"""First-party auth HTTP endpoints (login/logout/session restoration)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr

from app.auth.dependencies import (
    SESSION_COOKIE,
    ActorContext,
    get_current_actor,
)
from app.auth.service import AuthError, AuthService
from app.db.session import get_session_factory

router = APIRouter(prefix="/auth", tags=["auth"])

SESSION_TTL_SECONDS = 12 * 60 * 60


def _service() -> AuthService:
    return AuthService(get_session_factory())


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    tenant_id: uuid.UUID


def _set_session_cookies(response: Response, *, token: str, csrf: str, max_age: int) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        secure=False,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        "pi_csrf",
        csrf,
        max_age=max_age,
        httponly=False,
        secure=False,
        samesite="lax",
        path="/",
    )


@router.post("/login")
async def login(payload: LoginRequest, response: Response) -> dict[str, object]:
    try:
        context = await _service().login(
            email=payload.email,
            password=payload.password,
            tenant_id=payload.tenant_id,
        )
    except AuthError:
        raise HTTPException(status_code=401, detail="authentication failed") from None
    _set_session_cookies(
        response, token=context.raw_token, csrf=context.csrf_token, max_age=SESSION_TTL_SECONDS
    )
    return {
        "actor_subject_id": str(context.actor_subject_id),
        "role": context.role,
        "csrf_token": context.csrf_token,
    }


@router.post("/logout")
async def logout(request: Request, response: Response) -> dict[str, bool]:
    from app.auth.dependencies import _unauthorized

    raw_token = request.cookies.get(SESSION_COOKIE)
    if not raw_token:
        raise _unauthorized()
    revoked = await _service().logout(raw_token=raw_token)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"revoked": revoked}


@router.get("/session")
async def session_state(
    actor: ActorContext = Depends(get_current_actor),  # noqa: B008
) -> dict[str, object]:
    return {
        "actor_subject_id": str(actor.actor_subject_id),
        "tenant_id": str(actor.tenant_id),
        "role": actor.role,
    }
