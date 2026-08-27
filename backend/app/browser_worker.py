import argparse
import asyncio
import json
import logging
import signal
import socket
import traceback
import uuid
from pathlib import Path

from app.browser.cost import CheckpointCostRecorder
from app.browser.persistence import CheckpointRepository, CheckpointStateError, EvidencePersister
from app.browser.runner import BrowserRunner
from app.common.logging import configure_logging
from app.config.settings import Settings, get_settings
from app.db.session import get_session_factory
from app.jobs.queue import JobLease, JobQueue
from app.storage.s3 import S3Storage

logger = logging.getLogger(__name__)


def _safe_error_source(error: Exception) -> dict[str, str | int]:
    frames = traceback.extract_tb(error.__traceback__)
    if not frames:
        return {}
    frame = frames[-1]
    return {
        "error_module": Path(frame.filename).name,
        "error_function": frame.name,
        "error_line": frame.lineno or 0,
    }


async def handle_browser_job(
    *,
    queue: JobQueue,
    repository: CheckpointRepository,
    persister: EvidencePersister,
    runner: BrowserRunner,
    lease: JobLease,
    backoff_seconds: int,
    cost_recorder: CheckpointCostRecorder | None = None,
) -> None:
    context = {
        "job_id": str(lease.id),
        "tenant_id": str(lease.tenant_id) if lease.tenant_id else None,
        "attempt": lease.attempt,
    }
    if lease.job_type != "BROWSER_CHECKPOINT":
        await queue.fail_or_retry(
            job_id=lease.id,
            lock_token=lease.lock_token,
            retryable=False,
            error_class="UNKNOWN_JOB_TYPE",
            error_message="Browser worker received an unsupported job type",
            backoff_seconds=backoff_seconds,
        )
        logger.error("browser job rejected", extra={"context": context})
        return
    if lease.tenant_id is None or set(lease.payload) != {"checkpoint_run_id"}:
        await _fail_invalid(
            queue, lease, backoff_seconds, "Invalid browser job ownership or payload"
        )
        return
    try:
        checkpoint_run_id = uuid.UUID(str(lease.payload["checkpoint_run_id"]))
    except (ValueError, TypeError, AttributeError):
        await _fail_invalid(queue, lease, backoff_seconds, "Invalid checkpoint identifier")
        return

    try:
        target = await repository.begin_attempt(
            tenant_id=lease.tenant_id,
            checkpoint_run_id=checkpoint_run_id,
            attempt_number=lease.attempt,
        )
    except CheckpointStateError:
        await queue.fail_or_retry(
            job_id=lease.id,
            lock_token=lease.lock_token,
            retryable=False,
            error_class="CHECKPOINT_STATE_ERROR",
            error_message="Checkpoint ownership or lifecycle validation failed",
            backoff_seconds=backoff_seconds,
        )
        logger.error(
            "browser checkpoint state rejected",
            extra={"context": {**context, "checkpoint_run_id": str(checkpoint_run_id)}},
        )
        return

    try:
        evidence = await runner.run(target)
    except Exception as error:
        runtime_error_class = type(error).__name__[:100]
        error_source = _safe_error_source(error)
        # EP-026 M4: the browser attempt happened — record its measured cost
        # even on failure (idempotent per run; retries fold into one entry).
        if cost_recorder is not None:
            await cost_recorder.record(
                tenant_id=lease.tenant_id,
                checkpoint_run_id=checkpoint_run_id,
                status="RUNTIME_ERROR",
                attempt_count=lease.attempt,
            )
        retryable = lease.attempt < lease.max_attempts
        if retryable:
            await repository.record_retryable_failure(
                tenant_id=lease.tenant_id,
                checkpoint_run_id=checkpoint_run_id,
                attempt_number=lease.attempt,
                failure_class=runtime_error_class,
                failure_message="Browser runtime failed unexpectedly",
            )
        else:
            await repository.finalize_terminal_failure(
                tenant_id=lease.tenant_id,
                checkpoint_run_id=checkpoint_run_id,
                attempt_number=lease.attempt,
                failure_class=runtime_error_class,
                failure_message="Browser runtime failed unexpectedly",
            )
        await queue.fail_or_retry(
            job_id=lease.id,
            lock_token=lease.lock_token,
            retryable=retryable,
            error_class=runtime_error_class,
            error_message="Browser runtime failed unexpectedly",
            backoff_seconds=backoff_seconds,
        )
        logger.error(
            "browser runtime failed",
            extra={
                "context": {
                    **context,
                    "checkpoint_run_id": str(checkpoint_run_id),
                    "error_class": runtime_error_class,
                    **error_source,
                }
            },
        )
        return
    # EP-026 M4: measured cost telemetry — one run unit over the bounded
    # one-page set, recorded on every terminal execution outcome.
    if cost_recorder is not None:
        await cost_recorder.record(
            tenant_id=lease.tenant_id,
            checkpoint_run_id=checkpoint_run_id,
            status=evidence.status,
            attempt_count=lease.attempt,
        )
    if evidence.status == "BROWSER_ERROR" and lease.attempt < lease.max_attempts:
        await repository.record_retryable_failure(
            tenant_id=lease.tenant_id,
            checkpoint_run_id=checkpoint_run_id,
            attempt_number=lease.attempt,
            failure_class=evidence.failure_class or "BROWSER_ERROR",
            failure_message=evidence.failure_message or "Technical browser failure",
        )
        await queue.fail_or_retry(
            job_id=lease.id,
            lock_token=lease.lock_token,
            retryable=True,
            error_class=evidence.failure_class or "BROWSER_ERROR",
            error_message="Technical browser checkpoint failure",
            backoff_seconds=backoff_seconds,
        )
        logger.warning(
            "browser checkpoint scheduled for retry",
            extra={
                "context": {
                    **context,
                    "checkpoint_run_id": str(checkpoint_run_id),
                    "status": evidence.status,
                }
            },
        )
        return

    try:
        await persister.persist(target=target, attempt_number=lease.attempt, evidence=evidence)
    except Exception:
        retryable = lease.attempt < lease.max_attempts
        if retryable:
            await repository.record_retryable_failure(
                tenant_id=lease.tenant_id,
                checkpoint_run_id=checkpoint_run_id,
                attempt_number=lease.attempt,
                failure_class="STORAGE_ERROR",
                failure_message="Evidence persistence failed",
            )
        else:
            await repository.finalize_terminal_failure(
                tenant_id=lease.tenant_id,
                checkpoint_run_id=checkpoint_run_id,
                attempt_number=lease.attempt,
                failure_class="STORAGE_ERROR",
                failure_message="Evidence persistence failed",
            )
        await queue.fail_or_retry(
            job_id=lease.id,
            lock_token=lease.lock_token,
            retryable=retryable,
            error_class="STORAGE_ERROR",
            error_message="Evidence persistence failed",
            backoff_seconds=backoff_seconds,
        )
        logger.error(
            "browser evidence persistence failed",
            extra={"context": {**context, "checkpoint_run_id": str(checkpoint_run_id)}},
        )
        return

    completed = await queue.complete(job_id=lease.id, lock_token=lease.lock_token)
    logger.info(
        "browser checkpoint completed",
        extra={
            "context": {
                **context,
                "checkpoint_run_id": str(checkpoint_run_id),
                "status": evidence.status,
                "fenced_update": completed,
            }
        },
    )


async def _fail_invalid(
    queue: JobQueue, lease: JobLease, backoff_seconds: int, message: str
) -> None:
    await queue.fail_or_retry(
        job_id=lease.id,
        lock_token=lease.lock_token,
        retryable=False,
        error_class="INVALID_BROWSER_JOB",
        error_message=message,
        backoff_seconds=backoff_seconds,
    )
    logger.error("invalid browser job rejected", extra={"context": {"job_id": str(lease.id)}})


async def _heartbeat(
    queue: JobQueue, lease: JobLease, settings: Settings, stop: asyncio.Event
) -> None:
    interval = max(1.0, min(5.0, settings.job_lease_seconds / 3))
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            active = await queue.heartbeat(
                job_id=lease.id,
                lock_token=lease.lock_token,
                lease_seconds=settings.job_lease_seconds,
            )
            if not active:
                logger.error("browser job lease lost", extra={"context": {"job_id": str(lease.id)}})
                return


async def run(*, once: bool) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    factory = get_session_factory()
    queue = JobQueue(factory)
    repository = CheckpointRepository(factory)
    persister = EvidencePersister(repository, S3Storage(settings))
    runner = BrowserRunner(settings)
    cost_recorder = CheckpointCostRecorder(factory)
    worker_id = f"{socket.gethostname()}:{id(asyncio.current_task())}"
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, stop.set)
        except NotImplementedError:
            pass

    logger.info(
        "browser worker started",
        extra={"context": {"process": "browser-worker", "worker_id": worker_id}},
    )
    while not stop.is_set():
        reclaimed = await queue.reclaim_expired(
            backoff_seconds=settings.job_reclaim_backoff_seconds
        )
        if reclaimed:
            logger.warning("expired jobs reclaimed", extra={"context": {"count": reclaimed}})
        lease = await queue.claim(
            worker_id=worker_id,
            lease_seconds=settings.job_lease_seconds,
            job_type="BROWSER_CHECKPOINT",
        )
        if lease is not None:
            heartbeat_stop = asyncio.Event()
            heartbeat = asyncio.create_task(_heartbeat(queue, lease, settings, heartbeat_stop))
            try:
                await handle_browser_job(
                    queue=queue,
                    repository=repository,
                    persister=persister,
                    runner=runner,
                    lease=lease,
                    backoff_seconds=settings.job_reclaim_backoff_seconds,
                    cost_recorder=cost_recorder,
                )
            finally:
                heartbeat_stop.set()
                await heartbeat
        if once:
            return
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.job_poll_interval_seconds)
        except TimeoutError:
            continue


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the isolated browser checkpoint worker")
    parser.add_argument("--once", action="store_true", help="process at most one polling cycle")
    parser.add_argument("--check", action="store_true", help="validate the process entry point")
    args = parser.parse_args()
    if args.check:
        print(json.dumps({"process": "browser-worker", "status": "ready"}, sort_keys=True))
        return
    asyncio.run(run(once=args.once))


if __name__ == "__main__":
    main()
