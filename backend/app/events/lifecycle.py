import hashlib
import json
import uuid
from collections.abc import Mapping

from app.events.contracts import EventRule

SEVERITY_ORDER = {"INFO": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


def normalized_scope(scope: Mapping[str, object]) -> dict[str, object]:
    return {str(key): scope[key] for key in sorted(scope) if scope[key] is not None}


def condition_key(
    *,
    tenant_id: uuid.UUID,
    site_id: uuid.UUID,
    event_code: str,
    subject: str,
    scope: Mapping[str, object],
) -> str:
    payload = {
        "tenant_id": str(tenant_id),
        "site_id": str(site_id),
        "event_code": event_code,
        "subject": subject,
        "scope": normalized_scope(scope),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def severity_for(rule: EventRule, *, affected_urls: int, valid_urls: int) -> str:
    if affected_urls < 0 or valid_urls < 0 or affected_urls > valid_urls:
        raise ValueError("invalid affected/valid URL counts")
    if rule.severity_policy == "NOINDEX_SCOPE":
        return "CRITICAL" if affected_urls >= rule.min_affected_urls else "MEDIUM"
    if rule.severity_policy == "AFFECTED_URL_COUNT":
        critical = rule.critical_min_affected_urls
        if critical is not None and affected_urls >= critical and affected_urls == valid_urls:
            return "CRITICAL"
        return rule.default_severity
    return rule.default_severity


def higher_severity(current: str, proposed: str) -> str:
    if current not in SEVERITY_ORDER or proposed not in SEVERITY_ORDER:
        raise ValueError("unknown severity")
    return proposed if SEVERITY_ORDER[proposed] > SEVERITY_ORDER[current] else current
