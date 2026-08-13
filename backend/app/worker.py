import argparse
import asyncio
import logging
import signal
import socket

from app.common.logging import configure_logging
from app.config.settings import get_settings
from app.db.session import get_session_factory
from app.jobs.queue import JobLease, JobQueue

logger = logging.getLogger(__name__)


async def handle_job(queue: JobQueue, lease: JobLease, backoff_seconds: int) -> None:
    context = {
        "job_id": str(lease.id),
        "tenant_id": str(lease.tenant_id) if lease.tenant_id else None,
        "job_type": lease.job_type,
        "attempt": lease.attempt,
    }
    if lease.job_type == "BOOTSTRAP_NOOP":
        completed = await queue.complete(job_id=lease.id, lock_token=lease.lock_token)
        logger.info("job completed", extra={"context": {**context, "fenced_update": completed}})
        return
    failed = await queue.fail_or_retry(
        job_id=lease.id,
        lock_token=lease.lock_token,
        retryable=False,
        error_class="UNKNOWN_JOB_TYPE",
        error_message="No registered handler for job type",
        backoff_seconds=backoff_seconds,
    )
    logger.error("job failed", extra={"context": {**context, "fenced_update": failed}})


async def run(*, once: bool) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    queue = JobQueue(get_session_factory())
    worker_id = f"{socket.gethostname()}:{id(asyncio.current_task())}"
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, stop.set)
        except NotImplementedError:
            pass

    logger.info("worker started", extra={"context": {"process": "worker", "worker_id": worker_id}})
    while not stop.is_set():
        reclaimed = await queue.reclaim_expired(
            backoff_seconds=settings.job_reclaim_backoff_seconds
        )
        if reclaimed:
            logger.warning("expired jobs reclaimed", extra={"context": {"count": reclaimed}})
        lease = await queue.claim(
            worker_id=worker_id,
            lease_seconds=settings.job_lease_seconds,
            excluded_job_type="BROWSER_CHECKPOINT",
        )
        if lease is not None:
            await handle_job(queue, lease, settings.job_reclaim_backoff_seconds)
        if once:
            return
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.job_poll_interval_seconds)
        except TimeoutError:
            continue
    logger.info("worker stopped", extra={"context": {"process": "worker", "worker_id": worker_id}})


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the general background worker")
    parser.add_argument("--once", action="store_true", help="process at most one polling cycle")
    args = parser.parse_args()
    asyncio.run(run(once=args.once))


if __name__ == "__main__":
    main()
