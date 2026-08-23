# EP-025a — Authenticated Product Backend & Read APIs

**Status:** IN_PROGRESS
**Owner:** Codex / Engineering
**Created:** 2026-08-23
**Updated:** 2026-08-23
**Target milestone:** EP-025a backend product contracts (PLANS.md §76.1 delivery split)
**MVP scope impact:** NO — approved split of the single EP-025 product scope
**New infrastructure category:** NO

## Progress

- [x] M0 — Baseline verification and auth design reconciliation
- [x] M1 — Migration 0023: operators + sessions schema; Argon2id hashing boundary
- [x] M2 — First-party auth boundary implemented (security.py Argon2id + CSPRNG tokens +
      hash-at-rest; service.py login/rotation/restore/logout with fail-closed checks;
      integration coverage for scenarios 15/16/17/21/24/26/27);
      cookie semantics; CSRF for state-changing requests; account-disabled behavior
- [x] M3 — Product read APIs PARTIAL (P2-A: Home/status + source health + publisher/site
      condition shipped; P2-B Timeline T1–T9 shipped (own-timeline read, cross-tenant
      exclusion, machine_observed vs human_reported provenance, observed_at preserved,
      occurred_at only when EXACT, internal payload data absent from serialization);
      P2-B Incidents I1–I3 shipped (authenticated tenant lists own incidents; tenant A
      incident list excludes tenant B incidents and site identifiers server-side;
      authenticated tenant fetches own incident detail with site scope and empty
      symptom_segments exposed explicitly); cross-tenant detail coverage remains for I4;
      incident detail/evidence/LKG remain for P2-C):
      (leading hypothesis, supporting/contradicting/missing, rationale), evidence pack view,
      LKG visibility, source-health (HEALTHY/DEGRADED/BLOCKED/ACTION_REQUIRED/UNKNOWN) separate
      from publisher/site health, provenance (machine_observed vs human_reported; observed_at vs
      occurred_at vs window uncertainty), privacy-preserving monetization exposure gated by
      capability (ABSOLUTE/RELATIVE_ONLY/UNKNOWN)
- [ ] M4 — Minimal Investigate intake endpoint over EP-020 semantics (what/when/site+scope)
      with actor provenance
- [ ] M5 — Contract-validation-gate integration tests covering all 16 approved scenarios
- [ ] M6 — Full validation and release readiness

## 1. Purpose and User Outcome

The backend product contract that EP-025b's frontend consumes without inventing domain logic:
an authenticated operator can see Home status, Timeline, incidents, investigations with ranked
hypotheses and provenance-tagged evidence, source health distinct from publisher health, LKG
references, privacy-preserving monetization, and open an investigation via minimal Investigate
intake.

## 2. Scope and Non-Goals

### In
operator accounts (tenant-bound, active/disabled, opaque actor_subject_id canonical identity,
email as login attribute only) · server-side sessions (CSPRNG opaque ids, expiring, revocable,
rotated on login, invalidated on logout, rejected when account disabled) · HttpOnly/Secure-prod/
SameSite=Lax cookie · CSRF token verification for state-changing requests · Argon2id password
hashing with explicit parameters · read-only query endpoints listed in §3 of the split decision ·
Investigate intake write endpoint · tenant isolation everywhere.

### Out / Non-Goals
EP-025b frontend surface; signup/password-reset/MFA/SSO/OIDC/SCIM/social (new human gate if
required); enterprise RBAC beyond optional ADMIN/OPERATOR only if concrete behavior demands it
(documented otherwise); billing/chat/ticketing/collaboration; LLM synthesis/model grading;
EP-026 runtime WAF/challenge detection, egress verification, compatibility self-check runtime,
recovery re-check workflow (EP-025a only exposes a source-health contract capable of representing
those outcomes when supplied); production secret/cloud/network provider selection; entity-mapping
lifecycle; new event codes.

## 3. Canonical References

AGENTS.md §2.1/§7/§13/§15–18/§20/§24/§28 · PLANS.md §76.1 amended sequence · DECISIONS.md
ADR-007/029/047–049/057/060–061/089–091/130 + approved Option A decision & revisit triggers ·
SECURITY.md (session/CSRF/credential handling) · DATA_MODEL.md §66–68 · INCIDENT.md §88 ·
PRODUCT.md Home/Timeline/Investigate surfaces · EVENTS.md §15.1 · EP-018–EP-021 plans ·
superseded EP-025 plan (split record).

## 4. Current State

Main `060781f` post-EP-024. FastAPI app has only /health routes; no auth, no product endpoints.
Frontend is a single foundation page. Available backend capabilities to expose: EP-019
incidents/LKG/budget/holds, EP-020 intake/localization service, EP-021 relations/manual notes/
packs/fixtures, EP-023 ranked hypotheses, connector connection states incl.
monetization_capability, public-config snapshots, checkpoint runs/events. Migration head `0022`.

## 5. Target Behavior (contract summary)

Auth: POST /auth/login (email+password → session cookie set, rotated id), POST /auth/logout,
GET /auth/session (current actor: subject_id, tenant_id(s), role). All product routes require a
valid non-expired non-revoked session bound to an enabled account; 401 otherwise; 403 cross-
tenant; CSRF required on writes. Read endpoints (tenant-scoped): GET /home/status,
/timeline?window, /incidents, /incidents/{id} (with hypotheses+evidence+LKG+chronology),
/evidence/packs/{id}, /source-health, plus Investigate: POST /investigations (delegating to
IncidentIntakeService with actor_subject_id provenance). Source-health contract states:
HEALTHY/DEGRADED/BLOCKED/ACTION_REQUIRED/UNKNOWN per source, independent of publisher/site
condition field. Monetization sections render capability-gated: RELATIVE_ONLY exposes deltas/
index shapes only; ABSOLUTE additionally permits absolute values when present in evidence.
Provenance fields: evidence_source (machine_observed|human_reported), observed_at, occurred_at
(null when unknown) or occurred_after/before bounds.

## 6. Architecture

FastAPI routers under `app/api/product/` delegating to existing services/repositories
(InvestigationRepository, EvidenceRepository/PackBuilder, HypothesisRepository,
IntakeService); `app/auth/` module (hashing via argon2-cffi, session repository, cookie helpers,
CSRF dependency); migration `0023_product_backend_auth.py`: `operators`, `operator_tenants`,
`sessions` tables + guarded downgrade. No changes to collection/derivation paths.

## 7. Data Model

operators: id PK · tenant FK · email unique login attribute · password_hash ·
actor_subject_id uuid unique NOT NULL · role CHECK ADMIN/OPERATOR default OPERATOR ·
is_active bool · created_at/updated_at.
sessions: id PK · token_hash sha256 unique · operator FK RESTRICT · tenant_id FK · created_at ·
expires_at · revoked_at NULL · user_agent_hash NULL. Cookie carries raw token; DB stores hash.
Downgrade refuses while rows exist.

## 8. Milestones

M0 baseline ✔ criteria as prior plans · M1 schema+models · M2 auth boundary+endpoints ·
M3 read APIs + intake endpoint · M4 contract-gate integration tests (16 scenarios) ·
M5 full validation/release readiness.

## 9. Final Acceptance Criteria

All 16 API-contract gate scenarios proven by tests; tenant isolation and CSRF negative tests;
expired/disabled rejection; no absolute revenue leakage when capability ≠ ABSOLUTE; source health
independent of publisher health; zero inspect_ai imports under app/; full ladder green locally +
CI.

## 10. SECURITY + CONTRACT VALIDATION GATE (release blocker)

Both A and B must pass before COMPLETE. Critical paths exercise the real HTTP boundary,
auth dependency, PostgreSQL-backed operator/session state, and tenant authorization — not
helper-call mocks.

### A. Product / data contract

1. healthy browser source + healthy publisher/site
2. degraded browser/source without publisher/site failure
3. missing/unavailable connector represented as unavailable evidence, not publisher failure
4. incident with LEADING hypothesis
5. supporting evidence exposed correctly
6. contradicting evidence exposed correctly
7. missing/unavailable evidence exposed explicitly
8. human_reported distinguishable from machine_observed
9. observed_at known while occurred_at unknown (null occurred_at)
10. bounded time-window uncertainty without fabricated precision
11. RELATIVE_ONLY monetization with zero absolute revenue disclosure
12. ABSOLUTE values exposed only when capability == ABSOLUTE AND evidence contains them
13. minimal Investigate intake preserving tenant ownership, actor provenance,
    EP-020 localization semantics

### B. Authentication / authorization failure cases

14. cross-tenant read rejected server-side for: site, incident, investigation, evidence,
    source-health state, LKG data, timeline entries, Home/status aggregates
15. expired session rejected; no authenticated actor context restored
16. explicitly revoked session rejected; reuse of prior credential rejected
17. disabled operator rejected even with otherwise-valid session (checked at restoration,
    not only login)
18. missing CSRF token on cookie-authenticated state-changing request rejected
19. mismatched/invalid CSRF token rejected
20. unauthenticated request to protected product endpoint rejected (401)
21. logout invalidates session; replay of previous session credential rejected
22. session/actor binding cannot escape tenant membership or tenant authorization
23. removal/invalidation of tenant membership causes subsequent tenant-scoped access to fail closed
24. invalid password does not create a persisted session
25. failed authentication returns a generic error that does not leak credential-sensitive
    internal state
26. disabled operator cannot obtain a new login session
27. session expiry enforced server-side; stale browser cookie cannot bypass it

### C. Security invariants

Demonstrated via tests/inspection:
- plaintext passwords never persisted; hashing is one-way (Argon2id) with configured parameters;
- raw session secrets not stored recoverable (server stores hash only);
- password hashes / raw session tokens / CSRF secrets never emitted to logs;
- disabled-account check occurs during session restoration;
- tenant authorization enforced server-side (frontend filtering never authoritative);
- CSRF applies to state-changing cookie-authenticated routes; GETs remain side-effect free;
- failed authentication creates no persisted authenticated session;
- auth/session errors do not leak secret material or credential internals.

Any failure in a security-critical scenario above is an EP-025a release blocker.

