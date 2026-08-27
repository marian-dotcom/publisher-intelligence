import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.browser.models import CheckpointRun, CheckpointWindow, Publisher, Site
from app.browser.security import BrowserNetworkGuard, canonical_hostname
from app.browser.service import CheckpointService, _slug
from app.db.models import Tenant


class DuplicateSiteRegistrationError(ValueError):
    """Raised when a canonical domain is already registered in the tenant."""


@dataclass(frozen=True, slots=True)
class RegisteredOperatorSite:
    tenant_id: uuid.UUID
    site_id: uuid.UUID
    canonical_domain: str
    checkpoint_run_id: uuid.UUID
    job_id: uuid.UUID
    trigger_correlation_id: uuid.UUID


class OperatorSiteRegistrationService(CheckpointService):
    """EP-028 internal operator Add Site use case.

    Tenant identity is supplied only by the authenticated server-side actor.
    Site configuration, the initial DIAGNOSTIC checkpoint and its queue job are
    committed atomically. The service does not accept arbitrary observation or
    trigger provenance from callers.
    """

    async def register_for_tenant(
        self,
        *,
        tenant_id: uuid.UUID,
        publisher_name: str,
        site_name: str,
        url: str,
    ) -> RegisteredOperatorSite:
        if not site_name.strip():
            raise ValueError("site name is required")
        parts = urlsplit(url)
        if parts.hostname is None:
            raise ValueError("URL hostname is required")

        canonical_domain = canonical_hostname(parts.hostname)
        guard = BrowserNetworkGuard(
            canonical_domain=canonical_domain,
            allow_private_networks=self._settings.browser_allow_private_networks,
            max_requests=self._settings.browser_max_requests,
        )
        await guard.validate_initial(url)

        now = datetime.now(UTC)
        invocation_id = uuid.uuid4()
        async with self._session_factory() as session, session.begin():
            tenant_exists = await session.scalar(select(Tenant.id).where(Tenant.id == tenant_id))
            if tenant_exists is None:
                raise ValueError("tenant not found")

            publisher = await self._publisher_for_registration(
                session,
                tenant_id=tenant_id,
                publisher_name=publisher_name,
            )
            site = await self._insert_new_site(
                session,
                tenant_id=tenant_id,
                publisher_id=publisher.id,
                site_name=site_name,
                canonical_domain=canonical_domain,
                canonical_scheme=parts.scheme.lower(),
            )
            template = await self._template(session, tenant_id, site.id)
            monitored_url = await self._monitored_url(
                session, tenant_id, site.id, template.id, url
            )
            scenario = await self._scenario(session, tenant_id, site.id)
            await self._ensure_b2_configuration(
                session,
                tenant_id,
                site.id,
                site.timezone,
                now,
            )

            window = CheckpointWindow(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                site_id=site.id,
                scheduled_for=now,
                window_start=now,
                window_end=now + timedelta(minutes=5),
                status="SCHEDULED",
            )
            run = CheckpointRun(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                site_id=site.id,
                checkpoint_window_id=window.id,
                monitored_url_id=monitored_url.id,
                template_id=template.id,
                scenario_id=scenario.id,
                observation_kind="DIAGNOSTIC",
                trigger_source="OPERATOR_UI",
                trigger_correlation_id=invocation_id,
                scheduled_for=now,
                status="PENDING",
                attempt_count=0,
                collector_bundle_version="b8-v1",
                environment={},
                limitations=[],
                manifest={},
            )
            session.add(window)
            await session.flush()
            session.add(run)
            await session.flush()

            job_id = await self._queue.enqueue_in_session(
                session,
                job_type="BROWSER_CHECKPOINT",
                tenant_id=tenant_id,
                payload={"checkpoint_run_id": str(run.id)},
                idempotency_key=f"browser-checkpoint:{run.id}",
                max_attempts=2,
            )

        return RegisteredOperatorSite(
            tenant_id=tenant_id,
            site_id=site.id,
            canonical_domain=canonical_domain,
            checkpoint_run_id=run.id,
            job_id=job_id,
            trigger_correlation_id=invocation_id,
        )

    async def _publisher_for_registration(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        publisher_name: str,
    ) -> Publisher:
        slug = _slug(publisher_name)
        candidate_id = uuid.uuid4()
        inserted = (
            await session.execute(
                insert(Publisher)
                .values(
                    id=candidate_id,
                    tenant_id=tenant_id,
                    name=publisher_name.strip(),
                    slug=slug,
                    default_timezone=self._settings.browser_timezone,
                    status="ACTIVE",
                )
                .on_conflict_do_nothing(index_elements=["tenant_id", "slug"])
                .returning(Publisher.id)
            )
        ).scalar_one_or_none()
        publisher_id = inserted
        if publisher_id is None:
            publisher_id = await session.scalar(
                select(Publisher.id).where(
                    Publisher.tenant_id == tenant_id,
                    Publisher.slug == slug,
                )
            )
        if publisher_id is None:
            raise RuntimeError("publisher conflict could not be resolved")
        publisher = await session.scalar(
            select(Publisher).where(
                Publisher.id == publisher_id,
                Publisher.tenant_id == tenant_id,
            )
        )
        if publisher is None:
            raise RuntimeError("publisher registration could not be resolved")
        return publisher

    async def _insert_new_site(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        publisher_id: uuid.UUID,
        site_name: str,
        canonical_domain: str,
        canonical_scheme: str,
    ) -> Site:
        candidate_id = uuid.uuid4()
        inserted = (
            await session.execute(
                insert(Site)
                .values(
                    id=candidate_id,
                    tenant_id=tenant_id,
                    publisher_id=publisher_id,
                    name=site_name.strip(),
                    canonical_domain=canonical_domain,
                    canonical_scheme=canonical_scheme,
                    timezone=self._settings.browser_timezone,
                    status="ACTIVE",
                )
                .on_conflict_do_nothing(index_elements=["tenant_id", "canonical_domain"])
                .returning(Site.id)
            )
        ).scalar_one_or_none()
        if inserted is None:
            raise DuplicateSiteRegistrationError("site already registered")
        site = await session.scalar(
            select(Site).where(Site.id == inserted, Site.tenant_id == tenant_id)
        )
        if site is None:
            raise RuntimeError("site registration could not be resolved")
        return site
