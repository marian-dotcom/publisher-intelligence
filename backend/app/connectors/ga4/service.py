import uuid
from collections.abc import Mapping
from datetime import date, timedelta

from app.connectors.core.contracts import (
    AccessTokenResolver,
    ConnectionSnapshot,
    ConnectorError,
    ExtractPeriod,
    FreshnessStatus,
    NormalizedExtract,
)
from app.connectors.core.persistence import ConnectorRepository, ConnectorStateError
from app.connectors.drilldown.catalog import (
    DRILLDOWN_CATALOG_VERSION,
    get_drilldown_definition,
    provider_codes,
)
from app.connectors.ga4.client import GA4Client
from app.connectors.ga4.definitions import (
    GA4_BEHAVIOR_DAILY_V1,
    GA4_READONLY_SCOPE,
    GA4_TRAFFIC_HOURLY_V1,
    get_ga4_definition,
)
from app.connectors.ga4.drilldown import (
    GA4_DRILLDOWN_DEFINITIONS,
    get_ga4_drilldown_definition,
)
from app.connectors.ga4.normalization import normalize_report, validate_metadata


class GA4ConnectorService:
    def __init__(
        self,
        repository: ConnectorRepository,
        client: GA4Client,
        token_resolver: AccessTokenResolver,
    ) -> None:
        self._repository = repository
        self._client = client
        self._token_resolver = token_resolver

    async def register_connection(
        self,
        *,
        tenant_id: uuid.UUID,
        site_id: uuid.UUID,
        property_id: str,
        secret_reference: str,
    ) -> uuid.UUID:
        canonical_property = self._client.property_resource(property_id).removeprefix("properties/")
        return await self._repository.register_ga4_connection(
            tenant_id=tenant_id,
            site_id=site_id,
            property_id=canonical_property,
            scopes=(GA4_READONLY_SCOPE,),
            secret_reference=secret_reference,
        )

    async def validate_connection(
        self,
        *,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        probe_date: date,
    ) -> dict[str, object]:
        connection = await self._required_connection(tenant_id, connection_id)
        try:
            credential = await self._token_resolver.resolve(connection.secret_reference)
            metadata = await self._client.get_metadata(
                property_id=connection.external_property_id,
                access_token=credential.access_token,
            )
            traffic_capabilities = validate_metadata(metadata, GA4_TRAFFIC_HOURLY_V1)
            behavior_capabilities = validate_metadata(metadata, GA4_BEHAVIOR_DAILY_V1)
            response = await self._client.run_report(
                property_id=connection.external_property_id,
                access_token=credential.access_token,
                definition=GA4_TRAFFIC_HOURLY_V1,
                period=ExtractPeriod(probe_date, probe_date),
            )
            normalized = normalize_report(response, GA4_TRAFFIC_HOURLY_V1)
        except ConnectorError as error:
            await self._repository.fail_extract(
                connection=connection,
                extract_id=None,
                error_class=type(error).__name__,
                error_code=error.code,
            )
            raise
        capability_snapshot: dict[str, object] = {
            "provider": "GA4",
            "propertyId": connection.external_property_id,
            "propertyTimezone": normalized.source_timezone,
            "definitions": [GA4_TRAFFIC_HOURLY_V1.code, GA4_BEHAVIOR_DAILY_V1.code],
            "validatedDimensions": sorted(
                set(traffic_capabilities["validatedDimensions"])
                | set(behavior_capabilities["validatedDimensions"])
            ),
            "validatedMetrics": sorted(
                set(traffic_capabilities["validatedMetrics"])
                | set(behavior_capabilities["validatedMetrics"])
            ),
            "probeLimitations": list(normalized.limitations),
            "drilldownCatalogVersion": DRILLDOWN_CATALOG_VERSION,
            "validatedDrilldowns": _validated_drilldowns(metadata),
        }
        await self._repository.mark_connection_validated(
            tenant_id=tenant_id,
            connection_id=connection_id,
            capability_snapshot=capability_snapshot,
        )
        return capability_snapshot

    async def run_extract(
        self,
        *,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        definition_code: str,
        period: ExtractPeriod,
        freshness_status: FreshnessStatus,
        scheduled_run_key: str,
    ) -> NormalizedExtract | None:
        connection = await self._required_connection(tenant_id, connection_id)
        if connection.status not in {"CONNECTED", "DEGRADED"}:
            raise ConnectorError(
                "CONNECTION_UNAVAILABLE",
                retryable=False,
                message="GA4 connection is not available for extraction",
            )
        try:
            definition = get_ga4_definition(definition_code)
        except ValueError as error:
            raise ConnectorError(
                "INVALID_DEFINITION",
                retryable=False,
                message="GA4 extract definition is not allowed",
            ) from error
        if len(scheduled_run_key) > 255 or not scheduled_run_key.strip():
            raise ConnectorError(
                "INVALID_RUN_KEY", retryable=False, message="GA4 logical run key is invalid"
            )
        query_definition = definition.query_definition(period)
        start = await self._repository.start_extract(
            connection=connection,
            definition=definition,
            query_definition=query_definition,
            scheduled_run_key=scheduled_run_key,
            freshness_status=freshness_status,
        )
        if start.already_complete:
            return None
        try:
            credential = await self._token_resolver.resolve(connection.secret_reference)
            response = await self._client.run_report(
                property_id=connection.external_property_id,
                access_token=credential.access_token,
                definition=definition,
                period=period,
            )
            normalized = normalize_report(response, definition)
            await self._repository.complete_extract(
                connection=connection,
                extract_id=start.extract_id,
                normalized=normalized,
                period=period,
                freshness_status=freshness_status,
            )
            return normalized
        except ConnectorError as error:
            await self._repository.fail_extract(
                connection=connection,
                extract_id=start.extract_id,
                error_class=type(error).__name__,
                error_code=error.code,
            )
            raise

    async def run_drilldown(
        self,
        *,
        tenant_id: uuid.UUID,
        site_id: uuid.UUID,
        connection_id: uuid.UUID,
        investigation_id: uuid.UUID,
        definition_code: str,
        period: ExtractPeriod,
        scheduled_run_key: str,
    ) -> NormalizedExtract | None:
        connection = await self._required_connection(tenant_id, connection_id)
        if connection.site_id != site_id:
            raise ConnectorStateError("GA4 drill-down site does not belong to job tenant")
        if connection.status not in {"CONNECTED", "DEGRADED"}:
            raise ConnectorError(
                "CONNECTION_UNAVAILABLE",
                retryable=False,
                message="GA4 connection is not available for drill-down",
            )
        catalog_definition = get_drilldown_definition(definition_code)
        if catalog_definition.provider != "GA4":
            raise ConnectorError(
                "DRILLDOWN_SCOPE_INVALID",
                retryable=False,
                message="Incident drill-down provider does not match GA4",
            )
        validated = connection.metadata.get("validatedDrilldowns")
        if (
            connection.metadata.get("drilldownCatalogVersion") != DRILLDOWN_CATALOG_VERSION
            or not isinstance(validated, list)
            or definition_code not in validated
        ):
            raise ConnectorError(
                "DRILLDOWN_NOT_VALIDATED",
                retryable=False,
                message="GA4 drill-down was not validated for this connection",
            )
        definition = get_ga4_drilldown_definition(catalog_definition.provider_definition_code)
        if len(scheduled_run_key) > 255 or not scheduled_run_key.strip():
            raise ConnectorError(
                "INVALID_RUN_KEY", retryable=False, message="GA4 logical run key is invalid"
            )
        query_definition = definition.query_definition(period)
        query_definition.update(
            {
                "tier": "C",
                "catalogVersion": catalog_definition.catalog_version,
                "semanticRequest": definition_code,
                "investigationId": str(investigation_id),
                "costUnits": catalog_definition.cost_units,
            }
        )
        start = await self._repository.start_extract(
            connection=connection,
            definition=definition,
            query_definition=query_definition,
            scheduled_run_key=scheduled_run_key,
            freshness_status="PRELIMINARY",
        )
        if start.already_complete:
            return None
        try:
            credential = await self._token_resolver.resolve(connection.secret_reference)
            response = await self._client.run_report(
                property_id=connection.external_property_id,
                access_token=credential.access_token,
                definition=definition,
                period=period,
            )
            normalized = normalize_report(response, definition)
            await self._repository.complete_extract(
                connection=connection,
                extract_id=start.extract_id,
                normalized=normalized,
                period=period,
                freshness_status="PRELIMINARY",
            )
            return normalized
        except ConnectorError as error:
            await self._repository.fail_extract(
                connection=connection,
                extract_id=start.extract_id,
                error_class=type(error).__name__,
                error_code=error.code,
                affect_connection=error.code != "QUOTA_LIMIT",
            )
            raise

    async def _required_connection(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID
    ) -> ConnectionSnapshot:
        connection = await self._repository.load_connection(
            tenant_id=tenant_id, connection_id=connection_id
        )
        if connection is None or connection.provider != "GA4":
            raise ConnectorStateError("GA4 connection does not belong to job tenant")
        if connection.scopes != (GA4_READONLY_SCOPE,):
            raise ConnectorError(
                "SCOPE_INVALID",
                retryable=False,
                message="GA4 connection must use only the read-only scope",
            )
        return connection


def default_probe_date(today: date) -> date:
    return today - timedelta(days=1)


def _validated_drilldowns(metadata: Mapping[str, object]) -> list[str]:
    validated: list[str] = []
    for semantic_code in provider_codes("GA4"):
        catalog_definition = get_drilldown_definition(semantic_code)
        definition = GA4_DRILLDOWN_DEFINITIONS[catalog_definition.provider_definition_code]
        try:
            validate_metadata(metadata, definition)
        except ConnectorError as error:
            if error.code == "SCHEMA_INCOMPATIBLE":
                continue
            raise
        validated.append(semantic_code)
    return sorted(validated)
