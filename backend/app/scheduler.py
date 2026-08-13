import argparse
import asyncio
import logging
import signal

from app.common.logging import configure_logging
from app.config.settings import get_settings
from app.db.session import get_session_factory
from app.jobs.queue import JobQueue

logger = logging.getLogger(__name__)


async def run_once() -> None:
    queue = JobQueue(get_session_factory())
    job_id = await queue.enqueue(
        job_type="BOOTSTRAP_NOOP",
        payload={"purpose": "EP-001 scheduler integration smoke"},
        idempotency_key="global:bootstrap-noop:v1",
    )
    logger.info("bootstrap job scheduled", extra={"context": {"job_id": str(job_id)}})


async def run(*, once: bool) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    if once:
        await run_once()
        return
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, stop.set)
        except NotImplementedError:
            pass

    logger.info("scheduler started", extra={"context": {"process": "scheduler"}})
    while not stop.is_set():
        await run_once()
        try:
            await asyncio.wait_for(stop.wait(), timeout=60)
        except TimeoutError:
            continue
    logger.info("scheduler stopped", extra={"context": {"process": "scheduler"}})


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the lightweight scheduler")
    parser.add_argument("--once", action="store_true", help="insert one bootstrap job and exit")
    args = parser.parse_args()
    asyncio.run(run(once=args.once))


if __name__ == "__main__":
    main()
