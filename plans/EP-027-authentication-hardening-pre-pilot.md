# EP-027 — Authentication Hardening Pre-Limited-Pilot

**Status:** COMPLETE
**Owner:** Codex / Engineering
**Created:** 2026-08-27
**Updated:** 2026-08-27
**Accepted checkpoint:** `108f4d01848bd636be61f892efab898666ab0328`
**Target milestone:** Pre-Limited-Pilot security hardening (EP-026 M8 findings F-002, F-003, F-005, F-006)
**MVP scope impact:** NO — hardening of already-built auth; no new product behavior
**New infrastructure category:** NO — in-memory rate limiter, no Redis/Celery/new services

## Progress

- [x] M0 — Design decisions and reconciliation
- [x] M1 — Rate limiting (F-006)
- [x] M2 — Logout cookie hygiene (F-002)
- [x] M3 — Timing-safe CSRF comparison (F-003)
- [x] M4 — SameSite regression test (F-005)
- [x] M5 — Canonical and boundary reconciliation

## 1. Purpose and User Outcome

After this plan completes, the authentication layer satisfies pre-Limited-Pilot security
requirements: rate limiting protects against credential brute-force, session teardown is clean,
CSRF comparison is timing-safe, and cookie attributes have automated regression guards. No new
product behavior is added; this is pure security hardening of already-built auth.

## 2. Scope

### In

- Rate limiting on POST /auth/login (F-006)
- pi_csrf cookie cleared on logout (F-002)
- hmac.compare_digest for CSRF hash comparison (F-003)
- SameSite=lax automated regression test (F-005)
- README boundary summary reconciliation

### Out

- RBAC, CAPTCHA, fingerprinting, external IdP, Redis/Celery, auth UI redesign
- Rate limiting on non-auth endpoints (future scope)
- F-007 remediation (separate follow-up)

## 3. Canonical References

Read: AGENTS.md, SECURITY.md, DECISIONS.md, ARCHITECTURE.md, DATA_MODEL.md, PLANS.md

Relevant invariants:

- SECURITY.md s201: auth cookies MUST be Secure=True outside local/test
- SECURITY.md s95: rate-limiting required on login-sensitive endpoints
- EP-026 M8 F-006: "must be resolved before Limited Pilot authorization"
- EP-026 M8 F-002: stale CSRF cookie after logout
- EP-026 M8 F-003: non-timing-safe CSRF comparison
- EP-026 M8 F-005: no SameSite regression test

## 4. Current State

Auth implementation (EP-025a COMPLETE):

- routes.py: login, logout, session; _set_session_cookies sets both cookies with SameSite=lax
- service.py: verify_csrf uses hmac.compare_digest (F-003 remediated)
- dependencies.py: SESSION_COOKIE = "pi_session", CSRF_HEADER = "X-CSRF-Token", CSRF_COOKIE = "pi_csrf"
- security.py: SHA-256 hash, Argon2id, CSPRNG tokens
- settings.py: cookie_secure field with fail-closed validator
- rate_limit.py: in-memory RateLimitStore with periodic stale-key cleanup, client_ip(), check_rate_limit()

Deployment trust boundary (final):

```text
Internet → Caddy (public TLS edge, loopback-only Next.js)
  → Next.js (frontend proxy, reads Caddy X-Forwarded-For)
    → FastAPI backend (single-host Limited Pilot)
```

Client identity semantics:

- Caddy is the ONLY trusted public ingress and sets X-Forwarded-For.
- Next.js middleware reads X-Forwarded-For, validates the value is a well-formed IPv4 or IPv6 address, and strips ALL forwarding headers (x-real-ip, x-forwarded-for, x-forwarded-host, x-forwarded-proto).
- Next.js emits exactly ONE internal header: X-Real-IP containing the validated client IP.
- FastAPI reads X-Real-IP via client_ip() for the rate-limiting key.
- If the selected IP is missing or malformed, X-Real-IP is not set; FastAPI falls back to socket peer identity.
- Topology changes require this trust model to be revisited.

## 5. Target Behavior

Rate limiting:

- 5 failed logins from same client IP within 60s → HTTP 429 with Retry-After header
- Subsequent attempts within window → 429
- Window expires → counter resets, login allowed again
- Successful login → counter cleared for that key (allow recovery)
- No environment-based runtime bypass; integration tests reset the in-memory store through test fixtures (autouse `_clear_rate_limit_store` in `tests/integration/conftest.py`)

Logout:

- Both pi_session and pi_csrf cookies cleared with matching attributes

CSRF:

- verify_csrf uses hmac.compare_digest() instead of ==

SameSite:

- Existing test augmented to assert samesite=lax on both cookies

## 6. Architecture / Data Flow

```text
Rate Limiting:
  Internet → Caddy (X-Forwarded-For) → Next.js (validate + strip + X-Real-IP) → FastAPI /auth/login
     |
  client_ip(request) -> reads X-Real-IP; falls back to socket peer if missing/malformed
     |
  check_rate_limit(key, max_attempts, window) -> in-memory dict
     |
  429 if exceeded; proceed to AuthService.login if not

Logout:
  POST /auth/logout -> delete pi_session + pi_csrf cookies

CSRF:
  verify_csrf -> hmac.compare_digest(hash(presented), stored_hash)
```

## 7. Files and Modules Affected

Existing:

- backend/app/auth/routes.py — logout cookie cleanup (both cookies), rate limit on login
- backend/app/auth/service.py — hmac.compare_digest for CSRF
- backend/app/auth/dependencies.py — CSRF_COOKIE constant
- frontend/middleware.ts — Caddy trust boundary, isValidIpAddress(), header stripping, X-Real-IP
- backend/tests/unit/test_secure_cookie_gate.py — SameSite assertions
- backend/tests/integration/conftest.py — autouse _clear_rate_limit_store fixture
- README.md — boundary summary corrected

Created:

- backend/app/auth/rate_limit.py — in-memory rate limiter with periodic stale-key cleanup
- backend/tests/unit/test_auth_rate_limit.py — rate limiter unit tests (13 tests)
- backend/tests/unit/test_auth_rate_limit.py — deterministic mock-based time tests
- backend/tests/integration/test_auth_rate_limit_http.py — HTTP-layer rate limit integration tests (3 tests)
- frontend/tests/middleware.test.ts — trust boundary adversarial tests (8 tests)

## 8. Milestones

### M0 — Design decisions and reconciliation

Goal: Document rate-limiting design decisions; create branch.

Acceptance:

- [x] Design decisions documented in Decision Log
- [x] Branch created from HEAD 1d61c1b

### M1 — Rate limiting (F-006)

Goal: Implement in-memory rate limiting on POST /auth/login.

Implementation:

1. Create backend/app/auth/rate_limit.py with RateLimitStore, client_ip, check_rate_limit
2. Add CSRF_COOKIE constant to dependencies.py
3. Modify routes.py login endpoint: call check_rate_limit before auth service
4. Add Caddy trust boundary to frontend/middleware.ts: read X-Forwarded-For, validate IP format, strip all forwarding headers, emit X-Real-IP
5. Write unit tests for RateLimitStore (including deterministic mock-based time tests)
6. Write integration test for HTTP-layer rate limiting

Acceptance:

- [x] 5 failed logins from same IP → 429 on 6th attempt
- [x] 429 response includes Retry-After header
- [x] Successful login clears counter
- [x] Window expiry resets counter
- [x] Integration tests reset rate-limit store via shared autouse fixture (no environment bypass)
- [x] X-Real-IP set by Next.js middleware from validated Caddy X-Forwarded-For
- [x] No new dependencies added

### M2 — Logout cookie hygiene (F-002)

Goal: Clear pi_csrf cookie on logout with matching creation attributes.

Implementation:

1. Add response.delete_cookie(CSRF_COOKIE, path="/") after existing session cookie deletion
2. Match creation attributes on both delete calls (defense-in-depth)

Acceptance:

- [x] Logout clears both pi_session and pi_csrf
- [x] Both delete_cookie calls match creation attributes
- [x] Existing logout test still passes

### M3 — Timing-safe CSRF comparison (F-003)

Goal: Replace == with hmac.compare_digest() in verify_csrf.

Acceptance:

- [x] hmac.compare_digest used instead of ==
- [x] All existing CSRF tests pass

### M4 — SameSite regression test (F-005)

Goal: Add automated assertion that both cookies carry SameSite=lax.

Acceptance:

- [x] Test asserts samesite=lax on both cookies
- [x] Test would fail if samesite changed to "none"

### M5 — Canonical and boundary reconciliation

Goal: Fix README contradiction and update pilot-readiness runbook.

Implementation:

1. Fix README.md: remove "Home/Timeline UI" from excluded list (EP-025b implemented it)
2. Update pilot-readiness runbook with rate-limiting section

Acceptance:

- [x] README boundary summary accurate
- [x] Runbook updated with rate-limiting guidance

## 9. Final Acceptance Criteria

- [x] Rate limiting blocks brute-force on POST /auth/login
- [x] Logout clears both pi_session and pi_csrf cookies
- [x] CSRF comparison uses hmac.compare_digest
- [x] SameSite=lax has automated regression guard
- [x] All existing auth tests pass
- [x] README boundary summary accurate
- [x] No new infrastructure dependencies

## 10. Final Validation

All validation performed against accepted checkpoint `108f4d01848bd636be61f892efab898666ab0328`.

```bash
cd backend && uv run ruff check app tests
cd backend && uv run ruff format --check app tests
cd backend && uv run mypy app tests scripts migrations/env.py
cd backend && uv run pytest tests/unit                    # 364 passed
cd backend && uv run pytest tests/integration             # CI 33025776067 green
```

CI run `33025776067` on branch `agent/implement-ep-027`: all three jobs (backend, frontend, repository-safety) passed, including the full integration suite with rate limiting active and no environment bypass.

## 11. Test Cases

Happy path:

- Login succeeds within rate limit
- Logout clears both cookies
- CSRF validation works with timing-safe comparison

Failures:

- 6th failed login returns 429
- Rate limit resets after window expires
- Successful login clears rate limit counter

Regression:

- Changing samesite to "none" fails the new test
- Logout without clearing pi_csrf fails (was F-002)
- CSRF comparison with == instead of hmac.compare_digest fails (was F-003)

Trust boundary:

- Caddy X-Forwarded-For → X-Real-IP emitted to FastAPI
- Spoofed X-Forwarded-For from client is stripped
- Two concurrent clients get independent rate-limit buckets
- Missing or malformed X-Forwarded-For falls back to socket peer
- IPv6 addresses accepted and validated

## 12. Data / Migration Impact

None. No schema changes. Rate limiter state is in-memory only.

## 13. Security / Privacy Impact

Positive: closes four pre-pilot security gaps. Rate limiter stores only IP counters (no PII).
No new data collection. No tenant boundary changes.

## 14. Observability / Failure Handling

Rate limit 429 responses include Retry-After header. Rate limiter logs at WARNING level on
breach. In-memory state is process-local; API restart clears all counters; no cross-process
coordination is needed for the single-host Limited Pilot topology.

### Process-local limitation

- The rate-limit store is a plain Python dict, not shared across processes or API replicas.
- For Limited Pilot with one uvicorn worker this is acceptable.
- API restart clears all counters; brute-force protection resets until the next window fills.
- If scaled to multiple workers or replicas, a shared store (PostgreSQL or Redis) is required — this triggers an architecture review.
- Periodic stale-key cleanup (every 60s) prevents permanent one-off-IP accumulation.

## 15. Rollback Strategy

Revert the commit. Rate limiting is additive; removing it restores pre-EP-027 behavior.
Cookie cleanup and CSRF comparison changes are one-line reverts.

## 16. Known Risks

In-memory rate limiter does not share state across API processes. For single-host Limited Pilot
with one uvicorn worker this is acceptable. If scaled to multiple workers, a shared store
(PostgreSQL or Redis) would be needed.

## 17. Open Decisions

None. All design choices are constrained by the single-host Limited Pilot topology.

## 18. Decision Log

Date: 2026-08-27
Decision: In-memory rate limiter (dict + time), no external dependencies
Reason: Single-host deployment, one uvicorn process, simplest credible option
Alternatives: Redis (infrastructure), PostgreSQL-backed (complexity), slowapi (dependency)
Impact: No new infrastructure; adequate for Limited Pilot scale

Date: 2026-08-27
Decision: Client identity via Caddy → Next.js → FastAPI trust boundary
Reason: request.client.host in FastAPI always shows Next.js container IP; Caddy is the only
trusted public ingress. Next.js reads Caddy-supplied X-Forwarded-For, validates IP format,
strips all forwarding headers, emits exactly one X-Real-IP. FastAPI reads X-Real-IP for the
rate-limit key.
Alternatives: ProxyFix (adds dependency), request.ip (not available in Next.js 16.3.0)
Impact: Middleware gains trust-boundary logic; FastAPI reads X-Real-IP; topology changes require
this trust model to be revisited.

Date: 2026-08-27
Decision: Rate limit only POST /auth/login (5 attempts per 60s window)
Reason: Most critical auth-sensitive endpoint; conservative scope for pilot
Alternatives: Rate limit all state-changing endpoints (broader scope)
Impact: Focused protection; other endpoints can be added later

Date: 2026-08-27
Decision: Integration tests reset rate-limit store via shared autouse fixture; no environment bypass
Reason: CI sets ENVIRONMENT=test; an environment-based bypass would silently disable rate limiting
in the test suite. Shared conftest fixture provides deterministic per-test reset instead.
Alternatives: environment=="test" runtime bypass (removed in 108f4d0)
Impact: Rate limiter is always active; integration tests exercise real rate-limit code paths.

## 19. Discoveries / Surprises

- No rate limiting exists anywhere in the backend codebase (pre-EP-027)
- No proxy header handling exists (no ProxyFix, no X-Forwarded-For) (pre-EP-027)
- Uvicorn started without --proxy-headers flag
- pi_csrf cookie name is a hardcoded string, not a constant (pre-EP-027)
- README.md had a known contradiction (claims and denies Home/Timeline UI existence)
- Next.js 16.3.0 request.ip is undefined (property commented out in adapter)
- Caddy is the only public ingress in the Limited Pilot deployment topology
- CI sets ENVIRONMENT=test which triggered initial rate-limiter bypass removal

## 20. Progress Log

2026-08-27: M0 planning complete. Branch created.
2026-08-27: M1 complete. In-memory rate limiter on POST /auth/login. Trust boundary in middleware.
2026-08-27: M2 complete. Logout clears pi_session + pi_csrf with matching attributes.
2026-08-27: M3 complete. hmac.compare_digest for CSRF hash comparison.
2026-08-27: M4 complete. SameSite=lax regression test added.
2026-08-27: M5 complete. README boundary summary corrected.
2026-08-27: CI fix complete. Removed environment=test bypass; added autouse conftest fixture.
2026-08-27: EP-027 accepted at `108f4d01848bd636be61f892efab898666ab0328`. CI 33025776067 green.

## 21. Final Outcome / Retrospective

What shipped:

- In-memory rate limiter on POST /auth/login (5 attempts per 60s window, process-local)
- Caddy → Next.js → FastAPI client-IP trust boundary with header validation and stripping
- Logout clears both pi_session and pi_csrf cookies with matching attributes
- hmac.compare_digest for timing-safe CSRF hash comparison
- SameSite=lax regression test for both auth cookies
- README boundary summary corrected

What changed from original plan:

- Rate limit threshold is 5 attempts (plan said 5-6, chose 5 for maximum protection)
- No environment-based runtime bypass (CI fix commit 108f4d0 removed it)
- Integration tests share a common autouse fixture for rate-limit store reset instead
- Trust boundary uses Caddy X-Forwarded-For → validated → stripped → X-Real-IP (not request.ip)

Validation performed:

- 364 unit tests pass
- ruff check clean
- ruff format clean
- mypy full scope clean (265 files)
- CI run 33025776067: all three jobs green, full integration suite executed with rate limiting active

Known limitations:

- In-memory rate limiter does not share state across API processes (process-local)
- API restart clears all rate-limit counters
- Multiple API workers/replicas require shared state / architecture review
- Rate limiting only on POST /auth/login; other endpoints deferred

Follow-ups:

- Rate limiting on other auth-sensitive endpoints (future scope)
- Shared rate limit state if scaling to multiple API processes

Lessons for AGENTS/DECISIONS:

- Rate limiting should have been part of EP-025a (auth implementation)
- CSRF_COOKIE constant should have been introduced with the double-submit pattern
- Never use environment-based test bypasses for security-critical code; use shared test fixtures
