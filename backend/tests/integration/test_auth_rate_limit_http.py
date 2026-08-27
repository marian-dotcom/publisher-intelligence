"""EP-027 M1 — HTTP-layer rate limiting integration test."""

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient

from app.auth.models import Operator, OperatorTenant
from app.auth.security import hash_password
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
        tenant_id = uuid.uuid4()
        tenant_ids.append(tenant_id)
        session.add(Tenant(id=tenant_id, slug=f"rl-{tenant_id.hex[:8]}", name="RL"))
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
        session.add(OperatorTenant(operator_id=operator_id, tenant_id=tenant_id))
    return operator_id, tenant_ids, email


def test_rate_limit_blocks_after_max_attempts(
    http_operator: tuple[uuid.UUID, list[uuid.UUID], str],
) -> None:
    """5 allowed failed logins, 429 on 6th attempt."""
    _, tenants, email = http_operator
    client = TestClient(app)
    ip = "198.51.100.1"

    for i in range(5):
        response = client.post(
            "/auth/login",
            json={
                "email": email,
                "password": "wrong-password",
                "tenant_id": str(tenants[0]),
            },
            headers={"X-Real-IP": ip},
        )
        assert response.status_code == 401, f"attempt {i + 1} should be 401"

    blocked = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": "wrong-password",
            "tenant_id": str(tenants[0]),
        },
        headers={"X-Real-IP": ip},
    )
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers
    assert blocked.json()["detail"] == "too many requests"


def test_successful_login_clears_rate_limit(
    http_operator: tuple[uuid.UUID, list[uuid.UUID], str],
) -> None:
    """Successful login clears counter, allowing recovery."""
    _, tenants, email = http_operator
    client = TestClient(app)
    ip = "198.51.100.2"

    for _ in range(4):
        client.post(
            "/auth/login",
            json={
                "email": email,
                "password": "wrong-password",
                "tenant_id": str(tenants[0]),
            },
            headers={"X-Real-IP": ip},
        )

    success = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "tenant_id": str(tenants[0]),
        },
        headers={"X-Real-IP": ip},
    )
    assert success.status_code == 200

    again = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": "wrong-password",
            "tenant_id": str(tenants[0]),
        },
        headers={"X-Real-IP": ip},
    )
    assert again.status_code == 401


def test_different_ips_have_independent_limits(
    http_operator: tuple[uuid.UUID, list[uuid.UUID], str],
) -> None:
    """Rate limiting is per-IP, not global."""
    _, tenants, email = http_operator
    client = TestClient(app)

    for _ in range(5):
        client.post(
            "/auth/login",
            json={
                "email": email,
                "password": "wrong-password",
                "tenant_id": str(tenants[0]),
            },
            headers={"X-Real-IP": "198.51.100.3"},
        )

    other = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": "wrong-password",
            "tenant_id": str(tenants[0]),
        },
        headers={"X-Real-IP": "198.51.100.4"},
    )
    assert other.status_code == 401
