import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from typing import cast

from app.public_config.contracts import (
    MAX_ADS_TXT_RECORDS,
    AdsTxtRecordInput,
    AdsTxtRelationship,
    ParseStatus,
    ads_txt_record_hash,
)

ADS_TXT_NORMALIZER_VERSION = "ads-txt-1.1-v1"
MAX_DIAGNOSTICS = 20
MAX_SUMMARY_MANAGERS = 100
_DOMAIN_LABEL = re.compile(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)\Z")
_DIRECTIVES = frozenset(
    {"OWNERDOMAIN", "MANAGERDOMAIN", "CONTACT", "SUBDOMAIN", "INVENTORYPARTNERDOMAIN"}
)


@dataclass(frozen=True, slots=True)
class AdsTxtParseResult:
    parse_status: ParseStatus
    semantic_hash: str
    records: tuple[AdsTxtRecordInput, ...]
    owner_domain: str | None
    manager_domains: tuple[tuple[str, str | None], ...]
    diagnostics: tuple[str, ...]
    summary: dict[str, object]


def parse_ads_txt(content: bytes) -> AdsTxtParseResult:
    diagnostics: list[str] = []
    decoded = content.decode("utf-8", errors="replace").removeprefix("\ufeff")
    if "\ufffd" in decoded:
        _add_diagnostic(diagnostics, "INVALID_UTF8_REPLACED")
    records_by_hash: dict[str, AdsTxtRecordInput] = {}
    owner_domain: str | None = None
    manager_domains: set[tuple[str, str | None]] = set()
    directive_counts: Counter[str] = Counter()
    meaningful_lines = 0
    invalid_row_count = 0
    duplicate_record_count = 0

    for line_number, raw_line in enumerate(decoded.splitlines(), start=1):
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        meaningful_lines += 1
        directive_name = line.partition("=")[0].strip().upper()
        if "=" in line and directive_name in _DIRECTIVES:
            raw_value = line.split("=", 1)[1].strip()
            directive_counts[directive_name] += 1
            if directive_name == "OWNERDOMAIN":
                domain = _normalize_domain(raw_value)
                if domain is None:
                    _add_diagnostic(diagnostics, f"LINE_{line_number}_INVALID_OWNERDOMAIN")
                elif owner_domain is None:
                    owner_domain = domain
                else:
                    _add_diagnostic(diagnostics, f"LINE_{line_number}_DUPLICATE_OWNERDOMAIN")
            elif directive_name == "MANAGERDOMAIN":
                parts = [part.strip() for part in raw_value.split(",")]
                domain = _normalize_domain(parts[0]) if parts else None
                country = parts[1].upper() if len(parts) == 2 and parts[1] else None
                if (
                    domain is None
                    or len(parts) > 2
                    or (country is not None and not re.fullmatch(r"[A-Z]{2}", country))
                ):
                    _add_diagnostic(diagnostics, f"LINE_{line_number}_INVALID_MANAGERDOMAIN")
                else:
                    manager_domains.add((domain, country))
            elif directive_name in {"SUBDOMAIN", "INVENTORYPARTNERDOMAIN"}:
                if _normalize_domain(raw_value) is None:
                    _add_diagnostic(diagnostics, f"LINE_{line_number}_INVALID_{directive_name}")
            elif not raw_value:
                _add_diagnostic(diagnostics, f"LINE_{line_number}_EMPTY_{directive_name}")
            continue

        fields = [field.strip() for field in line.split(",")]
        if len(fields) not in {3, 4}:
            invalid_row_count += 1
            _add_diagnostic(diagnostics, f"LINE_{line_number}_INVALID_FIELD_COUNT")
            continue
        domain = _normalize_domain(fields[0])
        account_id = fields[1]
        relationship_value = fields[2].upper()
        cert_authority_id = fields[3].lower() if len(fields) == 4 and fields[3] else None
        if domain is None:
            invalid_row_count += 1
            _add_diagnostic(diagnostics, f"LINE_{line_number}_INVALID_DOMAIN")
            continue
        if not account_id or len(account_id) > 500:
            invalid_row_count += 1
            _add_diagnostic(diagnostics, f"LINE_{line_number}_INVALID_ACCOUNT_ID")
            continue
        if relationship_value not in {"DIRECT", "RESELLER"}:
            invalid_row_count += 1
            _add_diagnostic(diagnostics, f"LINE_{line_number}_INVALID_RELATIONSHIP")
            continue
        if len(fields) == 4 and (cert_authority_id is None or len(cert_authority_id) > 255):
            invalid_row_count += 1
            _add_diagnostic(diagnostics, f"LINE_{line_number}_INVALID_CERT_AUTHORITY")
            continue
        if len(records_by_hash) >= MAX_ADS_TXT_RECORDS:
            invalid_row_count += 1
            _add_diagnostic(diagnostics, "RECORD_LIMIT_EXCEEDED")
            continue
        relationship = cast(AdsTxtRelationship, relationship_value)
        record_hash = ads_txt_record_hash(
            advertising_system_domain=domain,
            publisher_account_id=account_id,
            relationship=relationship,
            cert_authority_id=cert_authority_id,
        )
        if record_hash in records_by_hash:
            duplicate_record_count += 1
            _add_diagnostic(diagnostics, f"LINE_{line_number}_DUPLICATE_RECORD")
            continue
        records_by_hash[record_hash] = AdsTxtRecordInput(
            advertising_system_domain=domain,
            publisher_account_id=account_id,
            relationship=relationship,
            cert_authority_id=cert_authority_id,
            record_hash=record_hash,
        )

    records = tuple(records_by_hash[key] for key in sorted(records_by_hash))
    managers = tuple(sorted(manager_domains, key=lambda value: (value[0], value[1] or "")))
    semantic_payload = {
        "manager_domains": managers,
        "owner_domain": owner_domain,
        "record_hashes": sorted(records_by_hash),
    }
    semantic_hash = hashlib.sha256(
        json.dumps(semantic_payload, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    if meaningful_lines == 0:
        parse_status: ParseStatus = "EMPTY"
    elif not records:
        parse_status = "INVALID"
        _add_diagnostic(diagnostics, "NO_VALID_SELLER_RECORDS")
    elif diagnostics:
        parse_status = "VALID_WITH_WARNINGS"
    else:
        parse_status = "VALID"
    summary: dict[str, object] = {
        "normalizer_version": ADS_TXT_NORMALIZER_VERSION,
        "semantic_hash": semantic_hash,
        "valid_record_count": len(records),
        "invalid_row_count": invalid_row_count,
        "duplicate_record_count": duplicate_record_count,
        "owner_domain": owner_domain,
        "manager_domains": [
            {"domain": domain, "country": country}
            for domain, country in managers[:MAX_SUMMARY_MANAGERS]
        ],
        "manager_domains_truncated": len(managers) > MAX_SUMMARY_MANAGERS,
        "directive_counts": dict(sorted(directive_counts.items())),
        "diagnostics": diagnostics,
    }
    return AdsTxtParseResult(
        parse_status=parse_status,
        semantic_hash=semantic_hash,
        records=records,
        owner_domain=owner_domain,
        manager_domains=managers,
        diagnostics=tuple(diagnostics),
        summary=summary,
    )


def _normalize_domain(value: str) -> str | None:
    candidate = value.strip().rstrip(".").lower()
    if not candidate or len(candidate) > 253 or "://" in candidate:
        return None
    try:
        candidate = candidate.encode("idna").decode("ascii")
    except UnicodeError:
        return None
    labels = candidate.split(".")
    if len(labels) < 2 or any(not _DOMAIN_LABEL.fullmatch(label) for label in labels):
        return None
    return candidate


def _add_diagnostic(diagnostics: list[str], code: str) -> None:
    if len(diagnostics) < MAX_DIAGNOSTICS:
        diagnostics.append(code[:200])
