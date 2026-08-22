"""Unified evidence-version comparability contract.

A fingerprint is a stable, ordered mapping of the version identities that make
two pieces of evidence semantically comparable: collector bundle, per-subsystem
normalizer versions, and applicable rule bundles. Two snapshots are comparable
only when every entry matches; partial matches are incomparable.

Version constants must be sourced from their owning modules (never re-typed
here) so registry drift is impossible at the import level.
"""

from typing import Any

FINGERPRINT_MAX_ENTRIES = 100


def evidence_fingerprints(values: dict[str, Any]) -> dict[str, str]:
    """Build a stable, sorted string snapshot of version identities."""
    if len(values) > FINGERPRINT_MAX_ENTRIES:
        raise ValueError("fingerprint exceeds the entry limit")
    cleaned = {str(key): str(item) for key, item in values.items()}
    return {key: cleaned[key] for key in sorted(cleaned)}


def fingerprints_comparable(a: dict[str, str], b: dict[str, str]) -> bool:
    """Two snapshots are comparable iff every version identity matches."""
    return a == b
