"""First-party authentication service (Option A, EP-025a M2).

Fail-closed semantics: every restore/login path re-checks expiry, revocation,
account-active state, and tenant membership. Errors are deliberately generic
("authentication failed") so internal state is never disclosed.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.models import Operator, OperatorTenant, Session
from app.auth.security import (
    generate_csrf_token,
    generate_session_token,
    hash_password,
    hash_session_token,
    verify_password,
)

GENERIC_AUTH_FAILURE = "authentication failed"
SESSION_TTL_MINUTES = 12 * 60


@dataclass(frozen=True, slots=True)
class SessionContext:
    session_id: uuid.UUID
    operator_id: uuid.UUID
    actor_subject_id: uuid.UUID
    role: str
    raw_token: str
    csrf_token: str
    expires_at: datetime


class AuthError(Exception):
    """Deliberately generic authentication/authorization failure."""


class AuthService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create_operator(
        self,
        *,
        email: str,
        password: str,
        actor_subject_id: uuid.UUID | None = None,
        role: str = "OPERATOR",
    ) -> Operator:
        from app.incidents.contracts import InvestigationStateError

        if not email.strip() or "@" not in email:
            raise InvestigationStateError("valid operator email is required")
        if len(password) < 10:
            raise InvestigationStateError("operator password must be at least 10 characters")
        subject = actor_subject_id or uuid.uuid4()
        async with self._session_factory() as session, session.begin():
            operator = Operator(
                id=uuid.uuid4(),
                actor_subject_id=subject,
                email=email.strip().lower(),
                password_hash=hash_password(password),
                role=role,
                is_active=True,
            )
            session.add(operator)
            await session.flush()
            return operator

    async def add_membership(self, *, operator_id: uuid.UUID, tenant_id: uuid.UUID) -> None:

        async with self._session_factory() as session, session.begin():
            exists = await session.scalar(
                select(OperatorTenant.tenant_id).where(
                    OperatorTenant.operator_id == operator_id,
                    OperatorTenant.tenant_id == tenant_id,
                )
            )
            if exists is not None:
                return
            session.add(OperatorTenant(operator_id=operator_id, tenant_id=tenant_id))

    async def login(
        self,
        *,
        email: str,
        password: str,
        tenant_id: uuid.UUID,
    ) -> SessionContext:
        """Verify credentials and membership; rotate in a fresh session.

        Invalid password / unknown email / disabled account all produce the
        same generic failure; no session is persisted on failure.
        """
        raw_token = generate_session_token()
        csrf_token = generate_csrf_token()
        token_hash = hash_session_token(raw_token)
        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=SESSION_TTL_MINUTES)
        async with self._session_factory() as session, session.begin():
            operator = await session.scalar(
                select(Operator).where(
                    Operator.email == email.strip().lower(),
                    Operator.is_active.is_(True),
                )
            )
            if operator is None or not verify_password(operator.password_hash, password):
                raise AuthError(GENERIC_AUTH_FAILURE)
            member = await session.scalar(
                select(OperatorTenant).where(
                    OperatorTenant.operator_id == operator.id,
                    OperatorTenant.tenant_id == tenant_id,
                )
            )
            if member is None:
                raise AuthError(GENERIC_AUTH_FAILURE)
            # Rotation: revoke any prior active sessions for this operator.
            prior = await session.scalars(
                select(Session).where(
                    Session.operator_id == operator.id,
                    Session.revoked_at.is_(None),
                )
            )
            for old in prior:
                old.revoked_at = now
            session.add(
                Session(
                    id=uuid.uuid4(),
                    operator_id=operator.id,
                    tenant_id=tenant_id,
                    token_hash=token_hash,
                    csrf_token_hash=hash_session_token(csrf_token),
                    created_at=now,
                    expires_at=expires_at,
                )
            )
            return SessionContext(
                session_id=uuid.uuid4(),
                operator_id=operator.id,
                actor_subject_id=operator.actor_subject_id,
                role=operator.role,
                raw_token=raw_token,
                csrf_token=csrf_token,
                expires_at=expires_at,
            )

    async def resolve_session(self, *, raw_token: str) -> SessionContext | None:
        """Restore an authenticated context; fail closed on any invalid state."""
        token_hash = hash_session_token(raw_token)
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            query = (
                select(Session, Operator, OperatorTenant.tenant_id)
                .join(Operator, Operator.id == Session.operator_id)
                .join(
                    OperatorTenant,
                    (OperatorTenant.operator_id == Operator.id)
                    & (OperatorTenant.tenant_id == Session.tenant_id),
                )
            )
            row = (
                await session.execute(
                    query.where(
                        Session.token_hash == token_hash,
                        Session.revoked_at.is_(None),
                        Session.expires_at > now,
                        Operator.is_active.is_(True),
                    )
                )
            ).first()
            if row is None:
                return None
            session_row, operator, _tenant_id = row
            return SessionContext(
                session_id=session_row.id,
                operator_id=operator.id,
                actor_subject_id=operator.actor_subject_id,
                role=operator.role,
                raw_token=raw_token,
                csrf_token="",
                expires_at=session_row.expires_at,
            )

    def verify_csrf(self, *, stored_hash: str, presented: str) -> bool:
        return hash_session_token(presented) == stored_hash

    async def logout(self, *, raw_token: str) -> bool:
        token_hash = hash_session_token(raw_token)
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            row = await session.scalar(
                select(Session).where(
                    Session.token_hash == token_hash,
                    Session.revoked_at.is_(None),
                )
            )
            if row is None:
                return False
            row.revoked_at = now
            return True
