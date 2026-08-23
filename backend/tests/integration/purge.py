"""Ordered full-database purge shared by integration suites."""

from collections.abc import Callable
from typing import Any

from sqlalchemy import text

PURGE_ORDER = (
    "event_evidence_refs",
    "event_relations",
    "hypothesis_evidence",
    "hypotheses",
    "events",
    "evidence_packs",
    "manual_notes",
    "investigation_usage",
    "last_known_good_refs",
    "retention_holds",
    "incident_symptom_segments",
    "incidents",
    "ads_txt_records",
    "public_config_snapshots",
    "metric_derivation_inputs",
    "metric_derivations",
    "metric_points",
    "metric_series",
    "source_extracts",
    "data_connections",
    "synthetic_performance_observations",
    "video_player_observations",
    "prebid_bidder_observations",
    "prebid_auction_observations",
    "consent_phase_dependency_observations",
    "cmp_observations",
    "gpt_slot_observations",
    "js_error_observations",
    "seo_observations",
    "entity_observations",
    "template_expected_entities",
    "domain_entities",
    "collector_runs",
    "artifacts",
    "checkpoint_attempts",
    "checkpoint_runs",
    "checkpoint_windows",
    "browser_scenarios",
    "interaction_profiles",
    "monitored_urls",
    "templates",
    "sites",
    "publishers",
    "jobs",
    "sessions",
    "operator_tenants",
    "operators",
    "tenants",
)


def make_purge(
    session_factory_getter: Callable[[], Any],
) -> Callable[[], Any]:
    """Build a purge bound to the session factory getter.

    Accepts the factory-getter (e.g. app.db.session.get_session_factory) so the
    async sessionmaker is resolved at purge time, on the caller's event loop.
    """

    async def purge() -> None:
        maker = session_factory_getter()
        async with maker() as session, session.begin():
            for table in PURGE_ORDER:
                await session.execute(text(f"DELETE FROM {table}"))

    return purge
