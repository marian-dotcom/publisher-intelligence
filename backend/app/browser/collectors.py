from datetime import UTC, datetime
from typing import Any, cast
from urllib.parse import urlsplit

from playwright.async_api import ConsoleMessage, Error, Page, Request

from app.browser.contracts import CollectorResult, JavaScriptError, RequestFailure
from app.browser.security import canonical_hostname, sanitize_url

COLLECTOR_VERSION = "b1-v1"


def _bounded(value: str, limit: int = 1_000) -> str:
    return value[:limit]


class BrowserObservationCollector:
    def __init__(self, canonical_domain: str) -> None:
        self._canonical_domain = canonical_hostname(canonical_domain)
        self.started_at = datetime.now(UTC)
        self.network_hosts: set[str] = set()
        self.request_failures: list[RequestFailure] = []
        self.javascript_errors: list[JavaScriptError] = []
        self.console_errors: list[JavaScriptError] = []
        self.redirect_chain: list[str] = []

    def attach(self, page: Page) -> None:
        page.on("request", self._on_request)
        page.on("requestfailed", self._on_request_failed)
        page.on("pageerror", self._on_page_error)
        page.on("console", self._on_console)
        page.on("framenavigated", self._on_frame_navigated)

    def _on_request(self, request: Request) -> None:
        hostname = urlsplit(request.url).hostname
        if hostname:
            try:
                self.network_hosts.add(canonical_hostname(hostname))
            except ValueError:
                return

    def _on_request_failed(self, request: Request) -> None:
        self.request_failures.append(
            RequestFailure(
                url=sanitize_url(request.url),
                resource_type=request.resource_type,
                error_text=_bounded(request.failure or "UNKNOWN_NETWORK_FAILURE"),
            )
        )

    def _on_page_error(self, error: Error) -> None:
        self.javascript_errors.append(JavaScriptError(message=_bounded(str(error))))

    def _on_console(self, message: ConsoleMessage) -> None:
        if message.type != "error":
            return
        location = message.location
        source = sanitize_url(str(location.get("url", ""))) if location.get("url") else None
        self.console_errors.append(
            JavaScriptError(
                message=_bounded(message.text),
                source=source,
                line=cast(int | None, location.get("lineNumber")),
                column=cast(int | None, location.get("columnNumber")),
            )
        )

    def _on_frame_navigated(self, frame: Any) -> None:
        if frame == frame.page.main_frame:
            safe_url = sanitize_url(frame.url)
            if not self.redirect_chain or self.redirect_chain[-1] != safe_url:
                self.redirect_chain.append(safe_url)

    async def scripts(self, page: Page) -> list[str]:
        raw = await page.eval_on_selector_all(
            "script[src]",
            "nodes => nodes.map(node => node.src).filter(Boolean)",
        )
        return sorted({sanitize_url(str(item)) for item in cast(list[object], raw)})

    def third_party_hosts(self) -> list[str]:
        result = []
        for host in self.network_hosts:
            if host != self._canonical_domain and not host.endswith(f".{self._canonical_domain}"):
                result.append(host)
        return sorted(result)

    def result(self, completed_at: datetime) -> CollectorResult:
        return CollectorResult(
            collector_type="B1_OBSERVATION",
            collector_version=COLLECTOR_VERSION,
            status="OK",
            started_at=self.started_at,
            completed_at=completed_at,
            summary={
                "network_host_count": len(self.network_hosts),
                "request_failure_count": len(self.request_failures),
                "javascript_error_count": len(self.javascript_errors),
                "console_error_count": len(self.console_errors),
            },
        )
