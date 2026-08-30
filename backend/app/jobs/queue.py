import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Job


@dataclass(frozen=True, slots=True)
class JobLease:
    id: uuid.UUID
    tenant_id: uuid.UUID | None
    job_type: str
    payload: dict[str, Any]
    attempt: int
    max_attempts: int
    lock_token: uuid.UUID


class JobQueue:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def enqueue(
        self,
        *,
        job_type: str,
        payload: dict[str, Any] | None = None,
        tenant_id: uuid.UUID | None = None,
        idempotency_key: str | None = None,
        priority: int = 0,
        max_attempts: int = 3,
        scheduled_at: datetime | None = None,
    ) -> uuid.UUID:
        async with self._session_factory() as session, session.begin():
            return await self.enqueue_in_session(
                session,
                job_type=job_type,
                payload=payload,
                tenant_id=tenant_id,
                idempotency_key=idempotency_key,
                priority=priority,
                max_attempts=max_attempts,
                scheduled_at=scheduled_at,
            )

    async def enqueue_in_session(
        self,
        session: AsyncSession,
        *,
        job_type: str,
        payload: dict[str, Any] | None = None,
        tenant_id: uuid.UUID | None = None,
        idempotency_key: str | None = None,
        priority: int = 0,
        max_attempts: int = 3,
        scheduled_at: datetime | None = None,
    ) -> uuid.UUID:
        """Insert a job using the caller's transaction.

        This preserves the queue's existing idempotency semantics while allowing
        a use case to commit its domain rows and the matching job atomically.
        The caller owns commit/rollback and must not pass a session outside an
        active transaction.
        """
        job_id = uuid.uuid4()
        scheduled = scheduled_at or datetime.now(UTC)
        statement = (
            insert(Job)
            .values(
                id=job_id,
                tenant_id=tenant_id,
                job_type=job_type,
                payload=payload or {},
                status="PENDING",
                priority=priority,
                max_attempts=max_attempts,
                scheduled_at=scheduled,
                available_at=scheduled,
                idempotency_key=idempotency_key,
            )
            .on_conflict_do_nothing()
            .returning(Job.id)
        )
        inserted = (await session.execute(statement)).scalar_one_or_none()
        if inserted is not None:
            return inserted
        if idempotency_key is None:
            raise RuntimeError("job insert conflicted without an idempotency key")
        existing = await session.scalar(
            select(Job.id).where(
                Job.tenant_id == tenant_id,
                Job.idempotency_key == idempotency_key,
            )
        )
        if existing is None:
            raise RuntimeError("idempotent job conflict could not be resolved")
        return existing

    async def claim(
        self,
        *,
        worker_id: str,
        lease_seconds: int,
        job_type: str | None = None,
        excluded_job_type: str | None = None,
    ) -> JobLease | None:
        if job_type is not None and excluded_job_type is not None:
            raise ValueError("job_type and excluded_job_type are mutually exclusive")
        lock_token = uuid.uuid4()
        statement = text(
            """
            WITH candidate AS (
                SELECT id
                FROM jobs
                WHERE status IN ('PENDING', 'RETRY')
                  AND scheduled_at <= CURRENT_TIMESTAMP
                  AND available_at <= CURRENT_TIMESTAMP
                  AND (
                      CAST(:job_type AS text) IS NULL
                      OR job_type = CAST(:job_type AS text)
                  )
                  AND (
                      CAST(:excluded_job_type AS text) IS NULL
                      OR job_type <> CAST(:excluded_job_type AS text)
                  )
                ORDER BY priority DESC, available_at ASC, created_at ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            UPDATE jobs AS job
            SET status = 'RUNNING',
                locked_by = :worker_id,
                lock_token = :lock_token,
                lock_expires_at = CURRENT_TIMESTAMP
                    + CAST(:lease_seconds AS integer) * INTERVAL '1 second',
                started_at = COALESCE(started_at, CURRENT_TIMESTAMP),
                finished_at = NULL,
                attempt = attempt + 1,
                updated_at = CURRENT_TIMESTAMP
            FROM candidate
            WHERE job.id = candidate.id
            RETURNING job.id, job.tenant_id, job.job_type, job.payload,
                      job.attempt, job.max_attempts, job.lock_token
            """
        )
        async with self._session_factory() as session, session.begin():
            row = (
                (
                    await session.execute(
                        statement,
                        {
                            "worker_id": worker_id,
                            "lock_token": lock_token,
                            "lease_seconds": lease_seconds,
                            "job_type": job_type,
                            "excluded_job_type": excluded_job_type,
                        },
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            return None
        return JobLease(
            id=row["id"],
            tenant_id=row["tenant_id"],
            job_type=row["job_type"],
            payload=dict(row["payload"]),
            attempt=row["attempt"],
            max_attempts=row["max_attempts"],
            lock_token=row["lock_token"],
        )

    async def heartbeat(
        self, *, job_id: uuid.UUID, lock_token: uuid.UUID, lease_seconds: int
    ) -> bool:
        statement = (
            update(Job)
            .where(Job.id == job_id, Job.status == "RUNNING", Job.lock_token == lock_token)
            .values(
                lock_expires_at=text(
                    "CURRENT_TIMESTAMP + CAST(:lease_seconds AS integer) * INTERVAL '1 second'"
                ),
                updated_at=text("CURRENT_TIMESTAMP"),
            )
        )
        async with self._session_factory() as session, session.begin():
            result = cast(
                CursorResult[Any],
                await session.execute(statement, {"lease_seconds": lease_seconds}),
            )
            return result.rowcount == 1

    async def complete(self, *, job_id: uuid.UUID, lock_token: uuid.UUID) -> bool:
        return await self._finish(
            job_id=job_id,
            lock_token=lock_token,
            status="COMPLETE",
            error_class=None,
            error_message=None,
        )

    async def fail_or_retry(
        self,
        *,
        job_id: uuid.UUID,
        lock_token: uuid.UUID,
        retryable: bool,
        error_class: str,
        error_message: str,
        backoff_seconds: int,
    ) -> bool:
        bounded_message = error_message[:1000]
        statement = text(
            """
            UPDATE jobs
            SET status = CASE
                    WHEN :retryable AND attempt < max_attempts THEN 'RETRY'
                    ELSE 'FAILED'
                END,
                available_at = CASE
                    WHEN :retryable AND attempt < max_attempts
                    THEN CURRENT_TIMESTAMP
                        + CAST(:backoff_seconds AS integer) * INTERVAL '1 second'
                    ELSE available_at
                END,
                finished_at = CASE
                    WHEN :retryable AND attempt < max_attempts THEN NULL
                    ELSE CURRENT_TIMESTAMP
                END,
                locked_by = NULL,
                lock_token = NULL,
                lock_expires_at = NULL,
                last_error_class = :error_class,
                last_error_message = :error_message,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :job_id
              AND status = 'RUNNING'
              AND lock_token = :lock_token
            """
        )
        async with self._session_factory() as session, session.begin():
            result = cast(
                CursorResult[Any],
                await session.execute(
                    statement,
                    {
                        "retryable": retryable,
                        "backoff_seconds": backoff_seconds,
                        "error_class": error_class,
                        "error_message": bounded_message,
                        "job_id": job_id,
                        "lock_token": lock_token,
                    },
                ),
            )
            return result.rowcount == 1

    async def _finish(
        self,
        *,
        job_id: uuid.UUID,
        lock_token: uuid.UUID,
        status: str,
        error_class: str | None,
        error_message: str | None,
    ) -> bool:
        statement = (
            update(Job)
            .where(Job.id == job_id, Job.status == "RUNNING", Job.lock_token == lock_token)
            .values(
                status=status,
                finished_at=text("CURRENT_TIMESTAMP"),
                locked_by=None,
                lock_token=None,
                lock_expires_at=None,
                last_error_class=error_class,
                last_error_message=error_message,
                updated_at=text("CURRENT_TIMESTAMP"),
            )
        )
        async with self._session_factory() as session, session.begin():
            result = cast(CursorResult[Any], await session.execute(statement))
            return result.rowcount == 1

    async def reclaim_expired(self, *, backoff_seconds: int, limit: int = 100) -> int:
        statement = text(
            """
            WITH expired AS (
                SELECT id
                FROM jobs
                WHERE status = 'RUNNING'
                  AND lock_expires_at < CURRENT_TIMESTAMP
                ORDER BY lock_expires_at ASC
                FOR UPDATE SKIP LOCKED
                LIMIT :limit
            )
            UPDATE jobs AS job
            SET status = CASE WHEN attempt < max_attempts THEN 'RETRY' ELSE 'FAILED' END,
                available_at = CASE
                    WHEN attempt < max_attempts
                    THEN CURRENT_TIMESTAMP
                        + CAST(:backoff_seconds AS integer) * INTERVAL '1 second'
                    ELSE available_at
                END,
                finished_at = CASE
                    WHEN attempt < max_attempts THEN NULL
                    ELSE CURRENT_TIMESTAMP
                END,
                locked_by = NULL,
                lock_token = NULL,
                lock_expires_at = NULL,
                last_error_class = 'LEASE_EXPIRED',
                last_error_message = 'Worker lease expired before completion',
                updated_at = CURRENT_TIMESTAMP
            FROM expired
            WHERE job.id = expired.id
            RETURNING job.id
            """
        )
        async with self._session_factory() as session, session.begin():
            rows = (
                await session.execute(
                    statement,
                    {"backoff_seconds": backoff_seconds, "limit": limit},
                )
            ).all()
            return len(rows)

    async def get_for_tenant(self, *, tenant_id: uuid.UUID, job_id: uuid.UUID) -> Job | None:
        async with self._session_factory() as session:
            return cast(
                Job | None,
                await session.scalar(
                    select(Job).where(Job.id == job_id, Job.tenant_id == tenant_id)
                ),
            )
