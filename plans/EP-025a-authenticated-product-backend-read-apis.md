# EP-025a — Authenticated Product Backend & Read APIs

**Status:** READY
**Owner:** Codex / Engineering
**Created:** 2026-08-23
**Updated:** 2026-08-23
**Target milestone:** EP-025a backend product contracts (PLANS.md §76.1 delivery split)
**MVP scope impact:** NO — approved split of the single EP-025 product scope
**New infrastructure category:** NO

## Progress

- [ ] M0 — Baseline verification and auth design reconciliation
- [ ] M1 — Migration 0023: operators + sessions schema; Argon2id hashing boundary
- [ ] M2 — First-party auth boundary: login/logout/session restoration/current-actor endpoints;
      cookie semantics; CSRF for state-changing requests; account-disabled behavior
- [ ] M3 — Product read APIs: Home/status, Timeline, incidents list/detail, investigation detail
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

## 10. Test Cases

See §8 scenario list plus: wrong-password rate-safe generic error; revoked session reuse;
disabled-account login; CSRF-missing write rejection; RELATIVE_ONLY pack hides absolute fields;
observed_at-only event renders null occurred_at; window uncertainty preserved as bounds.

## 11. Final Validation

Full ladder as EP-019–022 plus explicit auth/intake/contract integration files.

## 12. Security / Privacy Impact

This plan IS the security boundary implementation: Argon2id params configured+tested, sessions
hashed at rest, cookies hardened, CSRF enforced, tenant checks on every route. No secrets logged.
Absolute revenue never exposed unless capability=ABSOLUTE and value exists in stored evidence.

## 13. Observability / Failure Handling

Typed AuthError/EvidenceStateError mapped to 401/403/409 responses; structured logs carry
actor_subject_id + tenant only.

## 14. Rollback Strategy

Migration guarded downgrade refuses while operators/sessions exist; revert removes routes; no
collection paths affected.

## 15. Known Risks

CSRF/session subtleties → mitigated by established patterns + negative tests. Endpoint shape may
need adjustment when EP-025b lands — additive only.

## 16. Open Decisions

None block implementation (Option A fully specified by human decision).

## 17. Decision Log

### 2026-08-23 — Sessions hashed server-side; cookie carries opaque raw token
Standard practice: DB cannot leak usable tokens. ### 2026-08-23 — ADMIN/OPERATOR introduced
Only because intake writes are operator-gated while read surface is any active member; documented
per split decision §6.

## 18. Discoveries / Surprises

To be recorded during implementation.

## 19. Progress Log

### 2026-08-23 — Created after split decision; marked READY (Option A fully specified; no human
gates outstanding). Implementation begins immediately on this branch.

## 20. Final Outcome / Retrospective

Pending implementation.
