"""Sanitized connector fixture composition for evidence-pack consumers.

Loads the existing sanitized provider payloads from
``backend/tests/fixtures/connectors/`` so EP-023 ranking tests can exercise
evidence packs containing traffic/monetization data without live OAuth.
Payloads are returned as parsed dicts; nothing here performs network access.
"""

import json
from pathlib import Path
from typing import Any

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "connectors"

INVENTORY: dict[str, tuple[str, ...]] = {
    "ga4": (
        "metadata_core.json",
        "traffic_complete.json",
        "traffic_thresholded.json",
        "behavior_complete.json",
    ),
    "gsc": (
        "sites_accessible.json",
        "search_daily.json",
        "search_hourly_incomplete.json",
        "discover_empty.json",
        "url_inspection.json",
    ),
    "gam": (
        "networks.json",
        "network.json",
        "inventory_rows_page_1.json",
        "inventory_rows_page_2.json",
        "inventory_today_report.json",
    ),
}


def load_fixture(provider: str, name: str) -> dict[str, Any]:
    path = FIXTURE_ROOT / provider / name
    return cast_dict(json.loads(path.read_text()))


def load_provider_fixtures(provider: str) -> dict[str, dict[str, Any]]:
    return {name: load_fixture(provider, name) for name in INVENTORY[provider]}


def load_all_connector_fixtures() -> dict[str, dict[str, dict[str, Any]]]:
    return {provider: load_provider_fixtures(provider) for provider in sorted(INVENTORY)}


def cast_dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"fixture payload must be a JSON object, got {type(value)!r}")
    return value
