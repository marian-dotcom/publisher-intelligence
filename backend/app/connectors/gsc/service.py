import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

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
from app.connectors.gsc.client import GSCClient
from app.connectors.gsc.definitions import (
    GSC_CONNECTOR_VERSION,
    GSC_DEFINITIONS,
    GSC_DISCOVER_DAILY_V1,
    GSC_READONLY_SCOPE,
    GSC_SEARCH_DAILY_V1,
    GSC_SOURCE_TIMEZONE,
    get_gsc_definition,
)
from app.connectors.gsc.drilldown import get_gsc_drilldown_definition
from app.connectors.gsc.normalization import (
    normalize_inspection,
    normalize_query,
    validate_property_access,
)


@dataclass(frozen=True, slots=True)
class _InspectionDefinition:
    code: str = "GSC_URL_INSPECTION_V1"
    connector_version: str = GSC_CONNECTOR_VERSION


GSC_URL_INSPECTION_V1 = _InspectionDefinition()


class GSCConnectorService:
    def __init__(
        self,
        repository: ConnectorRepository,
        client: GSCClient,
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
        canonical = self._client.canonical_property(property_id)
        return await self._repository.register_connection(
            tenant_id=tenant_id,
            site_id=site_id,
            provider="GSC",
            property_id=canonical,
            scopes=(GSC_READONLY_SCOPE,),
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
            sites = await self._client.list_sites(access_token=credential.access_token)
            permission = validate_property_access(sites, connection.external_property_id)
            search_payload = await self._client.run_query(
                property_id=connection.external_property_id,
                access_token=credential.access_token,
                definition=GSC_SEARCH_DAILY_V1,
                period=ExtractPeriod(probe_date, probe_date),
            )
            search_probe = normalize_query(search_payload, GSC_SEARCH_DAILY_V1)
            discover_payload = await self._client.run_query(
                property_id=connection.external_property_id,
                access_token=credential.access_token,
                definition=GSC_DISCOVER_DAILY_V1,
                period=ExtractPeriod(probe_date, probe_date),
            )
            discover_probe = normalize_query(discover_payload, GSC_DISCOVER_DAILY_V1)
        except ConnectorError as error:
            await self._repository.fail_extract(
                connection=connection,
                extract_id=None,
                error_class=type(error).__name__,
                error_code=error.code,
            )
            raise
        snapshot: dict[str, object] = {
            "provider": "GSC",
            "propertyId": connection.external_property_id,
            "propertyType": self._client.property_type(connection.external_property_id),
            "permissionLevel": permission,
            "sourceTimezone": GSC_SOURCE_TIMEZONE,
            "definitions": sorted(GSC_DEFINITIONS),
            "searchProbeRowCount": len(search_probe.points) // len(GSC_SEARCH_DAILY_V1.metrics),
            "discoverAvailable": bool(discover_probe.points),
            "probeLimitations": sorted(
                set(search_probe.limitations) | set(discover_probe.limitations)
            ),
            "drilldownCatalogVersion": DRILLDOWN_CATALOG_VERSION,
            "validatedDrilldowns": list(provider_codes("GSC")),
        }
        await self._repository.mark_connection_validated(
            tenant_id=tenant_id,
            connection_id=connection_id,
            capability_snapshot=snapshot,
        )
        return snapshot

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
        connection = await self._available_connection(tenant_id, connection_id)
        try:
            definition = get_gsc_definition(definition_code)
        except ValueError as error:
            raise ConnectorError(
                "INVALID_DEFINITION",
                retryable=False,
                message="GSC extract definition is not allowed",
            ) from error
        _validate_run_key(scheduled_run_key)
        expected_freshness: FreshnessStatus = (
            "MATURE" if definition.data_state == "final" else "PRELIMINARY"
        )
        if freshness_status != expected_freshness:
            raise ConnectorError(
                "FRESHNESS_INVALID",
                retryable=False,
                message="GSC freshness does not match the fixed data state",
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
            payload = await self._client.run_query(
                property_id=connection.external_property_id,
                access_token=credential.access_token,
                definition=definition,
                period=period,
            )
            normalized = normalize_query(payload, definition)
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
        parameters: dict[str, str],
        scheduled_run_key: str,
    ) -> NormalizedExtract | None:
        connection = await self._available_connection(tenant_id, connection_id)
        if connection.site_id != site_id:
            raise ConnectorStateError("GSC drill-down site does not belong to job tenant")
        catalog_definition = get_drilldown_definition(definition_code)
        if catalog_definition.provider != "GSC":
            raise ConnectorError(
                "DRILLDOWN_SCOPE_INVALID",
                retryable=False,
                message="Incident drill-down provider does not match GSC",
            )
        if set(parameters) != set(catalog_definition.required_parameters):
            raise ConnectorError(
                "DRILLDOWN_PARAMETERS_INVALID",
                retryable=False,
                message="GSC drill-down parameters do not match the fixed definition",
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
                message="GSC drill-down was not validated for this connection",
            )
        definition = get_gsc_drilldown_definition(catalog_definition.provider_definition_code)
        _validate_run_key(scheduled_run_key)
        dimension_filter: dict[str, object] | None = None
        if "page" in parameters:
            page = parameters["page"]
            self._client.validate_inspection_url(connection.external_property_id, page)
            dimension_filter = {
                "groupType": "and",
                "filters": [{"dimension": "page", "operator": "equals", "expression": page}],
            }
        query_definition = definition.query_definition(period)
        query_definition.update(
            {
                "tier": "C",
                "catalogVersion": catalog_definition.catalog_version,
                "semanticRequest": definition_code,
                "investigationId": str(investigation_id),
                "dimensionFilterGroups": [dimension_filter] if dimension_filter else [],
                "costUnits": catalog_definition.cost_units,
            }
        )
        start = await self._repository.start_extract(
            connection=connection,
            definition=definition,
            query_definition=query_definition,
            scheduled_run_key=scheduled_run_key,
            freshness_status="MATURE",
        )
        if start.already_complete:
            return None
        try:
            credential = await self._token_resolver.resolve(connection.secret_reference)
            payload = await self._client.run_query(
                property_id=connection.external_property_id,
                access_token=credential.access_token,
                definition=definition,
                period=period,
                dimension_filter=dimension_filter,
            )
            normalized = normalize_query(payload, definition)
            await self._repository.complete_extract(
                connection=connection,
                extract_id=start.extract_id,
                normalized=normalized,
                period=period,
                freshness_status="MATURE",
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

    async def inspect_url(
        self,
        *,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        inspection_url: str,
        inspection_date: date,
        scheduled_run_key: str,
    ) -> dict[str, Any] | None:
        connection = await self._available_connection(tenant_id, connection_id)
        _validate_run_key(scheduled_run_key)
        self._client.validate_inspection_url(connection.external_property_id, inspection_url)
        period = ExtractPeriod(inspection_date, inspection_date)
        query_definition = {
            "definition": GSC_URL_INSPECTION_V1.code,
            "connectorVersion": GSC_URL_INSPECTION_V1.connector_version,
            "method": "urlInspection.index.inspect",
            "siteUrl": connection.external_property_id,
            "inspectionUrl": inspection_url,
            "languageCode": "en-US",
        }
        start = await self._repository.start_extract(
            connection=connection,
            definition=GSC_URL_INSPECTION_V1,
            query_definition=query_definition,
            scheduled_run_key=scheduled_run_key,
            freshness_status="UNKNOWN",
        )
        if start.already_complete:
            return None
        try:
            credential = await self._token_resolver.resolve(connection.secret_reference)
            payload = await self._client.inspect_url(
                property_id=connection.external_property_id,
                inspection_url=inspection_url,
                access_token=credential.access_token,
            )
            inspection = normalize_inspection(payload)
            normalized = NormalizedExtract(
                source_timezone=GSC_SOURCE_TIMEZONE,
                points=(),
                response_metadata={
                    "inspection": inspection,
                    "sourceTimezone": GSC_SOURCE_TIMEZONE,
                    "limitations": ["CURRENT_INDEX_VIEW_ONLY", "NOT_LIVE_URL_TEST"],
                },
                limitations=("CURRENT_INDEX_VIEW_ONLY", "NOT_LIVE_URL_TEST"),
            )
            await self._repository.complete_extract(
                connection=connection,
                extract_id=start.extract_id,
                normalized=normalized,
                period=period,
                freshness_status="UNKNOWN",
            )
            return inspection
        except ConnectorError as error:
            await self._repository.fail_extract(
                connection=connection,
                extract_id=start.extract_id,
                error_class=type(error).__name__,
                error_code=error.code,
                affect_connection=error.code != "QUOTA_LIMIT",
            )
            raise

    async def _available_connection(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID
    ) -> ConnectionSnapshot:
        connection = await self._required_connection(tenant_id, connection_id)
        if connection.status not in {"CONNECTED", "DEGRADED"}:
            raise ConnectorError(
                "CONNECTION_UNAVAILABLE",
                retryable=False,
                message="GSC connection is not available for extraction",
            )
        return connection

    async def _required_connection(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID
    ) -> ConnectionSnapshot:
        connection = await self._repository.load_connection(
            tenant_id=tenant_id, connection_id=connection_id
        )
        if connection is None or connection.provider != "GSC":
            raise ConnectorStateError("GSC connection does not belong to job tenant")
        if connection.scopes != (GSC_READONLY_SCOPE,):
            raise ConnectorError(
                "SCOPE_INVALID",
                retryable=False,
                message="GSC connection must use only the read-only scope",
            )
        return connection


def _validate_run_key(run_key: str) -> None:
    if len(run_key) > 255 or not run_key.strip():
        raise ConnectorError(
            "INVALID_RUN_KEY", retryable=False, message="GSC logical run key is invalid"
        )
