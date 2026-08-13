import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit

from app.browser.contracts import JavaScriptError, NetworkObservation
from app.browser.security import canonical_hostname

DOM_NORMALIZER_VERSION = "dom-b3-v1"
DEPENDENCY_NORMALIZER_VERSION = "dependency-b3-v1"
ERROR_NORMALIZER_VERSION = "js-error-b3-v1"

MAX_DOM_NODES = 20_000
MAX_DOM_DEPTH = 100
MAX_ATTRIBUTES_PER_NODE = 20
MAX_IDENTITY_COUNT = 2_000

_UUID_OR_HEX = re.compile(r"(?i)(?:[0-9a-f]{8}-[0-9a-f-]{27,}|\b[0-9a-f]{12,}\b)")
_LONG_NUMBER = re.compile(r"\d{4,}")
_PATH_ID = re.compile(r"^(?:\d+|[0-9a-f]{12,}|[0-9a-f-]{32,})$", re.IGNORECASE)
_SPACE = re.compile(r"\s+")
_SAFE_TOKEN = re.compile(r"[^a-zA-Z0-9_:-]+")

_VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}
_IGNORED_TAGS = {"noscript"}
_SAFE_ATTRS = {
    "aria-hidden",
    "data-ad-unit",
    "data-testid",
    "defer",
    "hidden",
    "id",
    "itemprop",
    "name",
    "property",
    "rel",
    "role",
    "type",
}


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def state_hash(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _volatile(value: str) -> str:
    result = _UUID_OR_HEX.sub(":token", value)
    result = _LONG_NUMBER.sub(":number", result)
    return _SPACE.sub(" ", result).strip()[:300]


def _safe_tokens(value: str) -> str:
    tokens = []
    for raw in _SPACE.split(value.strip()):
        token = _SAFE_TOKEN.sub("", _volatile(raw))[:100]
        if token:
            tokens.append(token)
    return " ".join(sorted(set(tokens))[:20])


def path_family(path: str) -> str:
    parts = []
    for part in path.split("/"):
        if not part:
            continue
        cleaned = part[:120]
        parts.append(":id" if _PATH_ID.fullmatch(cleaned) else _volatile(cleaned))
    result = "/" + "/".join(parts) if parts else "/"
    if len(result) > 500:
        digest = hashlib.sha256(result.encode()).hexdigest()[:16]
        return f"{result[:480]}~{digest}"
    return result


def dependency_identity(url: str, resource_type: str) -> dict[str, str] | None:
    parsed = urlsplit(url)
    if not parsed.hostname:
        return None
    try:
        host = canonical_hostname(parsed.hostname)
    except ValueError:
        return None
    family = path_family(parsed.path)
    normalized_type = resource_type.lower()[:50] or "other"
    return {
        "stable_key": f"{host}|{family}|{normalized_type}",
        "host": host,
        "path_family": family,
        "resource_type": normalized_type,
        "category": dependency_category(host, family),
    }


def dependency_category(host: str, path: str) -> str:
    value = f"{host}{path}".lower()
    rules = (
        (("googlesyndication", "doubleclick", "gampad", "securepubads"), "GOOGLE_AD_SERVING"),
        (("prebid", "openrtb", "bidder", "ssp"), "HEADER_BIDDING_SSP"),
        (("consent", "cmp", "privacy", "quantcast", "didomi"), "CMP_PRIVACY"),
        (("analytics", "google-analytics", "gtag", "segment"), "ANALYTICS"),
        (("player", "video", "vast", "ima3"), "VIDEO_PLAYER"),
        (("cdn", "static", "assets"), "CDN"),
    )
    for needles, category in rules:
        if any(needle in value for needle in needles):
            return category
    return "UNKNOWN"


class _StructuralHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.nodes: list[dict[str, object]] = []
        self.depth = 0
        self.truncated = False
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()[:50]
        if normalized_tag in _IGNORED_TAGS:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if len(self.nodes) >= MAX_DOM_NODES:
            self.truncated = True
            return
        safe_attrs = self._attributes(normalized_tag, attrs)
        node: dict[str, object] = {
            "depth": min(self.depth, MAX_DOM_DEPTH),
            "tag": normalized_tag,
        }
        if safe_attrs:
            node["attributes"] = safe_attrs
        self.nodes.append(node)
        if normalized_tag not in _VOID_TAGS:
            self.depth = min(self.depth + 1, MAX_DOM_DEPTH)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in _VOID_TAGS:
            self.depth = max(0, self.depth - 1)

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in _IGNORED_TAGS:
            self._ignored_depth = max(0, self._ignored_depth - 1)
            return
        if self._ignored_depth or normalized_tag in _VOID_TAGS:
            return
        self.depth = max(0, self.depth - 1)

    @staticmethod
    def _attributes(tag: str, attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        result: dict[str, str] = {}
        raw = {name.lower(): value or "" for name, value in attrs}
        for name in sorted(raw):
            if len(result) >= MAX_ATTRIBUTES_PER_NODE:
                break
            value = raw[name]
            if name in {"class", "id"}:
                normalized = _safe_tokens(value)
            elif name in _SAFE_ATTRS:
                normalized = _volatile(value.lower())
            elif name == "style":
                normalized = _structural_style(value)
            elif name in {"src", "href"} and tag in {"script", "iframe", "link"}:
                identity = dependency_identity(value, tag)
                normalized = identity["stable_key"] if identity else ""
            elif (
                name == "content"
                and tag == "meta"
                and raw.get("name", "").lower()
                in {
                    "robots",
                    "googlebot",
                }
            ):
                normalized = _volatile(value.lower())
            else:
                continue
            if normalized:
                result[name] = normalized
        return result


def _structural_style(value: str) -> str:
    retained: dict[str, str] = {}
    for declaration in value.split(";"):
        name, separator, raw_value = declaration.partition(":")
        if not separator:
            continue
        key = name.strip().lower()
        if key in {"display", "position", "visibility", "z-index"}:
            retained[key] = _volatile(raw_value.strip().lower())[:50]
    return ";".join(f"{key}:{retained[key]}" for key in sorted(retained))


def normalize_dom(html: str) -> dict[str, Any]:
    parser = _StructuralHTMLParser()
    parser.feed(html[:5_000_000])
    parser.close()
    structural = {
        "nodes": parser.nodes,
        "truncated": parser.truncated or len(html) > 5_000_000,
    }
    return {
        "normalizer_version": DOM_NORMALIZER_VERSION,
        "node_count": len(parser.nodes),
        "truncated": structural["truncated"],
        "sha256": state_hash(structural),
        "structure": structural,
    }


def normalize_scripts(urls: list[str]) -> dict[str, Any]:
    identities = []
    for url in urls:
        identity = dependency_identity(url, "script")
        if identity is not None:
            identities.append(identity)
    unique = {item["stable_key"]: item for item in identities}
    bounded = [unique[key] for key in sorted(unique)[:MAX_IDENTITY_COUNT]]
    return {
        "normalizer_version": DEPENDENCY_NORMALIZER_VERSION,
        "identities": bounded,
        "sha256": state_hash([item["stable_key"] for item in bounded]),
        "truncated": len(unique) > MAX_IDENTITY_COUNT,
    }


def normalize_network(observations: list[NetworkObservation]) -> dict[str, Any]:
    aggregates: dict[str, dict[str, Any]] = {}
    status_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for item in observations:
        identity = dependency_identity(item.url, item.resource_type)
        if identity is None:
            continue
        key = identity["stable_key"]
        state = aggregates.setdefault(
            key,
            {
                **identity,
                "request_count": 0,
                "failure_count": 0,
                "status_2xx": 0,
                "status_3xx": 0,
                "status_4xx": 0,
                "status_5xx": 0,
            },
        )
        state["request_count"] += 1
        if item.error_text:
            state["failure_count"] += 1
        if item.status is not None:
            family = f"status_{item.status // 100}xx"
            if family in state:
                state[family] += 1
            status_counts[key][str(item.status)] += 1
    bounded = []
    for key in sorted(aggregates)[:MAX_IDENTITY_COUNT]:
        state = aggregates[key]
        state["statuses"] = dict(sorted(status_counts[key].items()))
        bounded.append(state)
    hash_state = [
        {
            key: item[key]
            for key in (
                "stable_key",
                "request_count",
                "failure_count",
                "status_4xx",
                "status_5xx",
            )
        }
        for item in bounded
    ]
    return {
        "normalizer_version": DEPENDENCY_NORMALIZER_VERSION,
        "dependencies": bounded,
        "sha256": state_hash(hash_state),
        "truncated": len(aggregates) > MAX_IDENTITY_COUNT,
    }


@dataclass(frozen=True, slots=True)
class NormalizedError:
    fingerprint: str
    normalized_message: str
    source_host: str | None
    source_path: str | None
    count: int


def normalize_javascript_errors(errors: list[JavaScriptError]) -> dict[str, Any]:
    grouped: dict[str, NormalizedError] = {}
    counts: Counter[str] = Counter()
    for error in errors:
        message = _volatile(error.message.lower())[:500]
        source_host: str | None = None
        source_path: str | None = None
        if error.source:
            parsed = urlsplit(error.source)
            if parsed.hostname:
                try:
                    source_host = canonical_hostname(parsed.hostname)
                except ValueError:
                    source_host = None
            source_path = path_family(parsed.path) if parsed.path else None
        fingerprint = state_hash(
            {
                "version": ERROR_NORMALIZER_VERSION,
                "message": message,
                "source_host": source_host,
                "source_path": source_path,
            }
        )
        counts[fingerprint] += 1
        grouped[fingerprint] = NormalizedError(
            fingerprint=fingerprint,
            normalized_message=message,
            source_host=source_host,
            source_path=source_path,
            count=0,
        )
    items = [
        {
            "fingerprint": item.fingerprint,
            "normalized_message": item.normalized_message,
            "source_host": item.source_host,
            "source_path": item.source_path,
            "count": counts[fingerprint],
        }
        for fingerprint, item in sorted(grouped.items())[:MAX_IDENTITY_COUNT]
    ]
    return {
        "normalizer_version": ERROR_NORMALIZER_VERSION,
        "errors": items,
        "sha256": state_hash([item["fingerprint"] for item in items]),
        "truncated": len(grouped) > MAX_IDENTITY_COUNT,
    }


def normalized_dom_artifact(value: dict[str, Any]) -> bytes:
    return _canonical_json(value)
