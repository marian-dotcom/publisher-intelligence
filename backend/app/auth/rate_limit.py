"""In-memory rate limiter for auth-sensitive endpoints (EP-027, F-006).

Conservative per-process in-memory rate limiting suitable for the single-host
Limited Pilot deployment. No external dependencies (no Redis/Celery).

Client identity: X-Real-IP header (set by Next.js trusted-edge proxy) with
fallback to request.client.host. In test environments rate limiting is disabled.
"""

import logging
import time
from dataclasses import dataclass, field

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

CLIENT_IP_HEADER = "X-Real-IP"


@dataclass
class RateLimitStore:
    """In-memory fixed-window rate limiter per client key."""

    _counts: dict[str, list[float]] = field(default_factory=dict)
    _last_cleanup: float = field(default=0.0)
    _cleanup_interval: float = 60.0

    def is_rate_limited(
        self,
        key: str,
        *,
        max_attempts: int,
        window_seconds: float,
    ) -> tuple[bool, float]:
        """Check rate limit and increment counter.

        Returns (is_limited, retry_after_seconds).
        """
        now = time.monotonic()

        # Periodic pruning of stale keys prevents unbounded dict growth
        # when many distinct IPs each appear once and never return.
        if now - self._last_cleanup >= self._cleanup_interval:
            self.cleanup(window_seconds)
            self._last_cleanup = now

        window_start = now - window_seconds

        timestamps = self._counts.get(key, [])
        self._counts[key] = [t for t in timestamps if t > window_start]

        if len(self._counts[key]) >= max_attempts:
            oldest = self._counts[key][0]
            retry_after = oldest + window_seconds - now
            return True, max(retry_after, 0.0)

        self._counts.setdefault(key, []).append(now)
        return False, 0.0

    def clear(self, key: str) -> None:
        """Clear rate limit counter for key (e.g. on successful login)."""
        self._counts.pop(key, None)

    def cleanup(self, window_seconds: float) -> int:
        """Remove expired entries. Returns number of keys removed."""
        now = time.monotonic()
        window_start = now - window_seconds
        before = len(self._counts)
        self._counts = {
            k: [t for t in v if t > window_start]
            for k, v in self._counts.items()
            if any(t > window_start for t in v)
        }
        return before - len(self._counts)


_rate_limit_store = RateLimitStore()


def get_rate_limit_store() -> RateLimitStore:
    return _rate_limit_store


def client_ip(request: Request) -> str:
    """Extract client IP from X-Real-IP header or direct connection."""
    forwarded = request.headers.get(CLIENT_IP_HEADER)
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def check_rate_limit(
    request: Request,
    *,
    max_attempts: int = 5,
    window_seconds: float = 60.0,
) -> None:
    """Check rate limit for the requesting client.

    Raises HTTPException 429 if rate limit exceeded.
    """
    from app.config.settings import get_settings

    settings = get_settings()
    if settings.environment == "test":
        return

    ip = client_ip(request)
    store = get_rate_limit_store()
    limited, retry_after = store.is_rate_limited(
        ip, max_attempts=max_attempts, window_seconds=window_seconds
    )

    if limited:
        logger.warning(
            "rate_limit_exceeded client_ip=%s endpoint=%s retry_after=%.1f",
            ip,
            request.url.path,
            retry_after,
        )
        raise HTTPException(
            status_code=429,
            detail="too many requests",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )


def clear_rate_limit_for_ip(request: Request) -> None:
    """Clear rate limit counter after successful auth."""
    ip = client_ip(request)
    get_rate_limit_store().clear(ip)
