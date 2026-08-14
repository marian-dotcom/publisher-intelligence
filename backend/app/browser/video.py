from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlsplit

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page

from app.browser.contracts import (
    CollectorResult,
    CollectorStatus,
    NetworkObservation,
    VideoPlayerObservation,
)

VIDEO_COLLECTOR_VERSION = "video-b7-v1"
MAX_PLAYERS = 100
_VAST_PATH_PATTERN = re.compile(r"(?:^|[/_.-])(vast|vmap|video-?ad|ad-?tag)(?:[/_.-]|$)")
_MEDIA_EXTENSIONS = (
    ".m3u8",
    ".m4s",
    ".mp4",
    ".mpd",
    ".ogg",
    ".ogv",
    ".ts",
    ".webm",
)

_INIT_SCRIPT = r"""
(() => {
  const state = {
    schema: "pi-video-b7/v1",
    records: [],
    byElement: new WeakMap(),
    errors: [],
  };
  window.__piVideoB7 = state;

  const structuralPath = (element) => {
    const segments = [];
    let current = element;
    while (current && current.nodeType === 1 && segments.length < 12) {
      const tag = String(current.tagName || "unknown").toLowerCase().slice(0, 30);
      let index = 1;
      let sibling = current.previousElementSibling;
      while (sibling) {
        if (String(sibling.tagName || "").toLowerCase() === tag) index += 1;
        sibling = sibling.previousElementSibling;
      }
      segments.push(`${tag}:nth-of-type(${Math.min(index, 1000)})`);
      if (tag === "html") break;
      current = current.parentElement;
    }
    return segments.reverse().join(">").slice(0, 1000);
  };

  const visible = (element) => {
    try {
      const style = getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return style.display !== "none" && style.visibility !== "hidden" &&
        Number(style.opacity || 1) > 0 && rect.width > 0 && rect.height > 0 &&
        rect.bottom > 0 && rect.right > 0 &&
        rect.top < window.innerHeight && rect.left < window.innerWidth;
    } catch (_) { return null; }
  };

  const positionedContainer = (element) => {
    let current = element;
    for (let depth = 0; current && depth < 8; depth += 1) {
      try {
        const position = getComputedStyle(current).position;
        if (position === "fixed" || position === "sticky") return current;
      } catch (_) {}
      current = current.parentElement;
    }
    return element.parentElement || element;
  };

  const dismissPresent = (scope) => {
    try {
      const candidates = scope.querySelectorAll("button,[role='button']");
      for (const candidate of Array.from(candidates).slice(0, 100)) {
        const label = String(
          candidate.getAttribute("aria-label") || candidate.getAttribute("title") ||
          candidate.textContent || ""
        ).trim().slice(0, 100);
        if (/(^|\b)(close|dismiss|inchide|închide)(\b|$)|^[x\u00d7]$/i.test(label)) return true;
      }
    } catch (_) {}
    return null;
  };

  const ensure = (video) => {
    let record = state.byElement.get(video);
    if (record) return record;
    if (state.records.length >= 100) return null;
    record = {
      element: video,
      structuralPath: structuralPath(video),
      present: true,
      visible: null,
      sticky: false,
      fixed: false,
      autoplay: null,
      muted: null,
      controlsPresent: null,
      dismissControlPresent: null,
      widthPx: null,
      heightPx: null,
      playbackStarted: false,
      sawInline: false,
    };
    state.byElement.set(video, record);
    state.records.push(record);
    const markPlayback = () => { record.playbackStarted = true; };
    try {
      video.addEventListener("play", markPlayback, {passive: true});
      video.addEventListener("playing", markPlayback, {passive: true});
      video.addEventListener("timeupdate", () => {
        try { if (video.currentTime > 0) markPlayback(); } catch (_) {}
      }, {passive: true});
    } catch (_) {}
    return record;
  };

  const update = (record) => {
    const video = record.element;
    try {
      record.present = Boolean(video && video.isConnected);
      if (!record.present) return;
      const rect = video.getBoundingClientRect();
      const scope = positionedContainer(video);
      const position = getComputedStyle(scope).position;
      const fixedNow = position === "fixed";
      const stickyNow = position === "sticky";
      if (!fixedNow && !stickyNow) record.sawInline = true;
      record.fixed = record.fixed || fixedNow;
      record.sticky = record.sticky || stickyNow ||
        (fixedNow && record.sawInline && window.scrollY > 0);
      record.visible = visible(video);
      record.autoplay = Boolean(video.autoplay);
      record.muted = Boolean(video.muted || video.defaultMuted || video.volume === 0);
      record.controlsPresent = video.controls ? true : null;
      record.dismissControlPresent = dismissPresent(scope);
      record.widthPx = Number.isFinite(rect.width) && rect.width >= 0
        ? Math.min(rect.width, 100000) : null;
      record.heightPx = Number.isFinite(rect.height) && rect.height >= 0
        ? Math.min(rect.height, 100000) : null;
      if ((!video.paused && !video.ended) || video.currentTime > 0) {
        record.playbackStarted = true;
      }
    } catch (_) {
      if (state.errors.length < 20) state.errors.push("PLAYER_SAMPLE_ERROR");
    }
  };

  const sample = () => {
    try {
      for (const video of Array.from(document.querySelectorAll("video")).slice(0, 100)) {
        ensure(video);
      }
      for (const record of state.records) update(record);
    } catch (_) {
      if (state.errors.length < 20) state.errors.push("PLAYER_DISCOVERY_ERROR");
    }
  };

  state.snapshot = () => {
    sample();
    return {
      schema: state.schema,
      players: state.records.slice(0, 100).map(record => ({
        structural_path: record.structuralPath,
        present: record.present,
        visible: record.visible,
        sticky: record.sticky,
        fixed: record.fixed,
        autoplay: record.autoplay,
        muted: record.muted,
        controls_present: record.controlsPresent,
        dismiss_control_present: record.dismissControlPresent,
        width_px: record.widthPx,
        height_px: record.heightPx,
        playback_started: record.playbackStarted,
      })),
      errors: state.errors.slice(0, 20),
    };
  };

  sample();
  let attempts = 0;
  const timer = setInterval(() => {
    attempts += 1;
    sample();
    if (attempts >= 600) clearInterval(timer);
  }, 100);
})();
"""


@dataclass(frozen=True, slots=True)
class VideoNetworkEvidence:
    vast_request_count: int
    vast_error_count: int
    media_request_count: int

    @property
    def observed(self) -> bool:
        return self.vast_request_count > 0 or self.media_request_count > 0


@dataclass(frozen=True, slots=True)
class VideoCollection:
    present: bool
    limitations: list[str]
    players: list[VideoPlayerObservation]
    network: VideoNetworkEvidence
    result: CollectorResult


def video_player_stable_key(structural_path: str) -> str:
    digest = hashlib.sha256(structural_path.encode("utf-8")).hexdigest()
    return f"video-player|dom|{digest}"


def _is_vast_path(path: str) -> bool:
    return _VAST_PATH_PATTERN.search(path.lower()) is not None


def _is_media_path(path: str) -> bool:
    lowered = path.lower()
    return any(lowered.endswith(extension) for extension in _MEDIA_EXTENSIONS)


def summarize_video_network(observations: list[NetworkObservation]) -> VideoNetworkEvidence:
    vast_requests = 0
    vast_errors = 0
    media_requests = 0
    for observation in observations:
        path = urlsplit(observation.url).path[:2_000]
        is_vast = _is_vast_path(path)
        is_media = observation.resource_type == "media" or _is_media_path(path)
        if is_vast:
            vast_requests += 1
            if observation.error_text is not None or (
                observation.status is not None and observation.status >= 400
            ):
                vast_errors += 1
        if is_media and not is_vast:
            media_requests += 1
    return VideoNetworkEvidence(
        vast_request_count=min(vast_requests, 10_000),
        vast_error_count=min(vast_errors, 10_000),
        media_request_count=min(media_requests, 10_000),
    )


def _boolean(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return None
    return min(float(value), 100_000.0)


def _structural_path(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    result = value.strip()[:1_000]
    if not result or not result.split(">")[-1].startswith("video:nth-of-type("):
        return None
    segment = r"[a-z][a-z0-9-]{0,29}:nth-of-type\([1-9][0-9]{0,3}\)"
    if not re.fullmatch(rf"{segment}(?:>{segment})*", result):
        return None
    return result


def parse_video_snapshot(
    raw: object,
    observations: list[NetworkObservation],
) -> tuple[list[VideoPlayerObservation], VideoNetworkEvidence, list[str], int]:
    payload = raw if isinstance(raw, dict) else {}
    network = summarize_video_network(observations)
    raw_players = payload.get("players")
    parsed: list[dict[str, object]] = []
    if isinstance(raw_players, list):
        for item in raw_players[:MAX_PLAYERS]:
            if not isinstance(item, dict):
                continue
            path = _structural_path(item.get("structural_path"))
            present = _boolean(item.get("present"))
            if path is None or present is None:
                continue
            parsed.append(
                {
                    "stable_key": video_player_stable_key(path),
                    "present": present,
                    "visible": _boolean(item.get("visible")),
                    "sticky": _boolean(item.get("sticky")),
                    "fixed": _boolean(item.get("fixed")),
                    "autoplay": _boolean(item.get("autoplay")),
                    "muted": _boolean(item.get("muted")),
                    "controls_present": _boolean(item.get("controls_present")),
                    "dismiss_control_present": _boolean(item.get("dismiss_control_present")),
                    "width_px": _number(item.get("width_px")),
                    "height_px": _number(item.get("height_px")),
                    "playback_started": _boolean(item.get("playback_started")),
                }
            )

    unambiguous = len(parsed) == 1
    players = []
    for item in parsed:
        players.append(
            VideoPlayerObservation(
                stable_key=str(item["stable_key"]),
                present=bool(item["present"]),
                visible=item["visible"] if isinstance(item["visible"], bool) else None,
                sticky=item["sticky"] if isinstance(item["sticky"], bool) else None,
                fixed=item["fixed"] if isinstance(item["fixed"], bool) else None,
                autoplay=item["autoplay"] if isinstance(item["autoplay"], bool) else None,
                muted=item["muted"] if isinstance(item["muted"], bool) else None,
                controls_present=(
                    item["controls_present"] if isinstance(item["controls_present"], bool) else None
                ),
                dismiss_control_present=(
                    item["dismiss_control_present"]
                    if isinstance(item["dismiss_control_present"], bool)
                    else None
                ),
                width_px=(
                    float(item["width_px"])
                    if isinstance(item["width_px"], (int, float))
                    and not isinstance(item["width_px"], bool)
                    else None
                ),
                height_px=(
                    float(item["height_px"])
                    if isinstance(item["height_px"], (int, float))
                    and not isinstance(item["height_px"], bool)
                    else None
                ),
                vast_request_count=network.vast_request_count if unambiguous else 0,
                vast_error_count=network.vast_error_count if unambiguous else 0,
                media_request_count=network.media_request_count if unambiguous else 0,
                playback_started=(
                    item["playback_started"] if isinstance(item["playback_started"], bool) else None
                ),
            )
        )
    limitations = ["vast_payload_not_inspected"] if network.vast_request_count else []
    if network.observed and not players:
        limitations.append("video_network_player_not_observable")
    elif network.observed and len(players) > 1:
        limitations.append("video_network_player_attribution_ambiguous")
    errors = payload.get("errors")
    error_count = len(errors[:20]) if isinstance(errors, list) else 0
    return sorted(players, key=lambda item: item.stable_key), network, limitations, error_count


class VideoPlayerCollector:
    async def attach(self, page: Page) -> None:
        await page.add_init_script(_INIT_SCRIPT)

    async def collect(
        self,
        page: Page,
        observations: list[NetworkObservation],
    ) -> VideoCollection:
        started_at = datetime.now(UTC)
        network = summarize_video_network(observations)
        try:
            raw = await page.evaluate(
                "() => window.__piVideoB7 && window.__piVideoB7.snapshot "
                "? window.__piVideoB7.snapshot() : null"
            )
            players, network, limitations, error_count = parse_video_snapshot(raw, observations)
            observable = bool(players)
            present = any(item.present for item in players)
            status: CollectorStatus = (
                "OK" if observable else "NOT_OBSERVABLE" if network.observed else "NOT_PRESENT"
            )
            return VideoCollection(
                present=present,
                limitations=limitations,
                players=players,
                network=network,
                result=CollectorResult(
                    collector_type="VIDEO_PLAYER",
                    collector_version=VIDEO_COLLECTOR_VERSION,
                    status=status,
                    started_at=started_at,
                    completed_at=datetime.now(UTC),
                    summary={
                        "player_count": len(players),
                        "present_player_count": len([item for item in players if item.present]),
                        "sticky_player_count": len([item for item in players if item.sticky]),
                        "playback_started_count": len(
                            [item for item in players if item.playback_started]
                        ),
                        "vast_request_count": network.vast_request_count,
                        "vast_http_error_count": network.vast_error_count,
                        "media_request_count": network.media_request_count,
                        "observer_error_count": error_count,
                        "limitations": limitations,
                    },
                ),
            )
        except PlaywrightError:
            return VideoCollection(
                present=False,
                limitations=[],
                players=[],
                network=network,
                result=CollectorResult(
                    collector_type="VIDEO_PLAYER",
                    collector_version=VIDEO_COLLECTOR_VERSION,
                    status="ERROR",
                    started_at=started_at,
                    completed_at=datetime.now(UTC),
                    summary={
                        "vast_request_count": network.vast_request_count,
                        "vast_http_error_count": network.vast_error_count,
                        "media_request_count": network.media_request_count,
                    },
                    error_code="PLAYWRIGHT_ERROR",
                    error_message="Video player snapshot failed",
                ),
            )
