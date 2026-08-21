import uuid
from datetime import UTC, datetime
from typing import Any, cast

from app.public_config.contracts import PublicConfigSiteTarget
from app.public_config.scheduling import (
    PublicConfigSchedulingService,
    resolve_public_config_slot,
)


class Repository:
    def __init__(self, sites: tuple[PublicConfigSiteTarget, ...]) -> None:
        self._sites = sites

    async def schedulable_sites(self) -> tuple[PublicConfigSiteTarget, ...]:
        return self._sites


class Queue:
    def __init__(self) -> None:
        self.jobs: dict[str, dict[str, Any]] = {}

    async def enqueue(self, **kwargs: Any) -> uuid.UUID:
        key = cast(str, kwargs["idempotency_key"])
        self.jobs.setdefault(key, kwargs)
        return uuid.uuid5(uuid.NAMESPACE_URL, key)


def site(*, timezone: str = "Europe/Bucharest") -> PublicConfigSiteTarget:
    return PublicConfigSiteTarget(
        tenant_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        site_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        canonical_domain="example.com",
        canonical_scheme="https",
        timezone=timezone,
    )


async def test_two_scheduler_passes_create_one_job_per_type_and_window() -> None:
    queue = Queue()
    service = PublicConfigSchedulingService(cast(Any, Repository((site(),))), cast(Any, queue))
    now = datetime(2026, 8, 21, 5, 32, tzinfo=UTC)

    first = await service.schedule_due(now=now)
    second = await service.schedule_due(now=now)

    assert first.site_count == second.site_count == 1
    assert first.job_count == second.job_count == 2
    assert len(queue.jobs) == 2
    assert {job["payload"]["config_type"] for job in queue.jobs.values()} == {
        "ROBOTS_TXT",
        "ADS_TXT",
    }
    assert {job["payload"]["scheduled_for"] for job in queue.jobs.values()} == {
        "2026-08-21T03:00:00+00:00"
    }


def test_slot_is_the_current_six_hour_local_window() -> None:
    instant = datetime(2026, 3, 29, 7, 15, tzinfo=UTC)

    assert resolve_public_config_slot(instant, "Europe/Bucharest") == datetime(
        2026, 3, 29, 3, 0, tzinfo=UTC
    )


async def test_unknown_timezone_is_skipped_without_jobs() -> None:
    queue = Queue()
    service = PublicConfigSchedulingService(
        cast(Any, Repository((site(timezone="Not/AZone"),))), cast(Any, queue)
    )

    result = await service.schedule_due(now=datetime(2026, 8, 21, tzinfo=UTC))

    assert result.site_count == 0
    assert result.job_count == 0
    assert queue.jobs == {}
