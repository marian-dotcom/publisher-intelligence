"""EP-028 M2 — bounded initial-diagnostic projection on GET /product/home/status.

Covers the operator's first controlled observation projection. This is a
read-only view that must remain semantically separate from six-hour SCHEDULED
source health and must never leak raw evidence or internal classification
objects.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.auth.models import Operator, OperatorTenant
from app.auth.security import hash_password
from app.browser.models import (
    BrowserScenario,
    CheckpointRun,
    CheckpointWindow,
    MonitoredUrl,
    Publisher,
    Site,
    Template,
)
from app.db.models import Tenant
from app.db.session import get_session_factory
from app.main import app
from tests.integration.purge import make_purge

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _clean_db() -> None:
    asyncio.run(make_purge(get_session_factory)())


async def _seed_site(
    *, slug: str, tenant_id: uuid.UUID | None = None
) -> tuple[uuid.UUID, uuid.UUID, dict[str, uuid.UUID]]:
    """Create a tenant + publisher + site + template/monitored-url/scenario.

    When tenant_id is provided the site is created inside that existing tenant
    (so callers can seed multiple sites under one tenant). Returns
    (tenant_id, site_id, ids) where ids carries the template, monitored url and
    scenario uuids needed to build a CheckpointRun.
    """
    factory = get_session_factory()
    publisher_id, site_id = uuid.uuid4(), uuid.uuid4()
    template_id, monitored_url_id, scenario_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    if tenant_id is None:
        tenant_id = uuid.uuid4()
        create_tenant = True
    else:
        create_tenant = False
    async with factory() as session, session.begin():
        if create_tenant:
            session.add(Tenant(id=tenant_id, slug=slug, name=slug.title()))
            await session.flush()
        session.add(
            Publisher(
                id=publisher_id,
                tenant_id=tenant_id,
                name=f"Publisher {slug}",
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
                name=f"Site {slug}",
                canonical_domain=f"{site_id.hex}.example.com",
                canonical_scheme="https",
                timezone="UTC",
                status="ACTIVE",
            )
        )
        await session.flush()
        session.add(
            Template(
                id=template_id,
                tenant_id=tenant_id,
                site_id=site_id,
                code="article",
                display_name="Article",
                status="ACTIVE",
            )
        )
        await session.flush()
        session.add(
            MonitoredUrl(
                id=monitored_url_id,
                tenant_id=tenant_id,
                site_id=site_id,
                template_id=template_id,
                url=f"https://{site_id.hex}.example.com/a",
                status="ACTIVE",
            )
        )
        session.add(
            BrowserScenario(
                id=scenario_id,
                tenant_id=tenant_id,
                site_id=site_id,
                code=f"core_desktop_{scenario_id.hex[:6]}",
                version=1,
                status="ACTIVE",
            )
        )
    return (
        tenant_id,
        site_id,
        {
            "template_id": template_id,
            "monitored_url_id": monitored_url_id,
            "scenario_id": scenario_id,
        },
    )


async def _add_run(
    *,
    tenant_id: uuid.UUID,
    site_id: uuid.UUID,
    ids: dict[str, uuid.UUID],
    observation_kind: str,
    trigger_source: str | None,
    status: str = "PENDING",
    scheduled_for: datetime,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    classification: dict[str, object] | None = None,
    created_at: datetime | None = None,
) -> uuid.UUID:
    """Persist a CheckpointWindow + CheckpointRun and return the run id.

    ADR-130 requires every non-scheduled observation to carry both a controlled
    trigger source and a concrete, non-null correlation identity, so a fresh
    UUID is generated for non-scheduled kinds.
    """
    factory = get_session_factory()
    window_id, run_id = uuid.uuid4(), uuid.uuid4()
    trigger_correlation_id = None if observation_kind == "SCHEDULED" else uuid.uuid4()
    async with factory() as session, session.begin():
        session.add(
            CheckpointWindow(
                id=window_id,
                tenant_id=tenant_id,
                site_id=site_id,
                scheduled_for=scheduled_for,
                window_start=scheduled_for,
                window_end=scheduled_for + timedelta(minutes=30),
            )
        )
        await session.flush()
        session.add(
            CheckpointRun(
                id=run_id,
                tenant_id=tenant_id,
                site_id=site_id,
                checkpoint_window_id=window_id,
                monitored_url_id=ids["monitored_url_id"],
                template_id=ids["template_id"],
                scenario_id=ids["scenario_id"],
                observation_kind=observation_kind,
                trigger_source=trigger_source,
                trigger_correlation_id=trigger_correlation_id,
                scheduled_for=scheduled_for,
                started_at=started_at,
                completed_at=completed_at,
                status=status,
                attempt_count=1,
                collector_bundle_version="b8-v1",
                environment={},
                limitations=[],
                manifest={},
                browser_access_classification=classification,
                created_at=created_at or datetime.now(UTC),
            )
        )
    return run_id


def _login_operator(client: TestClient, tenant_id: uuid.UUID) -> dict[str, str]:
    operator_id = uuid.uuid4()
    email = f"m2-{operator_id.hex[:8]}@example.com"
    factory = get_session_factory()

    async def seed() -> None:
        async with factory() as session, session.begin():
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
    login = client.post(
        "/auth/login",
        json={"email": email, "password": "correct-horse-battery", "tenant_id": str(tenant_id)},
    )
    assert login.status_code == 200, login.text
    return dict(login.cookies)


def _home(client: TestClient, cookies: dict[str, str], site_id: uuid.UUID) -> Any:
    response = client.get(f"/product/home/status?site_id={site_id}", cookies=cookies)
    assert response.status_code == 200, response.text
    return response.json()


def test_no_qualifying_diagnostic_returns_null() -> None:
    slug = f"m2-none-{uuid.uuid4().hex[:8]}"
    tenant_id, site_id, _ids = asyncio.run(_seed_site(slug=slug))
    client = TestClient(app)
    cookies = _login_operator(client, tenant_id)

    body = _home(client, cookies, site_id)
    assert body["initial_diagnostic"] is None
    # No scheduled source-health either: absent diagnostic must not be healthy.
    assert body["source_health"]["BROWSER_MONITORING"] == "UNKNOWN"


def test_pending_operator_ui_diagnostic_returns_bounded_projection() -> None:
    slug = f"m2-pending-{uuid.uuid4().hex[:8]}"
    tenant_id, site_id, ids = asyncio.run(_seed_site(slug=slug))
    when = datetime.now(UTC) - timedelta(minutes=1)
    run_id = asyncio.run(
        _add_run(
            tenant_id=tenant_id,
            site_id=site_id,
            ids=ids,
            observation_kind="DIAGNOSTIC",
            trigger_source="OPERATOR_UI",
            status="PENDING",
            scheduled_for=when,
        )
    )
    client = TestClient(app)
    cookies = _login_operator(client, tenant_id)

    body = _home(client, cookies, site_id)
    diag = body["initial_diagnostic"]
    assert isinstance(diag, dict)
    assert diag["run_id"] == str(run_id)
    assert diag["status"] == "PENDING"
    assert diag["completed_at"] is None
    assert diag["browser_access_classification"] is None


def test_running_diagnostic_returns_running_status() -> None:
    slug = f"m2-running-{uuid.uuid4().hex[:8]}"
    tenant_id, site_id, ids = asyncio.run(_seed_site(slug=slug))
    when = datetime.now(UTC) - timedelta(minutes=1)
    asyncio.run(
        _add_run(
            tenant_id=tenant_id,
            site_id=site_id,
            ids=ids,
            observation_kind="DIAGNOSTIC",
            trigger_source="OPERATOR_UI",
            status="RUNNING",
            scheduled_for=when,
            started_at=when,
        )
    )
    client = TestClient(app)
    cookies = _login_operator(client, tenant_id)

    diag = _home(client, cookies, site_id)["initial_diagnostic"]
    assert isinstance(diag, dict)
    assert diag["status"] == "RUNNING"


def test_completed_diagnostic_serializes_completed_at_isoformat() -> None:
    slug = f"m2-completed-{uuid.uuid4().hex[:8]}"
    tenant_id, site_id, ids = asyncio.run(_seed_site(slug=slug))
    when = datetime.now(UTC) - timedelta(days=1)
    completed_at = when + timedelta(minutes=5)
    asyncio.run(
        _add_run(
            tenant_id=tenant_id,
            site_id=site_id,
            ids=ids,
            observation_kind="DIAGNOSTIC",
            trigger_source="OPERATOR_UI",
            status="COMPLETE",
            scheduled_for=when,
            started_at=when,
            completed_at=completed_at,
        )
    )
    client = TestClient(app)
    cookies = _login_operator(client, tenant_id)

    diag = _home(client, cookies, site_id)["initial_diagnostic"]
    assert isinstance(diag, dict)
    assert diag["status"] == "COMPLETE"
    assert diag["completed_at"] == completed_at.isoformat()


@pytest.mark.parametrize(
    "state",
    ["ok", "degraded", "challenge_suspected"],
)
def test_canonical_classification_projected(state: str) -> None:
    slug = f"m2-class-{state}-{uuid.uuid4().hex[:8]}"
    tenant_id, site_id, ids = asyncio.run(_seed_site(slug=slug))
    when = datetime.now(UTC) - timedelta(days=1)
    asyncio.run(
        _add_run(
            tenant_id=tenant_id,
            site_id=site_id,
            ids=ids,
            observation_kind="DIAGNOSTIC",
            trigger_source="OPERATOR_UI",
            status="COMPLETE",
            scheduled_for=when,
            started_at=when,
            completed_at=when + timedelta(minutes=5),
            classification={"state": state, "reason": f"{state} reason"},
        )
    )
    client = TestClient(app)
    cookies = _login_operator(client, tenant_id)

    diag = _home(client, cookies, site_id)["initial_diagnostic"]
    assert isinstance(diag, dict)
    assert diag["browser_access_classification"] == state


def test_malformed_or_unrecognized_classification_projected_as_null() -> None:
    slug = f"m2-malformed-{uuid.uuid4().hex[:8]}"
    tenant_id, site_id, ids = asyncio.run(_seed_site(slug=slug))
    when = datetime.now(UTC) - timedelta(days=1)
    # Unrecognized state string (not in the canonical set) must fail closed to null.
    asyncio.run(
        _add_run(
            tenant_id=tenant_id,
            site_id=site_id,
            ids=ids,
            observation_kind="DIAGNOSTIC",
            trigger_source="OPERATOR_UI",
            status="COMPLETE",
            scheduled_for=when,
            started_at=when,
            completed_at=when + timedelta(minutes=5),
            classification={"state": "site_down", "reason": "x"},
        )
    )
    client = TestClient(app)
    cookies = _login_operator(client, tenant_id)

    diag = _home(client, cookies, site_id)["initial_diagnostic"]
    assert isinstance(diag, dict)
    assert diag["browser_access_classification"] is None


@pytest.mark.parametrize(
    "storage",
    [
        {"state": "ok"},
        {"state": "ok", "reason": "no anomalies"},
        {"state": "degraded", "reason": "unexpected HTTP status 403"},
        {"state": "challenge_suspected", "reason": "deterministic markers"},
        {"state": "site_down", "reason": "x"},
        "not-a-dict",
        {"state": "degraded"},
        {"state": "degraded", "reason": ""},
    ],
)
def test_raw_classification_metadata_is_never_leaked(storage: object) -> None:
    slug = f"m2-noleak-{uuid.uuid4().hex[:8]}"
    tenant_id, site_id, ids = asyncio.run(_seed_site(slug=slug))
    when = datetime.now(UTC) - timedelta(days=1)
    asyncio.run(
        _add_run(
            tenant_id=tenant_id,
            site_id=site_id,
            ids=ids,
            observation_kind="DIAGNOSTIC",
            trigger_source="OPERATOR_UI",
            status="COMPLETE",
            scheduled_for=when,
            started_at=when,
            completed_at=when + timedelta(minutes=5),
            classification=storage,  # type: ignore[arg-type]
        )
    )
    client = TestClient(app)
    cookies = _login_operator(client, tenant_id)

    diag = _home(client, cookies, site_id)["initial_diagnostic"]
    assert isinstance(diag, dict)
    # The only permitted classification field is a single canonical state
    # string (or null). No raw object/keys/reason may appear.
    assert set(diag.keys()) == {
        "run_id",
        "status",
        "completed_at",
        "browser_access_classification",
    }
    value = diag["browser_access_classification"]
    assert value in (None, "ok", "degraded", "challenge_suspected")
    assert "reason" not in diag


def test_multiple_operator_ui_diagnostics_selects_deterministic_latest() -> None:
    slug = f"m2-multi-{uuid.uuid4().hex[:8]}"
    tenant_id, site_id, ids = asyncio.run(_seed_site(slug=slug))
    now = datetime.now(UTC)
    older_completed = now - timedelta(days=2)
    newer_completed = now - timedelta(minutes=5)

    older_run = asyncio.run(
        _add_run(
            tenant_id=tenant_id,
            site_id=site_id,
            ids=ids,
            observation_kind="DIAGNOSTIC",
            trigger_source="OPERATOR_UI",
            status="COMPLETE",
            scheduled_for=older_completed,
            started_at=older_completed,
            completed_at=older_completed + timedelta(minutes=5),
            classification={"state": "ok", "reason": "older"},
            created_at=older_completed,
        )
    )
    newer_run = asyncio.run(
        _add_run(
            tenant_id=tenant_id,
            site_id=site_id,
            ids=ids,
            observation_kind="DIAGNOSTIC",
            trigger_source="OPERATOR_UI",
            status="COMPLETE",
            scheduled_for=newer_completed,
            started_at=newer_completed,
            completed_at=newer_completed + timedelta(minutes=5),
            classification={"state": "degraded", "reason": "newer"},
            created_at=newer_completed,
        )
    )
    assert older_run != newer_run
    client = TestClient(app)
    cookies = _login_operator(client, tenant_id)

    diag = _home(client, cookies, site_id)["initial_diagnostic"]
    assert isinstance(diag, dict)
    assert diag["run_id"] == str(newer_run)
    assert diag["browser_access_classification"] == "degraded"


@pytest.mark.parametrize(
    ("observation_kind", "trigger_source"),
    [
        ("DIAGNOSTIC", "OPERATOR_CLI"),
        ("DIAGNOSTIC", "LEGACY_CLI"),
        ("INCIDENT_DIAGNOSTIC", "INCIDENT"),
        ("SCHEDULED", None),
    ],
)
def test_non_operator_ui_runs_are_excluded(
    observation_kind: str, trigger_source: str | None
) -> None:
    slug = f"m2-excl-{uuid.uuid4().hex[:8]}"
    tenant_id, site_id, ids = asyncio.run(_seed_site(slug=slug))
    when = datetime.now(UTC) - timedelta(minutes=1)
    asyncio.run(
        _add_run(
            tenant_id=tenant_id,
            site_id=site_id,
            ids=ids,
            observation_kind=observation_kind,
            trigger_source=trigger_source,
            status="COMPLETE",
            scheduled_for=when,
            started_at=when,
            completed_at=when + timedelta(minutes=5),
        )
    )
    client = TestClient(app)
    cookies = _login_operator(client, tenant_id)

    body = _home(client, cookies, site_id)
    assert body["initial_diagnostic"] is None


def test_scheduled_run_is_excluded_but_still_drives_source_health() -> None:
    """A SCHEDULED run must not appear as initial_diagnostic yet still drive
    BROWSER_MONITORING source health normally (cohort separation)."""
    slug = f"m2-sched-{uuid.uuid4().hex[:8]}"
    tenant_id, site_id, ids = asyncio.run(_seed_site(slug=slug))
    when = datetime.now(UTC) - timedelta(hours=1)
    asyncio.run(
        _add_run(
            tenant_id=tenant_id,
            site_id=site_id,
            ids=ids,
            observation_kind="SCHEDULED",
            trigger_source=None,
            status="COMPLETE",
            scheduled_for=when,
            started_at=when,
            completed_at=when + timedelta(minutes=5),
        )
    )
    client = TestClient(app)
    cookies = _login_operator(client, tenant_id)

    body = _home(client, cookies, site_id)
    assert body["initial_diagnostic"] is None
    assert body["source_health"]["BROWSER_MONITORING"] == "HEALTHY"


def test_diagnostic_for_another_site_is_excluded() -> None:
    slug_a = f"m2-siteA-{uuid.uuid4().hex[:8]}"
    slug_b = f"m2-siteB-{uuid.uuid4().hex[:8]}"
    tenant_id, site_a, ids_a = asyncio.run(_seed_site(slug=slug_a))
    _same_tenant, site_b, _ids_b = asyncio.run(_seed_site(slug=slug_b, tenant_id=tenant_id))
    assert _same_tenant == tenant_id
    when = datetime.now(UTC) - timedelta(minutes=1)
    asyncio.run(
        _add_run(
            tenant_id=tenant_id,
            site_id=site_a,
            ids=ids_a,
            observation_kind="DIAGNOSTIC",
            trigger_source="OPERATOR_UI",
            status="COMPLETE",
            scheduled_for=when,
            started_at=when,
            completed_at=when + timedelta(minutes=5),
        )
    )
    # Site B has no diagnostic.
    client = TestClient(app)
    cookies = _login_operator(client, tenant_id)

    body = _home(client, cookies, site_b)
    assert body["selected_site_id"] == str(site_b)
    assert body["initial_diagnostic"] is None


def test_diagnostic_for_another_tenant_cannot_leak() -> None:
    slug_a = f"m2-tenantA-{uuid.uuid4().hex[:8]}"
    slug_b = f"m2-tenantB-{uuid.uuid4().hex[:8]}"
    tenant_a, site_a, _ids_a = asyncio.run(_seed_site(slug=slug_a))
    tenant_b, site_b, ids_b = asyncio.run(_seed_site(slug=slug_b))
    when = datetime.now(UTC) - timedelta(minutes=1)
    # Tenant B has a qualifying OPERATOR_UI diagnostic.
    asyncio.run(
        _add_run(
            tenant_id=tenant_b,
            site_id=site_b,
            ids=ids_b,
            observation_kind="DIAGNOSTIC",
            trigger_source="OPERATOR_UI",
            status="COMPLETE",
            scheduled_for=when,
            started_at=when,
            completed_at=when + timedelta(minutes=5),
        )
    )
    client = TestClient(app)
    # Operator authenticated into tenant A only.
    cookies = _login_operator(client, tenant_a)

    body = _home(client, cookies, site_a)
    # Tenant A's site is the only one selectable; B's diagnostic is unreachable.
    assert body["initial_diagnostic"] is None
    assert all(str(item["site_id"]) != str(site_b) for item in body["sites"])


def test_completed_diagnostic_with_no_scheduled_observation_coexists_with_unknown_monitoring() -> (
    None
):
    """initial_diagnostic may be COMPLETE while BROWSER_MONITORING stays UNKNOWN
    when no normal scheduled observation exists yet."""
    slug = f"m2-cohort-{uuid.uuid4().hex[:8]}"
    tenant_id, site_id, ids = asyncio.run(_seed_site(slug=slug))
    when = datetime.now(UTC) - timedelta(days=1)
    asyncio.run(
        _add_run(
            tenant_id=tenant_id,
            site_id=site_id,
            ids=ids,
            observation_kind="DIAGNOSTIC",
            trigger_source="OPERATOR_UI",
            status="COMPLETE",
            scheduled_for=when,
            started_at=when,
            completed_at=when + timedelta(minutes=5),
            classification={"state": "ok", "reason": "no anomalies"},
        )
    )
    client = TestClient(app)
    cookies = _login_operator(client, tenant_id)

    body = _home(client, cookies, site_id)
    diag = body["initial_diagnostic"]
    assert isinstance(diag, dict)
    assert diag["status"] == "COMPLETE"
    # No scheduled evidence exists, so BROWSER_MONITORING must remain UNKNOWN —
    # the completed diagnostic must NOT be treated as scheduled source health.
    assert body["source_health"]["BROWSER_MONITORING"] == "UNKNOWN"
