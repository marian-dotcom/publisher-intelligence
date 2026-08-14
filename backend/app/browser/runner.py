import asyncio
from datetime import UTC, datetime
from importlib.metadata import version

from playwright.async_api import Browser, BrowserContext, Page, async_playwright
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.browser.cmp import (
    CMPCollection,
    CMPCollector,
    summarize_consent_dependencies,
)
from app.browser.collectors import BrowserObservationCollector
from app.browser.contracts import (
    ArtifactContent,
    BrowserEvidence,
    BrowserTarget,
    CheckpointStatus,
    CollectorResult,
    CollectorStatus,
    ConsentPhaseDependencyObservation,
    NormalizedEntityObservation,
)
from app.browser.gpt import GPTCollection, GPTLifecycleCollector
from app.browser.interactions import execute_interaction_steps
from app.browser.normalization import (
    normalize_dom,
    normalize_javascript_errors,
    normalize_network,
    normalize_scripts,
    normalized_dom_artifact,
    state_hash,
)
from app.browser.performance import PerformanceCollection, SyntheticPerformanceCollector
from app.browser.prebid import PrebidCollection, PrebidCollector
from app.browser.security import BrowserBlockedError, BrowserNetworkGuard, sanitize_url
from app.browser.video import VideoCollection, VideoPlayerCollector
from app.config.settings import Settings

COLLECTOR_BUNDLE_VERSION = "b8-v1"


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
                        collector_type="BROWSER_OBSERVATION",
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
        cmp_collector = CMPCollector(self._settings)
        cmp_collection: CMPCollection | None = None
        gpt_collector = GPTLifecycleCollector()
        gpt_collection: GPTCollection | None = None
        prebid_collector = PrebidCollector()
        prebid_collection: PrebidCollection | None = None
        video_collector = VideoPlayerCollector()
        video_collection: VideoCollection | None = None
        performance_collector = SyntheticPerformanceCollector()
        performance_collection: PerformanceCollection | None = None
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
                    device_scale_factor=target.device_scale_factor,
                    user_agent=target.user_agent,
                    is_mobile=target.is_mobile,
                    has_touch=target.has_touch,
                    locale=target.locale,
                    timezone_id=target.timezone,
                    accept_downloads=False,
                    service_workers="block",
                )
                await context.route("**/*", guard.route)
                page = await context.new_page()
                collector.attach(page)
                await cmp_collector.attach(page)
                await gpt_collector.attach(page)
                await prebid_collector.attach(page)
                await video_collector.attach(page)
                await performance_collector.attach(page)
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
                cmp_started = datetime.now(UTC)
                try:
                    cmp_pre = await cmp_collector.observe_pre(page, target, collector.elapsed_ms)
                    if cmp_pre.cmp_detected:
                        artifacts.append(
                            ArtifactContent(
                                artifact_type="SCREENSHOT_VIEWPORT_PRECONSENT",
                                filename="screenshots/viewport-preconsent.png",
                                content_type="image/png",
                                retention_class="CORE_MEDIUM",
                                content=await page.screenshot(type="png", full_page=False),
                            )
                        )
                        actions.append({"type": "screenshot", "kind": "viewport_preconsent"})
                    cmp_collection = await cmp_collector.act_and_collect(
                        page,
                        target,
                        cmp_pre,
                        collector.elapsed_ms,
                    )
                    actions.append(
                        {
                            "type": "consent_action",
                            "path": target.consent_path,
                            "status": cmp_collection.observation.consent_action_status,
                            "started_at_ms": (cmp_collection.observation.action_started_at_ms),
                            "completed_at_ms": (cmp_collection.observation.action_completed_at_ms),
                        }
                    )
                    if cmp_collection.capture_post:
                        artifacts.append(
                            ArtifactContent(
                                artifact_type="SCREENSHOT_VIEWPORT_POSTCONSENT",
                                filename="screenshots/viewport-postconsent.png",
                                content_type="image/png",
                                retention_class="CORE_MEDIUM",
                                content=await page.screenshot(type="png", full_page=False),
                            )
                        )
                        actions.append({"type": "screenshot", "kind": "viewport_postconsent"})
                except PlaywrightError:
                    cmp_collection = cmp_collector.failure(target, cmp_started)
                collector_results.append(cmp_collection.result)
                interaction_started = datetime.now(UTC)
                interaction = await execute_interaction_steps(page, target.interaction_steps)
                actions.extend(interaction.actions)
                collector_results.append(
                    CollectorResult(
                        collector_type="INTERACTION_PROFILE",
                        collector_version=COLLECTOR_BUNDLE_VERSION,
                        status=(
                            "ERROR"
                            if interaction.failed
                            else "OK"
                            if target.interaction_steps
                            else "NOT_PRESENT"
                        ),
                        started_at=interaction_started,
                        completed_at=datetime.now(UTC),
                        summary={
                            "step_count": len(target.interaction_steps),
                            "completed_step_count": len(
                                [item for item in interaction.actions if item["status"] == "OK"]
                            ),
                        },
                        error_code=interaction.error_code,
                        error_message=(
                            "Deterministic interaction failed" if interaction.failed else None
                        ),
                    )
                )
                gpt_collection = await gpt_collector.collect(page, target.expected_gpt_slots)
                collector_results.append(gpt_collection.result)
                prebid_collection = await prebid_collector.collect(
                    page,
                    collector.network_observations,
                    collector.elapsed_ms(),
                )
                collector_results.append(prebid_collection.result)
                video_collection = await video_collector.collect(
                    page,
                    collector.network_observations,
                )
                collector_results.append(video_collection.result)
                performance_collection = await performance_collector.collect(page)
                collector_results.append(performance_collection.result)
                consent_phase_dependencies = summarize_consent_dependencies(
                    collector.network_observations,
                    action_boundary_ms=cmp_collection.action_boundary_ms,
                    consent_path=target.consent_path,
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
                normalization_started = datetime.now(UTC)
                normalization_failed = False
                normalized_dom: dict[str, object] = {}
                try:
                    normalized_dom = normalize_dom(raw_dom.decode("utf-8"))
                    artifacts.append(
                        ArtifactContent(
                            artifact_type="NORMALIZED_DOM",
                            filename="dom/normalized.json",
                            content_type="application/json",
                            retention_class="CORE_LONG",
                            content=normalized_dom_artifact(normalized_dom),
                        )
                    )
                    dom_status: CollectorStatus = "OK"
                    dom_error_code = None
                    dom_error_message = None
                except (UnicodeError, ValueError):
                    normalization_failed = True
                    dom_status = "ERROR"
                    dom_error_code = "NORMALIZATION_ERROR"
                    dom_error_message = "Structural DOM normalization failed"
                collector_results.append(
                    CollectorResult(
                        collector_type="DOM_NORMALIZATION",
                        collector_version=COLLECTOR_BUNDLE_VERSION,
                        status=dom_status,
                        started_at=normalization_started,
                        completed_at=datetime.now(UTC),
                        summary={
                            "normalizer_version": normalized_dom.get("normalizer_version"),
                            "node_count": normalized_dom.get("node_count", 0),
                        },
                        error_code=dom_error_code,
                        error_message=dom_error_message,
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
                dependency_started = datetime.now(UTC)
                normalized_scripts = normalize_scripts(scripts)
                normalized_network = normalize_network(collector.network_observations)
                normalized_errors = normalize_javascript_errors(
                    [*collector.javascript_errors, *collector.console_errors]
                )
                normalized_dom_summary = {
                    key: value for key, value in normalized_dom.items() if key != "structure"
                }
                normalized_state: dict[str, object] = {
                    "schema": "browser-normalized-state/v1",
                    "dom": normalized_dom_summary,
                    "scripts": normalized_scripts,
                    "network": normalized_network,
                    "javascript_errors": normalized_errors,
                    "template_expectation": {
                        "fingerprint_version": target.template_fingerprint_version,
                        "expected_features": target.template_expected_features,
                    },
                }
                normalized_entities = self._normalized_entities(
                    normalized_scripts, normalized_network
                )
                collector_results.append(
                    CollectorResult(
                        collector_type="B3_NORMALIZED_EVIDENCE",
                        collector_version=COLLECTOR_BUNDLE_VERSION,
                        status="OK" if not normalization_failed else "ERROR",
                        started_at=dependency_started,
                        completed_at=datetime.now(UTC),
                        summary={
                            "script_identity_count": len(normalized_scripts.get("identities", [])),
                            "network_dependency_count": len(
                                normalized_network.get("dependencies", [])
                            ),
                            "javascript_error_fingerprint_count": len(
                                normalized_errors.get("errors", [])
                            ),
                        },
                        error_code=("DOM_NORMALIZATION_ERROR" if normalization_failed else None),
                        error_message=(
                            "One normalized evidence component failed"
                            if normalization_failed
                            else None
                        ),
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
                elif (
                    script_inventory_failed
                    or interaction.failed
                    or normalization_failed
                    or gpt_collection.result.status == "ERROR"
                    or prebid_collection.result.status == "ERROR"
                    or video_collection.result.status == "ERROR"
                    or performance_collection.result.status == "ERROR"
                    or cmp_collection.required_action_failed
                ):
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
                    normalized_state=normalized_state,
                    normalized_entities=normalized_entities,
                    gpt_collection=gpt_collection,
                    prebid_collection=prebid_collection,
                    video_collection=video_collection,
                    performance_collection=performance_collection,
                    cmp_collection=cmp_collection,
                    consent_phase_dependencies=consent_phase_dependencies,
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
                collector_type="BROWSER_OBSERVATION",
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
            gpt_collection=gpt_collection,
            prebid_collection=prebid_collection,
            video_collection=video_collection,
            performance_collection=performance_collection,
            cmp_collection=cmp_collection,
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
        normalized_state: dict[str, object] | None = None,
        normalized_entities: list[NormalizedEntityObservation] | None = None,
        gpt_collection: GPTCollection | None = None,
        prebid_collection: PrebidCollection | None = None,
        video_collection: VideoCollection | None = None,
        performance_collection: PerformanceCollection | None = None,
        cmp_collection: CMPCollection | None = None,
        consent_phase_dependencies: list[ConsentPhaseDependencyObservation] | None = None,
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
            normalized_state=normalized_state or {},
            normalized_entities=normalized_entities or [],
            gpt_present=gpt_collection.present if gpt_collection is not None else False,
            gpt_version=gpt_collection.version if gpt_collection is not None else None,
            gpt_slots=gpt_collection.slots if gpt_collection is not None else [],
            cmp_observation=(cmp_collection.observation if cmp_collection is not None else None),
            consent_phase_dependencies=consent_phase_dependencies or [],
            prebid_present=(prebid_collection.present if prebid_collection is not None else False),
            prebid_version=(prebid_collection.version if prebid_collection is not None else None),
            prebid_server_side_configured=(
                prebid_collection.server_side_configured if prebid_collection is not None else False
            ),
            prebid_targeting_keys=(
                prebid_collection.targeting_keys if prebid_collection is not None else []
            ),
            prebid_limitations=(
                prebid_collection.limitations if prebid_collection is not None else []
            ),
            prebid_auctions=(prebid_collection.auctions if prebid_collection is not None else []),
            prebid_bidders=(prebid_collection.bidders if prebid_collection is not None else []),
            video_present=(video_collection.present if video_collection is not None else False),
            video_limitations=(
                video_collection.limitations if video_collection is not None else []
            ),
            video_players=(video_collection.players if video_collection is not None else []),
            synthetic_performance=(
                performance_collection.observation if performance_collection is not None else None
            ),
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
            "device_scale_factor": target.device_scale_factor,
            "user_agent": target.user_agent,
            "is_mobile": target.is_mobile,
            "has_touch": target.has_touch,
            "locale": target.locale,
            "timezone": target.timezone,
            "cache_mode": "CLEAN",
            "service_workers": "BLOCKED",
            "downloads": "DISABLED",
            "interaction_profile": (
                {
                    "id": str(target.interaction_profile_id),
                    "code": target.interaction_profile_code,
                    "version": target.interaction_profile_version,
                }
                if target.interaction_profile_id is not None
                else None
            ),
        }

    @staticmethod
    def _limitations() -> list[str]:
        return [
            "synthetic_observation_not_real_user_truth",
            "application_ssrf_guard_requires_network_egress_enforcement_in_production",
            "no_consent_action_in_b2",
        ]

    @staticmethod
    def _normalized_entities(
        scripts: dict[str, object], network: dict[str, object]
    ) -> list[NormalizedEntityObservation]:
        result: list[NormalizedEntityObservation] = []
        for entity_kind, values in (
            ("SCRIPT_DEPENDENCY", scripts.get("identities", [])),
            ("NETWORK_DEPENDENCY", network.get("dependencies", [])),
        ):
            if not isinstance(values, list):
                continue
            for value in values:
                if not isinstance(value, dict) or not isinstance(value.get("stable_key"), str):
                    continue
                state = {str(key): item for key, item in value.items()}
                result.append(
                    NormalizedEntityObservation(
                        entity_kind=entity_kind,
                        stable_key=str(value["stable_key"]),
                        state_hash=state_hash(state),
                        state=state,
                    )
                )
        return result
