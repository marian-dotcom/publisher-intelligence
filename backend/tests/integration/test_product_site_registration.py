import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.models import Operator, OperatorTenant
from app.auth.security import hash_password
from app.browser.models import CheckpointRun, Site
from app.browser.operator_registration import (
    DuplicateSiteRegistrationError,
    OperatorSiteRegistrationService,
    RegisteredOperatorSite,
)
from app.browser.security import BrowserNetworkGuard
from app.browser.service import CheckpointService
from app.config.settings import get_settings
from app.db.models import Job, Tenant
from app.db.session import get_session_factory
from app.jobs.queue import JobQueue
from app.main import app
from tests.integration.purge import make_purge

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _clean_db() -> None:
    purge = make_purge(get_session_factory)
    asyncio.run(purge())
    yield
    asyncio.run(purge())


@pytest.fixture
async def operator_with_two_tenants() -> tuple[uuid.UUID, list[uuid.UUID], str]:
    factory = get_session_factory()
    operator_id = uuid.uuid4()
    email = f"site-op-{operator_id.hex[:8]}@example.com"
    tenant_ids = [uuid.uuid4(), uuid.uuid4()]
    async with factory() as session, session.begin():
        for index, tenant_id in enumerate(tenant_ids):
            session.add(
                Tenant(
                    id=tenant_id,
                    slug=f"site-reg-{index}-{tenant_id.hex[:8]}",
                    name=f"Site Registration Tenant {index}",
                )
            )
        await session.flush()
        session.add(
            Operator(
                id=operator_id,
                actor_subject_id=uuid.uuid4(),
                email=email,
                password_hash=hash_password("operator-site-password"),
                role="OPERATOR",
                is_active=True,
            )
        )
        await session.flush()
        for tenant_id in tenant_ids:
            session.add(OperatorTenant(operator_id=operator_id, tenant_id=tenant_id))
    return operator_id, tenant_ids, email


def _login(client: TestClient, *, email: str, tenant_id: uuid.UUID) -> tuple[str, dict[str, str]]:
    response = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": "operator-site-password",
            "tenant_id": str(tenant_id),
        },
    )
    assert response.status_code == 200
    return response.json()["csrf_token"], dict(response.cookies)


def _payload(url: str = "https://news.example.test/") -> dict[str, str]:
    return {
        "publisher_name": "Example Publisher",
        "site_name": "Example News",
        "url": url,
    }


async def _allow_target(_self: BrowserNetworkGuard, url: str) -> str:
    return url


@pytest.mark.asyncio
async def test_valid_csrf_registration_is_tenant_bound_and_atomic(
    operator_with_two_tenants: tuple[uuid.UUID, list[uuid.UUID], str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(BrowserNetworkGuard, "validate_initial", _allow_target)
    _operator_id, tenants, email = operator_with_two_tenants
    tenant_id = tenants[0]
    client = TestClient(app)
    csrf, cookies = _login(client, email=email, tenant_id=tenant_id)

    response = client.post(
        "/product/sites",
        headers={"X-CSRF-Token": csrf},
        cookies=cookies,
        json=_payload(),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["canonical_domain"] == "news.example.test"
    assert body["diagnostic_status"] == "PENDING"
    site_id = uuid.UUID(body["site_id"])
    run_id = uuid.UUID(body["checkpoint_run_id"])

    factory = get_session_factory()
    async with factory() as session:
        site = await session.scalar(
            select(Site).where(Site.id == site_id, Site.tenant_id == tenant_id)
        )
        run = await session.scalar(
            select(CheckpointRun).where(
                CheckpointRun.id == run_id,
                CheckpointRun.tenant_id == tenant_id,
            )
        )
        jobs = list(
            (
                await session.scalars(
                    select(Job).where(Job.tenant_id == tenant_id, Job.job_type == "BROWSER_CHECKPOINT")
                )
            ).all()
        )
    assert site is not None
    assert run is not None
    assert run.site_id == site_id
    assert run.observation_kind == "DIAGNOSTIC"
    assert run.trigger_source == "OPERATOR_UI"
    assert run.trigger_correlation_id is not None
    assert len(jobs) == 1
    assert jobs[0].payload == {"checkpoint_run_id": str(run_id)}
    assert jobs[0].idempotency_key == f"browser-checkpoint:{run_id}"


def test_registration_requires_authentication_and_csrf(
    operator_with_two_tenants: tuple[uuid.UUID, list[uuid.UUID], str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(BrowserNetworkGuard, "validate_initial", _allow_target)
    _operator_id, tenants, email = operator_with_two_tenants
    tenant_id = tenants[0]

    anonymous = TestClient(app).post(
        "/product/sites",
        headers={"X-CSRF-Token": "irrelevant"},
        json=_payload(),
    )
    assert anonymous.status_code == 401

    client = TestClient(app)
    csrf, cookies = _login(client, email=email, tenant_id=tenant_id)
    missing = client.post("/product/sites", cookies=cookies, json=_payload())
    assert missing.status_code == 403
    invalid = client.post(
        "/product/sites",
        headers={"X-CSRF-Token": f"{csrf}-wrong"},
        cookies=cookies,
        json=_payload(),
    )
    assert invalid.status_code == 403


def test_payload_cannot_select_tenant(
    operator_with_two_tenants: tuple[uuid.UUID, list[uuid.UUID], str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(BrowserNetworkGuard, "validate_initial", _allow_target)
    _operator_id, tenants, email = operator_with_two_tenants
    client = TestClient(app)
    csrf, cookies = _login(client, email=email, tenant_id=tenants[0])
    payload = {**_payload(), "tenant_id": str(tenants[1])}
    response = client.post(
        "/product/sites",
        headers={"X-CSRF-Token": csrf},
        cookies=cookies,
        json=payload,
    )
    assert response.status_code == 422


def test_forbidden_target_is_rejected_before_persistence(
    operator_with_two_tenants: tuple[uuid.UUID, list[uuid.UUID], str],
) -> None:
    _operator_id, tenants, email = operator_with_two_tenants
    tenant_id = tenants[0]
    client = TestClient(app)
    csrf, cookies = _login(client, email=email, tenant_id=tenant_id)
    response = client.post(
        "/product/sites",
        headers={"X-CSRF-Token": csrf},
        cookies=cookies,
        json=_payload("http://metadata.google.internal/"),
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "site URL is not an allowed public target"}

    async def counts() -> tuple[int, int, int]:
        factory = get_session_factory()
        async with factory() as session:
            sites = list((await session.scalars(select(Site))).all())
            runs = list((await session.scalars(select(CheckpointRun))).all())
            jobs = list((await session.scalars(select(Job))).all())
        return len(sites), len(runs), len(jobs)

    assert asyncio.run(counts()) == (0, 0, 0)


@pytest.mark.asyncio
async def test_duplicate_same_tenant_is_conflict_without_second_run_or_job(
    operator_with_two_tenants: tuple[uuid.UUID, list[uuid.UUID], str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(BrowserNetworkGuard, "validate_initial", _allow_target)
    _operator_id, tenants, email = operator_with_two_tenants
    tenant_id = tenants[0]
    client = TestClient(app)
    csrf, cookies = _login(client, email=email, tenant_id=tenant_id)

    first = client.post(
        "/product/sites",
        headers={"X-CSRF-Token": csrf},
        cookies=cookies,
        json=_payload(),
    )
    second = client.post(
        "/product/sites",
        headers={"X-CSRF-Token": csrf},
        cookies=cookies,
        json=_payload("https://NEWS.EXAMPLE.TEST/another-path"),
    )
    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json() == {"detail": "site already registered"}

    factory = get_session_factory()
    async with factory() as session:
        sites = list((await session.scalars(select(Site).where(Site.tenant_id == tenant_id))).all())
        runs = list(
            (
                await session.scalars(
                    select(CheckpointRun).where(
                        CheckpointRun.tenant_id == tenant_id,
                        CheckpointRun.trigger_source == "OPERATOR_UI",
                    )
                )
            ).all()
        )
        jobs = list((await session.scalars(select(Job).where(Job.tenant_id == tenant_id))).all())
    assert len(sites) == 1
    assert len(runs) == 1
    assert len(jobs) == 1


@pytest.mark.asyncio
async def test_same_domain_is_independent_across_tenants(
    operator_with_two_tenants: tuple[uuid.UUID, list[uuid.UUID], str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(BrowserNetworkGuard, "validate_initial", _allow_target)
    _operator_id, tenants, email = operator_with_two_tenants
    client = TestClient(app)

    csrf_a, cookies_a = _login(client, email=email, tenant_id=tenants[0])
    first = client.post(
        "/product/sites",
        headers={"X-CSRF-Token": csrf_a},
        cookies=cookies_a,
        json=_payload(),
    )
    assert first.status_code == 201

    csrf_b, cookies_b = _login(client, email=email, tenant_id=tenants[1])
    second = client.post(
        "/product/sites",
        headers={"X-CSRF-Token": csrf_b},
        cookies=cookies_b,
        json=_payload(),
    )
    assert second.status_code == 201
    assert first.json()["site_id"] != second.json()["site_id"]

    factory = get_session_factory()
    async with factory() as session:
        sites = list(
            (
                await session.scalars(
                    select(Site).where(Site.canonical_domain == "news.example.test")
                )
            ).all()
        )
    assert {site.tenant_id for site in sites} == set(tenants)


@pytest.mark.asyncio
async def test_concurrent_duplicate_registration_creates_one_site_run_and_job(
    operator_with_two_tenants: tuple[uuid.UUID, list[uuid.UUID], str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(BrowserNetworkGuard, "validate_initial", _allow_target)
    _operator_id, tenants, _email = operator_with_two_tenants
    tenant_id = tenants[0]
    factory = get_session_factory()
    service = OperatorSiteRegistrationService(factory, JobQueue(factory), get_settings())

    results = await asyncio.gather(
        service.register_for_tenant(
            tenant_id=tenant_id,
            publisher_name="Concurrent Publisher",
            site_name="Concurrent Site",
            url="https://concurrent.example.test/",
        ),
        service.register_for_tenant(
            tenant_id=tenant_id,
            publisher_name="Concurrent Publisher",
            site_name="Concurrent Site",
            url="https://concurrent.example.test/",
        ),
        return_exceptions=True,
    )
    successes = [result for result in results if isinstance(result, RegisteredOperatorSite)]
    conflicts = [result for result in results if isinstance(result, DuplicateSiteRegistrationError)]
    assert len(successes) == 1
    assert len(conflicts) == 1

    async with factory() as session:
        sites = list((await session.scalars(select(Site).where(Site.tenant_id == tenant_id))).all())
        runs = list(
            (
                await session.scalars(
                    select(CheckpointRun).where(
                        CheckpointRun.tenant_id == tenant_id,
                        CheckpointRun.trigger_source == "OPERATOR_UI",
                    )
                )
            ).all()
        )
        jobs = list((await session.scalars(select(Job).where(Job.tenant_id == tenant_id))).all())
    assert len(sites) == 1
    assert len(runs) == 1
    assert len(jobs) == 1


@pytest.mark.asyncio
async def test_cli_registration_keeps_operator_cli_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(BrowserNetworkGuard, "validate_initial", _allow_target)
    factory = get_session_factory()
    service = CheckpointService(factory, JobQueue(factory), get_settings())
    result = await service.register_and_enqueue(
        tenant_slug=f"cli-{uuid.uuid4().hex[:8]}",
        tenant_name="CLI Tenant",
        publisher_name="CLI Publisher",
        site_name="CLI Site",
        url="https://cli.example.test/",
    )
    async with factory() as session:
        run = await session.scalar(
            select(CheckpointRun).where(CheckpointRun.id == result.checkpoint_run_id)
        )
    assert run is not None
    assert run.observation_kind == "DIAGNOSTIC"
    assert run.trigger_source == "OPERATOR_CLI"
    assert run.trigger_correlation_id == result.trigger_correlation_id
