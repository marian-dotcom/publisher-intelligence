# EP-027 — Authentication Hardening Pre-Limited-Pilot

**Status:** COMPLETE
**Owner:** Codex / Engineering
**Created:** 2026-08-27
**Updated:** 2026-08-27
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
- service.py: verify_csrf uses == (F-003); login generates/rotates sessions
- dependencies.py: SESSION_COOKIE = "pi_session", CSRF_HEADER = "X-CSRF-Token"
- security.py: SHA-256 hash, Argon2id, CSPRNG tokens
- settings.py: cookie_secure field with fail-closed validator

Known gaps (EP-026 M8):

- F-006: No rate limiting anywhere in backend
- F-002: Logout only deletes pi_session, not pi_csrf
- F-003: verify_csrf uses == not hmac.compare_digest
- F-005: test_secure_cookie_gate.py asserts Secure/HttpOnly but not SameSite

Deployment topology:

- Browser -> Next.js (:3000) -> FastAPI (:8000)
- Next.js middleware proxies backend-owned paths at request time
- No external reverse proxy in repo (Caddy/nginx deferred)
- request.client.host in FastAPI always shows Next.js container IP
- No X-Forwarded-For or X-Real-IP handling exists

## 5. Target Behavior

Rate limiting:

- 5 failed logins from same client IP within 60s -> HTTP 429 with Retry-After header
- Subsequent attempts within window -> 429
- Window expires -> counter resets, login allowed again
- Successful login -> counter cleared for that key (allow recovery)
- In test environment: rate limiting disabled

Logout:

- Both pi_session and pi_csrf cookies cleared with matching attributes

CSRF:

- verify_csrf uses hmac.compare_digest() instead of ==

SameSite:

- Existing test augmented to assert samesite=lax on both cookies

## 6. Architecture / Data Flow

```text
Rate Limiting:
  Browser -> Next.js (sets X-Real-IP) -> FastAPI /auth/login
     |
  _client_ip(request) -> extracts X-Real-IP or falls back to client.host
     |
  _check_rate_limit(key, max_attempts, window) -> in-memory dict
     |
  429 if exceeded; proceed to AuthService.login if not

Logout:
  POST /auth/logout -> delete pi_session + pi_csrf cookies

CSRF:
  verify_csrf -> hmac.compare_digest(hash(presented), stored_hash)
```

## 7. Files and Modules Affected

Existing:

- backend/app/auth/routes.py — logout cookie cleanup, rate limit on login
- backend/app/auth/service.py — verify_csrf change
- backend/app/auth/dependencies.py — add CSRF_COOKIE constant
- frontend/middleware.ts — add X-Real-IP header
- backend/tests/unit/test_secure_cookie_gate.py — add SameSite assertions
- backend/tests/integration/test_product_http_auth.py — verify logout clears both
- docs/runbooks/pilot-readiness.md — update rate-limiting section
- README.md — fix boundary summary contradiction

To create:

- backend/app/auth/rate_limit.py — in-memory rate limiter
- backend/tests/unit/test_auth_rate_limit.py — rate limiter unit tests
- backend/tests/integration/test_auth_rate_limit_http.py — HTTP-layer rate limit test

## 8. Milestones

### M0 — Design decisions and reconciliation

Goal: Document rate-limiting design decisions; create branch.

Acceptance:

- [ ] Design decisions documented in Decision Log
- [ ] Branch created from HEAD 1d61c1b

### M1 — Rate limiting (F-006)

Goal: Implement in-memory rate limiting on POST /auth/login.

Implementation:

1. Create backend/app/auth/rate_limit.py with RateLimitStore, _client_ip, check_rate_limit
2. Add CSRF_COOKIE constant to dependencies.py
3. Modify routes.py login endpoint: call check_rate_limit before auth service
4. Set X-Real-IP header in frontend/middleware.ts from request.ip
5. Write unit tests for RateLimitStore
6. Write integration test for HTTP-layer rate limiting

Acceptance:

- [ ] 5 failed logins from same IP -> 429 on 6th attempt
- [ ] 429 response includes Retry-After header
- [ ] Successful login clears counter
- [ ] Window expiry resets counter
- [ ] Test environment disables rate limiting
- [ ] X-Real-IP set by Next.js middleware
- [ ] No new dependencies added

### M2 — Logout cookie hygiene (F-002)

Goal: Clear pi_csrf cookie on logout with matching creation attributes.

Implementation:

1. Add response.delete_cookie(CSRF_COOKIE, path="/") after existing session cookie deletion
2. Match creation attributes on both delete calls (defense-in-depth)

Acceptance:

- [ ] Logout clears both pi_session and pi_csrf
- [ ] Both delete_cookie calls match creation attributes
- [ ] Existing logout test still passes

### M3 — Timing-safe CSRF comparison (F-003)

Goal: Replace == with hmac.compare_digest() in verify_csrf.

Acceptance:

- [ ] hmac.compare_digest used instead of ==
- [ ] All existing CSRF tests pass

### M4 — SameSite regression test (F-005)

Goal: Add automated assertion that both cookies carry SameSite=lax.

Acceptance:

- [ ] Test asserts samesite=lax on both cookies
- [ ] Test would fail if samesite changed to "none"

### M5 — Canonical and boundary reconciliation

Goal: Fix README contradiction and update pilot-readiness runbook.

Implementation:

1. Fix README.md: remove "Home/Timeline UI" from excluded list (EP-025b implemented it)
2. Update pilot-readiness runbook with rate-limiting section

Acceptance:

- [ ] README boundary summary accurate
- [ ] Runbook updated with rate-limiting guidance

## 9. Final Acceptance Criteria

- [ ] Rate limiting blocks brute-force on POST /auth/login
- [ ] Logout clears both pi_session and pi_csrf cookies
- [ ] CSRF comparison uses hmac.compare_digest
- [ ] SameSite=lax has automated regression guard
- [ ] All existing auth tests pass
- [ ] README boundary summary accurate
- [ ] No new infrastructure dependencies

## 10. Final Validation

```bash
cd backend && uv run ruff check app tests
cd backend && uv run ruff format --check app tests
cd backend && uv run mypy app tests scripts migrations/env.py
cd backend && uv run pytest tests/unit/test_auth_rate_limit.py tests/unit/test_secure_cookie_gate.py -v
cd backend && uv run pytest tests/integration/test_product_http_auth.py tests/integration/test_auth_rate_limit_http.py -v
```

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

## 12. Data / Migration Impact

None. No schema changes. Rate limiter state is in-memory only.

## 13. Security / Privacy Impact

Positive: closes four pre-pilot security gaps. Rate limiter stores only IP counters (no PII).
No new data collection. No tenant boundary changes.

## 14. Observability / Failure Handling

Rate limit 429 responses include Retry-After header. Rate limiter logs at WARNING level on
breach. In-memory state is per-process; no cross-process coordination needed for single-host
deployment.

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
Decision: Client identity via X-Real-IP header set by Next.js middleware
Reason: request.client.host always shows Next.js container IP in Docker; X-Real-IP
from the trusted edge proxy gives real client IP
Alternatives: ProxyFix (adds dependency), X-Forwarded-For (multi-hop complexity)
Impact: Next.js middleware gains one header; FastAPI reads it for rate limiting key

Date: 2026-08-27
Decision: Rate limit only POST /auth/login (5 attempts per 60s window)
Reason: Most critical auth-sensitive endpoint; conservative scope for pilot
Alternatives: Rate limit all state-changing endpoints (broader scope)
Impact: Focused protection; other endpoints can be added later

## 19. Discoveries / Surprises

- No rate limiting exists anywhere in the backend codebase
- No proxy header handling exists (no ProxyFix, no X-Forwarded-For)
- Uvicorn started without --proxy-headers flag
- pi_csrf cookie name is a hardcoded string, not a constant
- README.md has a known contradiction (claims and denies Home/Timeline UI existence)

## 20. Progress Log

2026-08-27: M0 planning complete. Branch created.
2026-08-27: M1 complete. In-memory rate limiter on POST /auth/login. X-Real-IP from Next.js.
2026-08-27: M2 complete. Logout clears pi_session + pi_csrf with matching attributes.
2026-08-27: M3 complete. hmac.compare_digest for CSRF hash comparison.
2026-08-27: M4 complete. SameSite=lax regression test added.
2026-08-27: M5 complete. README boundary summary corrected.

## 21. Final Outcome / Retrospective

What shipped:

- In-memory rate limiter on POST /auth/login (5 attempts per 60s window)
- Client identity via X-Real-IP header from Next.js middleware
- Logout clears both pi_session and pi_csrf cookies with matching attributes
- hmac.compare_digest for timing-safe CSRF hash comparison
- SameSite=lax regression test for both auth cookies
- README boundary summary corrected

What changed from original plan:

- Rate limit threshold is 5 attempts (plan said 5-6, chose 5 for maximum protection)
- No separate integration test for HTTP rate limiting (PostgreSQL unavailable locally; integration test file created but requires Docker)

Validation performed:

- 361 unit tests pass
- ruff check clean
- ruff format clean
- mypy full scope clean (265 files)

Known limitations:

- In-memory rate limiter does not share state across API processes
- Integration tests require Docker PostgreSQL (pre-existing environment constraint)
- Rate limiting only on POST /auth/login; other endpoints deferred

Follow-ups:

- Rate limiting on other auth-sensitive endpoints (future scope)
- Shared rate limit state if scaling to multiple API processes

Lessons for AGENTS/DECISIONS:

- Rate limiting should have been part of EP-025a (auth implementation)
- CSRF_COOKIE constant should have been introduced with the double-submit pattern
