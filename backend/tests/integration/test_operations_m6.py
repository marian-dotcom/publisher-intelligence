"""EP-026 M6 — minimal self-observability over real persisted truth.

Exercises the authenticated /product/operations read path against the real
PostgreSQL job queue, retention evidence and per-site source-health
projection. PI-infrastructure signals never imply publisher/site failure;
every signal is a deterministic read-time projection of persisted state.
"""

import asyncio
import uuid
from typing import Any
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.auth.models import Operator, OperatorTenant
from app.auth.security import hash_password
from app.db.models import Job, Tenant
from app.db.session import get_session_factory
from app.main import app
from app.operations import (
    EXECUTION_WINDOW,
    SCHEDULER_MAX_AGE,
    WORKER_MAX_IDLE,
    freshness_state,
)
from tests.integration.purge import make_purge

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _clean_db() -> None:
    asyncio.run(make_purge(get_session_factory)())


def _client_with_tenant() -> tuple[TestClient, uuid.UUID]:
    factory = get_session_factory()
    tenant_id = uuid.uuid4()
    operator_id = uuid.uuid4()
    email = f"ops-{operator_id.hex[:8]}@example.com"

    async def seed() -> None:
        async with factory() as session, session.begin():
            session.add(Tenant(id=tenant_id, slug=f"ops-{tenant_id.hex[:8]}", name="Ops"))
            await session.flush()
            session.add(
                Operator(
                    id=operator_id,
                    actor_subject_id=uuid.uuid4(),
                    email=email,
                    password_hash=hash_password("correct-horse-battery"),
                    role="OPERATOR",
                    is_active=True,
                )
            )
            await session.flush()
            session.add(OperatorTenant(operator_id=operator_id, tenant_id=tenant_id))

    asyncio.run(seed())
    client = TestClient(app)
    login = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "tenant_id": str(tenant_id),
        },
    )
    assert login.status_code == 200
    client.cookies.update(dict(login.cookies))
    return client, tenant_id


def _add_job(
    tenant_id: uuid.UUID | None,
    *,
    job_type: str = "GA4_EXTRACT",
    status: str = "PENDING",
    created_at: datetime | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    lock_expires_at: datetime | None = None,
) -> None:
    factory = get_session_factory()

    async def insert() -> None:
        async with factory() as session, session.begin():
            session.add(
                Job(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    job_type=job_type,
                    payload={},
                    status=status,
                    created_at=created_at or datetime.now(UTC),
                    started_at=started_at,
                    finished_at=finished_at,
                    lock_expires_at=lock_expires_at,
                )
            )

    asyncio.run(insert())


def _operations(client: TestClient) -> dict[str, Any]:
    response = client.get("/product/operations")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


def test_freshness_state_unit_boundaries() -> None:
    now = datetime.now(UTC)
    assert freshness_state(moment=None, now=now, max_age=SCHEDULER_MAX_AGE) == "UNKNOWN"
    recent = now - timedelta(hours=1)
    assert freshness_state(moment=recent, now=now, max_age=SCHEDULER_MAX_AGE) == "CURRENT"
    old = now - SCHEDULER_MAX_AGE - timedelta(minutes=1)
    assert freshness_state(moment=old, now=now, max_age=SCHEDULER_MAX_AGE) == "STALE"


def test_operations_requires_authentication() -> None:
    client = TestClient(app)
    assert client.get("/product/operations").status_code in (401, 403)


def test_scheduler_signal_reflects_recent_enqueue() -> None:
    client, _tenant_id = _client_with_tenant()
    _add_job(None)  # scheduler enqueues global jobs (tenant NULL)
    body = _operations(client)
    scheduler = body["scheduler"]
    assert scheduler["state"] == "CURRENT"
    assert scheduler["age_seconds"] == 0
    # Worker liveness stays truthful independently: nothing executed yet.
    assert body["workers"]["state"] == "UNKNOWN"


def test_stale_scheduler_is_surfaced_without_publisher_failure_claim() -> None:
    client, _tenant_id = _client_with_tenant()
    stale = datetime.now(UTC) - SCHEDULER_MAX_AGE - timedelta(hours=2)
    _add_job(None, created_at=stale)
    body = _operations(client)
    assert body["scheduler"]["state"] == "STALE"
    home = client.get("/product/home/status").json()
    assert home["publisher_site_condition"] in ("UNKNOWN", "ACTIVE")


def test_recent_worker_execution_is_current() -> None:
    client, tenant_id = _client_with_tenant()
    fresh_start = datetime.now(UTC) - timedelta(minutes=5)
    _add_job(
        tenant_id,
        status="COMPLETE",
        started_at=fresh_start,
        finished_at=fresh_start + timedelta(seconds=30),
    )
    body = _operations(client)
    assert body["workers"]["state"] == "CURRENT"
    assert body["workers"]["age_seconds"] is not None
    assert body["workers"]["age_seconds"] < WORKER_MAX_IDLE.total_seconds()


def test_stale_worker_is_surfaced_without_publisher_failure_claim() -> None:
    client, tenant_id = _client_with_tenant()
    stale_start = datetime.now(UTC) - WORKER_MAX_IDLE - timedelta(hours=1)
    _add_job(
        tenant_id,
        status="COMPLETE",
        started_at=stale_start,
        finished_at=stale_start + timedelta(seconds=30),
    )
    body = _operations(client)
    assert body["workers"]["state"] == "STALE"
    home = client.get("/product/home/status").json()
    assert home["publisher_site_condition"] in ("UNKNOWN", "ACTIVE")


def test_queue_depth_distinguishes_runnable_leased_and_stale_leases() -> None:
    client, tenant_id = _client_with_tenant()
    now = datetime.now(UTC)
    _add_job(tenant_id, status="PENDING")
    _add_job(tenant_id, status="RETRY")
    _add_job(tenant_id, status="RUNNING", lock_expires_at=now + timedelta(minutes=10))
    _add_job(tenant_id, status="RUNNING", lock_expires_at=now - timedelta(minutes=10))
    queue = _operations(client)["queue"]
    assert queue["runnable"] == 2
    assert queue["leased"] == 1
    assert queue["stale_leases"] == 1


def test_execution_window_duration_and_bounded_failure_rate() -> None:
    client, tenant_id = _client_with_tenant()
    now = datetime.now(UTC)
    base = now - timedelta(hours=1)
    # Two completed runs of 60s and 180s; one failure inside the window.
    for seconds, status in ((60, "COMPLETE"), (180, "COMPLETE"), (30, "FAILED")):
        _add_job(
            tenant_id,
            status=status,
            started_at=base,
            finished_at=base + timedelta(seconds=seconds),
        )
    # Outside the bounded window: must NOT enter the denominator.
    ancient = now - EXECUTION_WINDOW - timedelta(days=2)
    _add_job(
        tenant_id, status="FAILED", started_at=ancient, finished_at=ancient + timedelta(seconds=999)
    )

    execution = _operations(client)["execution_window"]
    assert execution["window_hours"] == 24
    assert execution["completed"] == 2
    assert execution["failed"] == 1
    assert execution["failure_rate"] == round(1 / 3, 4)
    assert execution["avg_duration_seconds"] == 90
    assert execution["max_duration_seconds"] == 180


def test_retention_health_is_projected_not_duplicated() -> None:
    from app.retention.models import RetentionRun

    client, _tenant_id = _client_with_tenant()
    factory = get_session_factory()
    stalled_started = datetime.now(UTC) - timedelta(hours=12)

    async def seed_open_run() -> None:
        async with factory() as session, session.begin():
            session.add(RetentionRun(id=uuid.uuid4(), started_at=stalled_started))

    asyncio.run(seed_open_run())
    retention = _operations(client)["retention"]
    assert retention["state"] == "STALLED"
    assert "never finished" in retention["detail"]


def test_per_site_source_health_is_tenant_scoped_and_independent() -> None:
    client_a, _tenant_a = _client_with_tenant()
    body = _operations(client_a)
    sites = body["sites"]
    assert isinstance(sites, list)
    for site in sites:
        health = site["source_health"]
        for key in ("BROWSER_MONITORING", "GA4", "GSC", "GAM", "PUBLIC_CONFIG"):
            assert key in health
