import hashlib
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

SEO_COLLECTOR_VERSION = "seo-e1-v1"
MAX_CANONICAL_LENGTH = 2_048


@dataclass(frozen=True, slots=True)
class NormalizedSEO:
    title_hash: str | None
    meta_robots: str | None
    canonical_url: str | None

    def as_state(self) -> dict[str, object]:
        return {
            "normalizer_version": SEO_COLLECTOR_VERSION,
            "title_hash": self.title_hash,
            "meta_robots": self.meta_robots,
            "canonical_url": self.canonical_url,
        }


class _SEOParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_title = False
        self.title_parts: list[str] = []
        self.robots: list[str] = []
        self.canonical: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): (value or "") for key, value in attrs}
        if tag.lower() == "title":
            self.in_title = True
        elif tag.lower() == "meta" and values.get("name", "").strip().lower() == "robots":
            self.robots.append(values.get("content", ""))
        elif tag.lower() == "link":
            rel = {part.lower() for part in values.get("rel", "").split()}
            if "canonical" in rel and self.canonical is None:
                self.canonical = values.get("href", "").strip() or None

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)


def normalize_seo(html: str, *, final_url: str | None) -> NormalizedSEO:
    parser = _SEOParser()
    parser.feed(html)
    title = " ".join("".join(parser.title_parts).split())
    directives = sorted(
        {
            directive.strip().lower()
            for value in parser.robots
            for directive in value.split(",")
            if directive.strip()
        }
    )
    canonical = _normalize_url(parser.canonical, final_url)
    return NormalizedSEO(
        title_hash=hashlib.sha256(title.encode()).hexdigest() if title else None,
        meta_robots=",".join(directives)[:1_000] or None,
        canonical_url=canonical,
    )


def _normalize_url(value: str | None, base_url: str | None) -> str | None:
    if not value:
        return None
    absolute = urljoin(base_url or "", value.strip())
    parsed = urlsplit(absolute)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return None
    host = parsed.hostname.lower()
    port = parsed.port
    netloc = host if port is None else f"{host}:{port}"
    normalized = urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", parsed.query, ""))
    return normalized[:MAX_CANONICAL_LENGTH]
