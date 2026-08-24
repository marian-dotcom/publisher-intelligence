# EP-026 — Pilot Reliability & Operational Readiness

**Status:** READY
**Owner:** Codex / Engineering
**Created:** 2026-08-24
**Target milestone:** Pilot reliability & operational readiness (PLANS.md §76.1; mandatory prerequisite for Limited Pilot)
**MVP scope impact:** NO — reliability/operational hardening of already-built deterministic product
**New infrastructure category:** NO — existing stack only (PostgreSQL, FastAPI scheduler/worker, Playwright, Next.js)

## Progress

- [ ] M0 — Contract reconciliation & secure-cookie configuration surface design
- [x] (planning) Repository reconciliation @ main 3c96157: SECURITY.md §201 present;
      ADR-131 present and pointing at §201; PLANS.md §76.1 states EP-026 is a
      mandatory prerequisite for Limited Pilot; EP-025b COMPLETE. No contradictions.
- [x] M1 — SECURE-COOKIE PRE-PILOT HARD GATE COMPLETE (code-complete;
      pilot-gate-pending-HTTPS-smoke): Settings gained environment-aware
      cookie_secure (default False) with fail-closed model_validator —
      staging/production MUST set cookie_secure=True or construction raises
      (SECURITY.md §201 wording); _set_session_cookies defense-in-depth
      raises on Secure=False emission outside local/test and now emits
      secure=cookie_secure for both pi_session (HttpOnly preserved) and
      pi_csrf (JS-readable preserved), SameSite=lax documented. RED→GREEN:
      RED 3 failed/1 passed (no cookie_secure field, no validator, insecure
      emission) → GREEN 5/5 + 4/4 fail-closed negative tests. Auth
      regression: test_product_http_auth.py + test_auth_boundary.py →
      18 passed. Unit suite 298 passed. mypy full scope green. Remaining
      deployment verification: real HTTPS smoke of browser-visible cookie
      attributes (procedure in runbook, M7).
- [x] M2a — browser-source taxonomy + classifier + monitoring UA +
      challenge/recovery HTTP scenario COMPLETE
- [x] M2b-1a-1 — additive DIAGNOSTIC derive input path COMPLETE
      (load_diagnostic_input / DiagnosticInput; DIAGNOSTIC_NO_EVENT_RULES)
- [x] M2b-1a-2a — classification storage COMPLETE @ eb4d4ed: migration
      0024_browser_access_class (single nullable JSONB column
      checkpoint_runs.browser_access_classification; downgrade drops only it);
      CheckpointRun model field; DIAGNOSTIC-only finalize hook persists bounded
      {state, reason} via classify_access(status-only); non-DIAGNOSTIC runs
      remain NULL; storage tests green; full unit 303 passed; integration
      baseline unchanged (12 browser-env failures); mypy green.
- [ ] M2b-1a-2b — DiagnosticInput classification → canonical Event mapping
- [ ] M2 — Monitoring network reliability (allowlistable egress identity,
      documented non-deceptive User-Agent, compatibility self-check diagnostic,
      browser-source health events + recovery re-check)
- [ ] M3 — Retention enforcement proof + connector staleness/freshness
      operationalization
- [ ] M4 — Cost telemetry, hard caps & circuit breakers
- [ ] M5 — DST/timezone cross-source hardening regression
- [ ] M6 — Minimal self-observability (scheduler/worker/queue/retention/
      failure-rate visibility)
- [ ] M7 — Pilot runbook + technical-readiness exit gate validation
- [ ] M8 — Adversarial review & release readiness

## Canonical References

- **`SECURITY.md` §201 — Secure-cookie pre-pilot hard gate** (canonical security statement)
- **`DECISIONS.md` ADR-131** — decision record pointing at SECURITY.md §201
- **`PLANS.md` §76.1** — EP-026 scope and mandatory-prerequisite status
- `SECURITY.md` §22 (CSRF), retention/privacy sections
- `INCIDENT.md`, `EVENTS.md`, `CONNECTORS.md`, `BROWSER.md`, `EVALS.md`
- `AGENTS.md` gate-evidence rules

## Security / Privacy Impact

This EP's first milestone exists because auth cookies are currently emitted with
Secure=False (`auth/routes.py::_set_session_cookies`). Per SECURITY.md §201 /
ADR-131: pilot/production MUST emit `pi_session` and `pi_csrf` with Secure=True,
`pi_session` MUST remain HttpOnly, SameSite posture MUST be reviewed/documented,
cookie configuration MUST be environment-aware, and startup/deployment MUST fail
closed when pilot/production secure-cookie configuration is missing or invalid.
Automated tests MUST prove Secure=False cannot be emitted in pilot/production.
Tenant isolation, provenance, and non-disclosing error semantics from EP-025a/b
are preserved unchanged.

## Acceptance Criteria (EP-026 release blocker)

1. **M1 green — automated proof first:** a test MUST demonstrate that
   pilot/production configuration cannot emit `pi_session` or `pi_csrf` with
   Secure=False (fail-closed startup validation + cookie-emission assertions).
   This is the FIRST independently verifiable acceptance criterion of the EP.
2. HTTPS smoke validation confirms browser-visible Secure/HttpOnly/SameSite
   attributes in pilot/production mode.
3. Local development remains configurable but cannot silently weaken
   pilot/production (explicit environment selection required).
4. Retention/deletion enforcement PROVEN to execute (run records + eligible-row
   deletion evidence); missed/stalled retention detected and surfaced.
5. Connector staleness distinguishable from healthy/degraded/unavailable and
   from publisher/site failure; silent degradation impossible.
6. Browser-source degradation (monitoring network reliability) rendered only as
   monitoring-source health/data quality — never publisher/site failure — with
   bounded recovery re-check after allowlisting/remediation.
7. Cost telemetry + enforceable hard caps + circuit-breaker behavior verified;
   representative pilot workload cost measured; no uncontrolled retry loops.
8. DST/timezone cross-source regression green on a real transition boundary via
   an actual temporal code path (no naive-datetime fallback).
9. Minimal self-observability visible: scheduler/worker health, queue depth,
   stale lease/job detection, run duration/failure rate, retention-job health.
10. Pilot runbook covers all §Runbook items below.
11. Zero unresolved BLOCKER/HIGH/MEDIUM findings; aggregate regressions cited
    with exact command/scope/count per AGENTS.md.

**EP-026 MUST NOT be marked COMPLETE while M1 (or any criterion above) is red.
Limited Pilot SHALL NOT start while M1 is red.**

## Scope / Non-Goals

In: secure-cookie hardening; monitoring network reliability; retention
enforcement; connector staleness; source-health operationalization; cost caps;
DST hardening; minimal self-observability; pilot runbook.

Out (non-goals): feature expansion; LLM synthesis; dashboard redesign;
cloud/provider/secret-vendor selection (OPEN-003/OPEN-005 human gates);
observability-platform adoption (Datadog/Grafana/etc.); event-catalog expansion
beyond the canonical browser-source events below; broad refactors; Limited
Pilot execution.

## M1 — Secure-cookie pre-pilot hard gate (FIRST milestone)

Consumes **SECURITY.md §201** (Canonical References, Security / Privacy Impact,
Acceptance Criteria — all three cite it directly) and **DECISIONS.md ADR-131**.

Implementation sketch (smallest change): environment-aware settings object
(`ENVIRONMENT ∈ {local, pilot, production}`); cookie helper refuses to emit
auth cookies unless `(environment != local AND secure=True)` holds; startup
config validator raises before serving traffic when pilot/production lacks
Secure/HTTPS posture.

FIRST acceptance criterion (mandatory): automated test proving pilot/production
configuration cannot emit `pi_session`/`pi_csrf` with Secure=False.

Also: SameSite review note; local dev keeps current behavior explicitly scoped
to ENVIRONMENT=local; fail-closed startup; HTTPS smoke validation checklist in
the runbook. **EP-026/Limited Pilot blocked while M1 red.**

## M2 — Monitoring network reliability

Reconciled against repository truth:

- **User-Agent:** currently derived from scenario device profiles
  (`browser/persistence.py` device_profile.user_agent). EP-026 defines ONE
  documented, stable, non-deceptive monitoring UA string (product/version
  identifying Publisher Intelligence monitoring; contact pointer in runbook),
  applied to scheduled/diagnostic runs and recorded in run provenance.
  No stealth/CAPTCHA-bypass/residential-proxy behavior.
- **Egress identity:** deployment-dependent. Plan documents the allowlisting
  contract (stable identity + UA + guidance/runbook). Actual IP/provider
  architecture = HUMAN GATE (OPEN-005 territory); planning does not select.
- **Compatibility self-check diagnostic:** bounded onboarding check using
  EP-018 DIAGNOSTIC semantics: navigation failure, HTTP/redirect anomaly,
  challenge/WAF response markers, missing expected application shell,
  radically-reduced content. DOM variance ALONE is not blocking proof.
- **Canonical event taxonomy:** repository registry has no browser-source
  event today; EP-026 canonically introduces:
  `BROWSER_SOURCE_DEGRADED` (monitoring source degraded/blocked/unreliable),
  `BROWSER_ACCESS_CHALLENGE_SUSPECTED` (deterministic markers only),
  `BROWSER_SOURCE_RECOVERED` (post-remediation re-check passed).
- **M2 completion criterion (mandatory):** at least one deterministic
  challenge/WAF degradation-and-recovery scenario proven through the
  production-equivalent browser diagnostic/source-health path — a real
  consenting pilot-site case when organically available, otherwise a
  controlled synthetic/fixture-based validation (controlled local/test
  endpoint, HTTP-response fixture, or deterministic browser test page). The
  scenario MUST exercise the SAME deterministic detection and source-health
  logic used in production: challenge evidence → access-challenge /
  browser-source-degradation state → NO publisher/site failure → GA4/GSC/GAM/
  public-config monitoring unaffected → remediation input drives the bounded
  re-check → BROWSER_SOURCE_RECOVERED. No external anti-bot/WAF vendor may be
  adopted for this.
  Meaning: OUR observation source is degraded — NOT that the publisher site is
  broken. Rendered exclusively as monitoring-source health (EP-025a contract).
- **Partial operation:** browser-source degradation never blocks GA4/GSC/GAM/
  public-config monitoring. Recovery verified by a bounded diagnostic re-check.

## M3 — Retention enforcement + connector staleness

Repository truth: `retention_holds` model + budget ledger exist; a deletion-
enforcement job with execution proof does not. EP-026 adds:

- retention deletion job acting on eligible rows/artifacts per policy
  (incident-linked holds respected; artifacts/checkpoint evidence included);
- per-run execution records (started/finished, rows deleted per table) so
  execution is provable;
- missed/stalled detection wired into M6 observability with actionable state;
- connector staleness/freshness surfaced through the EXISTING source-health
  model (STALE freshness_status → source-level state), preserving
  observation-failure ≠ publisher-failure.

## M4 — Cost telemetry, hard caps, circuit breakers

- extend the existing budget-ledger pattern (DIAGNOSTIC_RUN) into a
  representative-workload cost measurement (runs × bounded page set);
- enforceable caps: per-site/per-window diagnostic + checkpoint budgets with
  circuit-breaker stop when exceeded; explicit degradation semantics
  (source-health ACTION_REQUIRED/BLOCKED style states), never fabricated data;
- bounded retries only (existing attempt_count semantics); no uncontrolled
  retry/spend loop;
- measured cost recorded for a representative pilot site/workload as
  acceptance evidence.

## M5 — DST/timezone hardening regression

Actual path identified: connector extract normalization
(`source_timezone` on SourceExtract; GA4/GSC/GAM normalizers) + browser
checkpoint window scheduling (UTC storage, tz-aware columns). Canonical
timezone source: extract definition/source_timezone; persisted timestamps are
UTC-aware. Regression cases: fall-back duplicated local hour; spring-forward
nonexistent local time; GA4/GSC/GAM/browser points straddling a DST boundary.
No naive-datetime fallback anywhere on these paths.

## M6 — Minimal self-observability

Existing stack only (no vendor): operational read endpoints/log-derived checks
for scheduler last-run age, worker heartbeat, job queue depth/backlog, stale
lease/job detection, run duration/failure-rate counters, retention-job health,
connector staleness, browser-source reliability state. Surfaced consistently
with EP-025a source-health semantics.

## M7 — Pilot runbook + technical-readiness exit gate

Runbook items: HTTPS/secure-cookie verification steps; OAuth permission
checklist; degraded/revoked connector handling; publisher allowlisting
(identity + UA + how to request allowlisting); compatibility self-check usage;
browser-source degradation troubleshooting + recovery verification; retention
job failure handling; cost-cap/circuit-breaker activation; scheduler/worker
failure recovery.

Technical-readiness exit gate (all must hold): all EP-026 criteria green ·
secure-cookie M1 green · retention execution proven · cost caps verified ·
DST regression green · network reliability green · browser degradation
separated from publisher health · connector staleness green ·
self-observability green · 3–5 end-to-end investigations executed and manually
reviewed (≥1 monetization case, ≥1 missing/degraded-source case, and ≥1
browser-access degradation/challenge scenario — prefer a real consenting
pilot-site case when organically available; otherwise the controlled
synthetic/fixture production-path validation from M2 is MANDATORY and is never
skipped solely because no organic WAF occurrence appeared) · measured
representative cost · zero
unresolved BLOCKER/HIGH findings. **LLM synthesis NOT required. Limited Pilot
start remains an explicit separate HUMAN GATE even when technically ready.**

## M8 — Adversarial review & release readiness

Full adversarial pass over the EP diff against §15 checklist; exact
command/scope/count evidence per AGENTS.md; CI green on final HEAD.

## Human Gates (unresolved — planning does NOT choose)

Cloud provider selection · managed-secret provider change (OPEN-003/OPEN-005) ·
deployment topology · stable egress/network provider/IP architecture · any new
external service · any new runtime dependency · auth/security boundary redesign
· destructive migration · tenant/provenance weakening · stealth/evasion
behavior (permanently forbidden) · Limited Pilot start.

## 15. Adversarial Planning Review (post-clarification, 2026-08-24)

Re-run after the WAF/challenge clarification: no BLOCKER/HIGH/MEDIUM remains.
Secure-cookie gate is fail-closed and first; retention has execution-proof +
stall detection; cost caps are enforceable with bounded retries; DST cases hit
real normalization paths; browser-source degradation is isolated from
publisher health and from other connectors; the challenge scenario is
production-path validated (organic case preferred, synthetic fixture mandatory
otherwise) — never skippable for lack of organic occurrence; no dependency,
provider, or security decision is required to execute this plan; scope fits
one coherent EP. Status advanced DRAFT → READY.

## Validation Discipline

Every milestone: exact behavior proven, automated unit + PostgreSQL integration
scope, failure cases, rollback/recovery note, observability hook, exact
command/scope/count evidence (AGENTS.md rules). No invented counts during
planning; counts recorded at execution time.
