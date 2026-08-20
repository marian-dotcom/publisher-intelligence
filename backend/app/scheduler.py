import argparse
import asyncio
import logging
import signal

from app.browser.scheduling import CheckpointSchedulingService
from app.common.logging import configure_logging
from app.config.settings import get_settings
from app.connectors.core.persistence import ConnectorRepository
from app.connectors.ga4.scheduling import GA4SchedulingService
from app.connectors.gam.scheduling import GAMSchedulingService
from app.connectors.gsc.scheduling import GSCSchedulingService
from app.db.session import get_session_factory
from app.jobs.queue import JobQueue

logger = logging.getLogger(__name__)


async def run_once() -> None:
    settings = get_settings()
    factory = get_session_factory()
    queue = JobQueue(factory)
    result = await CheckpointSchedulingService(factory, queue, settings).schedule_due()
    logger.info(
        "browser checkpoint scheduling pass completed",
        extra={
            "context": {
                "site_count": result.site_count,
                "run_count": result.run_count,
                "job_count": result.job_count,
            }
        },
    )
    ga4_result = await GA4SchedulingService(ConnectorRepository(factory), queue).schedule_due()
    logger.info(
        "GA4 scheduling pass completed",
        extra={
            "context": {
                "connection_count": ga4_result.connection_count,
                "job_count": ga4_result.job_count,
            }
        },
    )
    gsc_result = await GSCSchedulingService(ConnectorRepository(factory), queue).schedule_due()
    logger.info(
        "GSC scheduling pass completed",
        extra={
            "context": {
                "connection_count": gsc_result.connection_count,
                "job_count": gsc_result.job_count,
            }
        },
    )
    gam_result = await GAMSchedulingService(ConnectorRepository(factory), queue).schedule_due()
    logger.info(
        "GAM scheduling pass completed",
        extra={
            "context": {
                "connection_count": gam_result.connection_count,
                "job_count": gam_result.job_count,
            }
        },
    )


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
