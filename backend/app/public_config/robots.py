import hashlib
import json
import re
import string
from dataclasses import dataclass

from app.public_config.contracts import ParseStatus

ROBOTS_NORMALIZER_VERSION = "robots-rfc9309-v1"
MAX_DIAGNOSTICS = 20
MAX_SUMMARY_RULES = 100
MAX_SUMMARY_PATTERN_LENGTH = 300
_USER_AGENT_PATTERN = re.compile(r"(?:[-A-Za-z_]+|\*)\Z")
_HEX_DIGITS = frozenset(string.hexdigits)
_UNRESERVED = frozenset(string.ascii_letters + string.digits + "-._~")


@dataclass(frozen=True, slots=True, order=True)
class RobotsRule:
    directive: str
    pattern: str


@dataclass(frozen=True, slots=True)
class RobotsParseResult:
    parse_status: ParseStatus
    semantic_hash: str
    groups: tuple[tuple[str, tuple[RobotsRule, ...]], ...]
    broad_blocked: bool
    diagnostics: tuple[str, ...]
    summary: dict[str, object]

    def is_allowed(self, user_agent: str, path_and_query: str) -> bool:
        selected: list[RobotsRule] = []
        exact_matches = [
            (agent, rules)
            for agent, rules in self.groups
            if agent != "*" and agent.casefold() in user_agent.casefold()
        ]
        if exact_matches:
            longest = max(len(agent) for agent, _rules in exact_matches)
            for agent, rules in exact_matches:
                if len(agent) == longest:
                    selected.extend(rules)
        else:
            for agent, rules in self.groups:
                if agent == "*":
                    selected.extend(rules)
        matching = [rule for rule in selected if _rule_matches(rule.pattern, path_and_query)]
        if not matching:
            return True
        specificity = max(_rule_specificity(rule.pattern) for rule in matching)
        strongest = [rule for rule in matching if _rule_specificity(rule.pattern) == specificity]
        return any(rule.directive == "allow" for rule in strongest)


@dataclass(slots=True)
class _Group:
    agents: list[str]
    rules: list[RobotsRule]
    rules_started: bool = False


def parse_robots_txt(content: bytes) -> RobotsParseResult:
    diagnostics: list[str] = []
    decoded = content.decode("utf-8", errors="replace")
    if "\ufffd" in decoded:
        _add_diagnostic(diagnostics, "INVALID_UTF8_REPLACED")
    decoded = decoded.removeprefix("\ufeff")
    groups: list[_Group] = []
    current: _Group | None = None
    meaningful_lines = 0
    sitemaps: set[str] = set()

    for line_number, raw_line in enumerate(decoded.splitlines(), start=1):
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        meaningful_lines += 1
        if ":" not in line:
            _add_diagnostic(diagnostics, f"LINE_{line_number}_MISSING_SEPARATOR")
            continue
        field, value = (part.strip() for part in line.split(":", 1))
        field = field.casefold()
        if field == "user-agent":
            if not _USER_AGENT_PATTERN.fullmatch(value):
                _add_diagnostic(diagnostics, f"LINE_{line_number}_INVALID_USER_AGENT")
                continue
            normalized_agent = value.casefold()
            if current is None or current.rules_started:
                current = _Group(agents=[], rules=[])
                groups.append(current)
            if normalized_agent not in current.agents:
                current.agents.append(normalized_agent)
            continue
        if field in {"allow", "disallow"}:
            if current is None or not current.agents:
                _add_diagnostic(diagnostics, f"LINE_{line_number}_RULE_WITHOUT_AGENT")
                continue
            current.rules_started = True
            if not value:
                continue
            normalized_pattern, valid = _normalize_octets(value, allow_rule_tokens=True)
            if not valid or not normalized_pattern.startswith("/"):
                _add_diagnostic(diagnostics, f"LINE_{line_number}_INVALID_RULE")
                continue
            current.rules.append(RobotsRule(field, normalized_pattern))
            continue
        if field == "sitemap":
            if value and len(value) <= 500:
                sitemaps.add(value)
            elif value:
                _add_diagnostic(diagnostics, f"LINE_{line_number}_SITEMAP_TOO_LONG")
            continue

    merged: dict[str, set[RobotsRule]] = {}
    for group in groups:
        for agent in group.agents:
            merged.setdefault(agent, set()).update(group.rules)
    normalized_groups = tuple(
        (agent, tuple(sorted(rules))) for agent, rules in sorted(merged.items())
    )
    semantic_payload = [
        {
            "user_agent": agent,
            "rules": [[rule.directive, rule.pattern] for rule in rules],
        }
        for agent, rules in normalized_groups
    ]
    semantic_hash = hashlib.sha256(
        json.dumps(semantic_payload, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    broad_blocked = _is_broad_blocked(normalized_groups)
    rule_count = sum(len(rules) for _agent, rules in normalized_groups)
    summary_rules: list[dict[str, object]] = []
    for agent, rules in normalized_groups:
        if len(summary_rules) >= MAX_SUMMARY_RULES:
            break
        room = MAX_SUMMARY_RULES - len(summary_rules)
        summary_rules.extend(
            {
                "user_agent": agent,
                "directive": rule.directive,
                "pattern": rule.pattern[:MAX_SUMMARY_PATTERN_LENGTH],
                "pattern_truncated": len(rule.pattern) > MAX_SUMMARY_PATTERN_LENGTH,
            }
            for rule in rules[:room]
        )
    if meaningful_lines == 0:
        parse_status: ParseStatus = "EMPTY"
    elif not normalized_groups:
        parse_status = "INVALID"
    elif diagnostics:
        parse_status = "VALID_WITH_WARNINGS"
    else:
        parse_status = "VALID"
    summary: dict[str, object] = {
        "normalizer_version": ROBOTS_NORMALIZER_VERSION,
        "semantic_hash": semantic_hash,
        "group_count": len(normalized_groups),
        "rule_count": rule_count,
        "broad_blocked": broad_blocked,
        "rules": summary_rules,
        "rules_truncated": rule_count > len(summary_rules),
        "sitemaps": sorted(sitemaps)[:20],
        "sitemaps_truncated": len(sitemaps) > 20,
        "diagnostics": diagnostics,
    }
    return RobotsParseResult(
        parse_status=parse_status,
        semantic_hash=semantic_hash,
        groups=normalized_groups,
        broad_blocked=broad_blocked,
        diagnostics=tuple(diagnostics),
        summary=summary,
    )


def _add_diagnostic(diagnostics: list[str], code: str) -> None:
    if len(diagnostics) < MAX_DIAGNOSTICS:
        diagnostics.append(code[:200])


def _normalize_octets(value: str, *, allow_rule_tokens: bool) -> tuple[str, bool]:
    normalized: list[str] = []
    valid = True
    index = 0
    while index < len(value):
        character = value[index]
        if character == "%":
            if index + 2 >= len(value) or any(
                digit not in _HEX_DIGITS for digit in value[index + 1 : index + 3]
            ):
                valid = False
                normalized.append("%25")
                index += 1
                continue
            octet = int(value[index + 1 : index + 3], 16)
            decoded = chr(octet)
            normalized.append(decoded if decoded in _UNRESERVED else f"%{octet:02X}")
            index += 3
            continue
        if allow_rule_tokens and character == "*":
            normalized.append(character)
        elif allow_rule_tokens and character == "$" and index == len(value) - 1:
            normalized.append(character)
        elif character.isascii() and 0x21 <= ord(character) <= 0x7E:
            normalized.append(character)
        else:
            normalized.extend(f"%{octet:02X}" for octet in character.encode("utf-8"))
        index += 1
    return "".join(normalized), valid


def _rule_matches(pattern: str, path_and_query: str) -> bool:
    normalized_path, _valid = _normalize_octets(path_and_query, allow_rule_tokens=False)
    end_anchored = pattern.endswith("$")
    core = pattern[:-1] if end_anchored else pattern
    if not end_anchored:
        core += "*"
    pattern_index = 0
    path_index = 0
    last_star = -1
    star_path_index = -1
    while path_index < len(normalized_path):
        if pattern_index < len(core) and core[pattern_index] == normalized_path[path_index]:
            pattern_index += 1
            path_index += 1
        elif pattern_index < len(core) and core[pattern_index] == "*":
            last_star = pattern_index
            star_path_index = path_index
            pattern_index += 1
        elif last_star >= 0:
            pattern_index = last_star + 1
            star_path_index += 1
            path_index = star_path_index
        else:
            return False
    while pattern_index < len(core) and core[pattern_index] == "*":
        pattern_index += 1
    return pattern_index == len(core)


def _rule_specificity(pattern: str) -> int:
    core = pattern[:-1] if pattern.endswith("$") else pattern
    count = 0
    index = 0
    while index < len(core):
        if core[index] == "*":
            index += 1
        elif core[index] == "%" and index + 2 < len(core):
            count += 1
            index += 3
        else:
            count += len(core[index].encode("utf-8"))
            index += 1
    return count


def _is_broad_blocked(
    groups: tuple[tuple[str, tuple[RobotsRule, ...]], ...],
) -> bool:
    wildcard_rules = next((rules for agent, rules in groups if agent == "*"), ())
    return RobotsRule("disallow", "/") in wildcard_rules and not any(
        rule.directive == "allow" and rule.pattern for rule in wildcard_rules
    )
