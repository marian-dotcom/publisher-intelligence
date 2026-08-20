import hashlib
import json
import uuid
from datetime import UTC, datetime, time, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.browser.models import Site
from app.connectors.core.contracts import (
    ConnectionSnapshot,
    ExtractPeriod,
    ExtractStart,
    FreshnessStatus,
    NormalizedExtract,
    PersistableExtractDefinition,
)
from app.connectors.models import DataConnection, MetricPoint, MetricSeries, SourceExtract


class ConnectorStateError(RuntimeError):
    pass


class ConnectorRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def register_connection(
        self,
        *,
        tenant_id: uuid.UUID,
        site_id: uuid.UUID,
        provider: str,
        property_id: str,
        scopes: tuple[str, ...],
        secret_reference: str,
        connection_metadata: dict[str, Any] | None = None,
    ) -> uuid.UUID:
        async with self._session_factory() as session, session.begin():
            site = await session.scalar(
                select(Site.id).where(Site.id == site_id, Site.tenant_id == tenant_id)
            )
            if site is None:
                raise ConnectorStateError("site does not belong to connector tenant")
            connection_id = uuid.uuid4()
            statement = (
                insert(DataConnection)
                .values(
                    id=connection_id,
                    tenant_id=tenant_id,
                    site_id=site_id,
                    provider=provider,
                    external_property_id=property_id,
                    status="PENDING",
                    scopes=list(scopes),
                    secret_reference=secret_reference,
                    connection_metadata=connection_metadata or {},
                )
                .on_conflict_do_nothing(constraint="uq_data_connections_property")
                .returning(DataConnection.id)
            )
            created = await session.scalar(statement)
            if created is not None:
                return created
            existing = await session.scalar(
                select(DataConnection.id).where(
                    DataConnection.tenant_id == tenant_id,
                    DataConnection.site_id == site_id,
                    DataConnection.provider == provider,
                    DataConnection.external_property_id == property_id,
                )
            )
            if existing is None:
                raise ConnectorStateError("connection registration conflict could not be resolved")
            return existing

    async def register_ga4_connection(
        self,
        *,
        tenant_id: uuid.UUID,
        site_id: uuid.UUID,
        property_id: str,
        scopes: tuple[str, ...],
        secret_reference: str,
    ) -> uuid.UUID:
        return await self.register_connection(
            tenant_id=tenant_id,
            site_id=site_id,
            provider="GA4",
            property_id=property_id,
            scopes=scopes,
            secret_reference=secret_reference,
        )

    async def load_connection(
        self, *, tenant_id: uuid.UUID, connection_id: uuid.UUID
    ) -> ConnectionSnapshot | None:
        async with self._session_factory() as session:
            connection = await session.scalar(
                select(DataConnection).where(
                    DataConnection.id == connection_id,
                    DataConnection.tenant_id == tenant_id,
                    DataConnection.archived_at.is_(None),
                )
            )
            if connection is None:
                return None
            scopes = connection.scopes
            if not isinstance(scopes, list) or not all(isinstance(item, str) for item in scopes):
                raise ConnectorStateError("connection scopes are invalid")
            return ConnectionSnapshot(
                id=connection.id,
                tenant_id=connection.tenant_id,
                site_id=connection.site_id,
                provider=connection.provider,
                external_property_id=connection.external_property_id,
                status=connection.status,
                scopes=tuple(scopes),
                secret_reference=connection.secret_reference,
                metadata=connection.connection_metadata,
            )

    async def mark_connection_validated(
        self,
        *,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        capability_snapshot: dict[str, Any],
    ) -> None:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            result = await session.execute(
                update(DataConnection)
                .where(
                    DataConnection.id == connection_id,
                    DataConnection.tenant_id == tenant_id,
                )
                .values(
                    status="CONNECTED",
                    connected_at=now,
                    last_attempt_at=now,
                    last_success_at=now,
                    last_error_at=None,
                    last_error_class=None,
                    last_error_code=None,
                    connection_metadata=capability_snapshot,
                )
            )
            if cast(Any, result).rowcount != 1:
                raise ConnectorStateError("connection validation ownership failed")

    async def start_extract(
        self,
        *,
        connection: ConnectionSnapshot,
        definition: PersistableExtractDefinition,
        query_definition: dict[str, Any],
        scheduled_run_key: str,
        freshness_status: FreshnessStatus,
    ) -> ExtractStart:
        extract_id = uuid.uuid4()
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            ownership = await session.scalar(
                select(DataConnection.id).where(
                    DataConnection.id == connection.id,
                    DataConnection.tenant_id == connection.tenant_id,
                    DataConnection.site_id == connection.site_id,
                    DataConnection.provider == connection.provider,
                )
            )
            if ownership is None:
                raise ConnectorStateError("connector ownership changed before extraction")
            statement = (
                insert(SourceExtract)
                .values(
                    id=extract_id,
                    tenant_id=connection.tenant_id,
                    site_id=connection.site_id,
                    connection_id=connection.id,
                    source=connection.provider,
                    extract_type=definition.code,
                    scheduled_run_key=scheduled_run_key,
                    query_definition=query_definition,
                    requested_at=now,
                    status="PENDING",
                    freshness_status=freshness_status,
                    response_metadata={},
                    connector_version=definition.connector_version,
                )
                .on_conflict_do_nothing(constraint="uq_source_extracts_logical_run")
                .returning(SourceExtract.id)
            )
            created_id = await session.scalar(statement)
            await session.execute(
                update(DataConnection)
                .where(
                    DataConnection.id == connection.id,
                    DataConnection.tenant_id == connection.tenant_id,
                )
                .values(last_attempt_at=now)
            )
            if created_id is not None:
                return ExtractStart(
                    extract_id=created_id,
                    created=True,
                    already_complete=False,
                )
            existing = await session.scalar(
                select(SourceExtract).where(
                    SourceExtract.connection_id == connection.id,
                    SourceExtract.tenant_id == connection.tenant_id,
                    SourceExtract.site_id == connection.site_id,
                    SourceExtract.scheduled_run_key == scheduled_run_key,
                )
            )
            if existing is None:
                raise ConnectorStateError("extract idempotency conflict could not be resolved")
            if (
                existing.extract_type != definition.code
                or existing.query_definition != query_definition
                or existing.freshness_status != freshness_status
            ):
                raise ConnectorStateError("logical extract key was reused with different semantics")
            return ExtractStart(
                extract_id=existing.id,
                created=False,
                already_complete=existing.status == "COMPLETE",
            )

    async def complete_extract(
        self,
        *,
        connection: ConnectionSnapshot,
        extract_id: uuid.UUID,
        normalized: NormalizedExtract,
        period: ExtractPeriod,
        freshness_status: FreshnessStatus,
    ) -> None:
        now = datetime.now(UTC)
        source_timezone = ZoneInfo(normalized.source_timezone)
        period_start = datetime.combine(
            period.start_date, time.min, tzinfo=source_timezone
        ).astimezone(UTC)
        period_end = datetime.combine(
            period.end_date + timedelta(days=1), time.min, tzinfo=source_timezone
        ).astimezone(UTC)
        metadata = dict(normalized.response_metadata)
        metadata["limitations"] = list(normalized.limitations)
        async with self._session_factory() as session, session.begin():
            extract = await session.scalar(
                select(SourceExtract)
                .where(
                    SourceExtract.id == extract_id,
                    SourceExtract.tenant_id == connection.tenant_id,
                    SourceExtract.site_id == connection.site_id,
                    SourceExtract.connection_id == connection.id,
                )
                .with_for_update()
            )
            if extract is None:
                raise ConnectorStateError("source extract does not belong to connector tenant")
            if extract.status == "COMPLETE":
                return

            for point in normalized.points:
                series_key = _series_key(
                    tenant_id=connection.tenant_id,
                    site_id=connection.site_id,
                    metric_code=point.metric_code,
                    semantics_version=point.metric_semantics_version,
                    granularity=point.granularity,
                    dimensions=point.dimensions,
                    source=connection.provider,
                )
                series_id = uuid.uuid4()
                created_series_id = await session.scalar(
                    insert(MetricSeries)
                    .values(
                        id=series_id,
                        tenant_id=connection.tenant_id,
                        site_id=connection.site_id,
                        source=connection.provider,
                        metric_code=point.metric_code,
                        metric_semantics_version=point.metric_semantics_version,
                        unit=point.unit,
                        granularity=point.granularity,
                        dimensions=point.dimensions,
                        series_key=series_key,
                    )
                    .on_conflict_do_nothing(constraint="uq_metric_series_key")
                    .returning(MetricSeries.id)
                )
                if created_series_id is None:
                    created_series_id = await session.scalar(
                        select(MetricSeries.id).where(
                            MetricSeries.series_key == series_key,
                            MetricSeries.tenant_id == connection.tenant_id,
                            MetricSeries.site_id == connection.site_id,
                        )
                    )
                if created_series_id is None:
                    raise ConnectorStateError("metric series conflict could not be resolved")
                await session.execute(
                    insert(MetricPoint)
                    .values(
                        id=uuid.uuid4(),
                        tenant_id=connection.tenant_id,
                        site_id=connection.site_id,
                        series_id=created_series_id,
                        source_extract_id=extract_id,
                        source_time=point.source_time,
                        period_start=point.period_start,
                        period_end=point.period_end,
                        value=point.value,
                        numerator=point.numerator,
                        denominator=point.denominator,
                        sample_status=("LIMITED" if normalized.limitations else "COMPLETE"),
                        freshness_status=point.freshness_status or freshness_status,
                        retrieved_at=now,
                    )
                    .on_conflict_do_nothing(constraint="uq_metric_points_extract_period")
                )

            extract.status = "COMPLETE"
            extract.source_timezone = normalized.source_timezone
            extract.period_start = period_start
            extract.period_end = period_end
            extract.retrieved_at = now
            extract.response_metadata = metadata
            connection_result = await session.execute(
                update(DataConnection)
                .where(
                    DataConnection.id == connection.id,
                    DataConnection.tenant_id == connection.tenant_id,
                    DataConnection.site_id == connection.site_id,
                )
                .values(
                    status="CONNECTED",
                    last_success_at=now,
                    last_error_at=None,
                    last_error_class=None,
                    last_error_code=None,
                )
            )
            if cast(Any, connection_result).rowcount != 1:
                raise ConnectorStateError("connection ownership changed during completion")

    async def fail_extract(
        self,
        *,
        connection: ConnectionSnapshot,
        extract_id: uuid.UUID | None,
        error_class: str,
        error_code: str,
        affect_connection: bool = True,
    ) -> None:
        now = datetime.now(UTC)
        connection_status = {
            "AUTH_EXPIRED": "AUTH_EXPIRED",
            "PERMISSION_ERROR": "PERMISSION_ERROR",
        }.get(error_code, "DEGRADED")
        async with self._session_factory() as session, session.begin():
            if extract_id is not None:
                await session.execute(
                    update(SourceExtract)
                    .where(
                        SourceExtract.id == extract_id,
                        SourceExtract.tenant_id == connection.tenant_id,
                        SourceExtract.site_id == connection.site_id,
                        SourceExtract.connection_id == connection.id,
                        SourceExtract.status != "COMPLETE",
                    )
                    .values(
                        status="FAILED",
                        retrieved_at=now,
                        response_metadata={
                            "errorClass": error_class[:100],
                            "errorCode": error_code[:100],
                            "limitations": ["CONNECTOR_EXTRACTION_FAILED"],
                        },
                    )
                )
            if not affect_connection:
                return
            result = await session.execute(
                update(DataConnection)
                .where(
                    DataConnection.id == connection.id,
                    DataConnection.tenant_id == connection.tenant_id,
                    DataConnection.site_id == connection.site_id,
                )
                .values(
                    status=connection_status,
                    last_attempt_at=now,
                    last_error_at=now,
                    last_error_class=error_class[:100],
                    last_error_code=error_code[:100],
                )
            )
            if cast(Any, result).rowcount != 1:
                raise ConnectorStateError("connection failure ownership validation failed")

    async def schedulable_connections(
        self, *, provider: str = "GA4"
    ) -> tuple[ConnectionSnapshot, ...]:
        async with self._session_factory() as session:
            rows = (
                await session.scalars(
                    select(DataConnection).where(
                        DataConnection.provider == provider,
                        DataConnection.status.in_(["CONNECTED", "DEGRADED"]),
                        DataConnection.archived_at.is_(None),
                    )
                )
            ).all()
            result: list[ConnectionSnapshot] = []
            for connection in rows:
                if not isinstance(connection.scopes, list) or not all(
                    isinstance(scope, str) for scope in connection.scopes
                ):
                    continue
                result.append(
                    ConnectionSnapshot(
                        id=connection.id,
                        tenant_id=connection.tenant_id,
                        site_id=connection.site_id,
                        provider=connection.provider,
                        external_property_id=connection.external_property_id,
                        status=connection.status,
                        scopes=tuple(connection.scopes),
                        secret_reference=connection.secret_reference,
                        metadata=connection.connection_metadata,
                    )
                )
            return tuple(result)


def _series_key(
    *,
    tenant_id: uuid.UUID,
    site_id: uuid.UUID,
    metric_code: str,
    semantics_version: str,
    granularity: str,
    dimensions: dict[str, str],
    source: str = "GA4",
) -> str:
    canonical = json.dumps(
        {
            "tenantId": str(tenant_id),
            "siteId": str(site_id),
            "source": source,
            "metricCode": metric_code,
            "semanticsVersion": semantics_version,
            "granularity": granularity,
            "dimensions": dimensions,
            "entityId": None,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode()
    return hashlib.sha256(canonical).hexdigest()
