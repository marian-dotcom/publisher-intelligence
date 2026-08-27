"""EP-026 M3b: deterministic derived source freshness (STALE state).

Source health must distinguish recent trustworthy evidence from evidence
that has silently stopped arriving. Freshness is DERIVED at read time from
immutable success timestamps — never persisted, never written back into
historical extract/metric freshness_status fields.

Thresholds are small deterministic multiples of each source's already-coded
scheduler cadence (loose enough that healthy normal scheduling never reads
stale; tight enough that silent scheduler/worker stoppage is detected the
same day instead of "forever"):

- GA4:           preliminary slots every 2h  -> 6h  (3x)
- GSC:           fresh slots every 4h        -> 12h (3x)
- GAM:           TODAY slots every 2h        -> 6h  (3x)
- PUBLIC_CONFIG: scheduled slots every 6h    -> 18h (3x)
- BROWSER_MONITORING keeps its canonical ~7h heuristic over the 6h cadence.

Trustworthy timestamps only (never updated_at / attempt / enqueue times):
- GA4/GSC/GAM: DataConnection.last_success_at
- PUBLIC_CONFIG: latest SCHEDULED snapshot with parse_status VALID or
  VALID_WITH_WARNINGS, using observed_at
- BROWSER_MONITORING: latest SCHEDULED CheckpointRun.completed_at

STALE means "no trustworthy new evidence within this source's freshness
window". It is NOT publisher/site failure, vendor downtime, or an
authentication verdict, and it never overrides stronger explicit connection
states.
"""

from datetime import datetime, timedelta

# Per-source freshness windows over successful-evidence cadence.
SOURCE_FRESHNESS_THRESHOLDS: dict[str, timedelta] = {
    "GA4": timedelta(hours=6),
    "GSC": timedelta(hours=12),
    "GAM": timedelta(hours=6),
    "PUBLIC_CONFIG": timedelta(hours=18),
}

SUCCESS_STATES = frozenset({"HEALTHY", "UNKNOWN"})


def freshness_state(
    last_success_at: datetime | None, *, now: datetime, threshold: timedelta
) -> str:
    """Project one trustworthy success timestamp into HEALTHY/STALE/UNKNOWN.

    - None            -> UNKNOWN (never-synced has nothing to have gone stale;
                         it must not read as healthy merely because a
                         connection row exists)
    - age <= threshold -> HEALTHY (exactly at the boundary is still fresh)
    - age > threshold  -> STALE

    Naive timestamps are rejected loudly: freshness arithmetic is UTC-aware
    only (timestamptz columns always produce aware datetimes).
    """
    if last_success_at is None:
        return "UNKNOWN"
    if last_success_at.tzinfo is None or last_success_at.utcoffset() is None:
        raise ValueError("naive datetime rejected in freshness projection")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("naive datetime rejected in freshness projection")
    if now - last_success_at > threshold:
        return "STALE"
    return "HEALTHY"
