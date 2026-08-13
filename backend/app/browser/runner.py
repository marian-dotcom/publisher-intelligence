import asyncio
from datetime import UTC, datetime
from importlib.metadata import version

from playwright.async_api import Browser, BrowserContext, Page, async_playwright
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.browser.collectors import BrowserObservationCollector
from app.browser.contracts import (
    ArtifactContent,
    BrowserEvidence,
    BrowserTarget,
    CheckpointStatus,
    CollectorResult,
    CollectorStatus,
)
from app.browser.security import BrowserBlockedError, BrowserNetworkGuard, sanitize_url
from app.config.settings import Settings

COLLECTOR_BUNDLE_VERSION = "b1-v1"


class BrowserRunner:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def run(self, target: BrowserTarget) -> BrowserEvidence:
        started_at = datetime.now(UTC)
        try:
            return await asyncio.wait_for(
                self._run(target), timeout=self._settings.browser_overall_timeout_seconds
            )
        except TimeoutError:
            completed_at = datetime.now(UTC)
            return BrowserEvidence(
                status="TIMEOUT",
                started_at=started_at,
                completed_at=completed_at,
                final_url=None,
                http_status=None,
                playwright_version=version("playwright"),
                chromium_version=None,
                environment=self._environment(target),
                limitations=self._limitations(),
                failure_class="OVERALL_TIMEOUT",
                failure_message="Browser checkpoint exceeded its overall time budget",
                collectors=[
                    CollectorResult(
                        collector_type="B1_OBSERVATION",
                        collector_version=COLLECTOR_BUNDLE_VERSION,
                        status="TIMEOUT",
                        started_at=started_at,
                        completed_at=completed_at,
                        summary={},
                        error_code="OVERALL_TIMEOUT",
                        error_message="Browser checkpoint exceeded its overall time budget",
                    )
                ],
            )

    async def _run(self, target: BrowserTarget) -> BrowserEvidence:
        started_at = datetime.now(UTC)
        playwright_version = version("playwright")
        guard = BrowserNetworkGuard(
            canonical_domain=target.canonical_domain,
            allow_private_networks=self._settings.browser_allow_private_networks,
            max_requests=self._settings.browser_max_requests,
        )
        collector = BrowserObservationCollector(target.canonical_domain)
        artifacts: list[ArtifactContent] = []
        actions: list[dict[str, object]] = []
        browser: Browser | None = None
        context: BrowserContext | None = None
        page: Page | None = None
        chromium_version: str | None = None
        final_url: str | None = None
        http_status: int | None = None
        status: CheckpointStatus = "BROWSER_ERROR"
        failure_class: str | None = None
        failure_message: str | None = None
        collector_results: list[CollectorResult] = []

        try:
            safe_target = await guard.validate_initial(target.url)
            actions.append({"type": "navigate", "url": safe_target})
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=True)
                chromium_version = browser.version
                context = await browser.new_context(
                    viewport={"width": target.viewport_width, "height": target.viewport_height},
                    locale=target.locale,
                    timezone_id=target.timezone,
                    accept_downloads=False,
                    service_workers="block",
                )
                await context.route("**/*", guard.route)
                page = await context.new_page()
                collector.attach(page)
                response = await page.goto(
                    target.url,
                    wait_until="domcontentloaded",
                    timeout=self._settings.browser_navigation_timeout_ms,
                )
                final_url = sanitize_url(page.url)
                http_status = response.status if response is not None else None
                artifacts.append(
                    ArtifactContent(
                        artifact_type="SCREENSHOT_VIEWPORT",
                        filename="screenshots/viewport.png",
                        content_type="image/png",
                        retention_class="CORE_MEDIUM",
                        content=await page.screenshot(type="png", full_page=False),
                    )
                )
                actions.append({"type": "screenshot", "kind": "viewport"})
                await page.wait_for_timeout(self._settings.browser_stabilization_ms)
                actions.append(
                    {
                        "type": "bounded_stabilization",
                        "duration_ms": self._settings.browser_stabilization_ms,
                    }
                )
                raw_dom = (await page.content()).encode("utf-8")
                artifacts.append(
                    ArtifactContent(
                        artifact_type="RAW_DOM",
                        filename="dom/raw.html",
                        content_type="text/html; charset=utf-8",
                        retention_class="RAW_MEDIUM",
                        content=raw_dom,
                    )
                )
                scripts: list[str] = []
                script_collector_started = datetime.now(UTC)
                script_inventory_failed = False
                try:
                    scripts = await collector.scripts(page)
                    script_status: CollectorStatus = "OK"
                    script_error_code = None
                    script_error_message = None
                except PlaywrightError:
                    script_inventory_failed = True
                    script_status = "ERROR"
                    script_error_code = "PLAYWRIGHT_ERROR"
                    script_error_message = "Script inventory failed"
                collector_results.append(
                    CollectorResult(
                        collector_type="SCRIPT_INVENTORY",
                        collector_version=COLLECTOR_BUNDLE_VERSION,
                        status=script_status,
                        started_at=script_collector_started,
                        completed_at=datetime.now(UTC),
                        summary={"script_count": len(scripts)},
                        error_code=script_error_code,
                        error_message=script_error_message,
                    )
                )
                artifacts.append(
                    ArtifactContent(
                        artifact_type="SCREENSHOT_FULL_PAGE",
                        filename="screenshots/full-page.png",
                        content_type="image/png",
                        retention_class="CORE_MEDIUM",
                        content=await page.screenshot(type="png", full_page=True),
                    )
                )
                actions.append({"type": "screenshot", "kind": "full_page", "order": "last"})
                if http_status is not None and http_status >= 400:
                    status = "SITE_ERROR"
                elif script_inventory_failed:
                    status = "PARTIAL"
                else:
                    status = "COMPLETE"
                completed_at = datetime.now(UTC)
                collector_results.append(collector.result(completed_at))
                return self._evidence(
                    status=status,
                    started_at=started_at,
                    completed_at=completed_at,
                    target=target,
                    playwright_version=playwright_version,
                    chromium_version=chromium_version,
                    final_url=final_url,
                    http_status=http_status,
                    guard=guard,
                    collector=collector,
                    scripts=scripts,
                    actions=actions,
                    artifacts=artifacts,
                    collectors=collector_results,
                )
        except BrowserBlockedError as error:
            status = "BLOCKED"
            failure_class = error.code
            failure_message = str(error)
        except PlaywrightTimeoutError:
            status = "BLOCKED" if guard.blocked_top_level else "TIMEOUT"
            failure_class = "BLOCKED" if guard.blocked_top_level else "NAVIGATION_TIMEOUT"
            failure_message = (
                "Top-level request was blocked"
                if guard.blocked_top_level
                else "Browser navigation exceeded its time budget"
            )
        except PlaywrightError:
            status = "BLOCKED" if guard.blocked_top_level else "BROWSER_ERROR"
            failure_class = "BLOCKED" if guard.blocked_top_level else "PLAYWRIGHT_ERROR"
            failure_message = (
                "Top-level request was blocked"
                if guard.blocked_top_level
                else "Playwright operation failed"
            )
        finally:
            if context is not None:
                try:
                    await context.close()
                except PlaywrightError:
                    pass
            if browser is not None:
                try:
                    await browser.close()
                except PlaywrightError:
                    pass

        completed_at = datetime.now(UTC)
        collector_results.append(
            CollectorResult(
                collector_type="B1_OBSERVATION",
                collector_version=COLLECTOR_BUNDLE_VERSION,
                status="ERROR"
                if status == "BROWSER_ERROR"
                else "TIMEOUT"
                if status == "TIMEOUT"
                else "OK",
                started_at=collector.started_at,
                completed_at=completed_at,
                summary={
                    "network_host_count": len(collector.network_hosts),
                    "request_failure_count": len(collector.request_failures),
                },
                error_code=failure_class,
                error_message=(failure_message or "")[:1_000] or None,
            )
        )
        return self._evidence(
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            target=target,
            playwright_version=playwright_version,
            chromium_version=chromium_version,
            final_url=sanitize_url(page.url) if page is not None else final_url,
            http_status=http_status,
            guard=guard,
            collector=collector,
            scripts=[],
            actions=actions,
            artifacts=artifacts,
            collectors=collector_results,
            failure_class=failure_class,
            failure_message=(failure_message or "")[:1_000] or None,
        )

    def _evidence(
        self,
        *,
        status: CheckpointStatus,
        started_at: datetime,
        completed_at: datetime,
        target: BrowserTarget,
        playwright_version: str,
        chromium_version: str | None,
        final_url: str | None,
        http_status: int | None,
        guard: BrowserNetworkGuard,
        collector: BrowserObservationCollector,
        scripts: list[str],
        actions: list[dict[str, object]],
        artifacts: list[ArtifactContent],
        collectors: list[CollectorResult],
        failure_class: str | None = None,
        failure_message: str | None = None,
    ) -> BrowserEvidence:
        return BrowserEvidence(
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            final_url=final_url,
            http_status=http_status,
            playwright_version=playwright_version,
            chromium_version=chromium_version,
            environment=self._environment(target),
            redirect_chain=collector.redirect_chain,
            scripts=scripts,
            network_hosts=sorted(collector.network_hosts),
            third_party_hosts=collector.third_party_hosts(),
            request_count=guard.request_count,
            request_failures=collector.request_failures,
            javascript_errors=collector.javascript_errors,
            console_errors=collector.console_errors,
            blocked_requests=guard.blocked_requests,
            actions=actions,
            limitations=self._limitations(),
            artifacts=artifacts,
            collectors=collectors,
            failure_class=failure_class,
            failure_message=failure_message,
        )

    @staticmethod
    def _environment(target: BrowserTarget) -> dict[str, object]:
        return {
            "synthetic": True,
            "headless": True,
            "scenario_code": target.scenario_code,
            "scenario_version": target.scenario_version,
            "viewport": {"width": target.viewport_width, "height": target.viewport_height},
            "locale": target.locale,
            "timezone": target.timezone,
            "cache_mode": "CLEAN",
            "service_workers": "BLOCKED",
            "downloads": "DISABLED",
        }

    @staticmethod
    def _limitations() -> list[str]:
        return [
            "synthetic_observation_not_real_user_truth",
            "application_ssrf_guard_requires_network_egress_enforcement_in_production",
            "no_consent_or_interaction_actions_in_b1",
        ]
