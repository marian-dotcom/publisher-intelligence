import re
from collections.abc import Mapping
from typing import Any, Protocol, cast

import httpx

from app.connectors.core.contracts import ConnectorError, ExtractDefinition, ExtractPeriod

GA4_DATA_API_ROOT = "https://analyticsdata.googleapis.com/v1beta"
_PROPERTY_ID = re.compile(r"^[1-9][0-9]{0,19}$")


class GA4ProviderError(ConnectorError):
    pass


class GA4Transport(Protocol):
    async def request(
        self,
        *,
        method: str,
        url: str,
        access_token: str,
        json_body: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]: ...


class HttpxGA4Transport:
    def __init__(self, *, timeout_seconds: float = 30.0) -> None:
        self._timeout = httpx.Timeout(timeout_seconds, connect=min(10.0, timeout_seconds))

    async def request(
        self,
        *,
        method: str,
        url: str,
        access_token: str,
        json_body: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.request(method, url, headers=headers, json=json_body)
        except httpx.RequestError as error:
            raise GA4ProviderError(
                "TRANSPORT_ERROR",
                retryable=True,
                message="GA4 transport failed",
            ) from error

        if response.status_code >= 400:
            raise _http_error(response.status_code)
        try:
            payload = response.json()
        except ValueError as error:
            raise GA4ProviderError(
                "INVALID_RESPONSE",
                retryable=False,
                message="GA4 returned invalid JSON",
            ) from error
        if not isinstance(payload, dict):
            raise GA4ProviderError(
                "INVALID_RESPONSE",
                retryable=False,
                message="GA4 returned an invalid response object",
            )
        return cast(dict[str, Any], payload)


def _http_error(status_code: int) -> GA4ProviderError:
    if status_code == 401:
        return GA4ProviderError("AUTH_EXPIRED", retryable=False, message="GA4 authorization failed")
    if status_code == 403:
        return GA4ProviderError(
            "PERMISSION_ERROR", retryable=False, message="GA4 property permission denied"
        )
    if status_code == 429:
        return GA4ProviderError("QUOTA_LIMIT", retryable=True, message="GA4 quota limited")
    if 500 <= status_code <= 599:
        return GA4ProviderError("PROVIDER_ERROR", retryable=True, message="GA4 service failed")
    if status_code == 400:
        return GA4ProviderError(
            "INVALID_QUERY", retryable=False, message="GA4 rejected the report definition"
        )
    return GA4ProviderError(
        "PROVIDER_ERROR",
        retryable=False,
        message=f"GA4 request failed with HTTP {status_code}",
    )


class GA4Client:
    def __init__(self, transport: GA4Transport) -> None:
        self._transport = transport

    @staticmethod
    def property_resource(property_id: str) -> str:
        cleaned = property_id.strip()
        if not _PROPERTY_ID.fullmatch(cleaned):
            raise GA4ProviderError(
                "PROPERTY_ID_INVALID",
                retryable=False,
                message="GA4 property ID must be numeric",
            )
        return f"properties/{cleaned}"

    async def get_metadata(self, *, property_id: str, access_token: str) -> Mapping[str, Any]:
        resource = self.property_resource(property_id)
        return await self._transport.request(
            method="GET",
            url=f"{GA4_DATA_API_ROOT}/{resource}/metadata",
            access_token=_required_token(access_token),
        )

    async def run_report(
        self,
        *,
        property_id: str,
        access_token: str,
        definition: ExtractDefinition,
        period: ExtractPeriod,
    ) -> Mapping[str, Any]:
        resource = self.property_resource(property_id)
        query = definition.query_definition(period)
        body: dict[str, Any] = {
            "dimensions": [{"name": name} for name in definition.dimensions],
            "metrics": [{"name": metric.api_name} for metric in definition.metrics],
            "dateRanges": query["dateRanges"],
            "keepEmptyRows": False,
            "returnPropertyQuota": True,
        }
        return await self._transport.request(
            method="POST",
            url=f"{GA4_DATA_API_ROOT}/{resource}:runReport",
            access_token=_required_token(access_token),
            json_body=body,
        )


def _required_token(access_token: str) -> str:
    cleaned = access_token.strip()
    if not cleaned:
        raise GA4ProviderError(
            "AUTH_EXPIRED", retryable=False, message="GA4 access credential is unavailable"
        )
    return cleaned
