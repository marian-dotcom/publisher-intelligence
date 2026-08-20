import asyncio
import re
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Protocol, cast

import httpx

from app.connectors.core.contracts import ConnectorError
from app.connectors.gam.definitions import (
    GAM_API_ROOT,
    GAM_MAX_RESULT_ROWS,
    GAM_RESULT_PAGE_SIZE,
)

_NETWORK_CODE = re.compile(r"^[1-9][0-9]{0,19}$")
_REPORT_RESOURCE = re.compile(r"^networks/([1-9][0-9]{0,19})/reports/([1-9][0-9]{0,19})$")
_RESULT_RESOURCE = re.compile(
    r"^networks/([1-9][0-9]{0,19})/reports/([1-9][0-9]{0,19})/results/([^/]{1,200})$"
)
_OPERATION_RESOURCE = re.compile(
    r"^networks/([1-9][0-9]{0,19})/operations/reports/"
    r"[1-9][0-9]{0,19}/runs/[^/]{1,200}$"
)


class GAMProviderError(ConnectorError):
    pass


class GAMTransport(Protocol):
    async def request(
        self,
        *,
        method: str,
        url: str,
        access_token: str,
        query: Mapping[str, str | int] | None = None,
    ) -> Mapping[str, Any]: ...


class HttpxGAMTransport:
    def __init__(self, *, timeout_seconds: float = 30.0) -> None:
        self._timeout = httpx.Timeout(timeout_seconds, connect=min(10.0, timeout_seconds))

    async def request(
        self,
        *,
        method: str,
        url: str,
        access_token: str,
        query: Mapping[str, str | int] | None = None,
    ) -> Mapping[str, Any]:
        headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.request(method, url, headers=headers, params=query)
        except httpx.RequestError as error:
            raise GAMProviderError(
                "TRANSPORT_ERROR", retryable=True, message="GAM transport failed"
            ) from error
        if response.status_code >= 400:
            raise _http_error(response.status_code)
        try:
            payload = response.json()
        except ValueError as error:
            raise GAMProviderError(
                "INVALID_RESPONSE", retryable=False, message="GAM returned invalid JSON"
            ) from error
        if not isinstance(payload, dict):
            raise GAMProviderError(
                "INVALID_RESPONSE", retryable=False, message="GAM returned an invalid object"
            )
        return cast(dict[str, Any], payload)


def _http_error(status_code: int) -> GAMProviderError:
    if status_code == 401:
        return GAMProviderError("AUTH_EXPIRED", retryable=False, message="GAM authorization failed")
    if status_code == 403:
        return GAMProviderError(
            "PERMISSION_ERROR", retryable=False, message="GAM network permission denied"
        )
    if status_code == 404:
        return GAMProviderError(
            "REPORT_NOT_FOUND", retryable=False, message="GAM report resource is unavailable"
        )
    if status_code == 429:
        return GAMProviderError("QUOTA_LIMIT", retryable=True, message="GAM quota limited")
    if 500 <= status_code <= 599:
        return GAMProviderError("PROVIDER_ERROR", retryable=True, message="GAM service failed")
    if status_code == 400:
        return GAMProviderError(
            "INVALID_REPORT", retryable=False, message="GAM rejected the validated report"
        )
    return GAMProviderError(
        "PROVIDER_ERROR",
        retryable=False,
        message=f"GAM request failed with HTTP {status_code}",
    )


class GAMClient:
    def __init__(
        self,
        transport: GAMTransport,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        initial_poll_seconds: float = 5.0,
        max_polls: int = 12,
    ) -> None:
        if initial_poll_seconds < 0 or max_polls < 1 or max_polls > 30:
            raise ValueError("invalid GAM polling bounds")
        self._transport = transport
        self._sleep = sleep
        self._initial_poll_seconds = initial_poll_seconds
        self._max_polls = max_polls

    @staticmethod
    def canonical_network_code(network_code: str) -> str:
        cleaned = network_code.strip()
        if not _NETWORK_CODE.fullmatch(cleaned):
            raise GAMProviderError(
                "NETWORK_ID_INVALID",
                retryable=False,
                message="GAM network code must be a numeric identifier",
            )
        return cleaned

    @staticmethod
    def canonical_report_resource(network_code: str, report_resource: str) -> str:
        network_code = GAMClient.canonical_network_code(network_code)
        cleaned = report_resource.strip()
        match = _REPORT_RESOURCE.fullmatch(cleaned)
        if match is None or match.group(1) != network_code:
            raise GAMProviderError(
                "REPORT_BINDING_INVALID",
                retryable=False,
                message="GAM report resource must belong to the configured network",
            )
        return cleaned

    async def list_networks(self, *, access_token: str) -> Mapping[str, Any]:
        return await self._transport.request(
            method="GET",
            url=f"{GAM_API_ROOT}/networks",
            access_token=_required_token(access_token),
            query={"pageSize": 1000},
        )

    async def get_network(self, *, network_code: str, access_token: str) -> Mapping[str, Any]:
        code = self.canonical_network_code(network_code)
        return await self._transport.request(
            method="GET",
            url=f"{GAM_API_ROOT}/networks/{code}",
            access_token=_required_token(access_token),
        )

    async def get_report(
        self, *, network_code: str, report_resource: str, access_token: str
    ) -> Mapping[str, Any]:
        resource = self.canonical_report_resource(network_code, report_resource)
        return await self._transport.request(
            method="GET",
            url=f"{GAM_API_ROOT}/{resource}",
            access_token=_required_token(access_token),
        )

    async def run_report(
        self, *, network_code: str, report_resource: str, access_token: str
    ) -> Mapping[str, Any]:
        network_code = self.canonical_network_code(network_code)
        resource = self.canonical_report_resource(network_code, report_resource)
        token = _required_token(access_token)
        operation = await self._transport.request(
            method="POST",
            url=f"{GAM_API_ROOT}/{resource}:run",
            access_token=token,
        )
        operation_name = _required_resource(
            operation.get("name"), _OPERATION_RESOURCE, network_code, "operation"
        )
        poll_count = 0
        current = operation
        while current.get("done") is not True:
            if current.get("done") not in {None, False}:
                raise GAMProviderError(
                    "INVALID_RESPONSE", retryable=False, message="GAM operation state is invalid"
                )
            if poll_count >= self._max_polls:
                raise GAMProviderError(
                    "REPORT_TIMEOUT", retryable=True, message="GAM report operation timed out"
                )
            delay = min(60.0, self._initial_poll_seconds * (2**poll_count))
            if delay:
                await self._sleep(delay)
            current = await self._transport.request(
                method="GET",
                url=f"{GAM_API_ROOT}/{operation_name}",
                access_token=token,
            )
            if current.get("name") != operation_name:
                raise GAMProviderError(
                    "INVALID_RESPONSE", retryable=False, message="GAM operation identity changed"
                )
            poll_count += 1
        if "error" in current:
            raise GAMProviderError(
                "REPORT_FAILED", retryable=True, message="GAM report operation failed"
            )
        response = _mapping(current.get("response"), "operation response")
        report_result = _required_resource(
            response.get("reportResult"), _RESULT_RESOURCE, network_code, "report result"
        )
        expected_prefix = f"{resource}/results/"
        if not report_result.startswith(expected_prefix):
            raise GAMProviderError(
                "INVALID_RESPONSE", retryable=False, message="GAM report result changed report"
            )

        rows: list[Any] = []
        pages = 0
        next_token: str | None = None
        seen_tokens: set[str] = set()
        first_metadata: dict[str, Any] = {}
        total_rows: int | None = None
        while True:
            query: dict[str, str | int] = {"pageSize": GAM_RESULT_PAGE_SIZE}
            if next_token is not None:
                query["pageToken"] = next_token
            page = await self._transport.request(
                method="GET",
                url=f"{GAM_API_ROOT}/{report_result}:fetchRows",
                access_token=token,
                query=query,
            )
            pages += 1
            page_rows = page.get("rows", [])
            if not isinstance(page_rows, list):
                raise GAMProviderError(
                    "INVALID_RESPONSE", retryable=False, message="GAM result rows must be a list"
                )
            if len(page_rows) > GAM_RESULT_PAGE_SIZE:
                raise GAMProviderError(
                    "INVALID_RESPONSE",
                    retryable=False,
                    message="GAM result page exceeded its bound",
                )
            if pages == 1:
                total_rows = _nonnegative_int(page.get("totalRowCount"), "totalRowCount")
                if total_rows > GAM_MAX_RESULT_ROWS:
                    raise GAMProviderError(
                        "RESULT_TOO_LARGE",
                        retryable=False,
                        message="GAM result exceeds the fixed row bound",
                    )
                first_metadata = {
                    "runTime": page.get("runTime"),
                    "dateRanges": page.get("dateRanges"),
                    "comparisonDateRanges": page.get("comparisonDateRanges", []),
                }
            elif any(
                field in page for field in ("totalRowCount", "dateRanges", "comparisonDateRanges")
            ):
                raise GAMProviderError(
                    "INVALID_RESPONSE",
                    retryable=False,
                    message="GAM pagination repeated first-page metadata",
                )
            rows.extend(page_rows)
            if len(rows) > GAM_MAX_RESULT_ROWS:
                raise GAMProviderError(
                    "RESULT_TOO_LARGE", retryable=False, message="GAM result exceeded its bound"
                )
            raw_next = page.get("nextPageToken")
            if raw_next is None:
                break
            if not isinstance(raw_next, str) or not raw_next or len(raw_next) > 2048:
                raise GAMProviderError(
                    "INVALID_RESPONSE", retryable=False, message="GAM page token is invalid"
                )
            if raw_next in seen_tokens:
                raise GAMProviderError(
                    "INVALID_RESPONSE", retryable=False, message="GAM page token repeated"
                )
            seen_tokens.add(raw_next)
            next_token = raw_next
        if total_rows is None or len(rows) != total_rows:
            raise GAMProviderError(
                "PARTIAL_RESULT", retryable=True, message="GAM result pagination was incomplete"
            )
        return {
            "rows": rows,
            **first_metadata,
            "reportResource": resource,
            "operationName": operation_name,
            "reportResult": report_result,
            "lifecycle": [
                "API_REQUESTED",
                "REPORT_RUNNING",
                "RESULT_FETCHING",
                "NORMALIZING",
            ],
            "pagination": {
                "pagesFetched": pages,
                "pageSize": GAM_RESULT_PAGE_SIZE,
                "totalRowCount": total_rows,
                "allPagesFetched": True,
            },
        }


def _required_token(access_token: str) -> str:
    cleaned = access_token.strip()
    if not cleaned:
        raise GAMProviderError(
            "AUTH_EXPIRED", retryable=False, message="GAM access credential is unavailable"
        )
    return cleaned


def _mapping(raw: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(raw, dict):
        raise GAMProviderError(
            "INVALID_RESPONSE", retryable=False, message=f"GAM {field} must be an object"
        )
    return cast(dict[str, Any], raw)


def _required_resource(raw: Any, pattern: re.Pattern[str], network_code: str, field: str) -> str:
    if not isinstance(raw, str) or len(raw) > 500:
        raise GAMProviderError(
            "INVALID_RESPONSE", retryable=False, message=f"GAM {field} is invalid"
        )
    match = pattern.fullmatch(raw)
    if match is None or match.group(1) != network_code:
        raise GAMProviderError(
            "INVALID_RESPONSE", retryable=False, message=f"GAM {field} changed network"
        )
    return raw


def _nonnegative_int(raw: Any, field: str) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
        raise GAMProviderError(
            "INVALID_RESPONSE", retryable=False, message=f"GAM {field} is invalid"
        )
    return cast(int, raw)
