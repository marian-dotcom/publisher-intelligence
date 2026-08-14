import logging
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.browser.interactions import parse_interaction_steps
from app.browser.models import (
    BrowserScenario,
    CheckpointRun,
    CheckpointWindow,
    InteractionProfile,
    MonitoredUrl,
    Publisher,
    Site,
    Template,
)
from app.browser.security import BrowserNetworkGuard, canonical_hostname
from app.config.settings import Settings
from app.db.models import Tenant
from app.jobs.queue import JobQueue

logger = logging.getLogger(__name__)

CORE_SCENARIO_CODE = "core_desktop_v1"
B2_DESKTOP_SCENARIO_CODE = "core_desktop_v2"
B2_MOBILE_SCENARIO_CODE = "core_mobile_v1"
B2_INTERACTION_PROFILE_CODE = "core_scroll_v1"
B5_REJECT_SCENARIO_CODE = "consent_reject_mobile_v1"
B2_INTERACTION_STEPS: list[dict[str, Any]] = [
    {"type": "wait", "duration_ms": 500},
    {"type": "scroll", "percent": 25},
    {"type": "wait", "duration_ms": 250},
    {"type": "scroll", "percent": 50},
    {"type": "wait", "duration_ms": 250},
    {"type": "scroll", "percent": 75},
    {"type": "inspect", "marker": "sticky_and_video"},
]

DESKTOP_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)
MOBILE_USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 15; Pixel 7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36"
)


@dataclass(frozen=True, slots=True)
class EnqueuedCheckpoint:
    tenant_id: uuid.UUID
    checkpoint_run_id: uuid.UUID
    job_id: uuid.UUID


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not normalized:
        raise ValueError("name must contain at least one letter or digit")
    return normalized[:100]


class CheckpointService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        queue: JobQueue,
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._queue = queue
        self._settings = settings

    async def register_and_enqueue(
        self,
        *,
        tenant_slug: str,
        tenant_name: str,
        publisher_name: str,
        site_name: str,
        url: str,
    ) -> EnqueuedCheckpoint:
        hostname = urlsplit(url).hostname
        if hostname is None:
            raise ValueError("URL hostname is required")
        canonical_domain = canonical_hostname(hostname)
        canonical_scheme = urlsplit(url).scheme.lower()
        guard = BrowserNetworkGuard(
            canonical_domain=canonical_domain,
            allow_private_networks=self._settings.browser_allow_private_networks,
            max_requests=self._settings.browser_max_requests,
        )
        await guard.validate_initial(url)
        now = datetime.now(UTC)

        async with self._session_factory() as session, session.begin():
            tenant = await self._tenant(session, tenant_slug, tenant_name)
            publisher = await self._publisher(session, tenant.id, publisher_name)
            site = await self._site(
                session,
                tenant.id,
                publisher.id,
                site_name,
                canonical_domain,
                canonical_scheme,
            )
            template = await self._template(session, tenant.id, site.id)
            monitored_url = await self._monitored_url(session, tenant.id, site.id, template.id, url)
            scenario = await self._scenario(session, tenant.id, site.id)
            await self._ensure_b2_configuration(session, tenant.id, site.id, site.timezone, now)
            window = CheckpointWindow(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                site_id=site.id,
                scheduled_for=now,
                window_start=now,
                window_end=now + timedelta(minutes=5),
                status="SCHEDULED",
            )
            run = CheckpointRun(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                site_id=site.id,
                checkpoint_window_id=window.id,
                monitored_url_id=monitored_url.id,
                template_id=template.id,
                scenario_id=scenario.id,
                scheduled_for=now,
                status="PENDING",
                attempt_count=0,
                collector_bundle_version="b7-v1",
                environment={},
                limitations=[],
                manifest={},
            )
            session.add(window)
            await session.flush()
            session.add(run)
            tenant_id = tenant.id
            run_id = run.id

        job_id = await self._queue.enqueue(
            job_type="BROWSER_CHECKPOINT",
            tenant_id=tenant_id,
            payload={"checkpoint_run_id": str(run_id)},
            idempotency_key=f"browser-checkpoint:{run_id}",
            max_attempts=2,
        )
        return EnqueuedCheckpoint(
            tenant_id=tenant_id,
            checkpoint_run_id=run_id,
            job_id=job_id,
        )

    async def _tenant(self, session: AsyncSession, slug: str, name: str) -> Tenant:
        normalized_slug = _slug(slug)
        tenant = await session.scalar(select(Tenant).where(Tenant.slug == normalized_slug))
        if tenant is None:
            tenant = Tenant(id=uuid.uuid4(), slug=normalized_slug, name=name.strip())
            session.add(tenant)
            await session.flush()
        return tenant

    async def _publisher(self, session: AsyncSession, tenant_id: uuid.UUID, name: str) -> Publisher:
        slug = _slug(name)
        publisher = await session.scalar(
            select(Publisher).where(Publisher.tenant_id == tenant_id, Publisher.slug == slug)
        )
        if publisher is None:
            publisher = Publisher(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                name=name.strip(),
                slug=slug,
                default_timezone=self._settings.browser_timezone,
                status="ACTIVE",
            )
            session.add(publisher)
            await session.flush()
        return publisher

    async def _site(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        publisher_id: uuid.UUID,
        name: str,
        canonical_domain: str,
        canonical_scheme: str,
    ) -> Site:
        site = await session.scalar(
            select(Site).where(
                Site.tenant_id == tenant_id,
                Site.canonical_domain == canonical_domain,
            )
        )
        if site is None:
            site = Site(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                publisher_id=publisher_id,
                name=name.strip(),
                canonical_domain=canonical_domain,
                canonical_scheme=canonical_scheme,
                timezone=self._settings.browser_timezone,
                status="ACTIVE",
            )
            session.add(site)
            await session.flush()
        elif site.publisher_id != publisher_id:
            raise ValueError("site already belongs to another publisher in this tenant")
        return site

    async def _template(
        self, session: AsyncSession, tenant_id: uuid.UUID, site_id: uuid.UUID
    ) -> Template:
        template = await session.scalar(
            select(Template).where(Template.site_id == site_id, Template.code == "pilot")
        )
        if template is None:
            template = Template(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                site_id=site_id,
                code="pilot",
                display_name="Pilot URL",
                template_family="ARTICLE",
                fingerprint_version="template-config-v1",
                expected_features={},
                status="ACTIVE",
            )
            session.add(template)
            await session.flush()
        elif template.fingerprint_version is None:
            template.template_family = "ARTICLE"
            template.fingerprint_version = "template-config-v1"
        return template

    async def _monitored_url(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        site_id: uuid.UUID,
        template_id: uuid.UUID,
        url: str,
    ) -> MonitoredUrl:
        monitored_url = await session.scalar(
            select(MonitoredUrl).where(
                MonitoredUrl.tenant_id == tenant_id,
                MonitoredUrl.site_id == site_id,
                MonitoredUrl.url == url,
                MonitoredUrl.status == "ACTIVE",
            )
        )
        if monitored_url is None:
            monitored_url = MonitoredUrl(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                site_id=site_id,
                template_id=template_id,
                url=url,
                priority=0,
                is_canary=True,
                status="ACTIVE",
            )
            session.add(monitored_url)
            await session.flush()
        return monitored_url

    async def _scenario(
        self, session: AsyncSession, tenant_id: uuid.UUID, site_id: uuid.UUID
    ) -> BrowserScenario:
        scenario = await session.scalar(
            select(BrowserScenario).where(
                BrowserScenario.tenant_id == tenant_id,
                BrowserScenario.site_id == site_id,
                BrowserScenario.code == CORE_SCENARIO_CODE,
                BrowserScenario.version == 1,
            )
        )
        if scenario is None:
            scenario = BrowserScenario(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                site_id=site_id,
                code=CORE_SCENARIO_CODE,
                version=1,
                device_class="DESKTOP",
                device_profile={
                    "viewport": {
                        "width": self._settings.browser_viewport_width,
                        "height": self._settings.browser_viewport_height,
                    }
                },
                locale=self._settings.browser_locale,
                timezone=self._settings.browser_timezone,
                cache_mode="CLEAN",
                consent_path="NONE",
                status="ACTIVE",
            )
            session.add(scenario)
            await session.flush()
        return scenario

    async def _ensure_b2_configuration(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        site_id: uuid.UUID,
        timezone_name: str,
        now: datetime,
    ) -> None:
        profile = await self._interaction_profile(session, tenant_id, site_id)
        await self._b2_scenario(
            session,
            tenant_id=tenant_id,
            site_id=site_id,
            profile=profile,
            code=B2_DESKTOP_SCENARIO_CODE,
            version=2,
            device_class="DESKTOP",
            device_profile={
                "profile_name": "desktop_1440x900",
                "profile_version": 1,
                "viewport": {
                    "width": self._settings.browser_viewport_width,
                    "height": self._settings.browser_viewport_height,
                },
                "device_scale_factor": 1.0,
                "user_agent": DESKTOP_USER_AGENT,
                "is_mobile": False,
                "has_touch": False,
            },
            timezone_name=timezone_name,
            consent_path="PRIMARY",
        )
        await self._b2_scenario(
            session,
            tenant_id=tenant_id,
            site_id=site_id,
            profile=profile,
            code=B2_MOBILE_SCENARIO_CODE,
            version=1,
            device_class="MOBILE",
            device_profile={
                "profile_name": "pixel_7_class",
                "profile_version": 1,
                "viewport": {"width": 412, "height": 915},
                "device_scale_factor": 2.625,
                "user_agent": MOBILE_USER_AGENT,
                "is_mobile": True,
                "has_touch": True,
            },
            timezone_name=timezone_name,
            consent_path="PRIMARY",
        )
        await self._b2_scenario(
            session,
            tenant_id=tenant_id,
            site_id=site_id,
            profile=profile,
            code=B5_REJECT_SCENARIO_CODE,
            version=1,
            device_class="MOBILE",
            device_profile={
                "profile_name": "pixel_7_class",
                "profile_version": 1,
                "viewport": {"width": 412, "height": 915},
                "device_scale_factor": 2.625,
                "user_agent": MOBILE_USER_AGENT,
                "is_mobile": True,
                "has_touch": True,
            },
            timezone_name=timezone_name,
            consent_path="REJECT",
        )
        legacy = await session.scalar(
            select(BrowserScenario).where(
                BrowserScenario.tenant_id == tenant_id,
                BrowserScenario.site_id == site_id,
                BrowserScenario.code == CORE_SCENARIO_CODE,
                BrowserScenario.version == 1,
            )
        )
        if legacy is not None and legacy.status == "ACTIVE":
            legacy.status = "RETIRED"
            legacy.retired_at = now

    async def _interaction_profile(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        site_id: uuid.UUID,
    ) -> InteractionProfile:
        profile = await session.scalar(
            select(InteractionProfile).where(
                InteractionProfile.tenant_id == tenant_id,
                InteractionProfile.site_id == site_id,
                InteractionProfile.code == B2_INTERACTION_PROFILE_CODE,
                InteractionProfile.version == 1,
            )
        )
        parse_interaction_steps(B2_INTERACTION_STEPS)
        if profile is None:
            profile = InteractionProfile(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                site_id=site_id,
                code=B2_INTERACTION_PROFILE_CODE,
                version=1,
                description="Bounded deterministic B2 article scroll",
                steps=B2_INTERACTION_STEPS,
                status="ACTIVE",
            )
            session.add(profile)
            await session.flush()
        elif profile.steps != B2_INTERACTION_STEPS or profile.status != "ACTIVE":
            raise ValueError("existing B2 interaction profile does not match its immutable version")
        return profile

    async def _b2_scenario(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        site_id: uuid.UUID,
        profile: InteractionProfile,
        code: str,
        version: int,
        device_class: str,
        device_profile: dict[str, object],
        timezone_name: str,
        consent_path: str,
    ) -> BrowserScenario:
        scenario = await session.scalar(
            select(BrowserScenario).where(
                BrowserScenario.tenant_id == tenant_id,
                BrowserScenario.site_id == site_id,
                BrowserScenario.code == code,
                BrowserScenario.version == version,
            )
        )
        expected = {
            "interaction_profile_id": profile.id,
            "device_class": device_class,
            "device_profile": device_profile,
            "locale": self._settings.browser_locale,
            "timezone": timezone_name,
            "cache_mode": "CLEAN",
            "consent_path": consent_path,
            "status": "ACTIVE",
        }
        if scenario is None:
            scenario = BrowserScenario(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                site_id=site_id,
                code=code,
                version=version,
                **expected,
            )
            session.add(scenario)
            await session.flush()
            return scenario
        actual = {key: getattr(scenario, key) for key in expected}
        if actual != expected:
            raise ValueError(
                f"existing browser scenario {code} does not match its immutable version"
            )
        return scenario

    async def ensure_b2_configuration_for_active_sites(self) -> int:
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            sites = list((await session.scalars(select(Site).where(Site.status == "ACTIVE"))).all())
        configured = 0
        for site in sites:
            try:
                async with self._session_factory() as session, session.begin():
                    await self._ensure_b2_configuration(
                        session,
                        site.tenant_id,
                        site.id,
                        site.timezone,
                        now,
                    )
                configured += 1
            except ValueError as error:
                logger.error(
                    "B2 browser configuration rejected",
                    extra={
                        "context": {
                            "tenant_id": str(site.tenant_id),
                            "site_id": str(site.id),
                            "error_class": type(error).__name__,
                        }
                    },
                )
        return configured
