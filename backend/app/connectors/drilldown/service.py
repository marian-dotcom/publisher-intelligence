import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.connectors.core.contracts import ConnectorError
from app.connectors.drilldown.catalog import (
    DRILLDOWN_CATALOG_VERSION,
    MAX_DRILLDOWNS_PER_CONNECTION_DAY,
    MAX_DRILLDOWNS_PER_INVESTIGATION,
    get_drilldown_definition,
    validate_drilldown_scope,
)
from app.connectors.models import DataConnection
from app.db.models import Job


@dataclass(frozen=True, slots=True)
class DrilldownJobRequest:
    tenant_id: uuid.UUID
    site_id: uuid.UUID
    connection_id: uuid.UUID
    investigation_id: uuid.UUID
    definition_code: str
    start_date: date | None = None
    end_date: date | None = None
    profile: str | None = None
    parameters: dict[str, str] | None = None
    catalog_version: str = DRILLDOWN_CATALOG_VERSION


@dataclass(frozen=True, slots=True)
class DrilldownPlan:
    job_id: uuid.UUID
    created: bool
    request_key: str


class DrilldownPlanningService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def request(
        self, request: DrilldownJobRequest, *, now: datetime | None = None
    ) -> DrilldownPlan:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        parameters = dict(request.parameters or {})
        definition = get_drilldown_definition(
            request.definition_code, catalog_version=request.catalog_version
        )
        validate_drilldown_scope(
            definition,
            start_date=request.start_date,
            end_date=request.end_date,
            profile=request.profile,
            parameters=parameters,
            today=current.date(),
        )
        request_key = _request_key(request, parameters)
        idempotency_key = f"connector-drilldown:{request_key}"
        payload: dict[str, Any] = {
            "catalog_version": request.catalog_version,
            "connection_id": str(request.connection_id),
            "definition_code": request.definition_code,
            "end_date": request.end_date.isoformat() if request.end_date else None,
            "investigation_id": str(request.investigation_id),
            "parameters": parameters,
            "profile": request.profile,
            "request_key": request_key,
            "site_id": str(request.site_id),
            "start_date": request.start_date.isoformat() if request.start_date else None,
        }

        async with self._session_factory() as session, session.begin():
            connection = await session.scalar(
                select(DataConnection)
                .where(
                    DataConnection.id == request.connection_id,
                    DataConnection.tenant_id == request.tenant_id,
                    DataConnection.site_id == request.site_id,
                    DataConnection.archived_at.is_(None),
                )
                .with_for_update()
            )
            if connection is None or connection.provider != definition.provider:
                raise ConnectorError(
                    "DRILLDOWN_SCOPE_INVALID",
                    retryable=False,
                    message="Incident drill-down connection ownership or provider is invalid",
                )
            if connection.status not in {"CONNECTED", "DEGRADED"}:
                raise ConnectorError(
                    "CONNECTION_UNAVAILABLE",
                    retryable=False,
                    message="Incident drill-down connection is unavailable",
                )
            _validate_connection_capability(connection, definition.code, request.profile)

            existing = await session.scalar(
                select(Job.id).where(
                    Job.tenant_id == request.tenant_id,
                    Job.idempotency_key == idempotency_key,
                )
            )
            if existing is not None:
                return DrilldownPlan(existing, False, request_key)

            investigation_count = await session.scalar(
                select(func.count(Job.id)).where(
                    Job.tenant_id == request.tenant_id,
                    Job.job_type == "CONNECTOR_DRILLDOWN",
                    Job.payload["connection_id"].astext == str(request.connection_id),
                    Job.payload["investigation_id"].astext == str(request.investigation_id),
                )
            )
            day_start = datetime.combine(current.date(), time.min, tzinfo=UTC)
            daily_count = await session.scalar(
                select(func.count(Job.id)).where(
                    Job.tenant_id == request.tenant_id,
                    Job.job_type == "CONNECTOR_DRILLDOWN",
                    Job.payload["connection_id"].astext == str(request.connection_id),
                    Job.created_at >= day_start,
                )
            )
            if int(investigation_count or 0) >= MAX_DRILLDOWNS_PER_INVESTIGATION:
                raise ConnectorError(
                    "DRILLDOWN_INVESTIGATION_BUDGET_EXCEEDED",
                    retryable=False,
                    message="Incident drill-down investigation budget is exhausted",
                )
            if int(daily_count or 0) >= MAX_DRILLDOWNS_PER_CONNECTION_DAY:
                raise ConnectorError(
                    "DRILLDOWN_DAILY_BUDGET_EXCEEDED",
                    retryable=False,
                    message="Incident drill-down connection daily budget is exhausted",
                )

            job_id = uuid.uuid4()
            session.add(
                Job(
                    id=job_id,
                    tenant_id=request.tenant_id,
                    job_type="CONNECTOR_DRILLDOWN",
                    payload=payload,
                    status="PENDING",
                    priority=20,
                    scheduled_at=current,
                    available_at=current,
                    attempt=0,
                    max_attempts=3,
                    idempotency_key=idempotency_key,
                )
            )
            return DrilldownPlan(job_id, True, request_key)


def _validate_connection_capability(
    connection: DataConnection, definition_code: str, profile: str | None
) -> None:
    metadata = connection.connection_metadata
    if metadata.get("drilldownCatalogVersion") != DRILLDOWN_CATALOG_VERSION:
        raise ConnectorError(
            "DRILLDOWN_NOT_VALIDATED",
            retryable=False,
            message="Incident drill-down catalog was not validated for this connection",
        )
    validated = metadata.get("validatedDrilldowns")
    if not isinstance(validated, list) or definition_code not in validated:
        raise ConnectorError(
            "DRILLDOWN_NOT_VALIDATED",
            retryable=False,
            message="Incident drill-down was not validated for this connection",
        )
    if connection.provider == "GAM":
        bindings = metadata.get("validatedDrilldownBindings")
        key = f"{definition_code}:{profile}"
        if not isinstance(bindings, list) or key not in bindings:
            raise ConnectorError(
                "DRILLDOWN_NOT_VALIDATED",
                retryable=False,
                message="GAM drill-down profile was not validated for this connection",
            )


def _request_key(request: DrilldownJobRequest, parameters: dict[str, str]) -> str:
    canonical = json.dumps(
        {
            "catalogVersion": request.catalog_version,
            "connectionId": str(request.connection_id),
            "definitionCode": request.definition_code,
            "endDate": request.end_date.isoformat() if request.end_date else None,
            "investigationId": str(request.investigation_id),
            "parameters": parameters,
            "profile": request.profile,
            "siteId": str(request.site_id),
            "startDate": request.start_date.isoformat() if request.start_date else None,
            "tenantId": str(request.tenant_id),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode()
    return hashlib.sha256(canonical).hexdigest()
