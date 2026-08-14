import argparse
import asyncio
import logging
import signal
import socket
import uuid
from datetime import date

from app.common.logging import configure_logging
from app.config.settings import get_settings
from app.connectors.core.contracts import ConnectorError, ExtractPeriod, FreshnessStatus
from app.connectors.core.persistence import ConnectorRepository, ConnectorStateError
from app.connectors.core.secrets import EnvironmentAccessTokenResolver
from app.connectors.ga4.client import GA4Client, HttpxGA4Transport
from app.connectors.ga4.service import GA4ConnectorService
from app.connectors.gsc.client import GSCClient, HttpxGSCTransport
from app.connectors.gsc.service import GSCConnectorService
from app.db.session import get_session_factory
from app.jobs.queue import JobLease, JobQueue

logger = logging.getLogger(__name__)


async def handle_job(
    queue: JobQueue,
    lease: JobLease,
    backoff_seconds: int,
    ga4_service: GA4ConnectorService | None = None,
    gsc_service: GSCConnectorService | None = None,
) -> None:
    context: dict[str, object] = {
        "job_id": str(lease.id),
        "tenant_id": str(lease.tenant_id) if lease.tenant_id else None,
        "job_type": lease.job_type,
        "attempt": lease.attempt,
    }
    if lease.job_type == "BOOTSTRAP_NOOP":
        completed = await queue.complete(job_id=lease.id, lock_token=lease.lock_token)
        logger.info("job completed", extra={"context": {**context, "fenced_update": completed}})
        return
    if lease.job_type == "GA4_EXTRACT" and ga4_service is not None:
        await _handle_ga4_job(queue, lease, backoff_seconds, ga4_service, context)
        return
    if lease.job_type == "GSC_EXTRACT" and gsc_service is not None:
        await _handle_gsc_job(queue, lease, backoff_seconds, gsc_service, context)
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


async def _handle_ga4_job(
    queue: JobQueue,
    lease: JobLease,
    backoff_seconds: int,
    service: GA4ConnectorService,
    context: dict[str, object],
) -> None:
    required = {
        "connection_id",
        "definition_code",
        "start_date",
        "end_date",
        "freshness_status",
        "scheduled_run_key",
    }
    if lease.tenant_id is None or set(lease.payload) != required:
        await _fail_ga4_job(
            queue,
            lease,
            backoff_seconds,
            retryable=False,
            error_class="INVALID_GA4_JOB",
            error_code="INVALID_JOB_PAYLOAD",
            context=context,
        )
        return
    try:
        connection_id = uuid.UUID(str(lease.payload["connection_id"]))
        definition_code = _payload_string(lease.payload["definition_code"])
        start_date = date.fromisoformat(_payload_string(lease.payload["start_date"]))
        end_date = date.fromisoformat(_payload_string(lease.payload["end_date"]))
        freshness_raw = _payload_string(lease.payload["freshness_status"])
        if freshness_raw not in {"PRELIMINARY", "MATURE", "STALE", "UNKNOWN"}:
            raise ValueError("invalid freshness")
        freshness: FreshnessStatus = freshness_raw  # type: ignore[assignment]
        scheduled_run_key = _payload_string(lease.payload["scheduled_run_key"])
        period = ExtractPeriod(start_date=start_date, end_date=end_date)
    except (TypeError, ValueError, AttributeError):
        await _fail_ga4_job(
            queue,
            lease,
            backoff_seconds,
            retryable=False,
            error_class="INVALID_GA4_JOB",
            error_code="INVALID_JOB_PAYLOAD",
            context=context,
        )
        return

    try:
        normalized = await service.run_extract(
            tenant_id=lease.tenant_id,
            connection_id=connection_id,
            definition_code=definition_code,
            period=period,
            freshness_status=freshness,
            scheduled_run_key=scheduled_run_key,
        )
    except ConnectorError as error:
        await _fail_ga4_job(
            queue,
            lease,
            backoff_seconds,
            retryable=error.retryable,
            error_class=type(error).__name__,
            error_code=error.code,
            context=context,
        )
        return
    except ConnectorStateError:
        await _fail_ga4_job(
            queue,
            lease,
            backoff_seconds,
            retryable=False,
            error_class="CONNECTOR_STATE_ERROR",
            error_code="TENANT_OR_STATE_INVALID",
            context=context,
        )
        return
    except Exception:
        await _fail_ga4_job(
            queue,
            lease,
            backoff_seconds,
            retryable=True,
            error_class="CONNECTOR_RUNTIME_ERROR",
            error_code="CONNECTOR_RUNTIME_ERROR",
            context=context,
        )
        return

    completed = await queue.complete(job_id=lease.id, lock_token=lease.lock_token)
    logger.info(
        "GA4 extract job completed",
        extra={
            "context": {
                **context,
                "connection_id": str(connection_id),
                "definition": definition_code,
                "point_count": len(normalized.points) if normalized is not None else 0,
                "idempotent_reuse": normalized is None,
                "fenced_update": completed,
            }
        },
    )


async def _fail_ga4_job(
    queue: JobQueue,
    lease: JobLease,
    backoff_seconds: int,
    *,
    retryable: bool,
    error_class: str,
    error_code: str,
    context: dict[str, object],
) -> None:
    bounded_backoff = min(3600, max(1, backoff_seconds) * (2 ** max(0, lease.attempt - 1)))
    failed = await queue.fail_or_retry(
        job_id=lease.id,
        lock_token=lease.lock_token,
        retryable=retryable,
        error_class=error_class,
        error_message=error_code,
        backoff_seconds=bounded_backoff,
    )
    logger.error(
        "GA4 extract job failed",
        extra={
            "context": {
                **context,
                "error_class": error_class,
                "error_code": error_code,
                "retryable": retryable,
                "fenced_update": failed,
            }
        },
    )


async def _handle_gsc_job(
    queue: JobQueue,
    lease: JobLease,
    backoff_seconds: int,
    service: GSCConnectorService,
    context: dict[str, object],
) -> None:
    required = {
        "connection_id",
        "definition_code",
        "start_date",
        "end_date",
        "freshness_status",
        "scheduled_run_key",
    }
    if lease.tenant_id is None or set(lease.payload) != required:
        await _fail_gsc_job(
            queue,
            lease,
            backoff_seconds,
            retryable=False,
            error_class="INVALID_GSC_JOB",
            error_code="INVALID_JOB_PAYLOAD",
            context=context,
        )
        return
    try:
        connection_id = uuid.UUID(str(lease.payload["connection_id"]))
        definition_code = _payload_string(lease.payload["definition_code"])
        start_date = date.fromisoformat(_payload_string(lease.payload["start_date"]))
        end_date = date.fromisoformat(_payload_string(lease.payload["end_date"]))
        freshness_raw = _payload_string(lease.payload["freshness_status"])
        if freshness_raw not in {"PRELIMINARY", "MATURE", "STALE", "UNKNOWN"}:
            raise ValueError("invalid freshness")
        freshness: FreshnessStatus = freshness_raw  # type: ignore[assignment]
        scheduled_run_key = _payload_string(lease.payload["scheduled_run_key"])
        period = ExtractPeriod(start_date=start_date, end_date=end_date)
    except (TypeError, ValueError, AttributeError):
        await _fail_gsc_job(
            queue,
            lease,
            backoff_seconds,
            retryable=False,
            error_class="INVALID_GSC_JOB",
            error_code="INVALID_JOB_PAYLOAD",
            context=context,
        )
        return

    try:
        normalized = await service.run_extract(
            tenant_id=lease.tenant_id,
            connection_id=connection_id,
            definition_code=definition_code,
            period=period,
            freshness_status=freshness,
            scheduled_run_key=scheduled_run_key,
        )
    except ConnectorError as error:
        await _fail_gsc_job(
            queue,
            lease,
            backoff_seconds,
            retryable=error.retryable,
            error_class=type(error).__name__,
            error_code=error.code,
            context=context,
        )
        return
    except ConnectorStateError:
        await _fail_gsc_job(
            queue,
            lease,
            backoff_seconds,
            retryable=False,
            error_class="CONNECTOR_STATE_ERROR",
            error_code="TENANT_OR_STATE_INVALID",
            context=context,
        )
        return
    except Exception:
        await _fail_gsc_job(
            queue,
            lease,
            backoff_seconds,
            retryable=True,
            error_class="CONNECTOR_RUNTIME_ERROR",
            error_code="CONNECTOR_RUNTIME_ERROR",
            context=context,
        )
        return

    completed = await queue.complete(job_id=lease.id, lock_token=lease.lock_token)
    logger.info(
        "GSC extract job completed",
        extra={
            "context": {
                **context,
                "connection_id": str(connection_id),
                "definition": definition_code,
                "point_count": len(normalized.points) if normalized is not None else 0,
                "idempotent_reuse": normalized is None,
                "fenced_update": completed,
            }
        },
    )


async def _fail_gsc_job(
    queue: JobQueue,
    lease: JobLease,
    backoff_seconds: int,
    *,
    retryable: bool,
    error_class: str,
    error_code: str,
    context: dict[str, object],
) -> None:
    bounded_backoff = min(3600, max(1, backoff_seconds) * (2 ** max(0, lease.attempt - 1)))
    failed = await queue.fail_or_retry(
        job_id=lease.id,
        lock_token=lease.lock_token,
        retryable=retryable,
        error_class=error_class,
        error_message=error_code,
        backoff_seconds=bounded_backoff,
    )
    logger.error(
        "GSC extract job failed",
        extra={
            "context": {
                **context,
                "error_class": error_class,
                "error_code": error_code,
                "retryable": retryable,
                "fenced_update": failed,
            }
        },
    )


def _payload_string(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 255:
        raise ValueError("invalid job string")
    return value


async def run(*, once: bool) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    factory = get_session_factory()
    queue = JobQueue(factory)
    ga4_service = GA4ConnectorService(
        ConnectorRepository(factory),
        GA4Client(HttpxGA4Transport()),
        EnvironmentAccessTokenResolver(environment=settings.environment),
    )
    gsc_service = GSCConnectorService(
        ConnectorRepository(factory),
        GSCClient(HttpxGSCTransport()),
        EnvironmentAccessTokenResolver(environment=settings.environment),
    )
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
            await handle_job(
                queue,
                lease,
                settings.job_reclaim_backoff_seconds,
                ga4_service,
                gsc_service,
            )
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
