import re
from collections.abc import Mapping
from typing import Any, Protocol, cast
from urllib.parse import quote, urlsplit

import httpx

from app.connectors.core.contracts import ConnectorError, ExtractPeriod
from app.connectors.gsc.definitions import GSCExtractDefinition

GSC_API_ROOT = "https://www.googleapis.com/webmasters/v3"
GSC_INSPECTION_ROOT = "https://searchconsole.googleapis.com/v1"
_DOMAIN_PROPERTY = re.compile(
    r"^sc-domain:(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$",
)


class GSCProviderError(ConnectorError):
    pass


class GSCTransport(Protocol):
    async def request(
        self,
        *,
        method: str,
        url: str,
        access_token: str,
        json_body: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]: ...


class HttpxGSCTransport:
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
            raise GSCProviderError(
                "TRANSPORT_ERROR", retryable=True, message="GSC transport failed"
            ) from error
        if response.status_code >= 400:
            raise _http_error(response.status_code)
        try:
            payload = response.json()
        except ValueError as error:
            raise GSCProviderError(
                "INVALID_RESPONSE", retryable=False, message="GSC returned invalid JSON"
            ) from error
        if not isinstance(payload, dict):
            raise GSCProviderError(
                "INVALID_RESPONSE", retryable=False, message="GSC returned an invalid object"
            )
        return cast(dict[str, Any], payload)


def _http_error(status_code: int) -> GSCProviderError:
    if status_code == 401:
        return GSCProviderError("AUTH_EXPIRED", retryable=False, message="GSC authorization failed")
    if status_code == 403:
        return GSCProviderError(
            "PERMISSION_ERROR", retryable=False, message="GSC property permission denied"
        )
    if status_code == 429:
        return GSCProviderError("QUOTA_LIMIT", retryable=True, message="GSC quota limited")
    if 500 <= status_code <= 599:
        return GSCProviderError("PROVIDER_ERROR", retryable=True, message="GSC service failed")
    if status_code == 400:
        return GSCProviderError(
            "INVALID_QUERY", retryable=False, message="GSC rejected the fixed query"
        )
    return GSCProviderError(
        "PROVIDER_ERROR",
        retryable=False,
        message=f"GSC request failed with HTTP {status_code}",
    )


class GSCClient:
    def __init__(self, transport: GSCTransport) -> None:
        self._transport = transport

    @staticmethod
    def canonical_property(property_id: str) -> str:
        cleaned = property_id.strip()
        if _DOMAIN_PROPERTY.fullmatch(cleaned):
            return cleaned
        parsed = urlsplit(cleaned)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or not cleaned.endswith("/")
            or len(cleaned) > 200
        ):
            raise GSCProviderError(
                "PROPERTY_ID_INVALID",
                retryable=False,
                message="GSC property must be an exact Domain or URL-prefix identifier",
            )
        return cleaned

    @staticmethod
    def property_type(property_id: str) -> str:
        return "DOMAIN" if property_id.startswith("sc-domain:") else "URL_PREFIX"

    async def list_sites(self, *, access_token: str) -> Mapping[str, Any]:
        return await self._transport.request(
            method="GET",
            url=f"{GSC_API_ROOT}/sites",
            access_token=_required_token(access_token),
        )

    async def run_query(
        self,
        *,
        property_id: str,
        access_token: str,
        definition: GSCExtractDefinition,
        period: ExtractPeriod,
    ) -> Mapping[str, Any]:
        property_id = self.canonical_property(property_id)
        query = definition.query_definition(period)
        rows: list[Any] = []
        aggregation: Any = None
        metadata: Any = None
        pages_requested = 0
        while len(rows) < definition.max_rows:
            body = {
                "startDate": query["startDate"],
                "endDate": query["endDate"],
                "dimensions": query["dimensions"],
                "type": query["type"],
                "dataState": query["dataState"],
                "aggregationType": query["aggregationType"],
                "rowLimit": definition.row_limit,
                "startRow": len(rows),
            }
            page = await self._transport.request(
                method="POST",
                url=(f"{GSC_API_ROOT}/sites/{quote(property_id, safe='')}/searchAnalytics/query"),
                access_token=_required_token(access_token),
                json_body=body,
            )
            pages_requested += 1
            page_rows = page.get("rows", [])
            if not isinstance(page_rows, list):
                raise GSCProviderError(
                    "INVALID_RESPONSE", retryable=False, message="GSC rows must be a list"
                )
            page_aggregation = page.get("responseAggregationType")
            if page_aggregation is not None:
                if aggregation is None:
                    aggregation = page_aggregation
                elif page_aggregation != aggregation:
                    raise GSCProviderError(
                        "INVALID_RESPONSE",
                        retryable=False,
                        message="GSC pagination aggregation changed",
                    )
            page_metadata = page.get("metadata")
            if metadata is None:
                metadata = page_metadata
            elif page_metadata is not None and page_metadata != metadata:
                raise GSCProviderError(
                    "INVALID_RESPONSE", retryable=False, message="GSC pagination metadata changed"
                )
            rows.extend(page_rows)
            if len(page_rows) < definition.row_limit:
                break
        cap_reached = len(rows) >= definition.max_rows
        return {
            "rows": rows[: definition.max_rows],
            "responseAggregationType": aggregation,
            "metadata": metadata or {},
            "pagination": {
                "pagesRequested": pages_requested,
                "returnedRows": min(len(rows), definition.max_rows),
                "rowLimit": definition.row_limit,
                "maxRows": definition.max_rows,
                "capReached": cap_reached,
            },
        }

    async def inspect_url(
        self,
        *,
        property_id: str,
        inspection_url: str,
        access_token: str,
    ) -> Mapping[str, Any]:
        property_id = self.canonical_property(property_id)
        self.validate_inspection_url(property_id, inspection_url)
        return await self._transport.request(
            method="POST",
            url=f"{GSC_INSPECTION_ROOT}/urlInspection/index:inspect",
            access_token=_required_token(access_token),
            json_body={
                "inspectionUrl": inspection_url,
                "siteUrl": property_id,
                "languageCode": "en-US",
            },
        )

    @staticmethod
    def validate_inspection_url(property_id: str, inspection_url: str) -> None:
        parsed = urlsplit(inspection_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or len(inspection_url) > 2048
        ):
            raise GSCProviderError(
                "INSPECTION_URL_INVALID", retryable=False, message="Inspection URL is invalid"
            )
        if property_id.startswith("sc-domain:"):
            domain = property_id.removeprefix("sc-domain:").lower()
            hostname = parsed.hostname.lower()
            contained = hostname == domain or hostname.endswith(f".{domain}")
        else:
            contained = inspection_url.startswith(property_id)
        if not contained:
            raise GSCProviderError(
                "INSPECTION_URL_OUTSIDE_PROPERTY",
                retryable=False,
                message="Inspection URL is outside the GSC property",
            )


def _required_token(access_token: str) -> str:
    cleaned = access_token.strip()
    if not cleaned:
        raise GSCProviderError(
            "AUTH_EXPIRED", retryable=False, message="GSC access credential is unavailable"
        )
    return cleaned
