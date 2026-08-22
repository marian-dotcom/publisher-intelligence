# EP-020 — Incident Intake & Localization

**Status:** COMPLETE
**Owner:** Codex / Engineering
**Created:** 2026-08-22
**Updated:** 2026-08-22
**Target milestone:** Incident intake & localization (PLANS.md §76.1)
**MVP scope impact:** NO
**New infrastructure category:** NO

## Progress

- [x] M0 — Baseline verification
- [x] M1 — INCIDENT trigger source and incident-diagnostic checkpoint writer
- [x] M2 — Intake, localization, investigation initialization service
- [x] M3 — Bounded initial diagnostics with budget enforcement
- [x] M4 — Full validation and release readiness

## 1. Purpose and User Outcome

After this plan ships, a publisher/operator can open an incident through a deterministic backend
workflow: the symptom report is captured verbatim, the affected time window and scope are
localised against real scheduled evidence (last healthy observation before onset), a Last Known
Good reference is frozen for the investigation, and a bounded set of incident-diagnostic
checkpoints can be requested under budget enforcement. This is the first incident workflow; it is
service-layer only — no UI, no API endpoints, no LLM.

## 2. Scope and Non-Goals

### In

- `INCIDENT` added to the checkpoint trigger-source vocabulary (migration 0019 extends the CHECK;
  additive);
- incident-diagnostic checkpoint writer: ad-hoc windows + runs with
  `observation_kind='INCIDENT_DIAGNOSTIC'`, `trigger_source='INCIDENT'`, correlation = incident id,
  enqueued through the existing browser worker path;
- `IncidentIntakeService`: open-investigation (incident + segments via EP-019 repository),
  deterministic localization analysis over scheduled evidence, LKG freezing per
  site/template/scenario scope, bounded initial diagnostic requests enforced through the
  investigation budget ledger (`DIAGNOSTIC_RUN`);
- localization result object: last healthy scheduled observation before reported onset, earliest
  non-healthy/absent signal after onset (when available), affected scope from segments;
- unit + PostgreSQL integration tests.

### Out / Non-Goals

- evidence packs / typed relationships (EP-021);
- Inspect AI (EP-022); hypotheses/ranking (EP-023);
- OAuth/onboarding (EP-024); UI/endpoints (EP-025);
- retention enforcement, cost telemetry, network-reliability detection (EP-026);
- WAF/challenge detection of any kind (EP-026);
- hypothesis lifecycle or ranking; LLM anything;
- new event codes; changes to E1/E2/E3 derivation.

## 3. Canonical References

- `AGENTS.md` §2.1, §7, §15–18, §20, §28;
- `PLANS.md` §76.1 (EP-020 boundary);
- `INCIDENT.md` — intake starts from symptom (ADR-005); localization before explaining
  (ADR-049); baseline first (ADR-047); LKG selection/freeze (§88, ADR-060/061); UNRESOLVED valid;
- `DECISIONS.md` — ADR-029 (time uncertainty), ADR-047–049, ADR-057 (unaffected segments as
  evidence), ADR-062/063 (bounded falsifiable next tests), ADR-089/090, ADR-130, ADR-096/097;
- `DATA_MODEL.md` §66–68;
- completed EP-018 (observation kinds) and EP-019 (foundations).

## 4. Current State

Main `73fd563` after EP-019 merge. Existing: incidents/segments/LKG/usage/holds tables +
repository (EP-019); `checkpoint_runs.observation_kind` includes reserved
`INCIDENT_DIAGNOSTIC` with no writer; trigger-source CHECK allows only `OPERATOR_CLI`,
`LEGACY_CLI`; browser worker completes any PENDING→RUNNING run regardless of kind and skips
derivation for non-scheduled completions (EP-018). No intake/localization code exists. Migration
head `0018`.

## 5. Target Behavior

```text
open_investigation(site, symptom report)
  → incident(OPEN) + segments persisted; investigation_key = "inc-{id}"
localize(incident_id, fingerprints)
  → deterministic analysis of SCHEDULED evidence:
      last_healthy_at = latest COMPLETE scheduled run ≤ reported_start
      first_anomaly_at = earliest non-COMPLETE scheduled run in (last_healthy, reported_end]
      → freeze LKG ref(s) valid_for_incident_id=incident (per scenario/template scope)
      → return LocalizationResult
request_initial_diagnostics(incident_id, max_scenarios=2)
  → budget.consume(DIAGNOSTIC_RUN, correlation=incident, usage_key=inc|DIAG over budget)
        refused with InvestigationStateError when within_limit is false
  → per selected active scenario (≤ max_scenarios):
        ad-hoc window + INCIDENT_DIAGNOSTIC run (trigger_source=INCIDENT,
        correlation=incident_id) + BROWSER_CHECKPOINT job enqueue
```

Diagnostics never touch scheduled cohorts (EP-018 guarantees hold). Repeated diagnostic requests
with the same scenario set converge idempotently via distinct-but-deterministic usage keys
(`inc-{id}|DIAGNOSTIC_RUN|{scenario_id}:{attempt_seq}` derived from existing ledger entries count).

## 6. Architecture / Data Flow

```text
caller (EP-025 later)
  → IncidentIntakeService
       ├── InvestigationRepository (incidents, LKG freeze, ledger)   [EP-019]
       ├── CheckpointService.enqueue_incident_diagnostic            [new]
       │      └── ad-hoc window + INCIDENT_DIAGNOSTIC run + job
       └── fingerprint context from app.common.comparability
browser worker completes diagnostics → evidence stored → NO derivation (EP-018)
```

## 7. Files and Modules Affected

### Existing

- `backend/app/browser/contracts.py` — TRIGGER_SOURCES += "INCIDENT";
- `backend/app/browser/models.py` — CHECK mirror;
- `backend/app/browser/service.py` — generalise ad-hoc registration into an internal helper used
  by both operator CLI and the new incident-diagnostic method;
- `backend/tests/integration/test_observation_run_semantics.py` — extend constraint coverage to
  the INCIDENT source;
- `README.md` boundary sentence (M4).

### To create

- `backend/migrations/versions/0019_incident_trigger_source.py`;
- `backend/app/incidents/intake.py` (`IncidentIntakeService`, `LocalizationResult`);
- `backend/tests/unit/incidents/test_intake_contracts.py` (pure validation);
- `backend/tests/integration/test_incident_intake_localization.py`.

## 8. Data Model / Migration Impact

Migration `0019_incident_trigger_source`: drop + recreate
`ck_checkpoint_runs_trigger_source` allowing `'OPERATOR_CLI','LEGACY_CLI','INCIDENT'`. Additive;
no data change; downgrade restores the two-value vocabulary but must refuse while rows with
`trigger_source='INCIDENT'` exist. Model mirrors exactly.

## 9. Milestones

### M0 — Baseline verification

- [ ] branch from clean main; post-merge CI green; head/tables inspected.

### M1 — INCIDENT trigger source

Acceptance:

- [ ] migration up/down/up passes; downgrade refuses while INCIDENT-sourced runs exist;
- [ ] DB accepts INCIDENT_DIAGNOSTIC + INCIDENT + correlation rows; rejects unknown sources;
- [ ] model/constraint mirrored.

### M2 — Intake & localization service

Acceptance:

- [ ] open_investigation persists incident + segments atomically and returns investigation key;
- [ ] localize() anchors on latest healthy scheduled evidence before onset and freezes LKG refs
      per scenario/template scope with incident binding;
- [ ] localization is deterministic for identical evidence state;
- [ ] cross-tenant access impossible on every entry point.

Validation:

```bash
uv --directory backend run pytest tests/integration/test_incident_intake_localization.py -k "intake or localize"
```

### M3 — Bounded initial diagnostics

Acceptance:

- [ ] diagnostic requests create ad-hoc-window INCIDENT_DIAGNOSTIC runs with correct provenance
      and enqueue BROWSER_CHECKPOINT jobs;
- [ ] requests beyond the DIAGNOSTIC_RUN limit are refused without creating runs/jobs;
- [ ] ledger records consumption idempotently per scenario attempt;
- [ ] repeated request after refusal still refused until retention of entries changes (no silent
      limit reset).

Validation:

```bash
uv --directory backend run pytest tests/integration/test_incident_intake_localization.py -k diagnostic
```

### M4 — Full validation and release readiness

- [ ] full ladder locally + CI green; README sentence; plan COMPLETE.

## 10. Final Acceptance Criteria

- [x] intake → localization → LKG freeze → bounded diagnostics works end-to-end on seeded
  evidence;
- [x] every diagnostic carries concrete persistent provenance bound to its incident;
- [x] budget enforcement is persistent and refuses excess;
- [x] scheduled cohort purity untouched (regression suites prove it);
- [x] tenant isolation holds everywhere;
- [x] full validation ladder passes locally and in CI.

## 11. Test Cases

Happy: intake+segments; localization anchor + freeze; diagnostics created/enqueued within limits.
Counterexamples: end-before-start window; diagnostics past limit; wrong tenant; unknown source;
diagnostic completion generates no events (EP-018 regression). Regression: full integration suite.

## 12. Final Validation

Same ladder as EP-019 (ruff, mypy, unit, clean-DB upgrade/downgrade-up, integration, scheduler/
worker smoke, frontend, secret scan, compose config, git diff --check, GitHub CI).

## 13. Security / Privacy Impact

Incident text remains tenant-confidential; diagnostics inherit browser guard semantics (same
URL-derivation rules, private networks blocked outside controlled fixtures). Trigger provenance
references only internal ids. No new external surface.

## 14. Observability / Failure Handling

Budget refusals raise typed `InvestigationStateError` ("investigation budget exhausted") with the
resource kind; caller-visible only. No new job types.

## 15. Rollback Strategy

Revert removes service + writer; migration downgrade restores two-value vocabulary but refuses
while INCIDENT-sourced runs exist (evidence-safe). Diagnostics never feed cohorts, so rollback
cannot corrupt baselines.

## 16. Known Risks

- Diagnostic scenario selection policy (which scenarios to probe) is intentionally minimal
  (first N active scenarios by code); richer targeting waits for ranking milestones.
- Localization v1 uses only browser-checkpoint evidence availability; connector-based time
  localization arrives with evidence packs (EP-021).

## 17. Open Decisions

None block implementation. UI/API exposure is EP-025; richer diagnostic targeting is post-EP-023.

## 18. Decision Log

### 2026-08-22 — Diagnostics ride the existing browser pipeline

**Decision:** INCIDENT_DIAGNOSTIC runs are ordinary checkpoint rows/windows enqueued as
BROWSER_CHECKPOINT jobs; no new job type or worker.

**Reason:** Worker already isolates, completes, and stores evidence for any run; EP-018 already
guarantees non-scheduled completions generate no events.

**Alternatives:** Dedicated diagnostic worker/job — rejected: duplicates pipeline for zero gain.

**Impact:** None; bounded purely at the request layer via the ledger.

### 2026-08-22 — Per-scenario usage keys instead of one incident-wide key

**Decision:** usage_key = `inc-{id}|DIAGNOSTIC_RUN|{scenario_code}:{n}` where n = current entry
count for that scenario, so each granted diagnostic has its own auditable entry while total
consumption stays capped by the limit check.

**Reason:** Idempotent retries of the same grant collapse; distinct grants remain distinguishable
for forensics.

**Alternatives:** Single cumulative key — rejected: retry would double-count nothing but also
record nothing per grant.

**Impact:** Limit check counts entries; races are bounded by single-worker request flow today.

### 2026-08-22 — Autopilot execution started; M0–M4 complete

Branch `agent/implement-ep-020` from clean main `73fd563` (EP-019 merged, post-merge CI green).
Implemented: migration 0019 (INCIDENT trigger vocabulary), `enqueue_incident_diagnostic` writer
(ad-hoc windows, INCIDENT_DIAGNOSTIC kind, incident-correlated provenance), and
`IncidentIntakeService` (open_investigation, deterministic localize with LKG freeze per
scenario scope, bounded diagnostics through the EP-019 ledger). No human gates encountered.

Next step: release readiness recorded; PR #23 review/merge.

## 19. Discoveries / Surprises

- Localization must load non-COMPLETE scheduled runs to detect anomalies; the healthy/anomalous
  split happens in Python, not SQL status filters.
- The `(window, url, scenario)` uniqueness constraint means incident diagnostics of one URL can
  never silently mix into a scheduled window's cohort — structural purity on top of EP-018.
- Test cleanup order matters: foundation tables (usage/LKG/holds/segments/incidents) must be
  deleted before sites due to RESTRICT foreign keys.

## 20. Progress Log

### 2026-08-22

Created under the multi-ExecPlan program immediately after EP-019's merge and green post-merge CI.
Marked READY: builds entirely on landed foundations; the only schema touch is an additive CHECK
vocabulary extension; no human-gated decision required. Implementation not started.

### Correction validation — 2026-08-22

- Adversarial review found the 0019 downgrade guard untested (inconsistent with its predecessors).
  Added `test_downgrade_refuses_while_incident_sourced_runs_exist`; full integration suite now
  54/54.

## 20.1 Validation Results

### Local validation — 2026-08-22

- ruff format/check, mypy: PASS (209 files / 190 sources).
- Unit suite (clean environment): PASS, 267.
- Clean-database upgrade → head 0019; full downgrade base / re-upgrade cycle: PASS.
- New integration tests `test_incident_intake_localization.py`: PASS, 3 tests.
- Full PostgreSQL integration suite: PASS, 53/53.
- Scheduler/worker smoke, frontend lint/typecheck/test/build, secret scan, compose config,
  whitespace checks: PASS.

## 21. Final Outcome / Retrospective

### What shipped

The first incident workflow: `IncidentIntakeService.open_investigation` captures symptom reports
verbatim with structured segments; `localize` anchors investigations on the latest healthy
scheduled evidence before reported onset, records the earliest post-onset anomaly when present,
and freezes incident-bound Last Known Good references deterministically; and
`request_initial_diagnostics` grants bounded INCIDENT_DIAGNOSTIC checkpoints through the
persistent DIAGNOSTIC_RUN budget ledger. Migration 0019 extends the trigger vocabulary with
`INCIDENT`. Diagnostics ride the existing browser pipeline and never touch scheduled cohorts.

### What changed from the plan during implementation

Localization loads all scheduled runs for the site and splits healthy/anomalous in Python rather
than filtering by status in SQL — required to observe SITE_ERROR/TIMEOUT rows as anomaly signals.

### Validation performed

Full ladder as recorded above, plus GitHub Actions CI (see below).

### Known limitations

- Diagnostic targeting selects the first N active scenarios by code; richer targeting waits for
  ranking milestones.
- Localization v1 uses browser-checkpoint availability only; connector-based time localization
  arrives with EP-021 evidence packs.
- No UI/API surface yet (EP-025).

### Follow-ups

- PR #23 review/merge requires human authorization; then EP-021 per roadmap.

### Lessons

Foundation-first sequencing paid off: EP-020 needed zero schema invention beyond one CHECK
vocabulary extension.
