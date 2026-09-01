"""EP-029 M2a: diagnostic-results and diagnostic-artifacts endpoints."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.browser.models import (
    Artifact,
    BrowserScenario,
    CheckpointRun,
    CheckpointWindow,
    MonitoredUrl,
    Publisher,
    Site,
    Template,
)
from app.config.settings import Settings
from app.db.models import Tenant
from app.db.session import get_session_factory
from app.main import app
from app.storage.s3 import S3Storage
from tests.integration.purge import make_purge

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _clean_db() -> None:
    asyncio.run(make_purge(get_session_factory)())


async def _seed_diagnostic_site(*, slug: str) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Seed a tenant with a site, publisher, and a DIAGNOSTIC/OPERATOR_UI run with artifacts."""
    factory = get_session_factory()
    _tenant_id = uuid.uuid4()
    _publisher_id = uuid.uuid4()
    site_id = uuid.uuid4()
    async with factory() as session, session.begin():
        session.add(Tenant(id=_tenant_id, slug=slug, name=slug.title()))
        await session.flush()
        session.add(
            Publisher(
                id=_publisher_id,
                tenant_id=_tenant_id,
                name=f"Publisher {slug}",
                slug=f"pub-{_publisher_id.hex[:8]}",
                default_timezone="UTC",
                status="ACTIVE",
            )
        )
        await session.flush()
        session.add(
            Site(
                id=site_id,
                tenant_id=_tenant_id,
                publisher_id=_publisher_id,
                name=f"Site {slug}",
                canonical_domain=f"{site_id.hex}.example.com",
                canonical_scheme="https",
                timezone="UTC",
                status="ACTIVE",
            )
        )
        await session.flush()
        template_id = uuid.uuid4()
        monitored_url_id = uuid.uuid4()
        scenario_id = uuid.uuid4()
        window_id = uuid.uuid4()
        session.add(
            Template(
                id=template_id,
                tenant_id=_tenant_id,
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
                tenant_id=_tenant_id,
                site_id=site_id,
                template_id=template_id,
                url=f"https://{site_id.hex}.example.com/a",
                status="ACTIVE",
            )
        )
        session.add(
            BrowserScenario(
                id=scenario_id,
                tenant_id=_tenant_id,
                site_id=site_id,
                code=f"core_desktop_{scenario_id.hex[:6]}",
                version=1,
                status="ACTIVE",
            )
        )
        now = datetime.now(UTC)
        session.add(
            CheckpointWindow(
                id=window_id,
                tenant_id=_tenant_id,
                site_id=site_id,
                scheduled_for=now - timedelta(minutes=10),
                window_start=now - timedelta(minutes=10),
                window_end=now - timedelta(minutes=5),
            )
        )
        await session.flush()
        # Create DIAGNOSTIC/OPERATOR_UI run
        run_id = uuid.uuid4()
        session.add(
            CheckpointRun(
                id=run_id,
                tenant_id=_tenant_id,
                site_id=site_id,
                checkpoint_window_id=window_id,
                monitored_url_id=monitored_url_id,
                template_id=template_id,
                scenario_id=scenario_id,
                observation_kind="DIAGNOSTIC",
                trigger_source="OPERATOR_UI",
                trigger_correlation_id=uuid.uuid4(),
                scheduled_for=now - timedelta(minutes=10),
                started_at=now - timedelta(minutes=10),
                completed_at=now - timedelta(minutes=8),
                status="COMPLETE",
                attempt_count=1,
                final_url=f"https://{site_id.hex}.example.com/a",
                http_status=200,
                collector_bundle_version="b8-v1",
                environment={"is_mobile": False},
                limitations=[],
                manifest={},
                browser_access_classification={"state": "ok", "reason": "normal access"},
            )
        )
        await session.flush()
        # Add artifacts for this run
        artifact_types = [
            ("SCREENSHOT_VIEWPORT", "image/png", 1024),
            ("SCREENSHOT_FULL_PAGE", "image/png", 2048),
            ("RAW_DOM", "text/html", 512),
            ("NORMALIZED_DOM", "application/json", 256),
            ("MANIFEST", "application/json", 128),
        ]
        # Put dummy objects in MinIO for each artifact
        settings = Settings()
        storage = S3Storage(settings)
        for artifact_type, content_type, size in artifact_types:
            artifact_id = uuid.uuid4()
            object_key = (
                f"tenant/{_tenant_id}/site/{site_id}/checkpoints/{run_id}/"
                f"{artifact_type.lower()}.bin"
            )
            dummy_content = b"x" * size
            storage.put_bytes(key=object_key, content=dummy_content, content_type=content_type)
            session.add(
                Artifact(
                    id=artifact_id,
                    tenant_id=_tenant_id,
                    site_id=site_id,
                    checkpoint_run_id=run_id,
                    artifact_type=artifact_type,
                    storage_provider="S3_COMPATIBLE",
                    object_key=object_key,
                    content_type=content_type,
                    byte_size=size,
                    sha256="a" * 64,
                    retention_class="CORE_LONG",
                )
            )
    return _tenant_id, site_id, run_id


async def _seed_tenant_with_scheduled_run(*, slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    """Seed a tenant with a site and a SCHEDULED run (no diagnostic)."""
    factory = get_session_factory()
    _tenant_id = uuid.uuid4()
    _publisher_id = uuid.uuid4()
    site_id = uuid.uuid4()
    async with factory() as session, session.begin():
        session.add(Tenant(id=_tenant_id, slug=slug, name=slug.title()))
        await session.flush()
        session.add(
            Publisher(
                id=_publisher_id,
                tenant_id=_tenant_id,
                name=f"Publisher {slug}",
                slug=f"pub-{_publisher_id.hex[:8]}",
                default_timezone="UTC",
                status="ACTIVE",
            )
        )
        await session.flush()
        session.add(
            Site(
                id=site_id,
                tenant_id=_tenant_id,
                publisher_id=_publisher_id,
                name=f"Site {slug}",
                canonical_domain=f"{site_id.hex}.example.com",
                canonical_scheme="https",
                timezone="UTC",
                status="ACTIVE",
            )
        )
        await session.flush()
        template_id = uuid.uuid4()
        monitored_url_id = uuid.uuid4()
        scenario_id = uuid.uuid4()
        window_id = uuid.uuid4()
        session.add(
            Template(
                id=template_id,
                tenant_id=_tenant_id,
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
                tenant_id=_tenant_id,
                site_id=site_id,
                template_id=template_id,
                url=f"https://{site_id.hex}.example.com/a",
                status="ACTIVE",
            )
        )
        session.add(
            BrowserScenario(
                id=scenario_id,
                tenant_id=_tenant_id,
                site_id=site_id,
                code=f"core_desktop_{scenario_id.hex[:6]}",
                version=1,
                status="ACTIVE",
            )
        )
        now = datetime.now(UTC)
        session.add(
            CheckpointWindow(
                id=window_id,
                tenant_id=_tenant_id,
                site_id=site_id,
                scheduled_for=now - timedelta(hours=1),
                window_start=now - timedelta(hours=1),
                window_end=now - timedelta(minutes=30),
            )
        )
        await session.flush()
        scheduled_run_id = uuid.uuid4()
        session.add(
            CheckpointRun(
                id=scheduled_run_id,
                tenant_id=_tenant_id,
                site_id=site_id,
                checkpoint_window_id=window_id,
                monitored_url_id=monitored_url_id,
                template_id=template_id,
                scenario_id=scenario_id,
                observation_kind="SCHEDULED",
                scheduled_for=now - timedelta(hours=1),
                started_at=now - timedelta(hours=1),
                completed_at=now - timedelta(minutes=55),
                status="COMPLETE",
                attempt_count=1,
                collector_bundle_version="b8-v1",
                environment={"is_mobile": False},
                limitations=[],
                manifest={},
            )
        )
        await session.flush()
        # Add artifacts for the SCHEDULED run
        # (needed for test_diagnostic_artifact_wrong_run_rejected)
        artifact_types = [
            ("SCREENSHOT_VIEWPORT", "image/png", 1024),
            ("SCREENSHOT_FULL_PAGE", "image/png", 2048),
            ("RAW_DOM", "text/html", 512),
        ]
        # Put dummy objects in MinIO for each artifact
        settings = Settings()
        storage = S3Storage(settings)
        for artifact_type, content_type, size in artifact_types:
            artifact_id = uuid.uuid4()
            object_key = (
                f"tenant/{_tenant_id}/site/{site_id}/checkpoints/"
                f"{scheduled_run_id}/{artifact_type.lower()}.bin"
            )
            dummy_content = b"x" * size
            storage.put_bytes(key=object_key, content=dummy_content, content_type=content_type)
            session.add(
                Artifact(
                    id=artifact_id,
                    tenant_id=_tenant_id,
                    site_id=site_id,
                    checkpoint_run_id=scheduled_run_id,
                    artifact_type=artifact_type,
                    storage_provider="S3_COMPATIBLE",
                    object_key=object_key,
                    content_type=content_type,
                    byte_size=size,
                    sha256="a" * 64,
                    retention_class="CORE_LONG",
                )
            )
    return _tenant_id, site_id


async def _login_operator(tenant_id: uuid.UUID, client: TestClient) -> dict[str, str]:
    """Seed an operator for the tenant and log in."""
    from app.auth.models import Operator, OperatorTenant
    from app.auth.security import hash_password

    factory = get_session_factory()
    operator_id = uuid.uuid4()
    email = f"diag-{operator_id.hex[:8]}@example.com"
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
    login_response = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "tenant_id": str(tenant_id),
        },
    )
    assert login_response.status_code == 200
    return dict(login_response.cookies)


@pytest.mark.asyncio
async def test_diagnostic_results_happy_path() -> None:
    """Authenticated operator can retrieve diagnostic results for their site."""
    client = TestClient(app)
    tenant_id, site_id, run_id = await _seed_diagnostic_site(slug="ep29-diag-a")
    cookies = await _login_operator(tenant_id, client)

    resp = client.get(f"/product/sites/{site_id}/diagnostic-results", cookies=cookies)
    assert resp.status_code == 200
    body = resp.json()

    assert body["site_id"] == str(site_id)
    assert body["site_name"] == "Site ep29-diag-a"
    assert body["site_domain"] == f"{site_id.hex}.example.com"
    assert body["publisher_name"] == "Publisher ep29-diag-a"
    assert body["run"]["run_id"] == str(run_id)
    assert body["run"]["observation_kind"] == "DIAGNOSTIC"
    assert body["run"]["trigger_source"] == "OPERATOR_UI"
    assert body["run"]["trigger_correlation_id"] is not None
    assert body["run"]["status"] == "COMPLETE"
    assert body["run"]["attempt_count"] == 1
    assert body["run"]["http_status"] == 200
    assert body["run"]["browser_access_classification"] == "ok"
    assert len(body["artifacts"]) == 5

    # Verify artifact types present
    artifact_types = {a["artifact_type"] for a in body["artifacts"]}
    expected = {
        "SCREENSHOT_VIEWPORT",
        "SCREENSHOT_FULL_PAGE",
        "RAW_DOM",
        "NORMALIZED_DOM",
        "MANIFEST",
    }
    assert artifact_types == expected


@pytest.mark.asyncio
async def test_diagnostic_results_unauthenticated_rejected() -> None:
    """Unauthenticated request returns 401."""
    client = TestClient(app)
    _tenant_id, site_id, _ = await _seed_diagnostic_site(slug="ep29-diag-unauth")

    resp = client.get(f"/product/sites/{site_id}/diagnostic-results")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_diagnostic_results_wrong_tenant_rejected() -> None:
    """Operator from tenant A cannot access tenant B's diagnostic results."""
    client = TestClient(app)
    _tenant_a, _site_a, _ = await _seed_diagnostic_site(slug="ep29-diag-tenant-a")
    _tenant_b, site_b, _ = await _seed_diagnostic_site(slug="ep29-diag-tenant-b")

    # Login as tenant A operator
    cookies = await _login_operator(_tenant_a, client)

    # Try to access tenant B's site
    resp = client.get(f"/product/sites/{site_b}/diagnostic-results", cookies=cookies)
    assert resp.status_code == 404  # Non-disclosing


@pytest.mark.asyncio
async def test_diagnostic_results_nonexistent_site_404() -> None:
    """Non-existent site returns 404."""
    client = TestClient(app)
    _tenant_id, _site_id, _ = await _seed_diagnostic_site(slug="ep29-diag-404")
    cookies = await _login_operator(_tenant_id, client)

    fake_site_id = uuid.uuid4()
    resp = client.get(f"/product/sites/{fake_site_id}/diagnostic-results", cookies=cookies)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_diagnostic_results_no_diagnostic_run_404() -> None:
    """Site with only SCHEDULED runs (no DIAGNOSTIC/OPERATOR_UI) returns 404."""
    client = TestClient(app)
    tenant_id, site_id = await _seed_tenant_with_scheduled_run(slug="ep29-diag-no-diag")
    cookies = await _login_operator(tenant_id, client)

    resp = client.get(f"/product/sites/{site_id}/diagnostic-results", cookies=cookies)
    assert resp.status_code == 404
    assert "no diagnostic run found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_diagnostic_artifact_happy_path_screenshot_inline() -> None:
    """Screenshot artifact streams with inline disposition."""
    client = TestClient(app)
    tenant_id, site_id, run_id = await _seed_diagnostic_site(slug="ep29-artifact-a")
    cookies = await _login_operator(tenant_id, client)

    # Get artifact ID for screenshot

    factory = get_session_factory()
    async with factory() as session:
        artifact = await session.scalar(
            select(Artifact).where(
                Artifact.tenant_id == tenant_id,
                Artifact.site_id == site_id,
                Artifact.checkpoint_run_id == run_id,
                Artifact.artifact_type == "SCREENSHOT_VIEWPORT",
            )
        )
    assert artifact is not None

    resp = client.get(
        f"/product/sites/{site_id}/diagnostic-artifacts/{artifact.id}", cookies=cookies
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert "inline" in resp.headers["content-disposition"]
    assert resp.headers["cache-control"] == "private, no-store"
    assert len(resp.content) > 0


@pytest.mark.asyncio
async def test_diagnostic_artifact_happy_path_dom_download() -> None:
    """RAW_DOM/NORMALIZED_DOM artifacts stream with attachment disposition."""
    client = TestClient(app)
    tenant_id, site_id, run_id = await _seed_diagnostic_site(slug="ep29-artifact-b")
    cookies = await _login_operator(tenant_id, client)

    factory = get_session_factory()
    async with factory() as session:
        artifact = await session.scalar(
            select(Artifact).where(
                Artifact.tenant_id == tenant_id,
                Artifact.site_id == site_id,
                Artifact.checkpoint_run_id == run_id,
                Artifact.artifact_type == "RAW_DOM",
            )
        )
    assert artifact is not None

    resp = client.get(
        f"/product/sites/{site_id}/diagnostic-artifacts/{artifact.id}", cookies=cookies
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "attachment" in resp.headers["content-disposition"]
    assert resp.headers["cache-control"] == "private, no-store"


@pytest.mark.asyncio
async def test_diagnostic_artifact_unauthenticated_rejected() -> None:
    """Unauthenticated artifact request returns 401."""
    client = TestClient(app)
    tenant_id, site_id, run_id = await _seed_diagnostic_site(slug="ep29-artifact-unauth")

    factory = get_session_factory()
    async with factory() as session:
        artifact = await session.scalar(
            select(Artifact).where(
                Artifact.tenant_id == tenant_id,
                Artifact.site_id == site_id,
                Artifact.checkpoint_run_id == run_id,
                Artifact.artifact_type == "SCREENSHOT_VIEWPORT",
            )
        )
    assert artifact is not None

    resp = client.get(f"/product/sites/{site_id}/diagnostic-artifacts/{artifact.id}")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_diagnostic_artifact_wrong_tenant_404() -> None:
    """Operator from tenant A cannot access tenant B's artifacts."""
    client = TestClient(app)
    _tenant_a, _site_a, _run_a = await _seed_diagnostic_site(slug="ep29-artifact-tenant-a")
    tenant_b, site_b, run_b = await _seed_diagnostic_site(slug="ep29-artifact-tenant-b")

    cookies = await _login_operator(_tenant_a, client)

    factory = get_session_factory()
    async with factory() as session:
        artifact_b = await session.scalar(
            select(Artifact).where(
                Artifact.tenant_id == tenant_b,
                Artifact.site_id == site_b,
                Artifact.checkpoint_run_id == run_b,
                Artifact.artifact_type == "SCREENSHOT_VIEWPORT",
            )
        )
    assert artifact_b is not None

    resp = client.get(
        f"/product/sites/{site_b}/diagnostic-artifacts/{artifact_b.id}", cookies=cookies
    )
    assert resp.status_code == 404  # Non-disclosing


@pytest.mark.asyncio
async def test_diagnostic_artifact_wrong_run_rejected() -> None:
    """Artifact from SCHEDULED run not accessible via diagnostic artifact endpoint."""
    client = TestClient(app)
    tenant_id, site_id = await _seed_tenant_with_scheduled_run(slug="ep29-artifact-scheduled")
    cookies = await _login_operator(tenant_id, client)

    factory = get_session_factory()
    async with factory() as session:
        # Get artifact from SCHEDULED run
        scheduled_run = await session.scalar(
            select(CheckpointRun).where(
                CheckpointRun.tenant_id == tenant_id,
                CheckpointRun.site_id == site_id,
                CheckpointRun.observation_kind == "SCHEDULED",
            )
        )
        assert scheduled_run is not None
        artifact = await session.scalar(
            select(Artifact).where(
                Artifact.tenant_id == tenant_id,
                Artifact.site_id == site_id,
                Artifact.checkpoint_run_id == scheduled_run.id,
            )
        )
    assert artifact is not None

    resp = client.get(
        f"/product/sites/{site_id}/diagnostic-artifacts/{artifact.id}", cookies=cookies
    )
    assert resp.status_code == 404  # Non-disclosing - run is not DIAGNOSTIC/OPERATOR_UI


@pytest.mark.asyncio
async def test_diagnostic_artifact_unsupported_kind_rejected() -> None:
    """Unsupported artifact kind (not in allowlist) returns 404."""
    client = TestClient(app)
    tenant_id, site_id, run_id = await _seed_diagnostic_site(slug="ep29-artifact-kind")
    cookies = await _login_operator(tenant_id, client)

    factory = get_session_factory()
    async with factory() as session, session.begin():
        # Add an unsupported artifact type
        unsupported_id = uuid.uuid4()
        session.add(
            Artifact(
                id=unsupported_id,
                tenant_id=tenant_id,
                site_id=site_id,
                checkpoint_run_id=run_id,
                artifact_type="UNSUPPORTED_TYPE",
                storage_provider="S3_COMPATIBLE",
                object_key=f"tenant/{tenant_id}/site/{site_id}/checkpoints/{run_id}/unsupported.bin",
                content_type="application/octet-stream",
                byte_size=100,
                sha256="b" * 64,
                retention_class="CORE_LONG",
            )
        )

    resp = client.get(
        f"/product/sites/{site_id}/diagnostic-artifacts/{unsupported_id}", cookies=cookies
    )
    assert resp.status_code == 404  # Non-disclosing - kind not in allowlist


@pytest.mark.asyncio
async def test_diagnostic_results_non_operator_ui_run_excluded() -> None:
    """DIAGNOSTIC run with OPERATOR_CLI trigger_source is excluded."""

    client = TestClient(app)
    tenant_id, site_id = await _seed_tenant_with_scheduled_run(slug="ep29-diag-cli")
    run_id = uuid.uuid4()

    factory = get_session_factory()
    async with factory() as session, session.begin():
        # Add DIAGNOSTIC/OPERATOR_CLI run
        window_id = uuid.uuid4()
        template = await session.scalar(select(Template).where(Template.site_id == site_id))
        monitored_url = await session.scalar(
            select(MonitoredUrl).where(MonitoredUrl.site_id == site_id)
        )
        scenario = await session.scalar(
            select(BrowserScenario).where(BrowserScenario.site_id == site_id)
        )
        assert template is not None  # seeded by _seed_tenant_with_scheduled_run
        assert monitored_url is not None  # seeded by _seed_tenant_with_scheduled_run
        assert scenario is not None  # seeded by _seed_tenant_with_scheduled_run
        now = datetime.now(UTC)
        session.add(
            CheckpointWindow(
                id=window_id,
                tenant_id=tenant_id,
                site_id=site_id,
                scheduled_for=now,
                window_start=now,
                window_end=now + timedelta(minutes=5),
            )
        )
        await session.flush()
        session.add(
            CheckpointRun(
                id=run_id,
                tenant_id=tenant_id,
                site_id=site_id,
                checkpoint_window_id=window_id,
                monitored_url_id=monitored_url.id,
                template_id=template.id,
                scenario_id=scenario.id,
                observation_kind="DIAGNOSTIC",
                trigger_source="OPERATOR_CLI",
                trigger_correlation_id=uuid.uuid4(),
                scheduled_for=now,
                started_at=now,
                completed_at=now + timedelta(minutes=2),
                status="COMPLETE",
                attempt_count=1,
                collector_bundle_version="b8-v1",
                environment={},
                limitations=[],
                manifest={},
                browser_access_classification={"state": "ok", "reason": "normal"},
            )
        )

    cookies = await _login_operator(tenant_id, client)

    resp = client.get(f"/product/sites/{site_id}/diagnostic-results", cookies=cookies)
    assert resp.status_code == 404  # Only OPERATOR_UI runs qualify


@pytest.mark.asyncio
async def test_diagnostic_results_site_error_retrievable() -> None:
    """SITE_ERROR diagnostic run is retrievable (not hidden behind COMPLETE-only gate)."""
    client = TestClient(app)
    tenant_id, site_id, run_id = await _seed_diagnostic_site(slug="ep29-diag-site-error")
    # Override the run status to SITE_ERROR
    factory = get_session_factory()
    async with factory() as session, session.begin():
        run = await session.scalar(select(CheckpointRun).where(CheckpointRun.id == run_id))
        assert run is not None
        run.status = "SITE_ERROR"
        run.http_status = 429
        run.browser_access_classification = {"state": "challenge_suspected", "reason": "captcha"}
        run.final_url = "https://evz.ro/"
    cookies = await _login_operator(tenant_id, client)

    resp = client.get(f"/product/sites/{site_id}/diagnostic-results", cookies=cookies)
    assert resp.status_code == 200
    body = resp.json()
    assert body["run"]["status"] == "SITE_ERROR"
    assert body["run"]["http_status"] == 429
    assert body["run"]["browser_access_classification"] == "challenge_suspected"


@pytest.mark.asyncio
async def test_diagnostic_artifact_cross_site_same_tenant_accessible() -> None:
    """Artifact from another site in the same tenant IS accessible
    (operator manages all tenant sites)."""
    client = TestClient(app)

    # Create a tenant with two sites
    factory = get_session_factory()
    tenant_id = uuid.uuid4()
    publisher_id = uuid.uuid4()
    site_a_id = uuid.uuid4()
    site_b_id = uuid.uuid4()
    async with factory() as session, session.begin():
        session.add(Tenant(id=tenant_id, slug="ep29-site-test-a", name="Site Test A"))
        await session.flush()
        session.add(
            Publisher(
                id=publisher_id,
                tenant_id=tenant_id,
                name="Publisher Test",
                slug="publisher-test",
                default_timezone="UTC",
                status="ACTIVE",
            )
        )
        await session.flush()
        session.add(
            Site(
                id=site_a_id,
                tenant_id=tenant_id,
                publisher_id=publisher_id,
                name="Site A",
                canonical_domain="site-a.example.com",
                canonical_scheme="https",
                timezone="UTC",
                status="ACTIVE",
            )
        )
        session.add(
            Site(
                id=site_b_id,
                tenant_id=tenant_id,
                publisher_id=publisher_id,
                name="Site B",
                canonical_domain="site-b.example.com",
                canonical_scheme="https",
                timezone="UTC",
                status="ACTIVE",
            )
        )
        await session.flush()
        # Create templates, URLs, scenarios for both sites
        template_a_id = uuid.uuid4()
        template_b_id = uuid.uuid4()
        session.add(
            Template(
                id=template_a_id,
                tenant_id=tenant_id,
                site_id=site_a_id,
                code="article",
                display_name="Article",
                status="ACTIVE",
            )
        )
        session.add(
            Template(
                id=template_b_id,
                tenant_id=tenant_id,
                site_id=site_b_id,
                code="article",
                display_name="Article",
                status="ACTIVE",
            )
        )
        await session.flush()
        monitored_url_a_id = uuid.uuid4()
        monitored_url_b_id = uuid.uuid4()
        session.add(
            MonitoredUrl(
                id=monitored_url_a_id,
                tenant_id=tenant_id,
                site_id=site_a_id,
                template_id=template_a_id,
                url="https://site-a.example.com/a",
                status="ACTIVE",
            )
        )
        session.add(
            MonitoredUrl(
                id=monitored_url_b_id,
                tenant_id=tenant_id,
                site_id=site_b_id,
                template_id=template_b_id,
                url="https://site-b.example.com/a",
                status="ACTIVE",
            )
        )
        scenario_a_id = uuid.uuid4()
        scenario_b_id = uuid.uuid4()
        session.add(
            BrowserScenario(
                id=scenario_a_id,
                tenant_id=tenant_id,
                site_id=site_a_id,
                code="core_desktop_test",
                version=1,
                status="ACTIVE",
            )
        )
        session.add(
            BrowserScenario(
                id=scenario_b_id,
                tenant_id=tenant_id,
                site_id=site_b_id,
                code="core_desktop_test",
                version=1,
                status="ACTIVE",
            )
        )
        now = datetime.now(UTC)
        window_a_id = uuid.uuid4()
        window_b_id = uuid.uuid4()
        session.add(
            CheckpointWindow(
                id=window_a_id,
                tenant_id=tenant_id,
                site_id=site_a_id,
                scheduled_for=now - timedelta(minutes=10),
                window_start=now - timedelta(minutes=10),
                window_end=now - timedelta(minutes=5),
            )
        )
        session.add(
            CheckpointWindow(
                id=window_b_id,
                tenant_id=tenant_id,
                site_id=site_b_id,
                scheduled_for=now - timedelta(minutes=10),
                window_start=now - timedelta(minutes=10),
                window_end=now - timedelta(minutes=5),
            )
        )
        await session.flush()
        run_a_id = uuid.uuid4()
        run_b_id = uuid.uuid4()
        session.add(
            CheckpointRun(
                id=run_a_id,
                tenant_id=tenant_id,
                site_id=site_a_id,
                checkpoint_window_id=window_a_id,
                monitored_url_id=monitored_url_a_id,
                template_id=template_a_id,
                scenario_id=scenario_a_id,
                observation_kind="DIAGNOSTIC",
                trigger_source="OPERATOR_UI",
                trigger_correlation_id=uuid.uuid4(),
                scheduled_for=now - timedelta(minutes=10),
                started_at=now - timedelta(minutes=10),
                completed_at=now - timedelta(minutes=8),
                status="COMPLETE",
                attempt_count=1,
                final_url="https://site-a.example.com/a",
                http_status=200,
                collector_bundle_version="b8-v1",
                environment={"is_mobile": False},
                limitations=[],
                manifest={},
                browser_access_classification={"state": "ok", "reason": "normal access"},
            )
        )
        session.add(
            CheckpointRun(
                id=run_b_id,
                tenant_id=tenant_id,
                site_id=site_b_id,
                checkpoint_window_id=window_b_id,
                monitored_url_id=monitored_url_b_id,
                template_id=template_b_id,
                scenario_id=scenario_b_id,
                observation_kind="DIAGNOSTIC",
                trigger_source="OPERATOR_UI",
                trigger_correlation_id=uuid.uuid4(),
                scheduled_for=now - timedelta(minutes=10),
                started_at=now - timedelta(minutes=10),
                completed_at=now - timedelta(minutes=8),
                status="COMPLETE",
                attempt_count=1,
                final_url="https://site-b.example.com/a",
                http_status=200,
                collector_bundle_version="b8-v1",
                environment={"is_mobile": False},
                limitations=[],
                manifest={},
                browser_access_classification={"state": "ok", "reason": "normal access"},
            )
        )
        await session.flush()
        # Add artifact for site B
        artifact_b_id = uuid.uuid4()
        settings = Settings()
        storage = S3Storage(settings)
        dummy_content = b"x" * 1024
        object_key_b = (
            f"tenant/{tenant_id}/site/{site_b_id}/checkpoints/{run_b_id}/screenshot_viewport.bin"
        )
        storage.put_bytes(key=object_key_b, content=dummy_content, content_type="image/png")
        session.add(
            Artifact(
                id=artifact_b_id,
                tenant_id=tenant_id,
                site_id=site_b_id,
                checkpoint_run_id=run_b_id,
                artifact_type="SCREENSHOT_VIEWPORT",
                storage_provider="S3_COMPATIBLE",
                object_key=object_key_b,
                content_type="image/png",
                byte_size=1024,
                sha256="b" * 64,
                retention_class="CORE_LONG",
            )
        )

    client = TestClient(app)
    cookies = await _login_operator(tenant_id, client)

    factory = get_session_factory()
    async with factory() as session:
        artifact_b = await session.scalar(
            select(Artifact).where(
                Artifact.tenant_id == tenant_id,
                Artifact.site_id == site_b_id,
                Artifact.checkpoint_run_id == run_b_id,
                Artifact.artifact_type == "SCREENSHOT_VIEWPORT",
            )
        )
    assert artifact_b is not None

    # Operator can access site B's artifact using site B's ID in the URL
    resp = client.get(
        f"/product/sites/{site_b_id}/diagnostic-artifacts/{artifact_b_id}", cookies=cookies
    )
    assert resp.status_code == 200  # Accessible within same tenant


@pytest.mark.asyncio
async def test_diagnostic_artifact_missing_db_row() -> None:
    """Missing artifact DB row returns 404."""
    client = TestClient(app)
    _tenant_id, _site_id, _run_id = await _seed_diagnostic_site(slug="ep29-artifact-missing-db")
    cookies = await _login_operator(_tenant_id, client)

    fake_artifact_id = uuid.uuid4()
    resp = client.get(
        f"/product/sites/{_site_id}/diagnostic-artifacts/{fake_artifact_id}", cookies=cookies
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_diagnostic_artifact_missing_minio_object() -> None:
    """Missing MinIO object returns 404."""
    client = TestClient(app)
    tenant_id, site_id, run_id = await _seed_diagnostic_site(slug="ep29-artifact-missing-minio")
    cookies = await _login_operator(tenant_id, client)

    factory = get_session_factory()
    async with factory() as session:
        artifact = await session.scalar(
            select(Artifact).where(
                Artifact.tenant_id == tenant_id,
                Artifact.site_id == site_id,
                Artifact.checkpoint_run_id == run_id,
                Artifact.artifact_type == "SCREENSHOT_VIEWPORT",
            )
        )
    assert artifact is not None

    # Mock S3Storage.get_bytes to raise NoSuchKey
    with patch(
        "app.api.product.S3Storage.get_bytes",
        side_effect=ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "Not Found"}}, "GetObject"
        ),
    ):
        resp = client.get(
            f"/product/sites/{site_id}/diagnostic-artifacts/{artifact.id}", cookies=cookies
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_diagnostic_artifact_malicious_mime_blocked() -> None:
    """Stored malicious/incorrect MIME metadata cannot control response MIME."""
    client = TestClient(app)
    tenant_id, site_id, run_id = await _seed_diagnostic_site(slug="ep29-artifact-mime")
    cookies = await _login_operator(tenant_id, client)

    factory = get_session_factory()
    async with factory() as session, session.begin():
        # Get the artifact and verify its stored content_type is ignored
        artifact = await session.scalar(
            select(Artifact).where(
                Artifact.tenant_id == tenant_id,
                Artifact.site_id == site_id,
                Artifact.checkpoint_run_id == run_id,
                Artifact.artifact_type == "SCREENSHOT_VIEWPORT",
            )
        )
        assert artifact is not None
        # Corrupt the stored content_type (simulating malicious metadata)
        artifact.content_type = "text/html; charset=utf-8"

    resp = client.get(
        f"/product/sites/{site_id}/diagnostic-artifacts/{artifact.id}", cookies=cookies
    )
    assert resp.status_code == 200
    # Response MIME must be from server-side mapping, not stored metadata
    assert resp.headers["content-type"] == "image/png"
    assert resp.headers["content-disposition"].startswith("inline")


@pytest.mark.asyncio
async def test_diagnostic_artifact_safe_content_disposition_filename() -> None:
    """Content-Disposition filename is safely generated from trusted artifact type/ID."""
    client = TestClient(app)
    tenant_id, site_id, run_id = await _seed_diagnostic_site(slug="ep29-artifact-filename")
    cookies = await _login_operator(tenant_id, client)

    factory = get_session_factory()
    async with factory() as session:
        artifact = await session.scalar(
            select(Artifact).where(
                Artifact.tenant_id == tenant_id,
                Artifact.site_id == site_id,
                Artifact.checkpoint_run_id == run_id,
                Artifact.artifact_type == "SCREENSHOT_VIEWPORT",
            )
        )
    assert artifact is not None

    resp = client.get(
        f"/product/sites/{site_id}/diagnostic-artifacts/{artifact.id}", cookies=cookies
    )
    assert resp.status_code == 200
    # Filename should be safe: diagnostic-screenshot_viewport-{id}.png
    content_disposition = resp.headers["content-disposition"]
    assert 'inline; filename="diagnostic-screenshot_viewport-' in content_disposition
    assert content_disposition.endswith('.png"')
    # Should NOT contain path traversal or raw object key parts
    assert ".." not in content_disposition
    assert "/" not in content_disposition
    assert "\\" not in content_disposition


@pytest.mark.asyncio
async def test_diagnostic_artifact_headers_security() -> None:
    """Artifact responses have required security headers."""
    client = TestClient(app)
    tenant_id, site_id, run_id = await _seed_diagnostic_site(slug="ep29-artifact-headers")
    cookies = await _login_operator(tenant_id, client)

    factory = get_session_factory()
    async with factory() as session:
        artifact = await session.scalar(
            select(Artifact).where(
                Artifact.tenant_id == tenant_id,
                Artifact.site_id == site_id,
                Artifact.checkpoint_run_id == run_id,
                Artifact.artifact_type == "SCREENSHOT_VIEWPORT",
            )
        )
    assert artifact is not None

    resp = client.get(
        f"/product/sites/{site_id}/diagnostic-artifacts/{artifact.id}", cookies=cookies
    )
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "private, no-store"
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert "content-length" in resp.headers


@pytest.mark.asyncio
async def test_diagnostic_artifact_raw_dom_attachment_only() -> None:
    """RAW_DOM artifacts are attachment-only, never inline."""
    client = TestClient(app)
    tenant_id, site_id, run_id = await _seed_diagnostic_site(slug="ep29-artifact-rawdom")
    cookies = await _login_operator(tenant_id, client)

    factory = get_session_factory()
    async with factory() as session:
        artifact = await session.scalar(
            select(Artifact).where(
                Artifact.tenant_id == tenant_id,
                Artifact.site_id == site_id,
                Artifact.checkpoint_run_id == run_id,
                Artifact.artifact_type == "RAW_DOM",
            )
        )
    assert artifact is not None

    resp = client.get(
        f"/product/sites/{site_id}/diagnostic-artifacts/{artifact.id}", cookies=cookies
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "attachment" in resp.headers["content-disposition"]
    assert "inline" not in resp.headers["content-disposition"]


@pytest.mark.asyncio
async def test_diagnostic_artifact_normalized_dom_inert() -> None:
    """NORMALIZED_DOM artifacts are served as inert JSON attachment."""
    client = TestClient(app)
    tenant_id, site_id, run_id = await _seed_diagnostic_site(slug="ep29-artifact-normdom")
    cookies = await _login_operator(tenant_id, client)

    factory = get_session_factory()
    async with factory() as session:
        artifact = await session.scalar(
            select(Artifact).where(
                Artifact.tenant_id == tenant_id,
                Artifact.site_id == site_id,
                Artifact.checkpoint_run_id == run_id,
                Artifact.artifact_type == "NORMALIZED_DOM",
            )
        )
    assert artifact is not None

    resp = client.get(
        f"/product/sites/{site_id}/diagnostic-artifacts/{artifact.id}", cookies=cookies
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/json"
    assert "attachment" in resp.headers["content-disposition"]
    assert "inline" not in resp.headers["content-disposition"]


@pytest.mark.asyncio
async def test_diagnostic_artifact_oversized_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Oversized artifact (exceeds 20 MB cap) is rejected with 413."""
    # Test the endpoint logic directly by calling the route function
    from unittest.mock import MagicMock

    from fastapi import Request

    from app.api.product import diagnostic_artifact
    from app.auth.dependencies import ActorContext

    factory = get_session_factory()
    async with factory() as session, session.begin():
        # Create a test tenant, site, run, and oversized artifact
        tenant_id = uuid.uuid4()
        site_id = uuid.uuid4()
        run_id = uuid.uuid4()

        session.add(Tenant(id=tenant_id, slug="oversized-test", name="Oversized Test"))
        await session.flush()
        session.add(
            Publisher(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                name="Test Publisher",
                slug="test-pub",
                default_timezone="UTC",
                status="ACTIVE",
            )
        )
        await session.flush()
        session.add(
            Site(
                id=site_id,
                tenant_id=tenant_id,
                publisher_id=(
                    await session.execute(select(Publisher).where(Publisher.tenant_id == tenant_id))
                )
                .scalar_one()
                .id,
                name="Test Site",
                canonical_domain="oversized.example.com",
                canonical_scheme="https",
                timezone="UTC",
                status="ACTIVE",
            )
        )
        await session.flush()

        template_id = uuid.uuid4()
        monitored_url_id = uuid.uuid4()
        scenario_id = uuid.uuid4()
        window_id = uuid.uuid4()
        datetime.now(UTC)

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
                url="https://oversized.example.com/",
                status="ACTIVE",
            )
        )
        session.add(
            BrowserScenario(
                id=scenario_id,
                tenant_id=tenant_id,
                site_id=site_id,
                code="core_desktop_test",
                version=1,
                status="ACTIVE",
            )
        )
        session.add(
            CheckpointWindow(
                id=window_id,
                tenant_id=tenant_id,
                site_id=site_id,
                scheduled_for=datetime.now(UTC),
                window_start=datetime.now(UTC),
                window_end=datetime.now(UTC) + timedelta(minutes=5),
            )
        )
        await session.flush()

        run_id = uuid.uuid4()
        session.add(
            CheckpointRun(
                id=run_id,
                tenant_id=tenant_id,
                site_id=site_id,
                checkpoint_window_id=window_id,
                monitored_url_id=(
                    await session.execute(
                        select(MonitoredUrl).where(MonitoredUrl.site_id == site_id)
                    )
                )
                .scalar_one()
                .id,
                template_id=(
                    await session.execute(select(Template).where(Template.site_id == site_id))
                )
                .scalar_one()
                .id,
                scenario_id=(
                    await session.execute(
                        select(BrowserScenario).where(BrowserScenario.site_id == site_id)
                    )
                )
                .scalar_one()
                .id,
                observation_kind="DIAGNOSTIC",
                trigger_source="OPERATOR_UI",
                trigger_correlation_id=uuid.uuid4(),
                scheduled_for=datetime.now(UTC),
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC) + timedelta(minutes=2),
                status="COMPLETE",
                attempt_count=1,
                collector_bundle_version="b8-v1",
                environment={"is_mobile": False},
                limitations=[],
                manifest={},
                browser_access_classification={"state": "ok", "reason": "normal"},
            )
        )
        await session.flush()

        oversized_id = uuid.uuid4()
        session.add(
            Artifact(
                id=oversized_id,
                tenant_id=tenant_id,
                site_id=site_id,
                checkpoint_run_id=run_id,
                artifact_type="SCREENSHOT_FULL_PAGE",
                storage_provider="S3_COMPATIBLE",
                object_key="tenant/oversized.bin",
                content_type="image/png",
                byte_size=25 * 1024 * 1024,  # 25 MB > 20 MB cap
                sha256="c" * 64,
                retention_class="CORE_LONG",
            )
        )

    # Call the endpoint function directly with a mock request

    # Call the endpoint function directly with a mock request
    mock_request = MagicMock(spec=Request)
    mock_request.state.actor = ActorContext(
        session_id=uuid.uuid4(),
        operator_id=uuid.uuid4(),
        actor_subject_id=uuid.uuid4(),
        tenant_id=tenant_id,
        role="OPERATOR",
    )

    # Mock the session factory at the location production code resolves it
    # (app.api.product module globals) via the canonical pytest monkeypatch.
    from collections.abc import AsyncIterator
    from contextlib import asynccontextmanager

    from fastapi import HTTPException
    from sqlalchemy.ext.asyncio import AsyncSession

    import app.api.product as product_module

    @asynccontextmanager
    async def mock_session_factory() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    monkeypatch.setattr(product_module, "get_session_factory", lambda: mock_session_factory)

    try:
        await diagnostic_artifact(
            site_id=site_id, artifact_id=oversized_id, actor=mock_request.state.actor
        )
    except HTTPException as e:
        assert e.status_code == 413
        assert "exceeds maximum allowed size" in e.detail.lower()
    else:
        raise AssertionError("Expected HTTPException with status 413")


@pytest.mark.asyncio
async def test_diagnostic_artifact_no_internal_storage_info_exposed() -> None:
    """Artifact responses never expose internal MinIO bucket, keys, endpoints, or credentials."""
    client = TestClient(app)
    tenant_id, site_id, run_id = await _seed_diagnostic_site(slug="ep29-artifact-no-leak")
    cookies = await _login_operator(tenant_id, client)

    factory = get_session_factory()
    async with factory() as session:
        artifact = await session.scalar(
            select(Artifact).where(
                Artifact.tenant_id == tenant_id,
                Artifact.site_id == site_id,
                Artifact.checkpoint_run_id == run_id,
                Artifact.artifact_type == "SCREENSHOT_VIEWPORT",
            )
        )
    assert artifact is not None

    resp = client.get(
        f"/product/sites/{site_id}/diagnostic-artifacts/{artifact.id}", cookies=cookies
    )
    assert resp.status_code == 200
    # Verify no internal storage details in response
    response_text = resp.text
    assert "minio" not in response_text.lower()
    assert "s3" not in response_text.lower()
    assert artifact.object_key not in response_text
    assert "bucket" not in response_text.lower()
    assert "endpoint" not in response_text.lower()
    assert "access_key" not in response_text.lower()
    assert "secret" not in response_text.lower()
    # Only safe headers present
    assert "content-type" in resp.headers
    assert "content-disposition" in resp.headers
    assert "cache-control" in resp.headers
    assert "x-content-type-options" in resp.headers
    assert "content-length" in resp.headers
