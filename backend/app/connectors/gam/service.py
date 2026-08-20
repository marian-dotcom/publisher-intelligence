import uuid

from app.connectors.core.contracts import (
    AccessTokenResolver,
    ConnectionSnapshot,
    ConnectorError,
    FreshnessStatus,
    NormalizedExtract,
)
from app.connectors.core.persistence import ConnectorRepository, ConnectorStateError
from app.connectors.drilldown.catalog import (
    DRILLDOWN_CATALOG_VERSION,
    get_drilldown_definition,
    provider_codes,
)
from app.connectors.gam.client import GAMClient
from app.connectors.gam.definitions import (
    GAM_DEFINITIONS,
    GAM_PROFILES,
    GAM_READONLY_SCOPE,
    GAMProfile,
    binding_key,
    get_gam_definition,
)
from app.connectors.gam.drilldown import get_gam_drilldown_definition
from app.connectors.gam.normalization import (
    GAMNetwork,
    normalize_network,
    normalize_report,
    validate_network_access,
    validate_report,
)


class GAMConnectorService:
    def __init__(
        self,
        repository: ConnectorRepository,
        client: GAMClient,
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
        network_code: str,
        report_bindings: dict[str, str],
        secret_reference: str,
        drilldown_report_bindings: dict[str, str] | None = None,
    ) -> uuid.UUID:
        code = self._client.canonical_network_code(network_code)
        bindings = self._validate_bindings(code, report_bindings)
        drilldown_bindings = self._validate_drilldown_bindings(
            code, drilldown_report_bindings or {}
        )
        return await self._repository.register_connection(
            tenant_id=tenant_id,
            site_id=site_id,
            provider="GAM",
            property_id=code,
            scopes=(GAM_READONLY_SCOPE,),
            secret_reference=secret_reference,
            connection_metadata={
                "reportBindings": bindings,
                "drilldownReportBindings": drilldown_bindings,
            },
        )

    async def validate_connection(
        self,
        *,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
    ) -> dict[str, object]:
        connection = await self._required_connection(tenant_id, connection_id)
        bindings = self._bindings_from_connection(connection)
        drilldown_bindings = self._drilldown_bindings_from_connection(connection)
        try:
            credential = await self._token_resolver.resolve(connection.secret_reference)
            accessible = await self._client.list_networks(access_token=credential.access_token)
            validate_network_access(accessible, connection.external_property_id)
            network_payload = await self._client.get_network(
                network_code=connection.external_property_id,
                access_token=credential.access_token,
            )
            network = normalize_network(network_payload, connection.external_property_id)
            fingerprints: dict[str, str] = {}
            today_probe_rows: dict[str, int] = {}
            for definition in GAM_DEFINITIONS.values():
                for profile in GAM_PROFILES:
                    key = binding_key(definition.code, profile)
                    report_payload = await self._client.get_report(
                        network_code=network.network_code,
                        report_resource=bindings[key],
                        access_token=credential.access_token,
                    )
                    capability = validate_report(
                        report_payload,
                        definition=definition,
                        profile=profile,
                        network=network,
                        expected_resource=bindings[key],
                    )
                    fingerprint = capability["definitionFingerprint"]
                    if not isinstance(fingerprint, str):
                        raise ConnectorError(
                            "INVALID_RESPONSE",
                            retryable=False,
                            message="GAM report fingerprint is invalid",
                        )
                    fingerprints[key] = fingerprint
                probe_payload = await self._client.run_report(
                    network_code=network.network_code,
                    report_resource=bindings[binding_key(definition.code, "TODAY")],
                    access_token=credential.access_token,
                )
                probe = normalize_report(
                    probe_payload, definition=definition, network=network, profile="TODAY"
                )
                today_probe_rows[definition.code] = int(
                    probe.normalized.response_metadata["returnedRowCount"]
                )
            drilldown_fingerprints: dict[str, str] = {}
            validated_drilldowns: set[str] = set()
            for key, report_resource in drilldown_bindings.items():
                semantic_code, drilldown_profile_raw = key.rsplit(":", 1)
                if drilldown_profile_raw not in GAM_PROFILES:
                    raise ConnectorError(
                        "REPORT_BINDINGS_INVALID",
                        retryable=False,
                        message="GAM drill-down profile is invalid",
                    )
                drilldown_profile: GAMProfile = drilldown_profile_raw
                catalog_definition = get_drilldown_definition(semantic_code)
                definition = get_gam_drilldown_definition(
                    catalog_definition.provider_definition_code
                )
                report_payload = await self._client.get_report(
                    network_code=network.network_code,
                    report_resource=report_resource,
                    access_token=credential.access_token,
                )
                capability = validate_report(
                    report_payload,
                    definition=definition,
                    profile=drilldown_profile,
                    network=network,
                    expected_resource=report_resource,
                )
                fingerprint = capability["definitionFingerprint"]
                if not isinstance(fingerprint, str):
                    raise ConnectorError(
                        "INVALID_RESPONSE",
                        retryable=False,
                        message="GAM drill-down report fingerprint is invalid",
                    )
                drilldown_fingerprints[key] = fingerprint
                validated_drilldowns.add(semantic_code)
        except ConnectorError as error:
            await self._repository.fail_extract(
                connection=connection,
                extract_id=None,
                error_class=type(error).__name__,
                error_code=error.code,
            )
            raise
        snapshot: dict[str, object] = {
            "provider": "GAM",
            "networkCode": network.network_code,
            "networkDisplayName": network.display_name,
            "sourceTimezone": network.timezone,
            "currencyCode": network.currency_code,
            "apiAdapter": "REST_V1_BETA",
            "scope": GAM_READONLY_SCOPE,
            "reportBindings": bindings,
            "drilldownReportBindings": drilldown_bindings,
            "drilldownCatalogVersion": DRILLDOWN_CATALOG_VERSION,
            "definitionFingerprints": fingerprints,
            "drilldownDefinitionFingerprints": drilldown_fingerprints,
            "validatedDrilldowns": sorted(validated_drilldowns),
            "validatedDrilldownBindings": sorted(drilldown_fingerprints),
            "supportedCubes": sorted(GAM_DEFINITIONS),
            "todayProbeRows": today_probe_rows,
            "reportCreation": "EXTERNAL_PRECONFIGURATION_REQUIRED",
            "expandedCompatibility": False,
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
        profile: str,
        freshness_status: FreshnessStatus,
        scheduled_run_key: str,
    ) -> NormalizedExtract | None:
        connection = await self._available_connection(tenant_id, connection_id)
        try:
            definition = get_gam_definition(definition_code)
        except ValueError as error:
            raise ConnectorError(
                "INVALID_DEFINITION",
                retryable=False,
                message="GAM extract definition is not allowed",
            ) from error
        if profile not in GAM_PROFILES:
            raise ConnectorError(
                "INVALID_PROFILE", retryable=False, message="GAM report profile is not allowed"
            )
        typed_profile: GAMProfile = profile
        expected_freshness: FreshnessStatus = "PRELIMINARY"
        if freshness_status != expected_freshness:
            raise ConnectorError(
                "FRESHNESS_INVALID",
                retryable=False,
                message="GAM freshness does not match the fixed report profile",
            )
        _validate_run_key(scheduled_run_key)
        bindings = self._bindings_from_connection(connection)
        report_resource = bindings[binding_key(definition.code, typed_profile)]
        query_definition = definition.query_definition(
            report_resource=report_resource, profile=typed_profile
        )
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
            network = self._network_from_connection(connection)
            report_payload = await self._client.get_report(
                network_code=network.network_code,
                report_resource=report_resource,
                access_token=credential.access_token,
            )
            capability = validate_report(
                report_payload,
                definition=definition,
                profile=typed_profile,
                network=network,
                expected_resource=report_resource,
            )
            fingerprints = connection.metadata.get("definitionFingerprints")
            expected_fingerprint = (
                fingerprints.get(binding_key(definition.code, typed_profile))
                if isinstance(fingerprints, dict)
                else None
            )
            if capability["definitionFingerprint"] != expected_fingerprint:
                raise ConnectorError(
                    "REPORT_DEFINITION_CHANGED",
                    retryable=False,
                    message="GAM report definition changed after capability validation",
                )
            payload = await self._client.run_report(
                network_code=network.network_code,
                report_resource=report_resource,
                access_token=credential.access_token,
            )
            result = normalize_report(
                payload, definition=definition, network=network, profile=typed_profile
            )
            await self._repository.complete_extract(
                connection=connection,
                extract_id=start.extract_id,
                normalized=result.normalized,
                period=result.period,
                freshness_status=freshness_status,
            )
            return result.normalized
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
        profile: str,
        scheduled_run_key: str,
    ) -> NormalizedExtract | None:
        connection = await self._available_connection(tenant_id, connection_id)
        if connection.site_id != site_id:
            raise ConnectorStateError("GAM drill-down site does not belong to job tenant")
        catalog_definition = get_drilldown_definition(definition_code)
        if catalog_definition.provider != "GAM":
            raise ConnectorError(
                "DRILLDOWN_SCOPE_INVALID",
                retryable=False,
                message="Incident drill-down provider does not match GAM",
            )
        if profile not in GAM_PROFILES:
            raise ConnectorError(
                "DRILLDOWN_WINDOW_INVALID",
                retryable=False,
                message="GAM drill-down profile is not allowlisted",
            )
        typed_profile: GAMProfile = profile
        key = f"{definition_code}:{typed_profile}"
        validated = connection.metadata.get("validatedDrilldownBindings")
        if (
            connection.metadata.get("drilldownCatalogVersion") != DRILLDOWN_CATALOG_VERSION
            or not isinstance(validated, list)
            or key not in validated
        ):
            raise ConnectorError(
                "DRILLDOWN_NOT_VALIDATED",
                retryable=False,
                message="GAM drill-down profile was not validated for this connection",
            )
        definition = get_gam_drilldown_definition(catalog_definition.provider_definition_code)
        _validate_run_key(scheduled_run_key)
        bindings = self._drilldown_bindings_from_connection(connection)
        report_resource = bindings[key]
        query_definition = definition.query_definition(
            report_resource=report_resource, profile=typed_profile
        )
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
            network = self._network_from_connection(connection)
            report_payload = await self._client.get_report(
                network_code=network.network_code,
                report_resource=report_resource,
                access_token=credential.access_token,
            )
            capability = validate_report(
                report_payload,
                definition=definition,
                profile=typed_profile,
                network=network,
                expected_resource=report_resource,
            )
            fingerprints = connection.metadata.get("drilldownDefinitionFingerprints")
            expected_fingerprint = fingerprints.get(key) if isinstance(fingerprints, dict) else None
            if capability["definitionFingerprint"] != expected_fingerprint:
                raise ConnectorError(
                    "REPORT_DEFINITION_CHANGED",
                    retryable=False,
                    message="GAM drill-down report changed after capability validation",
                )
            payload = await self._client.run_report(
                network_code=network.network_code,
                report_resource=report_resource,
                access_token=credential.access_token,
            )
            result = normalize_report(
                payload, definition=definition, network=network, profile=typed_profile
            )
            await self._repository.complete_extract(
                connection=connection,
                extract_id=start.extract_id,
                normalized=result.normalized,
                period=result.period,
                freshness_status="PRELIMINARY",
            )
            return result.normalized
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
                message="GAM connection is not available for extraction",
            )
        return connection

    async def _required_connection(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID
    ) -> ConnectionSnapshot:
        connection = await self._repository.load_connection(
            tenant_id=tenant_id, connection_id=connection_id
        )
        if connection is None or connection.provider != "GAM":
            raise ConnectorStateError("GAM connection does not belong to job tenant")
        if connection.scopes != (GAM_READONLY_SCOPE,):
            raise ConnectorError(
                "SCOPE_INVALID",
                retryable=False,
                message="GAM connection must use only the read-only scope",
            )
        return connection

    def _bindings_from_connection(self, connection: ConnectionSnapshot) -> dict[str, str]:
        raw = connection.metadata.get("reportBindings")
        if not isinstance(raw, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in raw.items()
        ):
            raise ConnectorError(
                "REPORT_BINDINGS_INVALID",
                retryable=False,
                message="GAM report bindings are unavailable",
            )
        return self._validate_bindings(connection.external_property_id, raw)

    def _drilldown_bindings_from_connection(self, connection: ConnectionSnapshot) -> dict[str, str]:
        raw = connection.metadata.get("drilldownReportBindings", {})
        if not isinstance(raw, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in raw.items()
        ):
            raise ConnectorError(
                "REPORT_BINDINGS_INVALID",
                retryable=False,
                message="GAM drill-down report bindings are invalid",
            )
        return self._validate_drilldown_bindings(connection.external_property_id, raw)

    def _validate_bindings(
        self, network_code: str, report_bindings: dict[str, str]
    ) -> dict[str, str]:
        expected = {
            binding_key(definition.code, profile)
            for definition in GAM_DEFINITIONS.values()
            for profile in GAM_PROFILES
        }
        if set(report_bindings) != expected:
            raise ConnectorError(
                "REPORT_BINDINGS_INVALID",
                retryable=False,
                message="GAM requires every fixed cube and report profile",
            )
        return {
            key: self._client.canonical_report_resource(network_code, value)
            for key, value in sorted(report_bindings.items())
        }

    def _validate_drilldown_bindings(
        self, network_code: str, report_bindings: dict[str, str]
    ) -> dict[str, str]:
        allowed = {
            f"{definition_code}:{profile}"
            for definition_code in provider_codes("GAM")
            for profile in GAM_PROFILES
        }
        if not set(report_bindings).issubset(allowed):
            raise ConnectorError(
                "REPORT_BINDINGS_INVALID",
                retryable=False,
                message="GAM drill-down report binding is not allowlisted",
            )
        return {
            key: self._client.canonical_report_resource(network_code, value)
            for key, value in sorted(report_bindings.items())
        }

    @staticmethod
    def _network_from_connection(connection: ConnectionSnapshot) -> GAMNetwork:
        timezone = connection.metadata.get("sourceTimezone")
        currency = connection.metadata.get("currencyCode")
        display_name = connection.metadata.get("networkDisplayName")
        if not all(
            isinstance(value, str) and value for value in (timezone, currency, display_name)
        ):
            raise ConnectorError(
                "CAPABILITY_STATE_INVALID",
                retryable=False,
                message="GAM validated network metadata is unavailable",
            )
        return GAMNetwork(
            connection.external_property_id,
            str(timezone),
            str(currency),
            str(display_name),
        )


def _validate_run_key(run_key: str) -> None:
    if len(run_key) > 255 or not run_key.strip():
        raise ConnectorError(
            "INVALID_RUN_KEY", retryable=False, message="GAM logical run key is invalid"
        )
