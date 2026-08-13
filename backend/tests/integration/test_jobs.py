import asyncio
import uuid

import pytest
from sqlalchemy import delete, text

from app.db.models import Job, Tenant
from app.db.session import get_session_factory
from app.jobs.queue import JobQueue

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
async def clean_jobs() -> None:
    factory = get_session_factory()
    async with factory() as session, session.begin():
        await session.execute(delete(Job))
        await session.execute(delete(Tenant))


async def create_tenant(slug: str) -> uuid.UUID:
    tenant_id = uuid.uuid4()
    factory = get_session_factory()
    async with factory() as session, session.begin():
        session.add(Tenant(id=tenant_id, slug=slug, name=slug.title()))
    return tenant_id


async def test_tenant_and_global_idempotency_namespaces() -> None:
    queue = JobQueue(get_session_factory())
    tenant_a = await create_tenant("tenant-a")
    tenant_b = await create_tenant("tenant-b")

    tenant_a_first = await queue.enqueue(
        tenant_id=tenant_a, job_type="BOOTSTRAP_NOOP", idempotency_key="same-key"
    )
    tenant_a_duplicate = await queue.enqueue(
        tenant_id=tenant_a, job_type="BOOTSTRAP_NOOP", idempotency_key="same-key"
    )
    tenant_b_job = await queue.enqueue(
        tenant_id=tenant_b, job_type="BOOTSTRAP_NOOP", idempotency_key="same-key"
    )
    global_first = await queue.enqueue(job_type="BOOTSTRAP_NOOP", idempotency_key="same-key")
    global_duplicate = await queue.enqueue(job_type="BOOTSTRAP_NOOP", idempotency_key="same-key")

    assert tenant_a_first == tenant_a_duplicate
    assert global_first == global_duplicate
    assert len({tenant_a_first, tenant_b_job, global_first}) == 3


async def test_concurrent_claims_return_one_lease() -> None:
    queue = JobQueue(get_session_factory())
    job_id = await queue.enqueue(job_type="BOOTSTRAP_NOOP")

    first, second = await asyncio.gather(
        queue.claim(worker_id="worker-a", lease_seconds=30),
        queue.claim(worker_id="worker-b", lease_seconds=30),
    )

    leases = [lease for lease in (first, second) if lease is not None]
    assert len(leases) == 1
    assert leases[0].id == job_id


async def test_job_type_claim_filter_keeps_browser_work_isolated() -> None:
    queue = JobQueue(get_session_factory())
    browser_job = await queue.enqueue(job_type="BROWSER_CHECKPOINT", priority=10)
    general_job = await queue.enqueue(job_type="BOOTSTRAP_NOOP")

    general = await queue.claim(
        worker_id="general", lease_seconds=30, excluded_job_type="BROWSER_CHECKPOINT"
    )
    browser = await queue.claim(
        worker_id="browser", lease_seconds=30, job_type="BROWSER_CHECKPOINT"
    )

    assert general is not None and general.id == general_job
    assert browser is not None and browser.id == browser_job


async def test_reclaim_fences_stale_worker() -> None:
    queue = JobQueue(get_session_factory())
    await queue.enqueue(job_type="BOOTSTRAP_NOOP", max_attempts=3)
    first = await queue.claim(worker_id="worker-a", lease_seconds=30)
    assert first is not None

    factory = get_session_factory()
    async with factory() as session, session.begin():
        await session.execute(
            text(
                "UPDATE jobs SET lock_expires_at = "
                "CURRENT_TIMESTAMP - INTERVAL '1 second' WHERE id = :id"
            ),
            {"id": first.id},
        )

    assert await queue.claim(worker_id="worker-b", lease_seconds=30) is None
    assert await queue.reclaim_expired(backoff_seconds=0) == 1
    second = await queue.claim(worker_id="worker-b", lease_seconds=30)
    assert second is not None
    assert second.id == first.id
    assert second.lock_token != first.lock_token
    assert not await queue.complete(job_id=first.id, lock_token=first.lock_token)
    assert await queue.complete(job_id=second.id, lock_token=second.lock_token)


async def test_heartbeat_and_retry_exhaustion_are_fenced() -> None:
    queue = JobQueue(get_session_factory())
    await queue.enqueue(job_type="RETRY_TEST", max_attempts=2)
    first = await queue.claim(worker_id="worker-a", lease_seconds=30)
    assert first is not None
    assert await queue.heartbeat(job_id=first.id, lock_token=first.lock_token, lease_seconds=30)
    assert await queue.fail_or_retry(
        job_id=first.id,
        lock_token=first.lock_token,
        retryable=True,
        error_class="TIMEOUT",
        error_message="temporary failure",
        backoff_seconds=0,
    )

    second = await queue.claim(worker_id="worker-b", lease_seconds=30)
    assert second is not None
    assert second.attempt == 2
    assert not await queue.heartbeat(job_id=first.id, lock_token=first.lock_token, lease_seconds=30)
    assert await queue.fail_or_retry(
        job_id=second.id,
        lock_token=second.lock_token,
        retryable=True,
        error_class="TIMEOUT",
        error_message="x" * 2000,
        backoff_seconds=0,
    )

    factory = get_session_factory()
    async with factory() as session:
        job = await session.get(Job, second.id)
        assert job is not None
        assert job.status == "FAILED"
        assert job.last_error_class == "TIMEOUT"
        assert job.last_error_message == "x" * 1000
        assert job.finished_at is not None


async def test_tenant_scoped_lookup_denies_other_tenant() -> None:
    queue = JobQueue(get_session_factory())
    tenant_a = await create_tenant("lookup-a")
    tenant_b = await create_tenant("lookup-b")
    job_id = await queue.enqueue(tenant_id=tenant_a, job_type="BOOTSTRAP_NOOP")

    assert await queue.get_for_tenant(tenant_id=tenant_a, job_id=job_id) is not None
    assert await queue.get_for_tenant(tenant_id=tenant_b, job_id=job_id) is None
