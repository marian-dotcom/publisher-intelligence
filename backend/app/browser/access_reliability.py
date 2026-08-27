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

VALID_STATES: tuple[str, ...] = ("ok", "challenge_suspected", "degraded")

# EP-026 M2b-1b: deterministic cap on how much transient page text is scanned
# for challenge markers. The text itself is never retained anywhere.
CHALLENGE_MARKER_SCAN_CHARS = 100_000


@dataclass(frozen=True)
class AccessClassification:
    state: str  # "ok" | "challenge_suspected" | "degraded"
    reason: str


def detect_challenge_marker(text: str | None) -> str | None:
    """Deterministically reduce bounded transient page text to the first
    canonical challenge marker, if any (EP-026 M2b-1b).

    The scan is capped at CHALLENGE_MARKER_SCAN_CHARS; only the marker name —
    never the text — is returned, and the input is never retained.
    """
    if not text:
        return None
    lowered = text[:CHALLENGE_MARKER_SCAN_CHARS].lower()
    for marker in CHALLENGE_MARKERS:
        if marker in lowered:
            return marker
    return None


def classify_access(
    *,
    navigation_failed: bool,
    http_status: int | None,
    response_body: str | None,
    challenge_marker: str | None = None,
) -> AccessClassification:
    """Classify one bounded observation of our browser access path.

    ``challenge_marker`` is the pre-reduced signal from
    :func:`detect_challenge_marker` (EP-026 M2b-1b). A deterministic marker is
    more specific than a bare status anomaly, so it takes precedence: 403 with
    a canonical marker is challenge_suspected, 403 without one stays degraded.
    Status codes alone are NEVER proof of a challenge.
    """
    if navigation_failed:
        return AccessClassification("degraded", "navigation failed")
    marker = challenge_marker or detect_challenge_marker(response_body)
    if marker is not None:
        return AccessClassification(
            "challenge_suspected",
            f"deterministic challenge markers observed: {marker}",
        )
    if http_status is not None and (http_status >= 400 or 300 <= http_status < 400):
        # Redirect/status anomaly alone is degraded-context, not a challenge claim.
        return AccessClassification("degraded", f"unexpected HTTP status {http_status}")
    return AccessClassification("ok", "no access anomalies in bounded signal set")


def classification_from_storage(value: object) -> AccessClassification | None:
    """Parse a stored bounded {state, reason} classification (EP-026 M2b-1a-2b).

    Returns None for anything that is not a well-formed classification so
    malformed or legacy rows fail closed to "nothing derivable" instead of
    inventing an event.
    """
    if not isinstance(value, dict):
        return None
    state = value.get("state")
    reason = value.get("reason")
    if state not in VALID_STATES or not isinstance(reason, str) or not reason:
        return None
    return AccessClassification(str(state), reason[:200])
