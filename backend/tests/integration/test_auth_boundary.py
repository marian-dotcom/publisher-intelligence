"""M2 auth-boundary tests against PostgreSQL-backed state.

Covers gate scenarios 15/16/17/21/24/26/27 (expiry, revocation, disabled
account at restoration and login, logout/replay, invalid password, server-side
rotation) plus membership fail-closed semantics.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.auth.models import Operator, OperatorTenant, Session
from app.auth.security import hash_session_token
from app.auth.service import AuthError, AuthService
from app.db.models import Job, Tenant
from app.db.session import get_session_factory
from tests.integration.purge import make_purge

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
async def _clean_auth_state() -> None:
    from tests.integration.purge import make_purge

    purge = make_purge(get_session_factory)
    await purge()


@pytest.fixture
async def auth_service() -> AuthService:
    from app.db.session import get_session_factory

    return AuthService(get_session_factory())


async def _seed_operator(
    factory: Any,
    *,
    email: str = "auth-operator@example.com",
    password: str = "correct-horse-battery",
    is_active: bool = True,
) -> tuple[uuid.UUID, uuid.UUID, str]:
    tenant_id = uuid.uuid4()
    operator_id = uuid.uuid4()
    async with factory() as session, session.begin():
        session.add(Tenant(id=tenant_id, slug=f"auth-{tenant_id.hex[:8]}", name="Auth"))
        await session.flush()
        session.add(
            Operator(
                id=operator_id,
                actor_subject_id=uuid.uuid4(),
                email=email,
                password_hash=__import__(
                    "app.auth.security", fromlist=["hash_password"]
                ).hash_password(password),
                role="OPERATOR",
                is_active=is_active,
            )
        )
        await session.flush()
        session.add(OperatorTenant(operator_id=operator_id, tenant_id=tenant_id))
    return operator_id, tenant_id, email


async def _purge() -> None:
    from sqlalchemy import delete

    from app.db.session import get_session_factory
    from app.incidents.models import (
        Incident,
        InvestigationUsageEntry,
        LastKnownGoodRef,
        RetentionHold,
    )

    factory = get_session_factory()
    async with factory() as session, session.begin():
        await session.execute(delete(Session))
        await session.execute(delete(OperatorTenant))
        await session.execute(delete(Operator))
        for model in (RetentionHold, LastKnownGoodRef, InvestigationUsageEntry):
            await session.execute(delete(model))
        await session.execute(delete(Incident))
        from app.evidence.models import EventRelation, EvidencePack, ManualNote

        await session.execute(delete(EventRelation))
        await session.execute(delete(EvidencePack))
        await session.execute(delete(ManualNote))
        await session.execute(delete(Job))


@pytest.mark.asyncio
async def test_login_success_creates_rotated_session(auth_service: AuthService) -> None:
    from sqlalchemy import select

    from app.db.session import get_session_factory

    factory = get_session_factory()
    operator_id, tenant_id, email = await _seed_operator(factory)
    try:
        ctx = await auth_service.login(
            email=email, password="correct-horse-battery", tenant_id=tenant_id
        )
        assert ctx.actor_subject_id is not None
        async with factory() as session:
            rows = list(
                (
                    await session.scalars(select(Session).where(Session.operator_id == operator_id))
                ).all()
            )
        assert len(rows) == 1
        stored_hash = rows[0].token_hash
        assert stored_hash != ctx.raw_token
        assert len(stored_hash) == 64
        # Rotation: a second login revokes the first.
        await auth_service.login(email=email, password="correct-horse-battery", tenant_id=tenant_id)
        restored = await auth_service.resolve_session(raw_token=ctx.raw_token)
        assert restored is None
    finally:
        purge = make_purge(get_session_factory)
        await purge()


@pytest.mark.asyncio
async def test_invalid_password_fails_without_creating_session(auth_service: AuthService) -> None:
    factory = get_session_factory()
    _, tenant_id, email = await _seed_operator(factory)
    try:
        with pytest.raises(AuthError, match="authentication failed"):
            await auth_service.login(
                email=email, password="wrong-password-999", tenant_id=tenant_id
            )
        from sqlalchemy import func, select

        async with factory() as session:
            count = await session.scalar(select(func.count()).select_from(Session))
        assert count == 0
    finally:
        purge = make_purge(get_session_factory)
        await purge()


@pytest.mark.asyncio
async def test_disabled_operator_rejected_at_login_and_restoration(
    auth_service: AuthService,
) -> None:
    factory = get_session_factory()
    service = auth_service
    operator_id, tenant_id, email = await _seed_operator(factory)
    raw = "manual-opaque-token-for-disabled-case"

    from app.auth.security import hash_session_token

    token_hash = hash_session_token(raw)
    expires = datetime.now(UTC) + timedelta(hours=1)
    async with factory() as session, session.begin():
        session.add(
            Session(
                id=uuid.uuid4(),
                operator_id=operator_id,
                tenant_id=tenant_id,
                token_hash=token_hash,
                csrf_token_hash=hash_session_token("csrf"),
                created_at=datetime.now(UTC),
                expires_at=expires,
            )
        )
    # Disable the account.
    async with factory() as session, session.begin():
        op_row = await session.scalar(select(Operator).where(Operator.id == operator_id))
        assert op_row is not None
        op_row.is_active = False

    with pytest.raises(AuthError, match="authentication failed"):
        await service.login(email=email, password="correct-horse-battery", tenant_id=tenant_id)

    restored = await service.resolve_session(raw_token=raw)
    assert restored is None


@pytest.mark.asyncio
async def test_expired_and_revoked_sessions_fail_restoration(auth_service: AuthService) -> None:
    factory = get_session_factory()
    operator_id, tenant_id, _ = await _seed_operator(factory)
    expired_token = "expired-opaque-token"
    revoked_token = "revoked-opaque-token"
    now = datetime.now(UTC)
    async with factory() as session, session.begin():
        session.add_all(
            [
                Session(
                    id=uuid.uuid4(),
                    operator_id=operator_id,
                    tenant_id=tenant_id,
                    token_hash=hash_session_token(expired_token),
                    csrf_token_hash=hash_session_token("c1"),
                    created_at=now - timedelta(hours=13),
                    expires_at=now - timedelta(minutes=5),
                ),
                Session(
                    id=uuid.uuid4(),
                    operator_id=operator_id,
                    tenant_id=tenant_id,
                    token_hash=hash_session_token(revoked_token),
                    csrf_token_hash=hash_session_token("c2"),
                    created_at=now - timedelta(hours=1),
                    expires_at=now + timedelta(hours=1),
                    revoked_at=now - timedelta(minutes=1),
                ),
            ]
        )
    assert await auth_service.resolve_session(raw_token=expired_token) is None
    assert await auth_service.resolve_session(raw_token=revoked_token) is None


@pytest.mark.asyncio
async def test_logout_revokes_and_replay_is_rejected(auth_service: AuthService) -> None:
    factory = get_session_factory()
    _operator_id, tenant_id, email = await _seed_operator(factory)
    ctx = await auth_service.login(
        email=email, password="correct-horse-battery", tenant_id=tenant_id
    )
    assert await auth_service.logout(raw_token=ctx.raw_token) is True
    assert await auth_service.logout(raw_token=ctx.raw_token) is False
    assert await auth_service.resolve_session(raw_token=ctx.raw_token) is None


@pytest.mark.asyncio
async def test_membership_removal_fails_closed(auth_service: AuthService) -> None:
    factory = get_session_factory()
    operator_id, tenant_id, email = await _seed_operator(factory)
    ctx = await auth_service.login(
        email=email, password="correct-horse-battery", tenant_id=tenant_id
    )
    assert ctx is not None
    from sqlalchemy import delete

    async with factory() as session, session.begin():
        await session.execute(
            delete(OperatorTenant).where(
                OperatorTenant.operator_id == operator_id,
                OperatorTenant.tenant_id == tenant_id,
            )
        )
    restored = await auth_service.resolve_session(raw_token=ctx.raw_token)
    assert restored is None
