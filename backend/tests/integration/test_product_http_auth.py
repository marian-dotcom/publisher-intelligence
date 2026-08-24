"""EP-025a Part 1 HTTP-layer validation: auth sessions, CSRF, Investigate intake."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.auth.models import Operator, OperatorTenant
from app.auth.models import Session as SessionRow
from app.auth.security import hash_password
from app.browser.models import Publisher, Site
from app.db.models import Tenant
from app.db.session import get_session_factory
from app.main import app
from tests.integration.purge import make_purge

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _clean_db() -> None:
    asyncio.run(make_purge(get_session_factory)())


@pytest.fixture
async def http_operator() -> tuple[uuid.UUID, list[uuid.UUID], str]:
    factory = get_session_factory()
    operator_id = uuid.uuid4()
    subject_id = uuid.uuid4()
    email = f"op-{operator_id.hex[:8]}@example.com"
    tenant_ids: list[uuid.UUID] = []
    async with factory() as session, session.begin():
        for index in range(2):
            tenant_id = uuid.uuid4()
            tenant_ids.append(tenant_id)
            session.add(Tenant(id=tenant_id, slug=f"http{index}-{tenant_id.hex[:8]}", name="HTTP"))
        await session.flush()
        session.add(
            Operator(
                id=operator_id,
                actor_subject_id=subject_id,
                email=email,
                password_hash=hash_password("correct-horse-battery"),
                role="OPERATOR",
                is_active=True,
            )
        )
        await session.flush()
        for tenant_id in tenant_ids:
            session.add(OperatorTenant(operator_id=operator_id, tenant_id=tenant_id))
    return operator_id, tenant_ids, email


async def _seed_site_for(tenant_id: uuid.UUID) -> uuid.UUID:
    factory = get_session_factory()
    publisher_id = uuid.uuid4()
    site_id = uuid.uuid4()
    async with factory() as session, session.begin():
        session.add(
            Publisher(
                id=publisher_id,
                tenant_id=tenant_id,
                name="HTTP Publisher",
                slug=f"pub-{publisher_id.hex[:8]}",
                default_timezone="UTC",
                status="ACTIVE",
            )
        )
        await session.flush()
        session.add(
            Site(
                id=site_id,
                tenant_id=tenant_id,
                publisher_id=publisher_id,
                name="HTTP Site",
                canonical_domain=f"{site_id.hex}.example.com",
                canonical_scheme="https",
                timezone="UTC",
                status="ACTIVE",
            )
        )
    return site_id


async def _insert_session_row(
    *,
    tenant_id: uuid.UUID,
    operator_id: uuid.UUID,
    raw_token: str,
    csrf_token: str,
    expires_at: datetime,
    revoked_at: datetime | None = None,
) -> None:
    import hashlib

    factory = get_session_factory()
    async with factory() as session, session.begin():
        session.add(
            SessionRow(
                id=uuid.uuid4(),
                operator_id=operator_id,
                tenant_id=tenant_id,
                token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
                csrf_token_hash=hashlib.sha256(csrf_token.encode()).hexdigest(),
                created_at=datetime.now(UTC),
                expires_at=expires_at,
                revoked_at=revoked_at,
            )
        )


async def _disable_operator(operator_id: uuid.UUID) -> None:
    factory = get_session_factory()
    async with factory() as session, session.begin():
        op = await session.scalar(select(Operator).where(Operator.id == operator_id))
        assert op is not None
        op.is_active = False


async def _remove_membership(operator_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    factory = get_session_factory()
    async with factory() as session, session.begin():
        await session.execute(
            delete(OperatorTenant).where(
                OperatorTenant.operator_id == operator_id,
                OperatorTenant.tenant_id == tenant_id,
            )
        )


def _cookie_header(response: Any) -> str:
    return " | ".join(response.headers.get_list("set-cookie"))


def _intake_payload(site_id: uuid.UUID) -> dict[str, object]:
    return {
        "site_id": str(site_id),
        "title": "HTTP intake scenario",
        "symptom_family": "OTHER",
        "description": "Investigate via HTTP boundary.",
        "reported_start_at": "2026-08-22T00:00:00+00:00",
    }


def test_login_success_sets_hardened_cookies_and_body_token(
    http_operator: tuple[uuid.UUID, list[uuid.UUID], str],
) -> None:
    client = TestClient(app)
    _operator_id, tenants, email = http_operator
    login_response = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "tenant_id": str(tenants[0]),
        },
    )
    assert login_response.status_code == 200
    body = login_response.json()
    assert body["role"] == "OPERATOR"
    assert len(body["csrf_token"]) >= 16
    cookie_header = _cookie_header(login_response)
    assert (
        "pi_session=" in cookie_header and "HttpOnly" in cookie_header.split("pi_session=")[1][:60]
    )
    assert "pi_csrf=" in cookie_header
    # Raw session secret never appears in a JSON response body.
    assert "pi_session=" not in login_response.text


def test_invalid_credentials_rejected_without_session(
    http_operator: tuple[uuid.UUID, list[uuid.UUID], str],
) -> None:
    _, tenants, email = http_operator[0], [http_operator[1][0]], http_operator[2]
    response = TestClient(app).post(
        "/auth/login",
        json={"email": email, "password": "wrong-password", "tenant_id": str(tenants[0])},
    )
    assert response.status_code == 401
    assert "pi_session" not in response.cookies


def test_disabled_operator_cannot_login(
    http_operator: tuple[uuid.UUID, list[uuid.UUID], str],
) -> None:
    operator_id, tenants, email = http_operator
    asyncio.run(_disable_operator(operator_id))
    response = TestClient(app).post(
        "/auth/login",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "tenant_id": str(tenants[0]),
        },
    )
    assert response.status_code == 401


def test_session_restoration_returns_actor_context(
    http_operator: tuple[uuid.UUID, list[uuid.UUID], str],
) -> None:
    _operator_id, tenants, email = http_operator
    client = TestClient(app)
    login_response = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "tenant_id": str(tenants[0]),
        },
    )
    assert login_response.status_code == 200
    state = client.get("/auth/session", cookies=dict(login_response.cookies))
    assert state.status_code == 200
    assert state.json()["role"] == "OPERATOR"


@pytest.mark.asyncio
async def test_expired_and_revoked_sessions_cannot_restore(
    http_operator: tuple[uuid.UUID, list[uuid.UUID], str],
) -> None:
    operator_id, tenants, _email = http_operator
    tenant_id = tenants[0]
    now = datetime.now(UTC)
    expired_raw = "expired-opaque-token"
    revoked_raw = "revoked-opaque-token"
    await _insert_session_row(
        operator_id=operator_id,
        tenant_id=tenant_id,
        raw_token=expired_raw,
        csrf_token="c1",
        expires_at=now - timedelta(minutes=5),
    )
    await _insert_session_row(
        operator_id=operator_id,
        tenant_id=tenant_id,
        raw_token=revoked_raw,
        csrf_token="c2",
        expires_at=now + timedelta(hours=1),
        revoked_at=now - timedelta(minutes=1),
    )
    client = TestClient(app)
    assert (
        client.get("/auth/session", cookies={SESSION_COOKIE_NAME(): expired_raw}).status_code == 401
    )
    assert (
        client.get("/auth/session", cookies={SESSION_COOKIE_NAME(): revoked_raw}).status_code == 401
    )


@pytest.mark.asyncio
async def test_disabled_operator_with_valid_session_cannot_restore(
    http_operator: tuple[uuid.UUID, list[uuid.UUID], str],
) -> None:
    operator_id, tenants, _email = http_operator
    tenant_id = tenants[0]
    raw = "disabled-opaque-token"
    await _insert_session_row(
        operator_id=operator_id,
        tenant_id=tenant_id,
        raw_token=raw,
        csrf_token="csrf-disabled",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    await _disable_operator(operator_id)
    client = TestClient(app)
    assert client.get("/auth/session", cookies={SESSION_COOKIE_NAME(): raw}).status_code == 401


@pytest.mark.asyncio
async def test_removed_membership_fails_restoration_closed(
    http_operator: tuple[uuid.UUID, list[uuid.UUID], str],
) -> None:
    operator_id, tenants, email = http_operator
    tenant_id = tenants[0]
    client = TestClient(app)
    login_response = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "tenant_id": str(tenant_id),
        },
    )
    assert login_response.status_code == 200
    await _remove_membership(operator_id, tenant_id)
    state = client.get("/auth/session", cookies=dict(login_response.cookies))
    assert state.status_code == 401


def test_unauthenticated_protected_request_is_rejected() -> None:
    assert TestClient(app).get("/auth/session").status_code == 401


def test_logout_revokes_and_replay_fails(
    http_operator: tuple[uuid.UUID, list[uuid.UUID], str],
) -> None:
    _operator_id, tenants, email = http_operator
    client = TestClient(app)
    login_response = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "tenant_id": str(tenants[0]),
        },
    )
    cookies = dict(login_response.cookies)
    logout_response = client.post("/auth/logout", cookies=cookies)
    assert logout_response.status_code == 200
    assert logout_response.json()["revoked"] is True
    replay = client.get("/auth/session", cookies=cookies)
    assert replay.status_code == 401


def test_rotation_on_second_login_invalidates_first_session(
    http_operator: tuple[uuid.UUID, list[uuid.UUID], str],
) -> None:
    _operator_id, tenants, email = http_operator
    client = TestClient(app)
    first_login = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "tenant_id": str(tenants[0]),
        },
    )
    first_cookies = dict(first_login.cookies)
    second_login = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "tenant_id": str(tenants[0]),
        },
    )
    assert second_login.status_code == 200
    replay_first = client.get("/auth/session", cookies=first_cookies)
    assert replay_first.status_code == 401


def SESSION_COOKIE_NAME() -> str:
    from app.auth.dependencies import SESSION_COOKIE

    return SESSION_COOKIE


async def intake_scenario(
    http_operator: tuple[uuid.UUID, list[uuid.UUID], str],
) -> tuple[TestClient, uuid.UUID, uuid.UUID, str, dict[str, str]]:
    _operator_id, tenants, email = http_operator
    tenant_id = tenants[0]
    site_id = await _seed_site_for(tenant_id)
    client = TestClient(app)
    login_response = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "tenant_id": str(tenant_id),
        },
    )
    assert login_response.status_code == 200
    csrf_token = login_response.json()["csrf_token"]
    return client, tenant_id, site_id, csrf_token, dict(login_response.cookies)


@pytest.mark.asyncio
async def test_investigate_intake_csrf_and_tenant_scenarios(
    http_operator: tuple[uuid.UUID, list[uuid.UUID], str],
) -> None:
    _operator_id, tenants, email = http_operator
    tenant_id = tenants[0]
    other_tenant = tenants[1]
    site_id = await _seed_site_for(tenant_id)
    client = TestClient(app)
    login_response = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "tenant_id": str(tenant_id),
        },
    )
    assert login_response.status_code == 200
    csrf_token = login_response.json()["csrf_token"]
    cookies = dict(login_response.cookies)

    missing = client.post("/investigations", json=_intake_payload(site_id), cookies=cookies)
    assert missing.status_code == 403

    mismatched = client.post(
        "/investigations",
        headers={"X-CSRF-Token": "wrong-token-value"},
        json=_intake_payload(site_id),
        cookies=cookies,
    )
    assert mismatched.status_code == 403

    valid = client.post(
        "/investigations",
        headers={"X-CSRF-Token": csrf_token},
        json=_intake_payload(site_id),
        cookies=cookies,
    )
    assert valid.status_code == 200
    incident_id = uuid.UUID(valid.json()["incident_id"])
    assert valid.json()["status"] == "OPEN"

    anonymous = TestClient(app)
    anonymous_post = anonymous.post(
        "/investigations",
        headers={"X-CSRF-Token": "anything"},
        json=_intake_payload(site_id),
    )
    assert anonymous_post.status_code in (401, 403)

    # Cross-tenant write: an unrelated actor gets a non-disclosing 404.
    other_client = TestClient(app)
    cross = other_client.post(
        "/investigations",
        headers={"X-CSRF-Token": "irrelevant"},
        json=_intake_payload(site_id),
    )
    assert cross.status_code == 401

    async def _second_operator_with_membership() -> tuple[uuid.UUID, str]:
        factory = get_session_factory()
        operator_id2 = uuid.uuid4()
        email2 = f"op2-{operator_id2.hex[:8]}@example.com"
        from app.auth.security import hash_password

        async with factory() as session, session.begin():
            session.add(
                Operator(
                    id=operator_id2,
                    actor_subject_id=uuid.uuid4(),
                    email=email2,
                    password_hash=hash_password("another-valid-password"),
                    role="OPERATOR",
                    is_active=True,
                )
            )
            await session.flush()
            session.add(OperatorTenant(operator_id=operator_id2, tenant_id=other_tenant))
        return operator_id2, email2

    _other_operator_id, other_email = await _second_operator_with_membership()
    other_login = other_client.post(
        "/auth/login",
        json={
            "email": other_email,
            "password": "another-valid-password",
            "tenant_id": str(other_tenant),
        },
    )
    assert other_login.status_code == 200
    cross_authenticated = other_client.post(
        "/investigations",
        headers={"X-CSRF-Token": other_login.json()["csrf_token"]},
        json=_intake_payload(site_id),
        cookies=dict(other_login.cookies),
    )
    assert cross_authenticated.status_code == 404


def test_failed_login_response_is_generic_and_non_leaking(
    http_operator: tuple[uuid.UUID, list[uuid.UUID], str],
) -> None:
    """Scenario #25: auth failure is externally generic — identical safe body
    for wrong-password vs nonexistent-user; no secrets or internals exposed."""
    _operator_id, tenants, email = http_operator
    tenant_id = tenants[0]

    def _failed_login(password: str, target_email: str) -> dict[str, object]:
        response = TestClient(app).post(
            "/auth/login",
            json={"email": target_email, "password": password, "tenant_id": str(tenant_id)},
        )
        assert response.status_code == 401
        body: dict[str, object] = response.json()
        return body

    supplied_password = "wrong-password-␀-with-specials"
    wrong_password_body = _failed_login(supplied_password, email)
    nonexistent_body = _failed_login("whatever", f"ghost-{uuid.uuid4().hex[:8]}@example.com")

    # Exact approved error contract — nothing else.
    assert wrong_password_body == {"detail": "authentication failed"}
    # No account-existence oracle: both failures share the same external shape.
    assert nonexistent_body == {"detail": "authentication failed"}

    leaked_markers = [
        supplied_password,
        "password_hash",
        "actor_subject_id",
        str(_operator_id),
        "csrf_token",
        "pi_session",
        "traceback",
        "AuthError",
        str(tenant_id),
    ]
    serialized = repr(wrong_password_body)
    for marker in leaked_markers:
        assert marker not in serialized
