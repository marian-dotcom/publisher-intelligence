# EP-026 M8 — Adversarial Release-Readiness Review

**Reviewer:** Codex (automated adversarial pass)
**Date:** 2026-08-26
**Branch:** `agent/implement-ep-026`
**HEAD:** `b6eeadba3f4629a75fe3b98a6cde036a59f193f4`
**Scope:** Full adversarial challenge of EP-026 M1-M7 against actual code, tests,
documented evidence, and the live Oracle Cloud ARM64 staging deployment.

---

## Methodology

1. Verified branch HEAD and clean working tree.
2. Read AGENTS.md, EP-026 plan, pilot-readiness runbook in full.
3. Read all canonical docs: SECURITY.md, DECISIONS.md, PLANS.md, ARCHITECTURE.md,
   DATA_MODEL.md, BROWSER.md, CONNECTORS.md, EVENTS.md, INCIDENT.md, EVALS.md.
4. Verified M1-M7 code, tests, and evidence against acceptance criteria using
   parallel deep-reads of all affected source files, test files, and migrations.
5. Adversarial challenge across 10 review areas: authentication/tenant isolation,
   monitoring-network reliability, retention, connector staleness, cost controls,
   time/DST behavior, self-observability, incident/evidence correctness,
   deployment/runtime assumptions, canonical-document consistency.

---

## Findings

### F-001: ORM CheckConstraint drift on investigation_usage (CLOSED)

**Affected milestone:** M4 (cost telemetry)
**Evidence:** `backend/app/incidents/models.py:164-166` declared
`resource_kind IN ('DRILLDOWN','LLM_PASS','DIAGNOSTIC_RUN')` in the ORM
CheckConstraint. Migration `0027_checkpoint_run_budget_kind` correctly updated the
DB-level constraint to include `CHECKPOINT_RUN`, but the ORM model string was not
updated to match.
**Remediation:** One-line string update at `models.py:165` adding `CHECKPOINT_RUN`
to the ORM CheckConstraint. Regression test added in
`tests/unit/incidents/test_contracts.py::test_orm_check_constraint_includes_checkpoint_run`
inspecting ORM metadata to prove the constraint text admits `CHECKPOINT_RUN` (RED→GREEN
confirmed: old string fails, new string passes). Migration 0027 left untouched.
**Status:** CLOSED.

### F-002: pi_csrf cookie not cleared on logout (LOW)

**Affected milestone:** M1 (secure-cookie)
**Evidence:** `backend/app/auth/routes.py:97-109` — the `/auth/logout` endpoint
calls `response.delete_cookie(SESSION_COOKIE, path="/")` but does NOT delete the
`pi_csrf` cookie. After logout, a stale CSRF cookie persists in the browser.
**Why it matters:** Defense-in-depth. The stale CSRF token is useless without a
session, but clean session teardown is standard practice. Additionally,
`delete_cookie` does not set `SameSite` or `Secure` attributes matching those used
at creation, which may prevent proper cookie deletion in some edge cases.
**Reproducibility:** Login → verify cookies → logout → verify pi_csrf still present.
**Remediation scope:** Add `response.delete_cookie("pi_csrf", path="/")` and match
creation attributes on both delete calls. Pre-existing, not introduced by EP-026.
**Blocks M8 completion:** No.

### F-003: CSRF hash comparison not timing-safe (LOW)

**Affected milestone:** M1 (secure-cookie)
**Evidence:** `backend/app/auth/service.py` — `verify_csrf` uses Python `==` for
string comparison of SHA-256 hashes instead of `hmac.compare_digest()`. The
`==` operator short-circuits on the first differing character, theoretically leaking
timing information.
**Why it matters:** Practical risk is negligible because the raw token has 256 bits
of entropy and the attacker must guess the token, not the hash. `SameSite=Lax`
provides additional CSRF defense-in-depth. However, `hmac.compare_digest()` is the
correct implementation per OWASP guidance.
**Reproducibility:** Timing analysis on CSRF validation endpoint with valid/invalid
tokens.
**Remediation scope:** Replace `==` with `hmac.compare_digest()` in one function.
Pre-existing, not introduced by EP-026.
**Blocks M8 completion:** No.

### F-004: Mypy full-scope claim slightly overstated (CLOSED)

**Affected milestone:** M1
**Evidence:** The EP-026 plan stated "mypy full scope green" (plan line 27). A
prior targeted mypy run reported 11 errors, all in test files, all intentional
(passing raw `str` where `SecretStr` is typed, or deliberately testing invalid
environment literals). No production code had type errors.
**Why it matters:** Aggregate regression counts must be exact per AGENTS.md gate
evidence rules.
**Remediation:** CI run `33011814483` on branch `agent/implement-ep-026` at
`b6eeadba3f4629a75fe3b98a6cde036a59f193f4` ran the full canonical mypy scope
`mypy app tests scripts migrations/env.py` and reported **"Success: no issues
found in 262 source files"**. The 11 prior test-file annotations were resolved
between the initial finding and CI green. F-004 is CLOSED.
**Status:** CLOSED.

### F-005: No automated SameSite cookie attribute test (LOW)

**Affected milestone:** M1
**Evidence:** `test_secure_cookie_gate.py::test_pilot_production_cookies_must_be_secure`
asserts `Secure` and `HttpOnly` attributes but does NOT assert `SameSite=lax`.
The SameSite posture is documented in the plan and visible in code but has no
automated regression guard.
**Why it matters:** If someone changes `samesite="lax"` to `samesite="none"` or
removes it, no test would catch it.
**Reproducibility:** Change `samesite="lax"` to `samesite="none"` in routes.py —
all existing tests still pass.
**Remediation scope:** Add one assertion to the existing test. Trivial.
**Blocks M8 completion:** No.

### F-006: Rate limiting not implemented on auth endpoints (LOW — pre-existing, out of EP-026 scope)

**Affected milestone:** None (pre-existing gap)
**Evidence:** SECURITY.md §95 explicitly requires rate-limiting on login-sensitive
endpoints. No rate-limiting middleware or decorator exists anywhere in the backend.
The `POST /auth/login` endpoint is vulnerable to credential brute-forcing.
**Why it matters for Limited Pilot:** This is an MVP security requirement, not an
EP-026 requirement. EP-026 scope is pilot reliability/operational readiness, not
new security features. The login endpoint is protected by password authentication.
**Reproducibility:** Unlimited POST attempts to `/auth/login` succeed without
throttling.
**Remediation scope:** Implement rate-limiting middleware. Significant new code —
out of EP-026 scope. Should be tracked as a separate pre-pilot work item.
**Blocks M8 completion:** No (out of scope). Explicit pre-Limited-Pilot security
gap — must be resolved before Limited Pilot authorization.

### F-007: RetentionSchedulingService duplicated in health.py (LOW)

**Affected milestone:** M3a
**Evidence:** `backend/app/retention/health.py:18-34` contains a duplicate
definition of `RetentionSchedulingService` that is identical to
`backend/app/retention/scheduling.py:10-26`. Production imports use `scheduling.py`;
the `health.py` copy is dead code.
**Why it matters:** Code confusion risk. A future developer might import from the
wrong location.
**Remediation scope:** Delete the duplicate class from `health.py`. Trivial.
**Blocks M8 completion:** No.

---

## Challenge Area Summary

### 1. Authentication / tenant isolation

**Verdict: PASS (with LOW findings F-002, F-003)**

- Secure cookie: `cookie_secure` field + fail-closed model_validator +
  defense-in-depth RuntimeError — triple guard.
- pi_session: HttpOnly, Secure, SameSite=Lax, Path=/.
- pi_csrf: Secure, SameSite=Lax, Path=/, intentionally non-HttpOnly (double-submit).
- Session TTL: 12 hours absolute, rotation on login, revocation on logout.
- CSRF: double-submit pattern with SHA-256 hash storage + X-CSRF-Token header.
- Tenant isolation: server-derived `actor.tenant_id` on all tenant-owned endpoints.
- Non-disclosing errors: login failures produce generic "authentication failed".
- Fail-closed: startup refuses to boot without secure-cookie config in staging/production.
- Live HTTPS: PASS on Oracle Cloud ARM64 at deployed commit `59b0f42`.
- Logout: pi_session cleared; pi_csrf not cleared (F-002).

### 2. Monitoring-network reliability

**Verdict: PASS**

- Deterministic challenge detection: `detect_challenge_marker` with capped scan
  (100K chars), marker precedence over bare status.
- Challenge → `BROWSER_ACCESS_CHALLENGE_SUSPECTED` (MEDIUM); 403 alone →
  `BROWSER_SOURCE_DEGRADED`.
- Recovery: automatic bounded re-check with full context validation; emits
  `BROWSER_SOURCE_RECOVERED`.
- Source-health: deterministic read-time projection, no persistent mutable state.
- ADR-130 cohort purity: SCHEDULED runs never create/close reliability episodes.
- Cross-source independence: GA4/GSC/GAM/PUBLIC_CONFIG unaffected by browser
  degradation.
- Sentinel-based data-leak proof in integration tests.
- BROWSER.md §81.1 and EVENTS.md §0.1 document semantics.

### 3. Retention

**Verdict: PASS**

- Deletion: object-before-DB, FOR UPDATE row lock, active hold re-check.
- BATCH_SIZE=50 per-batch, not per-run; backlog drains in one execution.
- Non-progress guard fails loudly on stalled batches.
- All 4 health states: HEALTHY/MISSED/STALLED/FAILED with deterministic precedence.
- Missed/stalled visibility: surfaced via /product/operations (M6).
- Run audit: started_at/finished_at/rows_deleted_per_table/hold_conflicts_skipped.
- Migration 0026_retention_runs: additive, correct schema.
- 10 integration tests covering production chain, idempotency, storage failure,
  health states, race conditions, batch drain, audit integrity.

### 4. Connector staleness

**Verdict: PASS**

- STALE state added to canonical health vocabulary.
- Thresholds: GA4=6h, GSC=12h, GAM=6h, PUBLIC_CONFIG=18h (all 3x cadence).
- freshness_state: None→UNKNOWN, naive→ValueError, within→HEALTHY, beyond→STALE.
- Precedence: DEGRADED/ACTION_REQUIRED/BLOCKED dominate over STALE.
- Never-synced CONNECTED → UNKNOWN, never HEALTHY.
- One stale source never implies publisher/site failure.
- PUBLIC_CONFIG: only SCHEDULED snapshots with VALID/VALID_WITH_WARNINGS count.
- 9 integration tests covering thresholds, boundaries, precedence, independence.

### 5. Cost controls

**Verdict: PASS (with MEDIUM finding F-001)**

- CHECKPOINT_RUN resource kind: constants, Literal type, migration 0027.
- CheckpointCostRecorder: idempotent run-scoped entry, amount=1, records on
  success AND failure.
- Circuit breaker: deterministic read-time projection of append-only ledger.
- DEFAULT_CHECKPOINTS_PER_SITE_WINDOW=4 enforced at scheduling gate.
- SchedulingResult.breaker_skipped_sites tracked and logged.
- BLOCKED surfaced in source-health with correct precedence.
- BLOCKED scoped to observation source, never publisher/site health.
- 4 integration tests covering recording, idempotency, predicate, scheduling gate.

### 6. Time/DST behavior

**Verdict: PASS**

- GA4: `fold=0` explicit, spring-forward gap collapses deterministically.
- GSC: pins America/Los_Angeles, validates offsets, rejects contradictions.
- GAM: enumerates both folds, flags DST_AMBIGUOUS_HOUR, refuses nonexistent hours.
- Browser: naive instant rejected, UTC-aware throughout, fall-back 7h/spring 5h.
- Cross-source alignment by absolute instant.
- PostgreSQL round-trip preserves tz-awareness and exact instants.
- No naive datetime usage on any temporal code path.
- 9 unit tests + 1 integration test.

### 7. Self-observability

**Verdict: PASS**

- /product/operations: authenticated, tenant-scoped.
- Scheduler health: ENFORCE_RETENTION-only filter (soundness repair at a2ab2c1).
- Worker health: max(started_at) with 48h envelope.
- Queue depth: runnable(PENDING+RETRY), leased(RUNNING+valid lease),
  stale_leases(RUNNING+expired/NULL).
- Execution window: 24h bounded, with avg/max duration and failure rate.
- Retention health: projected from M3 retention_health, not duplicated.
- Per-site source-health: tenant-scoped, 5-source independence.
- Each sub-signal degrades independently to UNKNOWN.
- 4 regression tests proving unrelated jobs cannot fake scheduler health.

### 8. Incident/evidence correctness

**Verdict: PASS**

- INV-01 (browser-access degradation): ACCEPT.
- INV-02 (degraded-source partial operation): ACCEPT.
- INV-03 (monetization context): ACCEPT WITH NOTE.
- All three executed through production paths on 2026-08-25.
- Manual reviews recorded 2026-08-25.
- Evidence vs inference separation maintained throughout.
- No causal claims from monitoring failure alone.

### 9. Deployment/runtime assumptions

**Verdict: PASS**

- ARM64: live smoke on Oracle Cloud ARM64 at deployed commit 59b0f42.
- Reverse proxy / HTTPS: sslip.io domain, verified TLS.
- Frontend/backend proxy: Set-Cookie fix preserves both cookies independently.
- Loopback-only ports: all compose.yaml services bind 127.0.0.1.
- BROWSER_ALLOW_PRIVATE_NETWORKS: rejects in production settings.
- Chromium sandbox: enabled, non-root user, no --no-sandbox.
- Private network blocking: BrowserNetworkGuard with is_global check.
- Resource caps: browser timeouts, request budget, job max_attempts, circuit breaker.
- Single-host: compose.yaml deploys all services on one host.

### 10. Canonical-document consistency

**Verdict: PASS**

- SECURITY.md §201 → ADR-131 → EP-026 plan → implementation: consistent chain.
- PLANS.md §76.1 → EP-026 mandatory prerequisite: consistent.
- EP-026 plan progress checkboxes: all M1-M7 marked [x]; M8 unchecked.
- Pilot-readiness runbook Part B matrix: all criteria PASS (except HUMAN GATE items).
- Runbook Part D findings: 0 BLOCKER / 0 HIGH / 0 MEDIUM.
- No contradictory gate states found.
- No acceptance criterion marked PASS without evidence.

---

## Finding Counts

| Severity | Count | IDs |
|----------|-------|-----|
| BLOCKER | 0 | — |
| HIGH | 0 | — |
| MEDIUM | 0 | — |
| LOW | 5 | F-002, F-003, F-005, F-006, F-007 |
| CLOSED | 2 | F-001, F-004 |

---

## M8 Completion Status

- **Unresolved BLOCKER findings:** 0
- **Unresolved HIGH findings:** 0
- **Unresolved MEDIUM findings:** 0
- **Unresolved LOW findings:** 5 (F-002, F-003, F-005, F-006, F-007 — documented technical debt)
- **CLOSED findings:** 2 (F-001, F-004)
- **M8 status:** COMPLETE (zero unresolved BLOCKER/HIGH/MEDIUM findings)
- **EP-026 status:** M1-M8 TECHNICAL READINESS PASS
- **LIMITED PILOT:** NOT AUTHORIZED (independent human gate; completing M8 does
  not by itself authorize Limited Pilot; F-006 rate limiting remains an explicit
  pre-Limited-Pilot security gap)
