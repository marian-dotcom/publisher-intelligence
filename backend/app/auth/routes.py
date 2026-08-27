"""First-party auth HTTP endpoints (login/logout/session restoration)."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from app.auth.dependencies import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    ActorContext,
    _unauthorized,
    get_current_actor,
    get_current_actor_with_csrf,
)
from app.auth.rate_limit import check_rate_limit, clear_rate_limit_for_ip
from app.auth.service import AuthError, AuthService
from app.config.settings import Settings, get_settings
from app.db.session import get_session_factory

router = APIRouter(prefix="/auth", tags=["auth"])

SESSION_TTL_SECONDS = 12 * 60 * 60


def _service() -> AuthService:
    return AuthService(get_session_factory())


class LoginRequest(BaseModel):
    email: str
    password: str
    tenant_id: uuid.UUID


def _set_session_cookies(
    response: Any,
    *,
    token: str,
    csrf: str,
    max_age: int,
    settings: Settings | None = None,
) -> None:
    """Emit session + double-submit CSRF cookies.

    Fail-closed (SECURITY.md §201): outside local/test environments the
    cookies MUST be Secure; a configuration that would emit Secure=False is a
    programming error and raises instead of degrading silently.
    """

    app_settings = settings or get_settings()
    secure = app_settings.cookie_secure
    if app_settings.environment in ("staging", "production") and not secure:
        raise RuntimeError(
            "refusing to emit auth cookies with Secure=False in "
            f"{app_settings.environment} (SECURITY.md §201)"
        )
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf,
        max_age=max_age,
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
    )


@router.post("/login")
async def login(payload: LoginRequest, request: Request, response: Response) -> dict[str, object]:
    check_rate_limit(request)
    try:
        context = await _service().login(
            email=payload.email,
            password=payload.password,
            tenant_id=payload.tenant_id,
        )
    except AuthError:
        raise HTTPException(status_code=401, detail="authentication failed") from None
    clear_rate_limit_for_ip(request)
    _set_session_cookies(
        response, token=context.raw_token, csrf=context.csrf_token, max_age=SESSION_TTL_SECONDS
    )
    return {
        "actor_subject_id": str(context.actor_subject_id),
        "role": context.role,
        "csrf_token": context.csrf_token,
    }


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    actor: ActorContext = Depends(get_current_actor_with_csrf),  # noqa: B008
) -> dict[str, bool]:
    del actor  # CSRF proof and tenant-bound authentication happen in the dependency.
    raw_token = request.cookies.get(SESSION_COOKIE)
    if not raw_token:
        raise _unauthorized()
    revoked = await _service().logout(raw_token=raw_token)
    secure = get_settings().cookie_secure
    response.delete_cookie(SESSION_COOKIE, path="/", samesite="lax", secure=secure)
    response.delete_cookie(CSRF_COOKIE, path="/", samesite="lax", secure=secure)
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
