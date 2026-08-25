# EP-026 Pilot Runbook & Technical-Readiness Gate

Operator-facing runbook plus the technical-readiness reconciliation for
EP-026. Executable by an operator who did not build the system. Every claim
points at a persisted source of truth or an automated proof.

Status legend for the readiness matrix: `PASS` / `FAIL` /
`HUMAN GATE` / `UNKNOWN`.

---

## Part A — Operator runbook

### A1. HTTPS / secure-cookie verification

- Symptom: login works over plain HTTP in staging/production; cookies missing
  `Secure`.
- Confirm: from a browser devtools panel inspect `pi_session` /
  `pi_csrf` on the deployment domain; check `curl -sI https://<host>` uses TLS.
- Authoritative source: `app/config/settings.py`
  (`environment` + fail-closed model validator), SECURITY.md §201; startup
  refuses to boot staging/production with `cookie_secure=False`.
- Expected state: `environment=staging|production` ⇒ both cookies carry
  `Secure`; `pi_session` also `HttpOnly`; `SameSite=lax`; app served only via
  HTTPS.
- Safe action: set explicit `COOKIE_SECURE=true` and terminate TLS at the
  edge; restart and re-check attributes.
- Recovery verification: repeat the attribute inspection; login still succeeds
  over HTTPS only.
- Escalate if: startup fails with the secure-cookie validation error — that is
  the fail-closed gate working; fix configuration, never bypass it.
- Forbidden: disabling Secure/HttpOnly to "make login work"; serving auth
  cookies over plain HTTP.

### A2. OAuth permission checklist (GA4 / GSC / GAM)

- Symptom: connector reads fail; connection shows an error state.
- Confirm: `GET /product/home/status` per site → connector state;
  authoritative row is `data_connections` (`status`,
  `last_error_class/code`, `last_attempt_at`, `last_success_at`).
- Expected states: `CONNECTED` (fresh success), `DEGRADED` (recent attempt
  failed), `AUTH_EXPIRED` → source-health `ACTION_REQUIRED`,
  `PERMISSION_ERROR` → `BLOCKED`.
- Safe action: re-grant scopes in the provider console; re-run OAuth consent;
  verify the minimal read-only scope list against CONNECTORS.md before
  requesting.
- Recovery verification: after re-consent, next scheduled extract completes →
  `last_success_at` updates → source returns to HEALTHY (or STALE until then —
  STALE means "no trustworthy new evidence yet", see A3/A4).
- Escalate if: PERMISSION_ERROR persists after verified grants.
- Forbidden: storing tokens outside the secret layer; widening scopes beyond
  read-only; treating administrative `status=CONNECTED` as proof of freshness.

### A3. Degraded / revoked connector handling

- Symptom: source-health DEGRADED / ACTION_REQUIRED / BLOCKED / STALE.
- Confirm: `/product/source-health?site_id=…` plus `data_connections`
  timestamps (`last_success_at` drives STALE via the M3b freshness policy:
  GA4 >6h, GSC >12h, GAM >6h, PUBLIC_CONFIG >18h).
- Semantics: STALE = "PI has not received trustworthy new evidence within this
  source's freshness window". It does NOT mean vendor down, credentials
  expired, publisher data changed, or site unhealthy.
- Safe action: check provider status page; verify credentials; wait for the
  next scheduled extract; investigate worker logs if attempts stopped.
- Recovery verification: new successful extract updates `last_success_at`;
  state returns HEALTHY.
- Escalate if: STALE persists beyond one cadence window with no failed
  attempt recorded (scheduler/worker issue — see A9/A10) rather than connector
  failure.
- Forbidden: manually editing `last_success_at`; suppressing STALE states;
  blaming the publisher for PI-side staleness.

### A4. Publisher allowlisting / monitoring identity

- Runbook: docs/runbooks/publisher-allowlisting.md (identity, stable egress
  requirement, UA documentation).
- Confirm allowlisting works: run the bounded EP-018 DIAGNOSTIC checkpoint
  against a representative URL; outcomes map deterministically to
  classification states.
- Forbidden: CAPTCHA solving, fingerprint spoofing, proxy rotation, stealth
  evasion (ADR-020). No cloud/provider selection is made by this repository.

### A5. Compatibility self-check

- Symptom: onboarding uncertainty whether a site tolerates monitoring.
- Confirm: enqueue one DIAGNOSTIC checkpoint (operator CLI/incident path);
  inspect `checkpoint_runs.browser_access_classification`
  (`{state, reason}`): healthy/degraded/challenge-suspected/blocked.
- Expected: COMPLETE + no challenge markers ⇒ nothing derivable; challenge
  markers ⇒ BROWSER_ACCESS_CHALLENGE_SUSPECTED evidence event.
- Safe action: share identity docs (A4) with publisher; retry after
  remediation.
- Escalate if: repeated SITE_ERROR across unrelated sites (likely PI-side
  network issue).

### A6. Browser-source degradation troubleshooting

- Symptom: `BROWSER_MONITORING` = DEGRADED on `/product/source-health`
  (detail block explains state/reason/detected_at/event id).
- Confirm: events `BROWSER_SOURCE_DEGRADED` /
  `BROWSER_ACCESS_CHALLENGE_SUSPECTED` (RECORDED/ACTIVE); episode logic in
  `app/events/source_health.py`.
- Expected semantics: describes OUR observation source only — never
  publisher/site health; GA4/GSC/GAM/public-config unaffected.
- Safe action: diagnose network/egress; remediate; trigger the bounded
  diagnostic re-check.
- Escalate if: degradation persists across distinct target sites.

### A7. Recovery / re-check verification

- Confirm: after remediation the automatic recovery path records
  `BROWSER_SOURCE_RECOVERED`; episode closes; `BROWSER_MONITORING` leaves
  DEGRADED (automated proof:
  `tests/integration/test_browser_source_recovery.py::
   test_degradation_recheck_recovery_full_automatic_path`).
- Forbidden: marking recovered without a real successful observation; manual
  event edits.

### A8. Retention job failure handling

- Confirm: latest evidence = newest `retention_runs` row +
  `GET /product/operations` → `retention.state`
  (HEALTHY/MISSED/STALLED/FAILED from `app/retention/health.py`) and the
  ENFORCE_RETENTION job lifecycle (`jobs.status`, `last_error_class`).
- Semantics: open run older than the 6h stall threshold = STALLED; exhausted
  job = FAILED; nothing finished inside 48h = MISSED.
- Hold behavior: incident-linked RetentionHold rows always protect artifacts;
  deletion skips held rows and counts them (`hold_conflicts_skipped`).
- Safe action: fix the underlying storage/DB fault, let the daily job retry
  (max_attempts=3); backlog drains via bounded batches on the next success.
- Recovery verification: a new finished run with truthful
  `rows_deleted_per_table`; operations retention → HEALTHY.
- Forbidden: manual DELETEs against artifacts/artifact storage; editing
  retention_runs; raising BATCH_SIZE to "catch up".

### A9. Cost cap / circuit breaker

- Confirm: `/product/operations` → per-site source-health shows
  BROWSER_MONITORING `BLOCKED` when breaker is open; usage evidence lives in
  `investigation_usage` (`resource_kind='CHECKPOINT_RUN'`, keyed
  `site:<id>|window:<window_id>`), cap = 4 units per site/window.
- Semantics: at/over cap the scheduler schedules NOTHING further for that
  scope until the six-hour window rolls over; BLOCKED never implies publisher
 /site failure.
- Safe action: wait for window rollover (automatic); investigate why spend
  spiked using the ledger detail (per-run measured facts).
- Recovery verification: new window → scheduling resumes; BLOCKED clears once
  the latest window's usage is under cap.
- Escalate if: caps trip repeatedly without an obvious cause.
- Forbidden: raising the cap to unblock; deleting ledger rows; bypassing the
  scheduler to force runs.

### A10. Scheduler / worker failure recovery

Read surface: authenticated `GET /product/operations` (M6).

- Scheduler: state derived ONLY from scheduler-exclusive ENFORCE_RETENTION job
  creation (created solely by RetentionSchedulingService ← scheduler.run_once;
  repair commit `a2ab2c1`). CURRENT within 26h (> daily cadence + margin);
  STALE beyond it; UNKNOWN if no evidence exists. Generic Job creation
  (diagnostics, follow-ups, drilldowns) is NOT valid scheduler-liveness
  evidence.
  - Dead scheduler recovery: start the scheduler process; within one pass a
    new ENFORCE_RETENTION job appears; operations flips to CURRENT.
- Workers: state from max(`jobs.started_at`) within 48h; old completed rows
  never imply liveness. Stale workers + runnable backlog ⇒ start workers;
  fencing (lock_token/lease expiry + reclaim) makes recovery safe — expired
  leases are reclaimed automatically and retried within max_attempts.
- Queue: `runnable` (PENDING+RETRY), `leased` (RUNNING, lease valid),
  `stale_leases` (RUNNING with expired/absent lease). Persistent stale_leases
  with no live workers ⇒ worker outage; reclaim will recycle them once a
  worker returns.
- Escalate if: scheduler STALE persists after process start; stale_leases grow
  monotonically.
- Forbidden: hand-updating job rows to COMPLETE; disabling fencing; treating
  any operational staleness as publisher/site failure (publisher/site
  condition is serialized independently everywhere).

---

## Part B — Technical-readiness matrix (EP-026 acceptance criteria)

| Criterion | Status | Evidence |
|---|---|---|
| M1 secure-cookie fail-closed posture | PASS | settings validator + emission guard tests (plan M1 entry); HTTPS attribute smoke on real deployment remains operator step A1 |
| M1 HTTPS smoke on live deployment | HUMAN GATE | requires the actual pilot environment; procedure = A1 |
| M2 stable monitoring UA / non-deceptive identity | PASS | docs/runbooks/publisher-allowlisting.md; browser UA contract tests |
| M2 deterministic challenge detection → source-health impact | PASS | test_access_challenge_detection.py (real HTTP fixture → real Playwright → canonical event) |
| M2 degradation ≠ publisher failure; other connectors unaffected | PASS | test_product_read_p2a.py::test_degraded_source_health…; cross-source independence assertions in M3b suite |
| M2 automatic recovery re-check | PASS | test_browser_source_recovery.py full degrade→recover→degrade chain |
| M3a retention execution proof + hold-safe deletion + backlog drain | PASS | plan M3a entries @0fa419b/e01fe5a; tests test_retention_enforcement.py (12) incl. hold race + storage-failure + backlog>batch |
| M3a missed/stalled visibility | PASS | retention_health states tested; surfaced via /product/operations (M6) |
| M3b GA4/GSC/GAM freshness; CONNECTED-but-old → STALE | PASS | test_source_freshness_m3b.py (15) incl. boundary ±1min, never-synced UNKNOWN, precedence |
| M3b source staleness ≠ publisher failure | PASS | stale-source independence + home condition assertions |
| M4 measured cost + hard cap + exactly-at-cap breaker | PASS | test_cost_circuit_breaker_m4.py (4); ledger detail carries measured facts |
| M4 bounded retries / no spend loop | PASS | idempotent run-scoped cost entry test; existing max_attempts semantics unchanged |
| M4 representative workload evidence | PASS | seeded 60-run workload case in M4 suite (58 executed + 2 held) |
| M5 DST regression (fall-back / spring-forward / cross-source / no naive) | PASS | test_dst_temporal_regression_m5.py (9) + PG round-trip test |
| M6 authenticated /product/operations | PASS | test_operations_m6.py (auth negative + positive) |
| M6 scheduler health = scheduler-exclusive evidence | PASS | repair `a2ab2c1`; false-CURRENT regression pinned (Cases 1–4) |
| M6 worker/queue/stale-lease/duration/failure-rate visibility | PASS | test_operations_m6.py queue+execution-window tests (bounded denominator proven) |
| M6 retention health surfaced without duplication | PASS | STALLED projection test reusing retention_health |
| M6 infra health separate from publisher health | PASS | stale scheduler/worker tests assert home publisher_site_condition untouched |
| Exit-gate E2E investigations executed | PASS (execution) | three production-path investigations freshly executed — see Part C |
| Exit-gate investigations **manually reviewed** | PASS | human reviews recorded 2026-08-25: INV-01 ACCEPT, INV-02 ACCEPT, INV-03 ACCEPT WITH NOTE — see Part C verdict lines |
| Zero unresolved BLOCKER/HIGH/MEDIUM | PASS | findings review (Part D): 0/0/0 unresolved release findings |
| Provider selection / deployment egress identity / pilot go-ahead | HUMAN GATE | EP-024 deferred decision; A4 deployment-dependent egress identity; Limited Pilot human gate |

## Part C — End-to-end investigation records

All three were EXECUTED through real production paths (PostgreSQL + MinIO +
real Chromium where applicable) on 2026-08-25, all green. Manual review is
outstanding: every record below carries
`REVIEW: HUMAN GATE — MANUAL REVIEW REQUIRED`. The evidence packages are the
named tests plus the persisted rows they assert.

### INV-01 — Browser-access degradation/challenge (controlled synthetic)
- Category: browser-access degradation/challenge (mandatory).
- Trigger: controlled local HTTP fixture serving Cloudflare-style challenge
  body (sentinel-marked) → real DIAGNOSTIC checkpoint via real Chromium.
- Path: register_and_enqueue → browser_worker → finalize/classify
  (`challenge_suspected`) → DERIVE_BROWSER_EVENTS → worker handle_job →
  BROWSER_ACCESS_CHALLENGE_SUSPECTED event + TRIGGER_AFTER evidence ref.
- Source health: BROWSER_MONITORING DEGRADED during active episode; GA4/GSC/
  GAM/PUBLIC_CONFIG independently healthy; publisher_site_condition ACTIVE.
- Evidence/provenance: Event + EventEvidenceRef(CHECKPOINT_RUN), bounded
  classification JSONB on checkpoint_runs; sentinel proves no raw page content
  leaked into any persisted surface.
- Recovery: remediation fixture → automatic bounded re-check →
  BROWSER_SOURCE_RECOVERED → HEALTHY.
- Execution proof: test_browser_source_recovery.py::
  test_degradation_recheck_recovery_full_automatic_path (+episode/idempotence
  siblings) — green.
- REVIEW: **ACCEPT** (human review recorded 2026-08-25).

### INV-02 — Missing/degraded source with independent partial operation
- Category: degraded/missing source (mandatory).
- Trigger: PARTIAL scheduled browser run (observation degraded) while GA4/GSC/
  GAM remain connected; separately, CONNECTED-but-old sources vs fresh ones.
- Path: /product/home/status + /product/source-health projections.
- Result: BROWSER_MONITORING=DEGRADED (or STALE for aged evidence) while
  GA4/GSC/GAM stay HEALTHY; STALE semantics per source thresholds; no
  publisher/site failure fabricated (`publisher_site_condition` serialized
  independently); stale scheduler/worker signals likewise never imply site
  failure (M6 tests).
- Execution proof: test_degraded_source_health_does_not_become_publisher_site_failure;
  test_source_freshness_m3b.py boundary/independence cases;
  test_operations_m6.py stale scheduler/worker cases — green.
- REVIEW: **ACCEPT** (human review recorded 2026-08-25).

### INV-03 — Monetization context reconstruction
- Category: monetization (mandatory).
- Trigger: stored monetization metric points with capability classes.
- Path: product monetization exposure gated by capability: RELATIVE_ONLY
  suppresses currency amounts; ABSOLUTE exposes stored values; UNKNOWN fails
  closed; tenant isolation enforced (foreign tenant values invisible).
- Semantics: economic context reconstructed from stored, provenance-carrying
  points; NO causal claims (revenue drop ≠ cause anywhere in output).
- Execution proof: test_product_read_p2c.py::
  test_c5_monetization_exposure_is_gated_by_capability — green.
- REVIEW: **ACCEPT WITH NOTE** (human review recorded 2026-08-25). Reviewer note, preserved verbatim: "Validates monetization context reconstruction and gating/provenance, not a full monetization root-cause investigation." This scope limitation is accepted as-is; no broader causal claim is made anywhere in PI output.

(3 of the permitted 3–5 executed; additional cases declined because they would
duplicate existing coverage without adding review value.)

## Part D — Findings classification (release-relevant)

- BLOCKER: 0
- HIGH: 0
- MEDIUM: 0
- LOW / TECHNICAL DEBT (explicitly out of EP-026 release scope):
  - ~10 residual SQLAlchemy "non-checked-in connection" warnings from other
    pre-existing tests (latent async session hygiene debt; no EP-026 criterion
    violated; first lifecycle leak already fixed at `53fac01`).
  - 3 diagnostic-only M3b CI commits remain in branch history
    (`3e6dc89`, `367f3a1`, `f2561fc`); effect removed from workflow, history
    cleanup deliberately deferred.
- HUMAN GATES: live HTTPS cookie smoke on the real deployment (A1) — the one
  remaining technical-readiness blocker; stable egress identity publication
  (A4); EP-024 provider selection; Limited Pilot authorization itself.
  (Investigation manual reviews are no longer a gate: recorded ACCEPT /
  ACCEPT / ACCEPT WITH NOTE in Part C.)

## Part E — Gates

- Investigation manual-review gate: PASS (INV-01 ACCEPT, INV-02 ACCEPT,
  INV-03 ACCEPT WITH NOTE with the reviewer's preserved scope note).
- Remaining readiness blocker: M1 live HTTPS secure-cookie smoke on the real
  authorized deployment has not yet been performed successfully (procedure A1).
- EP-026 TECHNICAL READINESS: HUMAN GATE until that smoke is actually
  completed on the real deployment. All other technical criteria PASS.
- LIMITED PILOT AUTHORIZATION: NOT GRANTED (independent human decision;
  completing the HTTPS smoke does not by itself authorize Limited Pilot).
