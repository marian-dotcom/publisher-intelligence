"""Boundary and determinism guarantees for the eval runtime (ADR-129)."""

import subprocess
import sys
from pathlib import Path

from evals_runtime.adapter import (
    lkg_eligible,
    pick_localization_anchor,
    within_budget,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_app_tree_never_imports_inspect() -> None:
    """ADR-129 boundary: inspect_ai may only appear under backend/evals_runtime."""
    hits = subprocess.run(
        [
            sys.executable,
            "-m",
            "grep",
            "-rl",
            "inspect_ai",
            str(BACKEND_ROOT / "app"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert hits.stdout.strip() == "", hits.stdout


def test_localization_pick_is_deterministic_and_kind_scoped() -> None:
    runs = [
        {
            "run_id": "late-diagnostic",
            "observation_kind": "DIAGNOSTIC",
            "status": "COMPLETE",
            "completed_at": "2026-08-21T00:00:00+00:00",
        },
        {
            "run_id": "healthy-early",
            "observation_kind": "SCHEDULED",
            "status": "COMPLETE",
            "completed_at": "2026-08-20T06:00:00+00:00",
        },
    ]
    onset = "2026-08-21T00:00:00+00:00"
    first = pick_localization_anchor(runs, onset)
    second = pick_localization_anchor(list(reversed(runs)), onset)
    assert first == second == "healthy-early"


def test_lkg_eligibility_requires_scheduled_healthy_comparable() -> None:
    fingerprints = {"collector_bundle": "b8-v1"}
    assert lkg_eligible(
        {
            "observation_kind": "SCHEDULED",
            "status": "COMPLETE",
            "fingerprints": {"collector_bundle": "b8-v1"},
        },
        fingerprints,
    )
    assert not lkg_eligible(
        {
            "observation_kind": "DIAGNOSTIC",
            "status": "COMPLETE",
            "fingerprints": {"collector_bundle": "b8-v1"},
        },
        fingerprints,
    )
    assert not lkg_eligible(
        {
            "observation_kind": "SCHEDULED",
            "status": "SITE_ERROR",
            "fingerprints": {"collector_bundle": "b8-v1"},
        },
        fingerprints,
    )
    assert not lkg_eligible(
        {
            "observation_kind": "SCHEDULED",
            "status": "COMPLETE",
            "fingerprints": {"collector_bundle": "b9-v1"},
        },
        fingerprints,
    )


def test_budget_gate_matches_repository_defaults() -> None:
    assert within_budget("DRILLDOWN", 3)
    assert not within_budget("DRILLDOWN", 4)


def test_inspect_version_is_pinned_in_lockfile() -> None:
    from importlib.metadata import version

    pinned = version("inspect-ai")
    assert pinned.startswith("0.3.")
