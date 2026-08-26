"""EP-027 M1 — in-memory rate limiter unit tests."""

import time
from unittest.mock import patch

from app.auth.rate_limit import RateLimitStore, client_ip


class FakeRequest:
    def __init__(
        self,
        *,
        headers: dict[str, str] | None = None,
        client_host: str = "127.0.0.1",
    ) -> None:
        self.headers = headers or {}
        self.client = type("Client", (), {"host": client_host})()
        self.url = type("URL", (), {"path": "/auth/login"})()


class TestRateLimitStore:
    def test_allows_within_limit(self) -> None:
        store = RateLimitStore()
        for _ in range(5):
            limited, _ = store.is_rate_limited("10.0.0.1", max_attempts=5, window_seconds=60)
            assert not limited

    def test_blocks_on_sixth_attempt(self) -> None:
        store = RateLimitStore()
        for _ in range(5):
            limited, _ = store.is_rate_limited("10.0.0.1", max_attempts=5, window_seconds=60)
            assert not limited
        limited, retry_after = store.is_rate_limited("10.0.0.1", max_attempts=5, window_seconds=60)
        assert limited
        assert retry_after > 0

    def test_different_keys_independent(self) -> None:
        store = RateLimitStore()
        for _ in range(5):
            store.is_rate_limited("10.0.0.1", max_attempts=5, window_seconds=60)
        limited, _ = store.is_rate_limited("10.0.0.2", max_attempts=5, window_seconds=60)
        assert not limited

    def test_clear_resets_counter(self) -> None:
        store = RateLimitStore()
        for _ in range(5):
            store.is_rate_limited("10.0.0.1", max_attempts=5, window_seconds=60)
        store.clear("10.0.0.1")
        limited, _ = store.is_rate_limited("10.0.0.1", max_attempts=5, window_seconds=60)
        assert not limited

    def test_window_expiry_resets_counter(self) -> None:
        store = RateLimitStore()
        window = 60.0
        t0 = 1_000_000.0
        with patch("app.auth.rate_limit.time.monotonic", return_value=t0):
            for _ in range(5):
                limited, _ = store.is_rate_limited(
                    "10.0.0.1", max_attempts=5, window_seconds=window
                )
                assert not limited
        # Advance past the window.
        with patch("app.auth.rate_limit.time.monotonic", return_value=t0 + window + 1):
            limited, _ = store.is_rate_limited("10.0.0.1", max_attempts=5, window_seconds=window)
            assert not limited

    def test_one_off_ips_do_not_cause_unbounded_dict_growth(self) -> None:
        """REGRESSION: arbitrary one-off IPs must not grow the dict forever.

        Periodic cleanup prunes expired keys so the dict stays bounded.
        """
        store = RateLimitStore()
        store._cleanup_interval = 0.0  # cleanup on every call
        window = 60.0
        t0 = 1_000_000.0

        # Phase 1: 100 distinct IPs each appear once.
        with patch("app.auth.rate_limit.time.monotonic", return_value=t0):
            for i in range(100):
                store.is_rate_limited(f"10.0.0.{i}", max_attempts=5, window_seconds=window)
        assert len(store._counts) == 100

        # Phase 2: advance past window; cleanup prunes stale keys.
        with patch("app.auth.rate_limit.time.monotonic", return_value=t0 + window + 1):
            store.is_rate_limited("new-ip", max_attempts=5, window_seconds=window)
        # All 100 old keys expired and were pruned by cleanup.
        assert len(store._counts) == 1
        assert "new-ip" in store._counts

    def test_cleanup_removes_empty_keys(self) -> None:
        store = RateLimitStore()
        store._counts["10.0.0.1"] = []
        store._counts["10.0.0.2"] = [time.monotonic()]
        removed = store.cleanup(window_seconds=60)
        assert removed == 1
        assert "10.0.0.1" not in store._counts
        assert "10.0.0.2" in store._counts


class TestClientIp:
    def test_x_real_ip_header(self) -> None:
        req = FakeRequest(headers={"X-Real-IP": "203.0.113.1"})
        assert client_ip(req) == "203.0.113.1"  # type: ignore[arg-type]

    def test_x_real_ip_first_in_chain(self) -> None:
        req = FakeRequest(headers={"X-Real-IP": "203.0.113.1, 10.0.0.1"})
        assert client_ip(req) == "203.0.113.1"  # type: ignore[arg-type]

    def test_fallback_to_client_host(self) -> None:
        req = FakeRequest(client_host="172.18.0.2")
        assert client_ip(req) == "172.18.0.2"  # type: ignore[arg-type]

    def test_no_client_returns_unknown(self) -> None:
        req = FakeRequest()
        req.client = None
        assert client_ip(req) == "unknown"  # type: ignore[arg-type]

    def test_spoofed_x_real_ip_without_middleware_strip_is_trusted(self) -> None:
        """ADVERSARIAL: proves that a spoofed X-Real-IP header IS trusted by
        client_ip() when present — defense depends on middleware stripping it.

        frontend/middleware.ts explicitly deletes x-real-ip and x-forwarded-for
        before forwarding to the backend. If the middleware strip is removed,
        this test documents the resulting trust-boundary violation.
        """
        req = FakeRequest(
            headers={"X-Real-IP": "198.51.100.99"},
            client_host="10.0.0.1",
        )
        assert client_ip(req) == "198.51.100.99"  # type: ignore[arg-type]

    def test_absent_x_real_ip_falls_back_to_client_host(self) -> None:
        """Proves that when middleware strips X-Real-IP and no request.ip is
        available (fallback path), client_ip() uses the direct connection IP.
        """
        req = FakeRequest(client_host="10.0.0.1")
        assert client_ip(req) == "10.0.0.1"  # type: ignore[arg-type]
