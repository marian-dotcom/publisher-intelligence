"""EP-026 M2 — deterministic browser-access reliability classification.

Classifies bounded observation signals into monitoring-source states.
Invariants:
- DOM variance alone NEVER proves blocking/degradation;
- classification is about OUR monitoring access path, never publisher failure;
- a single transient degraded signal is not a persistent degradation
  (consecutive-signal hysteresis is applied by the caller).
"""

from dataclasses import dataclass

CHALLENGE_MARKERS: tuple[str, ...] = (
    "captcha",
    "cf-challenge",
    "attention required! | cloudflare",
    "access denied",
    "request unsuccessful. incapsula",
    "denied access",
)


@dataclass(frozen=True)
class AccessClassification:
    state: str  # "ok" | "challenge_suspected" | "degraded"
    reason: str


def classify_access(
    *,
    navigation_failed: bool,
    http_status: int | None,
    response_body: str | None,
) -> AccessClassification:
    """Classify one bounded observation of our browser access path."""
    if navigation_failed:
        return AccessClassification("degraded", "navigation failed")
    if http_status is not None and (http_status >= 400 or 300 <= http_status < 400):
        # Redirect/status anomaly alone is degraded-context, not a challenge claim.
        return AccessClassification(
            "degraded", f"unexpected HTTP status {http_status}"
        )
    lowered = (response_body or "").lower()
    matched = [marker for marker in CHALLENGE_MARKERS if marker in lowered]
    if matched:
        return AccessClassification(
            "challenge_suspected",
            f"deterministic challenge markers observed: {matched[0]}",
        )
    return AccessClassification("ok", "no access anomalies in bounded signal set")
