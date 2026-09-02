"""EP-030 M1: per-site monitoring controls (data model + authenticated API).

Integration coverage for the DELETE-free monitoring-control boundary:
- new sites default to OFF and create exactly one OPERATOR_UI/DIAGNOSTIC run;
- enabling/disabling is ADMIN + CSRF gated, actor-tenant-bound, and
  non-disclosing on missing/foreign sites;
- the guard produces exactly one append-only audit row per OFF<->ON transition
  and never for idempotent repeats;
- the ON projection reports the next strictly-future six-hour boundary;
- M1 authorization writes must not enqueue work or mutate evidence.
"""

import asyncio
import uuid
from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.auth.models import Operator, OperatorTenant
from app.auth.security import hash_password
from app.browser.models import (
    CheckpointRun,
    Publisher,
    Site,
    SiteMonitoringStateChange,
)
from app.browser.security import BrowserNetworkGuard
from app.db.models import Job, Tenant
from app.db.session import get_session_factory
from app.main import app
from tests.integration.purge import make_purge

pytestmark = pytest.mark.integration

PASSWORD = "monitor-site-password"
MONITORING_URL = "/product/sites/{site_id}/monitoring"


@pytest.fixture(autouse=True)
def _clean_db() -> Generator[None, None, None]:
    purge = make_purge(get_session_factory)
    asyncio.run(purge())
    yield
    asyncio.run(purge())


@pytest.fixture
async def admin_and_tenant() -> tuple[uuid.UUID, uuid.UUID, str]:
    """One tenant and an ADMIN operator bound to it; returns (operator_id, tenant_id, email).

    The operator's actor_subject_id doubles as the tenant id so the audit
    `actor_id` equals the tenant id in the cross-tenant regression.
    """
    factory = get_session_factory()
    operator_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    email = f"mon-admin-{operator_id.hex[:8]}@example.com"
    async with factory() as session, session.begin():
        session.add(Tenant(id=tenant_id, slug=f"mon-t-{tenant_id.hex[:8]}", name="M1"))
        await session.flush()
        session.add(
            Operator(
                id=operator_id,
                actor_subject_id=tenant_id,
                email=email,
                password_hash=hash_password(PASSWORD),
                role="ADMIN",
                is_active=True,
            )
        )
        session.add(OperatorTenant(operator_id=operator_id, tenant_id=tenant_id))
    return operator_id, tenant_id, email


async def _create_site(
    *, tenant_id: uuid.UUID, domain: str | None = None, timezone: str = "UTC"
) -> uuid.UUID:
    session_factory = get_session_factory()
    site_id = uuid.uuid4()
    publisher_id = uuid.uuid4()
    async with session_factory() as session, session.begin():
        session.add(
            Publisher(
                id=publisher_id,
                tenant_id=tenant_id,
                name="M1 Publisher",
                slug=f"mon-pub-{publisher_id.hex[:8]}",
                default_timezone=timezone,
                status="ACTIVE",
            )
        )
        await session.flush()
        session.add(
            Site(
                id=site_id,
                tenant_id=tenant_id,
                publisher_id=publisher_id,
                name="M1 Site",
                canonical_domain=domain or f"{site_id.hex}.example.test",
                canonical_scheme="https",
                timezone=timezone,
                status="ACTIVE",
            )
        )
    return site_id


def _login(
    client: TestClient, *, email: str, password: str = PASSWORD, tenant_id: uuid.UUID
) -> tuple[str, dict[str, str]]:
    response = client.post(
        "/auth/login",
        json={"email": email, "password": password, "tenant_id": str(tenant_id)},
    )
    assert response.status_code == 200
    return response.json()["csrf_token"], dict(response.cookies)


async def _site_state(site_id: uuid.UUID) -> str | None:
    session_factory = get_session_factory()
    async with session_factory() as session:
        value = await session.scalar(select(Site.monitoring_state).where(Site.id == site_id))
        return str(value) if value is not None else None


async def _audit_rows(site_id: uuid.UUID) -> list[SiteMonitoringStateChange]:
    """Audit rows in deterministic transition order: changed_at then id as the
    stable tie-breaker (no assumption about concurrency execution order)."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        return list(
            (
                await session.scalars(
                    select(SiteMonitoringStateChange)
                    .where(SiteMonitoringStateChange.site_id == site_id)
                    .order_by(
                        SiteMonitoringStateChange.changed_at,
                        SiteMonitoringStateChange.id,
                    )
                )
            ).all()
        )


@pytest.mark.asyncio
async def test_new_site_defaults_off_with_single_diagnostic_run_no_scheduled_work(
    admin_and_tenant: tuple[uuid.UUID, uuid.UUID, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Registration regression: a new site is OFF, has exactly one OPERATOR_UI
    DIAGNOSTIC run, and no recurring scheduled monitoring was enqueued."""

    async def _allow_url(_self: object, url: str) -> str:
        return url

    monkeypatch.setattr(BrowserNetworkGuard, "validate_initial", _allow_url)
    _operator_id, tenant_id, email = admin_and_tenant
    client = TestClient(app)
    csrf, cookies = _login(client, email=email, tenant_id=tenant_id)

    response = client.post(
        "/product/sites",
        headers={"X-CSRF-Token": csrf},
        cookies=cookies,
        json={
            "publisher_name": "Registration Publisher",
            "site_name": "Registration Site",
            "url": "https://example.test/",
        },
    )
    assert response.status_code == 201
    site_id = uuid.UUID(response.json()["site_id"])

    session_factory = get_session_factory()
    async with session_factory() as session:
        site = await session.scalar(select(Site).where(Site.id == site_id))
        assert site is not None
        assert site.monitoring_state == "OFF"
        assert site.monitoring_state_updated_at is not None
        runs = list(
            (
                await session.scalars(
                    select(CheckpointRun).where(
                        CheckpointRun.tenant_id == tenant_id,
                        CheckpointRun.site_id == site_id,
                    )
                )
            ).all()
        )
        jobs = list(
            (
                await session.scalars(
                    select(Job).where(
                        Job.tenant_id == tenant_id, Job.job_type == "BROWSER_CHECKPOINT"
                    )
                )
            ).all()
        )
        audit = list(
            (
                await session.scalars(
                    select(SiteMonitoringStateChange).where(
                        SiteMonitoringStateChange.site_id == site_id
                    )
                )
            ).all()
        )
    assert len(runs) == 1
    assert runs[0].observation_kind == "DIAGNOSTIC"
    assert runs[0].trigger_source == "OPERATOR_UI"
    assert len(jobs) == 1
    assert jobs[0].payload == {"checkpoint_run_id": str(runs[0].id)}
    assert audit == []


@pytest.mark.asyncio
async def test_enable_is_admin_gated_and_vertexmed(
    admin_and_tenant: tuple[uuid.UUID, uuid.UUID, str],
) -> None:
    _operator_id, tenant_id, email = admin_and_tenant
    site_id = await _create_site(tenant_id=tenant_id)
    client = TestClient(app)

    csrf, cookies = _login(client, email=email, tenant_id=tenant_id)
    response = client.put(
        MONITORING_URL.format(site_id=site_id),
        headers={"X-CSRF-Token": csrf},
        cookies=cookies,
        json={"enabled": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is True
    assert body["cadence"] == {"identifier": "six-hour", "hours": 6}
    assert body["next_scheduled_for"] is not None
    assert body["in_flight_scheduled_run_status"] is None

    assert await _site_state(site_id) == "ON"
    audit = await _audit_rows(site_id)
    assert len(audit) == 1
    assert audit[0].from_state == "OFF"
    assert audit[0].to_state == "ON"
    assert audit[0].actor_id == tenant_id


@pytest.mark.asyncio
async def test_missing_csrf_forbids(admin_and_tenant: tuple[uuid.UUID, uuid.UUID, str]) -> None:
    _operator_id, tenant_id, email = admin_and_tenant
    site_id = await _create_site(tenant_id=tenant_id)
    client = TestClient(app)
    _csrf, cookies = _login(client, email=email, tenant_id=tenant_id)

    missing = client.put(
        MONITORING_URL.format(site_id=site_id), cookies=cookies, json={"enabled": True}
    )
    assert missing.status_code == 403


@pytest.mark.asyncio
async def test_anonymous_is_unauthorized(
    admin_and_tenant: tuple[uuid.UUID, uuid.UUID, str],
) -> None:
    _operator_id, tenant_id, _email = admin_and_tenant
    site_id = await _create_site(tenant_id=tenant_id)
    response = TestClient(app).put(
        MONITORING_URL.format(site_id=site_id),
        headers={"X-CSRF-Token": "irrelevant"},
        json={"enabled": True},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_non_admin_operator_is_forbidden(
    admin_and_tenant: tuple[uuid.UUID, uuid.UUID, str],
) -> None:
    _operator_id, tenant_id, _email = admin_and_tenant
    site_id = await _create_site(tenant_id=tenant_id)
    factory = get_session_factory()
    member_id = uuid.uuid4()
    member_email = f"mon-member-{member_id.hex[:8]}@example.com"
    async with factory() as session, session.begin():
        session.add(
            Operator(
                id=member_id,
                actor_subject_id=uuid.uuid4(),
                email=member_email,
                password_hash=hash_password(PASSWORD),
                role="OPERATOR",
                is_active=True,
            )
        )
        session.add(OperatorTenant(operator_id=member_id, tenant_id=tenant_id))

    client = TestClient(app)
    csrf, cookies = _login(client, email=member_email, tenant_id=tenant_id)
    response = client.put(
        MONITORING_URL.format(site_id=site_id),
        headers={"X-CSRF-Token": csrf},
        cookies=cookies,
        json={"enabled": True},
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "insufficient permissions"}
    assert await _site_state(site_id) == "OFF"


@pytest.mark.asyncio
async def test_foreign_site_is_non_disclosing_404(
    admin_and_tenant: tuple[uuid.UUID, uuid.UUID, str],
) -> None:
    """A site owned by another tenant is indistinguishable from a missing site."""
    _operator_id, tenant_id, email = admin_and_tenant
    other_tenant_id = uuid.uuid4()
    session_factory = get_session_factory()
    async with session_factory() as session, session.begin():
        session.add(
            Tenant(id=other_tenant_id, slug=f"mon-other-{other_tenant_id.hex[:8]}", name="Other")
        )
    foreign_site_id = await _create_site(tenant_id=other_tenant_id)
    client = TestClient(app)
    csrf, cookies = _login(client, email=email, tenant_id=tenant_id)

    foreign = client.put(
        MONITORING_URL.format(site_id=foreign_site_id),
        headers={"X-CSRF-Token": csrf},
        cookies=cookies,
        json={"enabled": True},
    )
    missing_site_id = uuid.uuid4()
    missing = client.put(
        MONITORING_URL.format(site_id=missing_site_id),
        headers={"X-CSRF-Token": csrf},
        cookies=cookies,
        json={"enabled": True},
    )
    assert foreign.status_code == 404
    assert missing.status_code == 404
    assert foreign.json() == missing.json() == {"detail": "resource not found"}
    assert await _site_state(foreign_site_id) == "OFF"


@pytest.mark.asyncio
async def test_idempotent_repeat_writes_no_audit_and_keeps_watermark(
    admin_and_tenant: tuple[uuid.UUID, uuid.UUID, str],
) -> None:
    _operator_id, tenant_id, email = admin_and_tenant
    site_id = await _create_site(tenant_id=tenant_id)
    client = TestClient(app)
    csrf, cookies = _login(client, email=email, tenant_id=tenant_id)

    first = client.put(
        MONITORING_URL.format(site_id=site_id),
        headers={"X-CSRF-Token": csrf},
        cookies=cookies,
        json={"enabled": True},
    )
    assert first.status_code == 200

    session_factory = get_session_factory()
    async with session_factory() as session:
        before_watermark = await session.scalar(
            select(Site.monitoring_state_updated_at).where(Site.id == site_id)
        )

    second = client.put(
        MONITORING_URL.format(site_id=site_id),
        headers={"X-CSRF-Token": csrf},
        cookies=cookies,
        json={"enabled": True},
    )
    assert second.status_code == 200
    assert second.json()["enabled"] is True

    async with session_factory() as session:
        after_watermark = await session.scalar(
            select(Site.monitoring_state_updated_at).where(Site.id == site_id)
        )
    assert before_watermark == after_watermark
    assert len(await _audit_rows(site_id)) == 1


@pytest.mark.asyncio
async def test_disable_flow_is_audited(
    admin_and_tenant: tuple[uuid.UUID, uuid.UUID, str],
) -> None:
    _operator_id, tenant_id, email = admin_and_tenant
    site_id = await _create_site(tenant_id=tenant_id)
    client = TestClient(app)
    csrf, cookies = _login(client, email=email, tenant_id=tenant_id)

    enable = client.put(
        MONITORING_URL.format(site_id=site_id),
        headers={"X-CSRF-Token": csrf},
        cookies=cookies,
        json={"enabled": True},
    )
    assert enable.status_code == 200

    disable = client.put(
        MONITORING_URL.format(site_id=site_id),
        headers={"X-CSRF-Token": csrf},
        cookies=cookies,
        json={"enabled": False},
    )
    assert disable.status_code == 200
    assert disable.json()["enabled"] is False
    assert disable.json()["next_scheduled_for"] is None

    audit = await _audit_rows(site_id)
    assert len(audit) == 2
    assert (audit[0].from_state, audit[0].to_state) == ("OFF", "ON")
    assert (audit[1].from_state, audit[1].to_state) == ("ON", "OFF")


@pytest.mark.asyncio
async def test_on_projection_reports_next_future_boundary(
    admin_and_tenant: tuple[uuid.UUID, uuid.UUID, str],
) -> None:
    _operator_id, tenant_id, email = admin_and_tenant
    site_id = await _create_site(tenant_id=tenant_id)
    client = TestClient(app)
    csrf, cookies = _login(client, email=email, tenant_id=tenant_id)

    before = datetime.now(UTC)
    response = client.put(
        MONITORING_URL.format(site_id=site_id),
        headers={"X-CSRF-Token": csrf},
        cookies=cookies,
        json={"enabled": True},
    )
    next_at = response.json()["next_scheduled_for"]
    assert next_at is not None
    parsed = datetime.fromisoformat(next_at).astimezone(UTC)
    assert parsed > before
    # Strictly future and aligned to a canonical six-hour boundary.
    assert parsed.tzinfo is not None
    assert (parsed.minute, parsed.second, parsed.microsecond) == (0, 0, 0)
    assert parsed.hour in (0, 6, 12, 18)


@pytest.mark.asyncio
async def test_next_boundary_is_strictly_future_and_defers_at_canonical_boundaries() -> None:
    """Deterministically drives the production boundary resolver.

    The ON projection's next_scheduled_for is always strictly after the enable
    watermark and always lands on a canonical six-hour boundary. Enabling exactly at
    00:00 / 06:00 / 12:00 / 18:00 defers to the following boundary, never the current.
    This drives the exact production function that computes next_scheduled_for with
    fixed instants, so no wall clock or new dependency is involved.
    """
    from app.browser.monitoring_control import _resolve_next_boundary

    canonical = (0, 6, 12, 18)
    for hour in canonical:
        enable_at = datetime(2026, 3, 5, hour, 0, 0, tzinfo=UTC)
        next_boundary = _resolve_next_boundary("ON", enable_at, "UTC")
        assert next_boundary is not None
        # Exactly-on-boundary defers to the following boundary, never the current.
        if hour == 18:
            expected = datetime(2026, 3, 6, 0, 0, 0, tzinfo=UTC)
        else:
            expected = datetime(2026, 3, 5, hour + 6, 0, 0, tzinfo=UTC)
        assert next_boundary == expected
        assert next_boundary > enable_at
        assert (next_boundary.minute, next_boundary.second, next_boundary.microsecond) == (0, 0, 0)

    # An ordinary between-boundaries watermark resolves to the next canonical boundary.
    mid_window = datetime(2026, 3, 5, 7, 42, 13, tzinfo=UTC)
    next_boundary = _resolve_next_boundary("ON", mid_window, "UTC")
    assert next_boundary == datetime(2026, 3, 5, 12, 0, 0, tzinfo=UTC)
    assert next_boundary > mid_window
    assert (next_boundary.minute, next_boundary.second, next_boundary.microsecond) == (0, 0, 0)

    # A disabled site never reports a next boundary.
    assert _resolve_next_boundary("OFF", mid_window, "UTC") is None

    # A late-evening watermark wraps to the following day's first boundary.
    late = datetime(2026, 3, 5, 18, 31, 0, tzinfo=UTC)
    next_boundary = _resolve_next_boundary("ON", late, "UTC")
    assert next_boundary == datetime(2026, 3, 6, 0, 0, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_enable_does_not_enqueue_work_or_mutate_evidence(
    admin_and_tenant: tuple[uuid.UUID, uuid.UUID, str],
) -> None:
    _operator_id, tenant_id, email = admin_and_tenant
    site_id = await _create_site(tenant_id=tenant_id)
    client = TestClient(app)
    csrf, cookies = _login(client, email=email, tenant_id=tenant_id)

    session_factory = get_session_factory()

    async def _browser_job_rows() -> int:
        async with session_factory() as session:
            row = await session.scalar(
                select(func.count(Job.id)).where(
                    Job.tenant_id == tenant_id, Job.job_type == "BROWSER_CHECKPOINT"
                )
            )
            return int(row or 0)

    async def _run_rows() -> int:
        async with session_factory() as session:
            row = await session.scalar(
                select(func.count(CheckpointRun.id)).where(CheckpointRun.tenant_id == tenant_id)
            )
            return int(row or 0)

    async def _count_all() -> dict[str, int]:
        """Counts over all evidence/observation tables the M1 write must not touch."""
        async with session_factory() as session:
            result: dict[str, int] = {}
            for table in (
                "artifacts",
                "checkpoint_windows",
                "events",
                "source_extracts",
                "metric_points",
                "browser_scenarios",
                "incidents",
                "evidence_packs",
            ):
                result[table] = int(
                    (await session.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()
                )
        return result

    async def _snapshot() -> dict[str, int]:
        return {
            "jobs": await _browser_job_rows(),
            "runs": await _run_rows(),
            "artifacts": (await _count_all())["artifacts"],
            "tables_total": sum((await _count_all()).values()),
        }

    before = await _snapshot()
    assert before["jobs"] == 0
    assert before["runs"] == 0
    assert before["artifacts"] == 0
    assert before["tables_total"] == 0

    response = client.put(
        MONITORING_URL.format(site_id=site_id),
        headers={"X-CSRF-Token": csrf},
        cookies=cookies,
        json={"enabled": True},
    )
    assert response.status_code == 200

    after = await _snapshot()
    assert after == before
    assert after["jobs"] == 0
    assert after["runs"] == 0
    assert after["tables_total"] == 0


@pytest.mark.asyncio
async def test_unknown_payload_field_is_rejected(
    admin_and_tenant: tuple[uuid.UUID, uuid.UUID, str],
) -> None:
    _operator_id, tenant_id, email = admin_and_tenant
    site_id = await _create_site(tenant_id=tenant_id)
    client = TestClient(app)
    csrf, cookies = _login(client, email=email, tenant_id=tenant_id)

    response = client.put(
        MONITORING_URL.format(site_id=site_id),
        headers={"X-CSRF-Token": csrf},
        cookies=cookies,
        json={"enabled": True, "request_id": "nope"},
    )
    assert response.status_code == 422
    assert await _site_state(site_id) == "OFF"
    assert await _audit_rows(site_id) == []


@pytest.mark.asyncio
async def test_concurrent_enable_produces_one_audit_row(
    admin_and_tenant: tuple[uuid.UUID, uuid.UUID, str],
) -> None:
    from app.browser.monitoring_control import set_monitoring_state

    _operator_id, tenant_id, _email = admin_and_tenant
    site_id = await _create_site(tenant_id=tenant_id)
    factory = get_session_factory()

    results = await asyncio.gather(
        set_monitoring_state(
            factory, tenant_id=tenant_id, site_id=site_id, enabled=True, actor_id=tenant_id
        ),
        set_monitoring_state(
            factory, tenant_id=tenant_id, site_id=site_id, enabled=True, actor_id=tenant_id
        ),
    )
    assert all(result.enabled for result in results)

    assert await _site_state(site_id) == "ON"
    assert len(await _audit_rows(site_id)) == 1


@pytest.mark.asyncio
async def test_concurrent_opposing_transitions_serialize_truthfully(
    admin_and_tenant: tuple[uuid.UUID, uuid.UUID, str],
) -> None:
    """Concurrent enable+disable against an initially-OFF site must serialize on the
    row lock into exactly one of the two truthful outcomes, with a continuous,
    contradiction-free audit chain and zero registry/evidence mutation."""
    from app.browser.monitoring_control import set_monitoring_state

    _operator_id, tenant_id, _email = admin_and_tenant
    site_id = await _create_site(tenant_id=tenant_id)
    factory = get_session_factory()

    results = await asyncio.gather(
        set_monitoring_state(
            factory, tenant_id=tenant_id, site_id=site_id, enabled=True, actor_id=tenant_id
        ),
        set_monitoring_state(
            factory, tenant_id=tenant_id, site_id=site_id, enabled=False, actor_id=tenant_id
        ),
    )
    assert len(results) == 2
    assert not any(isinstance(result, BaseException) for result in results)

    final_state = await _site_state(site_id)
    assert final_state in ("ON", "OFF")
    audit = await _audit_rows(site_id)

    if final_state == "ON":
        # Outcome A: the no-op disable raced ahead; a single OFF->ON transition.
        assert len(audit) == 1
        assert (audit[0].from_state, audit[0].to_state) == ("OFF", "ON")
    else:
        # Outcome B: enable then disable; a continuous OFF->ON->OFF chain.
        assert len(audit) == 2
        assert (audit[0].from_state, audit[0].to_state) == ("OFF", "ON")
        assert (audit[1].from_state, audit[1].to_state) == ("ON", "OFF")

    # Universal audit-chain invariants.
    assert all(row.from_state != row.to_state for row in audit)
    assert all(audit[i].to_state == audit[i + 1].from_state for i in range(len(audit) - 1))
    assert audit[-1].to_state == final_state
    assert len({(row.from_state, row.to_state) for row in audit}) == len(audit)
    assert len({row.id for row in audit}) == len(audit)

    async def _count_all() -> dict[str, int]:
        async with factory() as session:
            result: dict[str, int] = {}
            for table in (
                "jobs",
                "checkpoint_runs",
                "artifacts",
                "checkpoint_windows",
                "events",
                "incidents",
                "evidence_packs",
                "source_extracts",
                "metric_points",
                "browser_scenarios",
                "site_monitoring_state_changes",
            ):
                result[table] = int(
                    (
                        await session.execute(
                            text(f"SELECT count(*) FROM {table} WHERE tenant_id = :tenant_id"),
                            {"tenant_id": tenant_id},
                        )
                    ).scalar_one()
                )
        return result

    counts = await _count_all()
    assert counts["jobs"] == 0
    assert all(v == 0 for table, v in counts.items() if table != "site_monitoring_state_changes")
    assert counts["site_monitoring_state_changes"] == len(audit)
