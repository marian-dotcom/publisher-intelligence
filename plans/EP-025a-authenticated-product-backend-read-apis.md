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
      symptom_segments exposed explicitly; cross-tenant incident detail is non-disclosing
      (tenant-scoped 404, no B-side identifiers or content in response body);
      I5 canonical symptom/scope/status serialization verified (symptom_family, status
      incl. RESOLVED, site_id scope, title, description round-trip exactly as stored);
      I6 onset/window semantics verified (reported_start_at/reported_end_at bounded
      window round-trips exactly via ISO serialization, opened_at exact, resolved_at
      stays explicitly null — no timestamp substitution/fabrication);
      I7 associated-investigation-reference tenant-safety classified NOT APPLICABLE to
      the current incident-detail contract (GET /incidents/{incident_id} serializes
      exactly incident / symptom_segments / last_known_good_references; no investigation
      reference is exposed on any read surface yet, so no nested-leakage path exists;
      investigation-ref tenant safety must be tested on the read surface that actually
      exposes it when such a surface ships);
      I8 frozen LKG reference tenant safety verified (incident detail returns only the
      authenticated tenant's LKG refs; tenant A's frozen reference serialized with
      canonical reference_id/scope_key/selection_method/selection_version/selected_at/
      fingerprints; tenant B's ref id, scope_key, and site id absent from response);
      I9 incident-detail read proven observational for frozen LKG (DB state compared
      before vs after the HTTP read: same single row, reference_id/scope_key/
      checkpoint_run_id/valid_for_incident_id/selected_at/selection_method/
      selection_version/reason/fingerprints all unchanged; no rows created or
      replaced). P2-B incident-read scenarios I1–I9 complete (I7 N/A by contract);
      **P2-B COMPLETE** — completion gate 2026-08-24 @ ddb013a: T+I scenarios 17/17 in
      normal order AND reversed order (order-independent, purge isolation holds);
      product-read regression 29/29; full integration 86 pass + 12 known browser-
      environment failures (identical to pre-P2-B baseline); unit 289; Ruff/mypy clean
      on incident test file; known static-quality debt remains in test_memory_p2b.py
      (21 ruff / 11 mypy findings from original T-series commit: dead _add_bounded_event
      helper + unused-variable/annotation debt) — functional behavior unaffected,
      remediation proposed before P2-C;
      **P2-B static-debt closure** (post-gate cleanup @ 8763c39→): dead _add_bounded_event
      helper removed; all 21 Ruff findings in test_memory_p2b.py resolved (unused locals
      renamed/removed individually, no closure breakage); all 6 mypy findings resolved
      (explicit return annotations on the three inner setups); factories.py format-only
      reflow; T1–T9 behaviorally unchanged (9/9 before and after every step);
      full mypy scope now green (240 files); remaining full-scope Ruff findings are
      pre-existing category-B files outside P2-B (test_product_http_auth.py,
      test_product_read_p2a.py); completion-gate evidence remains valid;
- [ ] P2-C — remaining product read depth (IN_PROGRESS). Contract reconciliation:
      ranked hypotheses live in app/hypotheses (Hypothesis: status
      LEADING/CONTENDER/WEAKENED/UNRESOLVED, confidence LOW/MEDIUM/HIGH, rank,
      hypothesis_key stable identity, rationale, engine_version, supporting/
      contradicting counts; HypothesisEvidence relation SUPPORTS/CONTRADICTS/CONTEXT
      with source_kind EVENT/MANUAL_NOTE/OBSERVATION_GAP; HypothesisRepository.
      list_for_incident is tenant+incident scoped, rank-ordered). LKG refs and
      symptom segments already exposed by P2-B detail. C1 implemented:
      GET /incidents/{id} now serializes "hypotheses" via
      HypothesisRepository.list_for_incident (hypothesis_id, hypothesis_key,
      family, statement, status, confidence, rank, counts, rationale,
      engine_version); tenant-B hypothesis data proven absent; deterministic
      rank order + LEADING representation proven (test_product_read_p2c.py).
      Remaining: C2 SUPPORTS/CONTRADICTS/MISSING evidence relationships;
      C3 evidence pack read surface (PackBuilder/EvidenceRepository contract);
      C4 remaining LKG visibility; C5 monetization capability gating
      (RELATIVE_ONLY/ABSOLUTE/UNKNOWN fail-closed); then Investigate intake.
      C2 implemented: each hypothesis in incident detail now carries nested
      "evidence" rows (evidence_id, evidence_key, relation, source_kind, event_id,
      manual_note_id, reason) loaded via tenant+hypothesis-scoped query; canonical
      missing/unavailable representation is source_kind OBSERVATION_GAP (ranking.py:
      degraded observations = missing-evidence context only) — never serialized as
      CONTRADICTS; only safe identifying metadata exposed (no Event.details/raw
      payloads); persisted supporting/contradicting counts untouched.
      C3 implemented: new authenticated GET /evidence/packs/{pack_id} route
      (memory.py) reads the persisted EvidencePack entity directly (stable UUID
      identity, tenant-scoped 404 on foreign packs, read-only — no rebuild);
      response exposes canonical pack metadata (pack_id/site_id/incident_id/
      window bounds/fingerprints/content_hash/engine_version/created_at) plus the
      temporal fields pass through unaltered.
      C5 implemented: canonical capability model is
      DataConnection.monetization_capability (ABSOLUTE/RELATIVE_ONLY/UNKNOWN,
      tenant+site scoped, connectors/models.py); persisted monetization values
      live in MetricSeries (unit COUNT/RATIO/NUMBER/CURRENCY) + MetricPoint.
      GET /incidents/{id} now carries "monetization" {capability, metrics[]};
      UNKNOWN fails closed to empty metrics; RELATIVE_ONLY suppresses CURRENCY
      series while COUNT/RATIO/NUMBER remain visible; ABSOLUTE exposes only
      values actually persisted (no derivation/imputation/conversion); source
      health untouched; purge.py ordering bug fixed (metric_points before
      metric_derivations). All three capability states + tenant-B isolation +
      absolute-suppression proven in test_product_read_p2c.py.
      **P2-C COMPLETE** — completion gate @ 0128720: C1/C2/C3/C5 4/4 normal AND
      reversed order (purge isolation holds incl. new metric tables); I8/I9
      revalidated green (LKG tenant safety + immutability intact); product-read
      regression 33/33; full integration 90 pass + unchanged 12 browser-env
      failures; unit 289; full mypy scope green; Ruff clean except two documented
      category-B findings outside P2-C. Acceptance scenarios: #4 LEADING
      hypothesis PASS (C1); #5 SUPPORTS PASS (C2); #6 CONTRADICTS PASS (C2);
      #7 missing/unavailable via canonical OBSERVATION_GAP PASS (C2); #11
      RELATIVE_ONLY zero absolute disclosure PASS (C5, active suppression of
      persisted CURRENCY value proven); #12 ABSOLUTE gated on capability AND
      stored evidence PASS (C5, no fabrication). Security review: hypotheses/
      evidence/packs/monetization all server-side tenant-scoped; no raw payload,
      credentials, secret_reference, or internal debug exposure on any P2-C
      surface; GETs observational only. purge.py fix audited: FK direction
      points→derivations requires points purged first; order now matches schema;
      test-infra only.
      Next: Investigate intake (P2-D per PLANS.md §76.1 split).
- [x] M4 — Minimal Investigate intake (P2-D). D1 reconciliation:
      POST /investigations already existed (M4 slice) with CSRF via
      get_current_actor_with_csrf, server-side tenant derivation + site-ownership
      404s, delegation to canonical EP-020 IncidentIntakeService.open_investigation.
      D1 closed the single gap: route now passes created_by=ActorContext.
      actor_subject_id (Incident.created_by column + service param were already
      canonical; OPEN-003 note resolved at the boundary). Request schema:
      site_id/title/symptom_family/description/reported_start_at/reported_end_at;
      response: {incident_id, investigation_key, status} only. D1 test
      (test_investigate_intake_p2d.py) proves persisted created_by ==
      authenticated actor_subject_id, tenant/site ownership, verbatim WHAT,
      bounded/unknown WHEN preserved, investigation_key stability. Remaining:
      D2 negative/security matrix; then M5/M6 gate.
      D2 classified GAP CLOSED (test-only, no production change): scenario
      matrix — unauth 401/403, missing/mismatched CSRF 403, cross-tenant 404,
      valid happy path (all pre-existing in test_product_http_auth.py); NEW
      focused coverage in test_investigate_intake_p2d.py: rejected writes
      (missing CSRF / cross-tenant / nonexistent site 404 / malformed site 404)
      leave incident count unchanged (no partial state, no side effects);
      spoofed extra fields tenant_id/actor_subject_id are ignored and
      non-authoritative (persisted tenant + created_by still derive from
      ActorContext only); Pydantic extras policy documented as
      ignore-and-non-authoritative. No security defect found.
      D3 classified ALREADY CORRECT — OPEN ONLY: POST /investigations is
      intentionally report capture/open; localization is a separate canonical
      step via IncidentIntakeService.localize(incident_id,
      expected_fingerprints) — deterministic analysis over scheduled evidence
      with LKG freezing (EP-020 M2, proven by
      test_incident_intake_localization.py: healthy-anchor selection, first
      anomaly, lkg_frozen=True, degraded/absent evidence never fabricated as
      publisher failure). expected_fingerprints come from collector-bundle
      evidence fingerprints of the site's scheduled runs, NOT from the user
      request (PRODUCT.md §30: conversational what/when input only); wiring
      them into the HTTP layer would require new sourcing/failure-semantics
      decisions = contract work outside D3. Response
      {incident_id, investigation_key, status} is intentionally complete for
      intake. Prior wording implying open_investigation performs localization
      corrected: localize() is invoked separately downstream.
      Acceptance #13 mapping: tenant ownership (D1/D2), actor provenance
      (D1/D2 created_by==actor_subject_id), WHAT/WHEN capture (D1), EP-020
      localization semantics preserved unmodified and proven by EP-020's own
      suite. PASS on that basis.
- [x] M4 — Minimal Investigate intake COMPLETE (gate @ 491fcb2): D1 happy
      path + provenance wiring; D2 security matrix GAP CLOSED (rejected writes
      leave zero state; spoofed extras inert; nonexistent/malformed site 404);
      D3 OPEN-only disposition (localize() separate downstream, fingerprints
      evidence-derived); D1/D2 2/2 normal AND reversed order; existing CSRF/
      tenant scenario green; EP-020 domain regression 10 passed (incl. LKG
      freeze + degraded-evidence semantics); product-read regression 35/35;
      full integration 92 pass + unchanged 12 browser-env failures; unit 289;
      full mypy green; Ruff clean except documented category-B pair. Acceptance
      #13 PASS. Production delta: created_by wiring in investigations.py only.
      No HUMAN GATE crossed. Remaining: M5 contract-validation gate, M6 release
      readiness.
- [ ] M5 — Contract-validation gate (IN_PROGRESS). Evidence matrix @ 4c4be40,
      all suites re-run green (product groups 35, auth 11+6, EP-020 domain 10,
      P2-B/C/D 23, unit 289, mypy green, Ruff category-B pair unchanged).
      Product/data: #1 PASS (test_product_read_p2a healthy+isolated);
      #4–#12 PASS (P2-B T/I files, P2-C file — see gate reports); #13 PASS
      (P2-D D1/D2/D3). PARTIAL: #2 degraded-source-without-publisher-failure —
      health mapping implemented (DEGRADED/ACTION_REQUIRED/BLOCKED) but no
      committed integration test seeds degraded state asserting publisher-site
      independence; #3 missing-connector-as-UNKNOWN — code path proven
      indirectly (GA4 in HEALTHY|UNKNOWN), explicit absence assertion missing.
      Auth/security: #15–#27 PASS via test_product_http_auth (11) +
      test_auth_boundary (6) — expired/revoked/disabled restoration, logout
      replay, rotation, membership removal, unauth 401, CSRF trio, intake
      CSRF/tenant. #25 PARTIAL: generic-error assertion proves 401/no-session;
      no explicit body-content non-leak assertion. Scenario 14 submatrix:
      site PASS (home sites own-tenant only), incident PASS (I2/I4),
      investigation N/A-BY-CONTRACT (no standalone read endpoint; identity
      covered via incidents + intake response), evidence PASS (C3 foreign-pack
      404 + nested evidence tenant-scoped), source-health PASS (p2a 404),
      LKG PASS (I8), timeline PASS (T2), home/status aggregates PASS (p2a).
      GAPS (test-only, no production change, no HUMAN GATE): G1 seed degraded
      browser/connection state asserting source-health degradation AND
      publisher-site independence (#2/#3); G2 explicit unknown-connector
      assertion (#3); G3 failed-login body non-leak assertion (#25).
      C4 classified ALREADY SATISFIED by P2-B: INCIDENT.md §88 requires selection
      to record method/reason/scope/checkpoint-ID — all four are product-visible
      on GET /incidents/{incident_id} (selection_method, reason, scope_key,
      checkpoint_run_id) plus selected_at/selection_version/fingerprints/
      reference_id exactly as stored; checkpoint_run_id IS product-approved
      (explicitly required by §88), not an internal-only detail; MVP §53 defines
      LKG as an incident/scope-scoped comparison reference — no separate LKG
      endpoint is approved; §90's LAST KNOWN GOOD DIFF is engine-reasoning
      consumption, not part of the product read contract, and would be new
      domain work if ever required. Tenant safety + frozen/read-only semantics
      proven by P2-B I8/I9 (reused as regression evidence).
      P2-C work (incident detail/evidence depth, investigations, LKG visibility,
      monetization exposure) remains;
      incident detail/evidence/LKG remain for P2-C):
      (leading hypothesis, supporting/contradicting/missing, rationale), evidence pack view,
      LKG visibility, source-health (HEALTHY/DEGRADED/BLOCKED/ACTION_REQUIRED/UNKNOWN) separate
      from publisher/site health, provenance (machine_observed vs human_reported; observed_at vs
      occurred_at vs window uncertainty), privacy-preserving monetization exposure gated by
      capability (ABSOLUTE/RELATIVE_ONLY/UNKNOWN)
- [ ] M4 — Minimal Investigate intake endpoint over EP-020 semantics (what/when/site+scope)
      with actor provenance
- [x] M5 — Contract-validation-gate integration tests covering the 27 approved scenarios (see matrix below)
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

