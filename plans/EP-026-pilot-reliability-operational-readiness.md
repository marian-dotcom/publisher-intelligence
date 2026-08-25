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
- [x] M2b-1a-2b-i — DIAGNOSTIC classification → canonical Event persistence
      COMPLETE (clean split; automatic trigger deferred to 2b-ii):
      load_diagnostic_input surfaces the stored bounded classification
      (fail-closed parser `classification_from_storage`); new
      `evaluate_diagnostic` maps degraded → BROWSER_SOURCE_DEGRADED (HIGH) and
      challenge_suspected (dormant until M2b-1b marker/body work) →
      BROWSER_ACCESS_CHALLENGE_SUSPECTED (MEDIUM) as site-level POINT events
      with the diagnostic run as TRIGGER_AFTER evidence (occurred_after_at
      NULL, no fabricated predecessor); ok/missing/malformed classifications
      stay quiet. Migration 0025_browser_source_events_e26 AUTHORIZED for this
      slice: DATA-ONLY seed of the three e26-v1 definitions (0016 pattern,
      guarded downgrade). Dedicated `_validate_diagnostic_scope_against_run`
      accepts site-level scopes via an explicit SOURCE_LEVEL validation mode;
      the strict SCHEDULED validator is byte-identical to HEAD. NO
      DERIVE_BROWSER_EVENTS job is enqueued for DIAGNOSTIC finalize in this
      slice — acceptance path is explicit EventService.derive; ADR-130 test
      expectations unchanged from b757546. EVENTS.md §0.1 legend updated incl.
      single-observation TRIGGER_AFTER clarification. Evidence: ruff
      check+format clean; canonical mypy scope `mypy app tests scripts
      evals_runtime migrations/env.py` clean (249 files worktree; 248 at HEAD;
      the historical "242" figure was the same command without evals_runtime);
      unit + PostgreSQL integration suites green except the documented
      pre-existing browser-env failures in test_browser_checkpoint.py.
- [x] M2b-1a-2b-ii — AUTOMATIC diagnostic reliability derivation COMPLETE:
      DIAGNOSTIC finalize (classification present) now enqueues exactly one
      DERIVE_BROWSER_EVENTS job (idempotency key
      derive-browser-events:{run}:e26-v1, on_conflict_do_nothing, bounded
      max_attempts=3); existing worker handler and EventService.derive reused
      unchanged; no new job type, no schema change, no worker modification.
      RED→GREEN proven by tests/integration/test_diagnostic_reliability_autoderive.py:
      RED 4 collected / 0 passed (finalize enqueued nothing: assert 0 == 1)
      → GREEN 4 passed — full production path begin_attempt→finalize(403
      PARTIAL)→job→worker handle_job→exactly one BROWSER_SOURCE_DEGRADED
      event + one TRIGGER_AFTER evidence ref; retry attempts cannot duplicate
      jobs; worker rederivation stays single-event/single-ref; healthy
      diagnostics enqueue but derive zero events (no false degradation).
      ADR-130 comment narrowed in place; SCHEDULED enqueue/key byte-identical.
      M2b-1a (diagnostic classification → canonical reliability events,
      explicit + automatic) complete.
- [x] M2b-1b — bounded access-challenge detection COMPLETE: the runner reduces
      the already-in-memory DOM to a deterministic marker signal immediately
      after content read (`detect_challenge_marker`, scan capped at
      CHALLENGE_MARKER_SCAN_CHARS=100_000, output = marker name only; text
      never retained/persisted); BrowserEvidence carries only
      `challenge_marker: str | None`; finalize passes it to the unchanged
      classify_access (marker now takes precedence over bare status anomaly:
      403+marker → challenge_suspected, 403 alone → degraded). RED→GREEN via
      tests/integration/test_access_challenge_detection.py through the REAL
      path (local controlled challenge fixture → Playwright collection →
      finalize → DERIVE_BROWSER_EVENTS → worker handle_job): RED 4 collected /
      2 passed / 2 failed ('degraded' != 'challenge_suspected') → GREEN 4
      passed incl. exactly one BROWSER_ACCESS_CHALLENGE_SUSPECTED event + one
      TRIGGER_AFTER ref, sentinel-based no-raw-persistence proof across
      classification/manifest/limitations/environment/events/refs/jobs,
      plain-403-stays-degraded control, healthy control, idempotency. Full
      integration suite green locally with CI's BROWSER_ALLOW_PRIVATE_NETWORKS
      opt-in (the historical "12 browser-env failures" were that missing env
      var): 126 passed / 0 failed.
- [x] M2b-2 — deterministic browser source health + recovery/recheck
      COMPLETE: read-time projection over immutable reliability events (new
      app/events/source_health.py: BrowserSourceHealth HEALTHY|DEGRADED with
      reason/detected_at/source-event/trigger-run linkage; NO persistent
      source-health state, no schema). Hysteresis contract resolved explicitly
      (decision A): reliability Events are observation-level facts; one
      confirmed DIAGNOSTIC degradation establishes source DEGRADED until a
      qualifying recheck recovers it; routine SCHEDULED observations never
      create or close episodes (ADR-130 untouched). Qualifying recovery = open
      episode + full truthful context + healthy DIAGNOSTIC recheck strictly
      AFTER the degradation evidence, different run;
      BROWSER_SOURCE_RECOVERED POINT event with prior degraded run as BEFORE
      evidence, recheck as TRIGGER_AFTER, occurred_after_at = prior detection
      time (truthful lower bound); evaluation fails closed on partial
      context. load_diagnostic_input surfaces bounded open-episode context.
      /product/source-health reports a DEGRADED override for open episodes
      plus additive browser_monitoring_detail (state/reason/timestamps/event
      ids/explicit boundary wording); home_status honors the override;
      connector states unchanged. RED→GREEN:
      tests/integration/test_browser_source_recovery.py — behavioral RED 4
      collected / 0 passed ('assert 0 == 1' recovered count after qualifying
      recheck) → GREEN 4 passed: degradation→recovery full automatic path,
      episode degrade→recover→degrade (history immutable), idempotent
      reprocessing, unrelated-SCHEDULED-success control. Unit controls:
      pre-degradation recheck cannot recover, partial context fail-closed,
      self-recovery blocked. Full integration 130 passed / 0 failed; unit 331
      passed; ruff/mypy(254)/secrets clean; scheduler+worker smoke clean.
      Data-quality semantics documented in BROWSER.md §81.1 and EVENTS.md
      §0.1. Remaining M2 item: egress-provider HUMAN GATE at M2 closeout.
- [ ] M2 — Monitoring network reliability closeout (allowlistable egress
      identity HUMAN GATE, documented non-deceptive User-Agent rollout,
      compatibility self-check diagnostic)
- [x] M3a-0 — retention class reconciliation COMPLETE @ efea202: routine
      browser screenshots (viewport/pre-consent/post-consent/full-page)
      reclassified CORE_MEDIUM -> RAW_MEDIUM per SECURITY.md §105-106
      (CORE_MEDIUM is not a canonical class); RAW_DOM stays RAW_MEDIUM,
      NORMALIZED_DOM stays CORE_LONG; artifact types/filenames/capture
      timing/storage/schema untouched; real-path checkpoint tests pin exact
      retention class per artifact type; zero production CORE_MEDIUM writes.
- [x] M3a — retention enforcement + auditable execution proof COMPLETE:
      migration 0026_retention_runs (additive append-only audit table:
      id/started_at/finished_at NULLable/rows_deleted_per_table JSONB/
      hold_conflicts_skipped; global execution scope so NO fabricated
      tenant_id); ENFORCE_RETENTION job type enqueued once per UTC day by
      RetentionSchedulingService (idempotency key enforce-retention:{date},
      priority -20, max_attempts 3), consumed by narrow worker handler via
      existing queue lifecycle; RetentionService deletes expired RAW_MEDIUM
      artifacts (screenshots 90d, RAW_DOM 30d, keyed by retention_class +
      artifact_type) in bounded batches of 50, object-store delete BEFORE DB
      row delete (absent objects idempotent), active RetentionHold always
      prevents deletion and is counted as hold_conflicts_skipped;
      finished_at written only on success — failed executions leave an open
      run plus FAILED/RETRY job truthfully. Missed/stalled visibility:
      deterministic retention_health helper (HEALTHY/MISSED/STALLED/FAILED)
      over runs + job lifecycle for M6 wiring. RED→GREEN proven through the
      production chain (scheduler→claim→handle_job→S3→DB→retention_runs):
      RED 4 collected / 1 passed / 3 failed (no enforcement path existed)
      → GREEN 5 passed incl. hold preservation, fresh/CORE_LONG controls,
      idempotent second run appending audit history (deletion count 0),
      storage-outage failure leaving row + open run, all four health states.
      Full integration 135 passed / 0 failed; unit 331 passed; ruff/mypy(260)/
      secrets clean; scheduler+worker live smoke clean. Connector freshness
      (M3b) followed as the next milestone below.
- [x] M3a final correctness fix @ (this commit): one ENFORCE_RETENTION
      execution now drains the full eligible unheld backlog via repeated
      bounded batches — BATCH_SIZE=50 bounds each selection query, never the
      run/day; a tiny deterministic non-progress guard fails loudly instead of
      looping if a fully-skipped batch were re-selected. finished_at is now a
      fresh completion timestamp read only after successful enforcement
      (previously reused started_at); failed runs keep finished_at NULL.
      hold_conflicts_skipped is execution-level truthful: pre-existing holds
      counted once at start, late holds increment exactly once, held rows are
      excluded from later selections so no double counting. Behavioral RED on
      0fa419b: seeded BATCH_SIZE+5 eligible expired → deleted exactly 50,
      5 left; GREEN: all 55 drained in one execution, backlog 0,
      retention_health HEALTHY; >BATCH_SIZE backlog with 2 pre-holds and
      3 late holds deletes only unheld rows with counts exact. Full
      integration 142 passed / 0 failed; unit 331 passed; ruff/mypy(260)/
      secrets clean; scheduler+worker smoke clean against isolated EP-026
      test Postgres.
- [x] M3b — connector staleness/freshness surfaced through the EXISTING
      source-health model COMPLETE: additive STALE state (backend
      SOURCE_HEALTH_STATES + frontend SourceHealth union); freshness is
      DERIVED at read time from trustworthy success timestamps only —
      GA4/GSC/GAM DataConnection.last_success_at, PUBLIC_CONFIG latest
      SCHEDULED snapshot with parse_status VALID/VALID_WITH_WARNINGS using
      observed_at, BROWSER latest SCHEDULED CheckpointRun.completed_at with
      its canonical ~7h heuristic (stale outcome now STALE instead of
      UNAVAILABLE). Thresholds = 3x scheduler cadence, no magic numbers in
      handlers: GA4 6h (2h slots), GSC 12h (4h slots), GAM 6h (2h slots),
      PUBLIC_CONFIG 18h (6h slots). Precedence preserved: DEGRADED/
      ACTION_REQUIRED/BLOCKED connection states dominate staleness;
      never-synced CONNECTED reads UNKNOWN not HEALTHY; one stale source
      never implies publisher/site failure nor touches other sources.
      No schema, no persisted health rows, no extract freshness_status
      writes. Behavioral RED on e01fe5a: CONNECTED + 14-day-old success
      reported HEALTHY; GREEN reports STALE with boundary tests just
      inside/outside each threshold. Focused suite 15 passed; full unit 331
      passed; full integration 157 passed; ruff/mypy(262) clean; frontend
      lint/typecheck/test(38)/build clean; secrets clean. M4 NOT started.
- [x] M3 — connector staleness/freshness operationalization (M3b)
- [x] M4 — Cost telemetry, hard caps & circuit breakers COMPLETE: ledger
      pattern extended with CHECKPOINT_RUN resource kind (migration
      0027_checkpoint_run_budget_kind widens the check constraint only);
      measured cost is recorded at execution time by the real browser worker
      via an injected CheckpointCostRecorder — one idempotent run-scoped entry
      (amount=1 over the bounded one-page set; detail carries measured
      status/attempt), recorded on success AND runtime failure, retries folded
      into the single entry so bounded attempts can never become a spend loop.
      Circuit breaker is a deterministic read-time projection of the same
      append-only ledger: DEFAULT_CHECKPOINTS_PER_SITE_WINDOW=4 per
      site/window; schedule_due stops materializing runs/jobs for a scope at/
      above cap (SchedulingResult.breaker_skipped_sites, warning logged,
      fail-closed) and source-health surfaces BLOCKED for browser monitoring
      with precedence active-DEGRADED-episode > breaker-BLOCKED > heuristic;
      never publisher/site failure. No mutable breaker state, no global engine
      coupling in unit-tested paths. RED→GREEN: without wiring, cost recording,
      scope resolution and cap-stop all failed behaviorally; GREEN 4/4 M4
      tests + full integration 162 passed; unit 331 passed; ruff/mypy(257)
      clean; scheduler+worker smoke green on the isolated EP-026 test
      Postgres; canonical monolithic integration 162 passed locally.
- [x] M5 — DST/timezone cross-source hardening regression COMPLETE
      (regression-hardening only; zero production changes required —
      investigation CONFIRMED all four temporal paths already correct):
      GA4 normalizer attaches property tz with explicit fold=0 and converts
      to UTC — fall-back label 03:00 Bucharest anchors at its first absolute
      instant with a truthful two-real-hour period spanning both occurrences;
      spring-forward gap hour collapses deterministically to the transition
      instant (zero-length period, never fabricated, never naive). GSC pins
      America/Los_Angeles, validates offset hours against the source zone and
      rejects contradicting offsets; LA fall-back day proven to span 25 real
      hours. GAM explicitly enumerates both folds — ambiguous hours produce
      intervals spanning both absolute instants flagged DST_AMBIGUOUS_HOUR;
      nonexistent local hours are refused. Browser six-hour windows stay
      deterministic and UTC-aware: fall-back night spans 7 real hours,
      spring-forward 5; naive instants are rejected. Cross-source alignment
      test proves GA4/GSC/GAM/browser points order by absolute instant across
      one boundary. PostgreSQL round-trip via SourceExtract + CheckpointWindow
      preserves tz-awareness and exact instants. New tests: 9 unit
      (normalizers/scheduler) + 1 integration (round trip). Full integration
      163 passed; unit 340 passed; ruff/mypy clean; scheduler+worker smoke
      green.
- [x] M6 — Minimal self-observability COMPLETE: authenticated tenant-scoped
      GET /product/operations projects PI-infrastructure signals from
      EXISTING persisted truth (no new persistence, no vendor): scheduler
      last-run age from max(jobs.created_at) filtered to the scheduler-
      EXCLUSIVE ENFORCE_RETENTION job type (created only by
      RetentionSchedulingService.schedule_due whose sole production caller is
      scheduler.run_once) with CURRENT/STALE at 26h (> daily retention
      cadence + margin); a post-implementation soundness review CONFIRMED the
      original unfiltered max(jobs.created_at) was defective — non-scheduler
      production paths (diagnostic checkpoints, incident diagnostics,
      VALIDATE_PUBLIC_CONFIG worker follow-ups, drilldown planning) could
      refresh it while the scheduler was dead — and regression tests now pin
      that unrelated work can neither fake CURRENT nor replace last_run_at; worker liveness from
      max(jobs.started_at) with a 48h envelope — old rows alone never read
      healthy; queue depth splits runnable(PENDING/RETRY), leased(RUNNING
      with future lock_expires_at) and stale leases (expired lease, same
      predicate as the existing reclaim path); run duration + failure rate
      derived from real started/finished timestamps over a bounded 24h
      window; retention health projected from M3 retention_health (STALLED/
      FAILED/MISSED/HEALTHY reused verbatim); per-site source-health rows
      reuse M2/M3b/M4 states unchanged (DEGRADED episode > breaker BLOCKED >
      heuristic; connector STALE untouched). Strict separation maintained:
      infrastructure staleness never implies publisher/site failure. Every
      sub-signal degrades independently to UNKNOWN instead of fabricating
      HEALTHY. Behavioral RED: without the route /product/operations returns
      404 (no operational visibility); GREEN 10/10 integration tests incl.
      bounded-denominator and tenant-scoping proofs. Full integration 173
      passed; unit 340 passed; ruff/mypy(261) clean; scheduler+worker smoke
      green.
      failure-rate visibility)
- [x] M7 — Pilot runbook + technical-readiness exit gate COMPLETE
      (documentation/evidence milestone; zero production changes):
      docs/runbooks/pilot-readiness.md adds the operator runbook (HTTPS/
      secure-cookie verification incl. live-smoke procedure, OAuth permission
      checklist, degraded/revoked connector handling incl. STALE semantics,
      publisher allowlisting + compatibility self-check + challenge
      troubleshooting + recovery re-check, retention failure handling with
      hold/forbidden-action rules, cost-cap/circuit-breaker activation and
      window-rollover recovery, scheduler/worker/queue recovery using final
      M6 scheduler-exclusive semantics) plus the full EP-026 readiness matrix
      and findings classification. All technical criteria PASS; the exit-gate
      3 E2E investigations (browser-access degradation/challenge, degraded-
      source partial operation, monetization capability gating) were EXECUTED
      green through production paths on 2026-08-25 (named tests recorded in
      the runbook); their MANUAL REVIEW was subsequently performed by the human
      reviewer on 2026-08-25: INV-01 ACCEPT, INV-02 ACCEPT, INV-03 ACCEPT
      WITH NOTE (preserved verbatim: "Validates monetization context
      reconstruction and gating/provenance, not a full monetization root-cause
      investigation") — investigation-review gate = PASS. The single
      remaining technical-readiness blocker is the M1 live HTTPS
      secure-cookie smoke on the real authorized deployment, so:
      EP-026 TECHNICAL READINESS = HUMAN GATE pending that smoke;
      Limited Pilot authorization NOT GRANTED (independent human gate).
      Findings: 0 BLOCKER / 0 HIGH / 0 MEDIUM unresolved release findings;
      LOW/debt explicitly retained (~10 SQLAlchemy lifecycle warnings,
      3 diagnostic-only M3b commits in branch history, provider-selection
      gate deferred to deployment). validation
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
