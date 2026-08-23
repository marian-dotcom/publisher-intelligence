"""Authenticated actor/tenant request boundary and CSRF enforcement."""

import uuid
from dataclasses import dataclass

from fastapi import HTTPException, Request

from app.auth.models import Session as SessionRow
from app.auth.service import AuthService
from app.db.session import get_session_factory

SESSION_COOKIE = "pi_session"
CSRF_HEADER = "X-CSRF-Token"


def _service() -> AuthService:
    return AuthService(get_session_factory())


@dataclass(frozen=True, slots=True)
class ActorContext:
    session_id: uuid.UUID
    operator_id: uuid.UUID
    actor_subject_id: uuid.UUID
    tenant_id: uuid.UUID
    role: str


def _unauthorized() -> HTTPException:
    return HTTPException(status_code=401, detail="authentication required")


def _csrf_failure() -> HTTPException:
    return HTTPException(status_code=403, detail="CSRF validation failed")


async def resolve_actor(request: Request) -> tuple[ActorContext, SessionRow]:
    """Resolve the opaque session cookie into a fail-closed actor context."""
    raw_token = request.cookies.get(SESSION_COOKIE)
    if not raw_token:
        raise _unauthorized()
    service = _service()
    context = await service.resolve_session(raw_token=raw_token)
    if context is None:
        raise _unauthorized()
    factory = get_session_factory()
    async with factory() as session:
        from sqlalchemy import select

        row = await session.scalar(select(SessionRow).where(SessionRow.id == context.session_id))
    if row is None:
        raise _unauthorized()
    actor = ActorContext(
        session_id=row.id,
        operator_id=context.operator_id,
        actor_subject_id=context.actor_subject_id,
        tenant_id=row.tenant_id,
        role=context.role,
    )
    return actor, row


async def get_current_actor(request: Request) -> ActorContext:
    actor, _row = await resolve_actor(request)
    return actor


async def get_current_actor_with_csrf(request: Request) -> ActorContext:
    """Actor resolution plus server-verifiable CSRF proof for state-changing requests."""
    actor, row = await resolve_actor(request)
    presented = request.headers.get(CSRF_HEADER)
    service = _service()
    if not presented or not service.verify_csrf(
        stored_hash=row.csrf_token_hash, presented=presented
    ):
        raise _csrf_failure()
    return actor


def require_tenant(actor: ActorContext, tenant_id: uuid.UUID) -> None:
    """Fail closed when a resource is not owned by the authenticated tenant."""
    if actor.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="resource not found")
