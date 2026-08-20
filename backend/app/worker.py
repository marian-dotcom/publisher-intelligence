import argparse
import asyncio
import logging
import signal
import socket
import uuid
from datetime import UTC, date, datetime

from app.common.logging import configure_logging
from app.config.settings import get_settings
from app.connectors.core.contracts import ConnectorError, ExtractPeriod, FreshnessStatus
from app.connectors.core.persistence import ConnectorRepository, ConnectorStateError
from app.connectors.core.secrets import EnvironmentAccessTokenResolver
from app.connectors.drilldown.catalog import (
    DRILLDOWN_CATALOG_VERSION,
    get_drilldown_definition,
    validate_drilldown_scope,
)
from app.connectors.ga4.client import GA4Client, HttpxGA4Transport
from app.connectors.ga4.service import GA4ConnectorService
from app.connectors.gam.client import GAMClient, HttpxGAMTransport
from app.connectors.gam.service import GAMConnectorService
from app.connectors.gsc.client import GSCClient, HttpxGSCTransport
from app.connectors.gsc.service import GSCConnectorService
from app.db.session import get_session_factory
from app.events.persistence import EventRepository, EventStateError
from app.events.service import EventService
from app.jobs.queue import JobLease, JobQueue
from app.metrics.contracts import CROSS_SOURCE_RULE_VERSION
from app.metrics.persistence import MetricDerivationRepository, MetricDerivationStateError
from app.metrics.service import CrossSourceMetricService

logger = logging.getLogger(__name__)


async def handle_job(
    queue: JobQueue,
    lease: JobLease,
    backoff_seconds: int,
    ga4_service: GA4ConnectorService | None = None,
    gsc_service: GSCConnectorService | None = None,
    gam_service: GAMConnectorService | None = None,
    metric_service: CrossSourceMetricService | None = None,
    event_service: EventService | None = None,
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
    if lease.job_type == "GAM_EXTRACT" and gam_service is not None:
        await _handle_gam_job(queue, lease, backoff_seconds, gam_service, context)
        return
    if (
        lease.job_type == "CONNECTOR_DRILLDOWN"
        and ga4_service is not None
        and gsc_service is not None
        and gam_service is not None
    ):
        await _handle_drilldown_job(
            queue,
            lease,
            backoff_seconds,
            ga4_service,
            gsc_service,
            gam_service,
            context,
        )
        return
    if lease.job_type == "DERIVE_CROSS_SOURCE" and metric_service is not None:
        await _handle_cross_source_job(queue, lease, backoff_seconds, metric_service, context)
        return
    if lease.job_type == "DERIVE_BROWSER_EVENTS" and event_service is not None:
        await _handle_browser_events_job(queue, lease, backoff_seconds, event_service, context)
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


async def _handle_browser_events_job(
    queue: JobQueue,
    lease: JobLease,
    backoff_seconds: int,
    service: EventService,
    context: dict[str, object],
) -> None:
    if lease.tenant_id is None or set(lease.payload) != {"checkpoint_run_id"}:
        failed = await queue.fail_or_retry(
            job_id=lease.id,
            lock_token=lease.lock_token,
            retryable=False,
            error_class="INVALID_BROWSER_EVENT_JOB",
            error_message="INVALID_JOB_PAYLOAD",
            backoff_seconds=backoff_seconds,
        )
        logger.error(
            "browser event job failed", extra={"context": {**context, "fenced_update": failed}}
        )
        return
    try:
        checkpoint_run_id = uuid.UUID(str(lease.payload["checkpoint_run_id"]))
        result = await service.derive(
            tenant_id=lease.tenant_id, checkpoint_run_id=checkpoint_run_id
        )
    except (ValueError, EventStateError):
        failed = await queue.fail_or_retry(
            job_id=lease.id,
            lock_token=lease.lock_token,
            retryable=False,
            error_class="BROWSER_EVENT_STATE_ERROR",
            error_message="TENANT_OR_STATE_INVALID",
            backoff_seconds=backoff_seconds,
        )
        logger.error(
            "browser event job failed", extra={"context": {**context, "fenced_update": failed}}
        )
        return
    except Exception:
        failed = await queue.fail_or_retry(
            job_id=lease.id,
            lock_token=lease.lock_token,
            retryable=True,
            error_class="BROWSER_EVENT_RUNTIME_ERROR",
            error_message="BROWSER_EVENT_RUNTIME_ERROR",
            backoff_seconds=backoff_seconds,
        )
        logger.exception(
            "browser event job failed", extra={"context": {**context, "fenced_update": failed}}
        )
        return
    completed = await queue.complete(job_id=lease.id, lock_token=lease.lock_token)
    logger.info(
        "browser event job completed",
        extra={
            "context": {
                **context,
                "checkpoint_run_id": str(checkpoint_run_id),
                "candidate_count": result.candidate_count,
                "persisted_count": result.persisted_count,
                "updated_count": result.updated_count,
                "resolved_count": result.resolved_count,
                "unsupported_count": result.unsupported_count,
                "skip_reasons": list(result.skip_reasons),
                "fenced_update": completed,
            }
        },
    )


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


async def _handle_gam_job(
    queue: JobQueue,
    lease: JobLease,
    backoff_seconds: int,
    service: GAMConnectorService,
    context: dict[str, object],
) -> None:
    required = {
        "connection_id",
        "definition_code",
        "profile",
        "freshness_status",
        "scheduled_run_key",
    }
    if lease.tenant_id is None or set(lease.payload) != required:
        await _fail_gam_job(
            queue,
            lease,
            backoff_seconds,
            retryable=False,
            error_class="INVALID_GAM_JOB",
            error_code="INVALID_JOB_PAYLOAD",
            context=context,
        )
        return
    try:
        connection_id = uuid.UUID(str(lease.payload["connection_id"]))
        definition_code = _payload_string(lease.payload["definition_code"])
        profile = _payload_string(lease.payload["profile"])
        freshness_raw = _payload_string(lease.payload["freshness_status"])
        if freshness_raw not in {"PRELIMINARY", "MATURE", "STALE", "UNKNOWN"}:
            raise ValueError("invalid freshness")
        freshness: FreshnessStatus = freshness_raw  # type: ignore[assignment]
        scheduled_run_key = _payload_string(lease.payload["scheduled_run_key"])
    except (TypeError, ValueError, AttributeError):
        await _fail_gam_job(
            queue,
            lease,
            backoff_seconds,
            retryable=False,
            error_class="INVALID_GAM_JOB",
            error_code="INVALID_JOB_PAYLOAD",
            context=context,
        )
        return
    try:
        normalized = await service.run_extract(
            tenant_id=lease.tenant_id,
            connection_id=connection_id,
            definition_code=definition_code,
            profile=profile,
            freshness_status=freshness,
            scheduled_run_key=scheduled_run_key,
        )
    except ConnectorError as error:
        await _fail_gam_job(
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
        await _fail_gam_job(
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
        await _fail_gam_job(
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
        "GAM extract job completed",
        extra={
            "context": {
                **context,
                "connection_id": str(connection_id),
                "definition": definition_code,
                "profile": profile,
                "point_count": len(normalized.points) if normalized is not None else 0,
                "idempotent_reuse": normalized is None,
                "fenced_update": completed,
            }
        },
    )


async def _fail_gam_job(
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
        "GAM extract job failed",
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


async def _handle_drilldown_job(
    queue: JobQueue,
    lease: JobLease,
    backoff_seconds: int,
    ga4_service: GA4ConnectorService,
    gsc_service: GSCConnectorService,
    gam_service: GAMConnectorService,
    context: dict[str, object],
) -> None:
    required = {
        "catalog_version",
        "connection_id",
        "definition_code",
        "end_date",
        "investigation_id",
        "parameters",
        "profile",
        "request_key",
        "site_id",
        "start_date",
    }
    if lease.tenant_id is None or set(lease.payload) != required:
        await _fail_drilldown_job(
            queue,
            lease,
            backoff_seconds,
            retryable=False,
            error_class="INVALID_DRILLDOWN_JOB",
            error_code="INVALID_JOB_PAYLOAD",
            context=context,
        )
        return
    try:
        catalog_version = _payload_string(lease.payload["catalog_version"])
        if catalog_version != DRILLDOWN_CATALOG_VERSION:
            raise ValueError("unsupported catalog version")
        connection_id = uuid.UUID(_payload_string(lease.payload["connection_id"]))
        site_id = uuid.UUID(_payload_string(lease.payload["site_id"]))
        investigation_id = uuid.UUID(_payload_string(lease.payload["investigation_id"]))
        definition_code = _payload_string(lease.payload["definition_code"])
        request_key = _payload_string(lease.payload["request_key"])
        start_date = _optional_payload_date(lease.payload["start_date"])
        end_date = _optional_payload_date(lease.payload["end_date"])
        profile = _optional_payload_string(lease.payload["profile"], 30)
        parameters = _payload_parameters(lease.payload["parameters"])
        definition = get_drilldown_definition(definition_code, catalog_version=catalog_version)
        validate_drilldown_scope(
            definition,
            start_date=start_date,
            end_date=end_date,
            profile=profile,
            parameters=parameters,
            today=datetime.now(UTC).date(),
        )
    except (ConnectorError, TypeError, ValueError, AttributeError):
        await _fail_drilldown_job(
            queue,
            lease,
            backoff_seconds,
            retryable=False,
            error_class="INVALID_DRILLDOWN_JOB",
            error_code="INVALID_JOB_PAYLOAD",
            context=context,
        )
        return

    run_key = f"tier-c:{request_key}"
    try:
        if definition.provider == "GA4":
            if start_date is None or end_date is None:
                raise ConnectorError(
                    "DRILLDOWN_WINDOW_INVALID",
                    retryable=False,
                    message="GA4 drill-down date window is unavailable",
                )
            normalized = await ga4_service.run_drilldown(
                tenant_id=lease.tenant_id,
                site_id=site_id,
                connection_id=connection_id,
                investigation_id=investigation_id,
                definition_code=definition_code,
                period=ExtractPeriod(start_date, end_date),
                scheduled_run_key=run_key,
            )
        elif definition.provider == "GSC":
            if start_date is None or end_date is None:
                raise ConnectorError(
                    "DRILLDOWN_WINDOW_INVALID",
                    retryable=False,
                    message="GSC drill-down date window is unavailable",
                )
            normalized = await gsc_service.run_drilldown(
                tenant_id=lease.tenant_id,
                site_id=site_id,
                connection_id=connection_id,
                investigation_id=investigation_id,
                definition_code=definition_code,
                period=ExtractPeriod(start_date, end_date),
                parameters=parameters,
                scheduled_run_key=run_key,
            )
        else:
            if profile is None:
                raise ConnectorError(
                    "DRILLDOWN_WINDOW_INVALID",
                    retryable=False,
                    message="GAM drill-down profile is unavailable",
                )
            normalized = await gam_service.run_drilldown(
                tenant_id=lease.tenant_id,
                site_id=site_id,
                connection_id=connection_id,
                investigation_id=investigation_id,
                definition_code=definition_code,
                profile=profile,
                scheduled_run_key=run_key,
            )
    except ConnectorError as error:
        await _fail_drilldown_job(
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
        await _fail_drilldown_job(
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
        await _fail_drilldown_job(
            queue,
            lease,
            backoff_seconds,
            retryable=True,
            error_class="DRILLDOWN_RUNTIME_ERROR",
            error_code="DRILLDOWN_RUNTIME_ERROR",
            context=context,
        )
        return
    completed = await queue.complete(job_id=lease.id, lock_token=lease.lock_token)
    logger.info(
        "connector drill-down job completed",
        extra={
            "context": {
                **context,
                "connection_id": str(connection_id),
                "definition": definition_code,
                "provider": definition.provider,
                "point_count": len(normalized.points) if normalized is not None else 0,
                "idempotent_reuse": normalized is None,
                "fenced_update": completed,
            }
        },
    )


async def _fail_drilldown_job(
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
        "connector drill-down job failed",
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


async def _handle_cross_source_job(
    queue: JobQueue,
    lease: JobLease,
    backoff_seconds: int,
    service: CrossSourceMetricService,
    context: dict[str, object],
) -> None:
    required = {"site_id", "window_start", "window_end", "rule_version"}
    if lease.tenant_id is None or set(lease.payload) != required:
        await _fail_cross_source_job(
            queue,
            lease,
            backoff_seconds,
            retryable=False,
            error_class="INVALID_DERIVATION_JOB",
            error_code="INVALID_JOB_PAYLOAD",
            context=context,
        )
        return
    try:
        site_id = uuid.UUID(_payload_string(lease.payload["site_id"]))
        window_start = datetime.fromisoformat(_payload_string(lease.payload["window_start"]))
        window_end = datetime.fromisoformat(_payload_string(lease.payload["window_end"]))
        rule_version = _payload_string(lease.payload["rule_version"])
        if rule_version != CROSS_SOURCE_RULE_VERSION:
            raise ValueError("unsupported rule version")
        if window_start.tzinfo is None or window_end.tzinfo is None:
            raise ValueError("derivation times must have offsets")
    except (TypeError, ValueError, AttributeError):
        await _fail_cross_source_job(
            queue,
            lease,
            backoff_seconds,
            retryable=False,
            error_class="INVALID_DERIVATION_JOB",
            error_code="INVALID_JOB_PAYLOAD",
            context=context,
        )
        return
    try:
        result = await service.derive_site(
            tenant_id=lease.tenant_id,
            site_id=site_id,
            window_start=window_start,
            window_end=window_end,
        )
    except (MetricDerivationStateError, ValueError):
        await _fail_cross_source_job(
            queue,
            lease,
            backoff_seconds,
            retryable=False,
            error_class="DERIVATION_STATE_ERROR",
            error_code="TENANT_OR_STATE_INVALID",
            context=context,
        )
        return
    except Exception:
        await _fail_cross_source_job(
            queue,
            lease,
            backoff_seconds,
            retryable=True,
            error_class="DERIVATION_RUNTIME_ERROR",
            error_code="DERIVATION_RUNTIME_ERROR",
            context=context,
        )
        return
    completed = await queue.complete(job_id=lease.id, lock_token=lease.lock_token)
    logger.info(
        "cross-source derivation job completed",
        extra={
            "context": {
                **context,
                "site_id": str(site_id),
                "candidate_count": result.candidate_count,
                "created_count": result.created_count,
                "skipped_counts": result.skipped_counts,
                "fenced_update": completed,
            }
        },
    )


async def _fail_cross_source_job(
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
        "cross-source derivation job failed",
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


def _optional_payload_string(value: object, max_length: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > max_length:
        raise ValueError("invalid optional job string")
    return value


def _optional_payload_date(value: object) -> date | None:
    raw = _optional_payload_string(value, 10)
    return date.fromisoformat(raw) if raw is not None else None


def _payload_parameters(value: object) -> dict[str, str]:
    if not isinstance(value, dict) or not all(
        isinstance(key, str)
        and isinstance(item, str)
        and key
        and len(key) <= 50
        and item
        and len(item) <= 2048
        for key, item in value.items()
    ):
        raise ValueError("invalid drill-down parameters")
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
    gam_service = GAMConnectorService(
        ConnectorRepository(factory),
        GAMClient(HttpxGAMTransport()),
        EnvironmentAccessTokenResolver(environment=settings.environment),
    )
    metric_service = CrossSourceMetricService(MetricDerivationRepository(factory))
    event_service = EventService(EventRepository(factory))
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
                gam_service,
                metric_service,
                event_service,
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
