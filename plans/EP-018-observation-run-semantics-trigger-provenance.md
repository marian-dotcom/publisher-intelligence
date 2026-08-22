# EP-018 — Observation Run Semantics & Trigger Provenance

**Status:** READY
**Owner:** Codex / Engineering
**Created:** 2026-08-22
**Updated:** 2026-08-22
**Target milestone:** ADR-130 browser run taxonomy
**MVP scope impact:** NO
**New infrastructure category:** NO

## Progress

- [x] M0 — Baseline verification and historical run audit
- [x] M1 — Migration 0017: run kind and trigger provenance on checkpoint runs
- [x] M2 — Scheduler, worker, and CLI behavior for observation kinds
- [x] M3 — Cohort purity: lineage, event derivation, and window aggregation exclusion
- [ ] M4 — Full validation and release readiness

## 1. Purpose and User Outcome

After this plan ships, every synthetic browser checkpoint carries an explicit, persistent,
auditable observation kind (`SCHEDULED`, `DIAGNOSTIC`; `INCIDENT_DIAGNOSTIC` reserved) and, for
non-scheduled runs, persistent trigger provenance. Operator/tooling-initiated checkpoints remain
first-class immutable evidence but can no longer silently pollute six-hour baselines, comparison
lineage, semantic-event derivation cohorts, or future Last Known Good selection. This closes the
last cohort-purity gap in the evidence store before Incident Engine work begins.

## 2. Scope and Non-Goals

### In

- add `observation_kind` and trigger-provenance fields to `checkpoint_runs` (migration 0017);
- controlled vocabularies: kind `SCHEDULED | DIAGNOSTIC | INCIDENT_DIAGNOSTIC`;
  trigger source vocabulary for non-scheduled runs;
- scheduler-created runs are always `SCHEDULED` with null provenance;
- CLI diagnostic registration creates `DIAGNOSTIC` runs whose provenance includes a concrete
  invocation UUID (category-only provenance is rejected);
- comparison-lineage predecessor lookup excludes non-scheduled runs;
- event derivation (`load_input`, window inputs) excludes non-scheduled runs;
- window aggregation cohorts exclude non-scheduled runs;
- document (not implement) LKG eligibility as scheduled-only;
- unit + PostgreSQL integration tests for scheduled-vs-diagnostic behavior;
- fresh-database migration validation.

### Out / Non-Goals

- incident tables, investigations, hypotheses, or any Incident Engine schema;
- relationship graph tables;
- Last Known Good implementation itself (only its future eligibility rule is documented);
- any LLM behavior;
- Inspect AI or eval-runtime work;
- connector redesign (connector drill-downs already satisfy ADR-130 semantics);
- public-config changes (its `fetch_kind` already satisfies ADR-130);
- retention/deletion jobs;
- UI/API surfaces;
- broader MVP expansion.

## 3. Canonical References

Read:

- `AGENTS.md` — sections 7 (evidence invariants), 8 (browser invariants), 10 (event invariants),
  15–18 (ExecPlans), 20 (data-model changes), 28 (diff discipline);
- `PLANS.md` — planning contract; §76.1 approved forward sequence;
- `DECISIONS.md` — **ADR-130 (Observation run taxonomy and cohort purity)**, ADR-016 (immutable
  evidence), ADR-017 (observer provenance), ADR-025 (checkpoint ≠ event), ADR-089/090 (tenant
  scoping), ADR-128 (job queue contracts);
- `EVENTS.md` — §3 (candidate persistence), §15.1 (observation-kind cohort purity);
- `BROWSER.md` — §7.4 (incident-triggered scenarios), observer-provenance requirements;
- `DATA_MODEL.md` — `checkpoint_runs` specification including new `observation_kind` and
  trigger-provenance fields;
- `INCIDENT.md` — §88 (Last Known Good deterministic selection and scheduled-evidence eligibility);
- completed `plans/EP-002…EP-009` (checkpoint/window/run schema history),
  `plans/EP-015`/`EP-016` (derivation and lifecycle behavior).

Relevant invariants:

- raw evidence is immutable; adding columns must not rewrite historical meaning;
- a checkpoint is never an event (ADR-025); kinds change cohort membership only;
- tenant/site ownership validated server-side everywhere;
- scheduler inserts jobs only (ADR-082); workers execute domain logic;
- do not retry away real publisher evidence.

## 4. Current State

Post-EP-017 main (`5e747cf`). Browser evidence pipeline:

- `checkpoint_windows` materialize site-local six-hour slots; `CheckpointRun` requires
  `checkpoint_window_id` (NOT NULL) with UNIQUE `(checkpoint_window_id, monitored_url_id,
  scenario_id)` (`backend/app/browser/models.py:203-233`);
- the operator CLI (`app.browser_cli register-and-enqueue` →
  `BrowserService.register_and_enqueue`, `backend/app/browser/service.py:80-155`) creates an
  ad-hoc five-minute window plus one run that is structurally identical to a scheduled run — it
  can enter comparison lineage and event derivation;
- comparison predecessor lookup lives in `backend/app/browser/persistence.py`
  (`ComparableCheckpoint`, exact-URL then SAME_TEMPLATE_URL_ROTATION fallback, ~line 1304) and has
  no kind filter because no kind exists;
- event derivation loads predecessor/window inputs via
  `EventRepository.load_input` / `load_window_inputs` (`backend/app/events/persistence.py`) with no
  kind filter;
- `public_config_snapshots.fetch_kind` already implements SCHEDULED/VALIDATION separation for
  public config (migration 0015) — not touched here;
- migration head is `0016_public_config_events_e3`.

## 5. Target Behavior

1. Every new `checkpoint_runs` row records `observation_kind`. The scheduler path writes
   `SCHEDULED` always. The CLI diagnostic path writes `DIAGNOSTIC` plus concrete provenance.
   Nothing today writes `INCIDENT_DIAGNOSTIC`; it exists in the vocabulary so I1 needs no migration.
2. Non-scheduled runs record persistent, concrete provenance at creation: a controlled
   `trigger_source` (e.g., `OPERATOR_CLI`) AND a non-null correlation UUID identifying the
   specific invocation/request (for the CLI: one fresh UUID per invocation; for future
   incident diagnostics: the requesting investigation/action ID per the implementing EP).
   SCHEDULED rows carry NULL provenance on both fields. Category-only provenance is impossible
   at the database level.
3. Comparison-lineage lookup refuses non-scheduled predecessors: a diagnostic rerun of the same
   URL/scenario produces no diff-derived events against it and does not displace the legitimate
   scheduled predecessor.
4. Event derivation skips diagnostic runs entirely: they contribute to neither pair evaluation nor
   window aggregation, and their completion enqueues no derivation job.
5. Diagnostic runs remain fully queryable immutable evidence with complete manifests, screenshots,
   and collector provenance.
6. Existing scheduled behavior is byte-for-byte unchanged: same windows, same jobs, same events.

Example:

```text
Run: uv … python -m app.browser_cli register-and-enqueue … (existing pilot site)
Expected:
  checkpoint_run persisted with observation_kind='DIAGNOSTIC',
  trigger_source='OPERATOR_CLI',
  trigger_correlation_id=<fresh invocation UUID>
  → completes normally, artifacts stored
  → appears in zero comparison lineages, zero derivations, zero events
Next scheduled six-hour run behaves exactly as before EP-018.
```

## 6. Architecture / Data Flow

```text
scheduler ──→ FETCH jobs ──→ browser worker ──→ CheckpointRun(kind=SCHEDULED)
CLI/operator ──→ BROWSER_CHECKPOINT job ──→ browser worker ──→ CheckpointRun(kind=DIAGNOSTIC,
                                                              trigger_source, correlation)
                                   │
                     completion ───┼─→ comparison lineage lookup   [kind = SCHEDULED only]
                                   ├─→ DERIVE_BROWSER_EVENTS job   [kind = SCHEDULED only]
                                   ├─→ window aggregation cohorts  [kind = SCHEDULED only]
                                   └─→ artifact/evidence store     [all kinds, immutable]
future: LKG eligibility lookup                                    [kind = SCHEDULED only]
```

The queue, worker, and repository boundaries are reused unchanged (ADR-079/081/083).

## 7. Files and Modules Affected

### Existing

- `backend/app/browser/models.py` — CheckpointRun columns + constraints;
- `backend/app/browser/contracts.py` — kind/source vocabularies and validation;
- `backend/app/browser/scheduling.py` — scheduler writes explicit SCHEDULED;
- `backend/app/browser/service.py` — CLI registration writes DIAGNOSTIC + provenance;
- `backend/app/browser/persistence.py` — lineage lookup filter (~line 1304 region);
- `backend/app/browser_worker.py` / worker handling — pass-through of stored kind (no branching
  expected);
- `backend/app/events/persistence.py` — `load_input`/`load_window_inputs` filters;
- `backend/migrations/versions/0017_observation_run_kind.py` — to create;
- `backend/tests/unit/browser/*`, `backend/tests/unit/events/test_worker.py`,
  `backend/tests/integration/test_browser_checkpoint.py`,
  `backend/tests/integration/test_migrations.py` — extensions;
- `README.md` — boundary summary sentence update (M4).

### To create

- `backend/migrations/versions/0017_observation_run_kind.py`;
- targeted tests for kind/provenance persistence and cohort exclusion.

## 8. Milestones

### M0 — Baseline verification and historical run audit

Goal: bind EP-018 to merged EP-017 main and establish whether any historical non-scheduled runs
exist before choosing a classification strategy.

Acceptance:

- [x] branch starts from clean `origin/main`; post-merge CI green;
- [x] lineage/derivation/window code paths inspected and recorded in this plan;
- [x] confirm no other writer creates checkpoint runs besides scheduler and CLI service;
- [ ] **historical run audit**: inspect every environment that can hold `checkpoint_runs` data
  (local pilot databases, any staging/production instances) for evidence of non-scheduled/ad-hoc
  browser runs. Deterministic identification signals to check (in order of trust):
  - creating job idempotency keys (`browser-checkpoint:{run_id}` CLI pattern vs the scheduler's
    window-scoped keys) joined through the jobs table where history survives;
  - `checkpoint_windows` whose `window_start` does not coincide with a canonical site-local
    00/06/12/18 boundary (the CLI creates ad-hoc five-minute windows);
  - window creation timestamps vs scheduler activity records.
- [x] audit executed — see Progress Log entry "M0 complete" for per-environment results.
- [x] record the audit result and chosen classification path (see M1) in this plan before M1
  implementation starts. Path A applied; see Progress Log.

Validation:

```bash
git status --short --branch && git rev-parse HEAD origin/main
gh run list --branch main --limit 1
# plus the audit queries against each target database, pasted into the Progress Log
```

### M1 — Migration 0017 and model changes

Goal: durable kind/provenance before behavior changes.

Implementation:

- `checkpoint_runs.observation_kind`: text NOT NULL, server default `'SCHEDULED'`, CHECK constraint
  limited to `('SCHEDULED','DIAGNOSTIC','INCIDENT_DIAGNOSTIC')`;
- `checkpoint_runs.trigger_source`: text NULL, bounded CHECK-controlled vocabulary (initial value:
  `'OPERATOR_CLI'`);
- `checkpoint_runs.trigger_correlation_id`: uuid, NOT NULL when `observation_kind !=
  'SCHEDULED'`, NULL when `SCHEDULED` (CHECK-enforced both directions); no foreign key by design —
  see Decision Log;
- SQLAlchemy model mirrors constraints exactly; partial index supporting future per-kind queries
  only if a query path needs it (avoid speculative indexes);
- **historical classification rule** (executes the M0 audit result — evidence semantics outrank
  convenience):
  1. If M0 proves no non-scheduled/ad-hoc runs exist in any target database, the column defaults
     apply and no backfill runs; record that proof in this plan.
  2. If ad-hoc runs are deterministically identifiable from trustworthy repository state
     (jobs idempotency-key join or canonical-boundary window check per M0), migration 0017's
     upgrade reclassifies exactly those rows to `DIAGNOSTIC` with `trigger_source='LEGACY_CLI'`
     and a derived correlation UUID recorded alongside the audit evidence; the reclassification
     statement is part of migration 0017 and is covered by its tests.
  3. If identification is not deterministic, do NOT invent a heuristic: keep ambiguous legacy rows
     on the SCHEDULED default but introduce an explicit fail-safe eligibility cutoff — a
     migration-added boolean (or equivalent marker) that renders pre-migration ambiguous rows
     ineligible for Last Known Good selection and records them for operator review; the marker
     semantics must be documented here and honored by future LKG consumers before I1 ships.
- downgrade drops the added columns; downgrade refuses if any non-SCHEDULED row exists
  (fail-closed evidence safety).

Acceptance:

- [x] upgrade/downgrade/upgrade passes from clean database;
- [x] constraint violations rejected at database level (kind; source-implied-null rules;
      non-scheduled without correlation identity rejected; SCHEDULED with either provenance field
      populated rejected);
- [x] two CLI diagnostic invocations persist distinct correlation UUIDs;
- [x] retry of the same run preserves its original correlation identity unchanged;
- [x] historical classification path matches the M0 audit result (Path A: proven absence, no
      backfill; paths B/C not applicable);
- [x] existing integration suite passes unchanged with defaults.

Validation:

```bash
uv --directory backend run pytest tests/integration/test_migrations.py
```

### M2 — Scheduler, worker, and CLI behavior

Goal: correct kind assignment at every write path.

Implementation:

- scheduling service sets `SCHEDULED` explicitly (no silent reliance on default);
- `register_and_enqueue` gains explicit kind/provenance parameters defaulting to
  `DIAGNOSTIC`/`OPERATOR_CLI`; validates the controlled vocabulary; rejects unknown sources
  fail-closed;
- worker requires no behavioral branch: it persists what the row already declares (kinds are set
  at row creation, never mutated afterwards);
- idempotency keys unchanged; retries preserve the original kind/provenance.

Acceptance:

- [x] scheduler pass produces SCHEDULED rows only (explicit column value + integration suite);
- [x] CLI registration produces DIAGNOSTIC rows with provenance;
- [x] invalid kind/source combinations fail closed without enqueueing network work;
- [x] job retry does not mutate kind/provenance (mapper-level immutability guard + regression
      tests).

Validation:

```bash
uv --directory backend run pytest tests/unit/browser
```

### M3 — Cohort purity

Goal: prove exclusions end-to-end.

Implementation:

- lineage predecessor lookup adds `observation_kind == 'SCHEDULED'` filter (both exact-URL and
  template-rotation branches);
- `EventRepository.load_input` and `load_window_inputs` join/filter to SCHEDULED runs only;
- derivation enqueue on completion occurs only for SCHEDULED runs (diagnostic completions skip
  the enqueue step);
- window aggregation naturally excludes diagnostic runs once its input loader filters (verify, do
  not double-filter silently — assert in tests).

Acceptance:

- [ ] diagnostic run completion creates no derivation job and no events;
- [ ] diagnostic run is never selected as comparison predecessor, including the
      same-template rotation fallback;
- [ ] a diagnostic run inside a scheduled window's time range does not alter that window's
      aggregation outcome;
- [ ] scheduled-path events are bit-identical before/after the change for identical fixtures
      (regression);
- [ ] cross-tenant isolation tests still pass.

Validation:

```bash
uv --directory backend run pytest tests/unit/events
uv --directory backend run pytest tests/integration/test_browser_checkpoint.py
RUN_INTEGRATION=1 uv --directory backend run pytest tests/integration/test_event_lifecycle.py
```

### M4 — Full validation and release readiness

Goal: close only after all repository contracts are proven.

Acceptance:

- [ ] all M1–M3 criteria pass;
- [ ] README boundary summary updated (one paragraph: run-kind semantics shipped, diagnostics
      excluded from baselines/events/LKG eligibility);
- [ ] full local ladder green (see Final Validation) and CI green;
- [ ] plan retrospective completed; status COMPLETE only after results recorded.

## 9. Final Acceptance Criteria

- [ ] every checkpoint run row carries a constrained `observation_kind`;
- [ ] non-scheduled runs carry persistent, auditable, **concrete** trigger provenance: source
  vocabulary entry plus a non-null correlation identity; SCHEDULED rows carry none;
- [ ] diagnostic/incident-diagnostic runs are excluded from lineage, derivation, aggregation, and
  documented LKG eligibility;
- [ ] diagnostic runs remain complete immutable evidence;
- [ ] scheduled behavior is regression-free;
- [ ] migration is safe forward, backward-compatible, and fail-closed on downgrade;
- [ ] tenant isolation holds on all touched paths;
- [ ] full validation ladder passes locally and in CI.

## 10. Final Validation

```bash
uv --directory backend run ruff format --check .
uv --directory backend run ruff check .
uv --directory backend run mypy app tests scripts migrations/env.py
uv --directory backend run pytest tests/unit
uv --directory backend run alembic upgrade head
RUN_INTEGRATION=1 uv --directory backend run pytest tests/integration
pnpm --dir frontend lint && pnpm --dir frontend typecheck && pnpm --dir frontend test
python scripts/check_secrets.py
docker compose config
git diff --check
```

## 11. Test Cases

Happy path:

- scheduler materializes SCHEDULED runs; derivation and events behave identically to pre-change
  fixtures;
- CLI diagnostic run persists kind + provenance, completes, stores artifacts, generates nothing
  downstream.

Failure / edge paths:

- SCHEDULED run with `trigger_source` or `trigger_correlation_id` populated is rejected by the
  database constraint;
- non-scheduled run missing `trigger_source` is rejected;
- non-scheduled run missing `trigger_correlation_id` is rejected (category-only provenance is
  impossible);
- two independent CLI diagnostic invocations persist distinct correlation UUIDs;
- retry of the same persisted run preserves its original correlation ID unchanged;
- unknown kind or source rejected before job insert;
- downgrade attempted while a DIAGNOSTIC row exists fails closed;
- historical classification: if the M0 audit finds identifiable ad-hoc runs, they reclassify to
  DIAGNOSTIC with LEGACY_CLI provenance; if identification is indeterminate, ambiguous legacy rows
  carry the fail-safe ineligibility marker and are excluded from LKG eligibility;
- concurrent scheduler tick still yields unique window/run/job identities (unchanged).

Cohort counterexamples:

- diagnostic run between two scheduled runs: pair evaluation still uses the two SCHEDULED runs;
- diagnostic-only "window" (CLI ad-hoc window): `evaluate_window` receives no valid cohort and
  skips;
- same-template rotation never selects a diagnostic predecessor.

Regression:

- E1/E2 event suites, browser suites, migration inventory test, tenant-isolation tests all green.

## 12. Data / Migration Impact

Migration `0017_observation_run_kind`: additive columns + constraints on `checkpoint_runs` only.
Historical rows are classified strictly per the M0-audited rule in M1 (proof of no ad-hoc runs →
default; deterministic identification → targeted DIAGNOSTIC reclassification with
`LEGACY_CLI` provenance; otherwise fail-safe eligibility marker). No heuristic backfills.
Downgrade drops columns but refuses to proceed while any non-SCHEDULED row exists — evidence is
never rewritten or deleted to enable a downgrade. No changes to `checkpoint_windows`, artifacts,
events, or public-config tables.

## 13. Security / Privacy Impact

No new external input, credential, or network surface. Kind/provenance values are short controlled
strings/UUIDs stored tenant-scoped on the existing table; repository access paths keep existing
tenant filters. Provenance correlation IDs reference internal objects only and never contain URLs,
headers, or secrets. No material security/privacy impact beyond preserving existing isolation.

## 14. Observability / Failure Handling

Structured logs gain `observation_kind` and (when present) `trigger_source` on run completion
events. No new error classes needed: invalid kind/source at creation is a state error surfaced
through the existing job failure path (terminal, non-retryable).

## 15. Rollback Strategy

Revert removes the code paths; migration downgrade is guarded (fails while non-scheduled evidence
exists). Because scheduled behavior is unchanged and diagnostics generate no downstream effects,
rollback cannot lose or corrupt evidence. No feature flag required (behavioral surface is one CLI
path plus passive filters).

## 16. Known Risks

- Hidden consumers of `checkpoint_runs` could implicitly assume all runs are scheduled; mitigated
  by exhaustive grep + regression suites during M3.
- Future incident-diagnostic writers must remember provenance requirements; mitigated by the
  NOT-NULL-implied check constraint making unprovenanced non-scheduled rows impossible.

## 17. Open Decisions

None block implementation. Initial trigger-source vocabulary contains only `OPERATOR_CLI`;
`INCIDENT` and `EVENT_VALIDATION` entries are reserved names to be introduced by the EPs that
create those writers (I-series), each recorded in that plan's Decision Log if extended.

## 18. Decision Log

### 2026-08-22 — Provenance by value columns, not foreign key

**Decision:** Store `trigger_source` (controlled string) and `trigger_correlation_id`
(uuid, no FK) rather than a hard FK into `jobs`.

**Reason:** The jobs table is operational infrastructure with independent lifecycle/retention
(ADR-096); evidence rows must never block or depend on queue cleanup. Correlation remains
auditable by value.

**Alternatives:** FK to `jobs.id` — rejected for retention coupling; JSONB blob — rejected: core
semantics stay typed relational columns (ADR-027).

**Impact:** Cross-referencing requires an index-by-value lookup later; acceptable at MVP scale.

### 2026-08-22 — Concrete correlation identity is mandatory for non-scheduled runs

**Decision:** CHECK constraints require `trigger_correlation_id IS NOT NULL` whenever
`observation_kind != 'SCHEDULED'`, and both provenance fields NULL for SCHEDULED. The CLI
generates one fresh invocation UUID per diagnostic request.

**Reason:** ADR-130 auditability requires identifying the concrete invocation that produced the
evidence; a category alone cannot answer "which run/request was this?" during an investigation.

**Alternatives:** Optional correlation — rejected: leaves provenance holes the audit trail cannot
close.

**Impact:** Every future non-scheduled writer must be able to supply a correlation identity;
this is a designed entry requirement, not incidental.

### 2026-08-22 — Historical rows are classified only from evidence

**Decision:** Migration 0017's treatment of pre-existing rows follows the M0 historical-run audit:
proven default-absence → plain default; deterministic identification → targeted DIAGNOSTIC
reclassification with `LEGACY_CLI` provenance; indeterminate → fail-safe ineligibility marker on
ambiguous legacy rows instead of any heuristic backfill.

**Reason:** Silently labeling unknown-origin runs as SCHEDULED would let them act as baseline,
event-cohort, and LKG evidence they were never guaranteed to be. Evidence semantics outrank
convenience.

**Alternatives:** Unconditional SCHEDULED default with no audit — rejected as potentially false
at the record level.

**Impact:** M0 gains a mandatory audit deliverable before M1 code is written; LKG consumers must
honor the fail-safe marker if path 3 activates.

### 2026-08-22 — Kind set excludes VALIDATION for browser runs

**Decision:** `checkpoint_runs` CHECK allows only SCHEDULED/DIAGNOSTIC/INCIDENT_DIAGNOSTIC.

**Reason:** ADR-130 makes applicability subsystem-specific; the browser subsystem has no
validation-run producer today. Public config keeps its own `fetch_kind` storage model.

**Alternatives:** Uniform four-kind column everywhere — rejected: encodes unused states and
invites misuse.

**Impact:** If a browser validation producer ever exists, one migration extends the CHECK; the
taxonomy semantics are already canonical.

### 2026-08-22 — Derivation enqueue skipped, not filtered, for diagnostics

**Decision:** Completion of a non-SCHEDULED run does not enqueue `DERIVE_BROWSER_EVENTS` at all.

**Reason:** Cheaper and clearer than enqueue-then-empty-filter; avoids meaningless job rows.

**Alternatives:** Always enqueue, filter inside loader — rejected: noisy jobs, weaker guarantee.

**Impact:** If a future rule must derive over diagnostics (contrary to ADR-130), it requires a
versioned rule change first.

### 2026-08-22 — Provenance immutability via mapper-level guard

**Decision:** Enforce creation-time provenance with a SQLAlchemy `before_update` mapper listener
on `CheckpointRun` that raises when `observation_kind`, `trigger_source`, or
`trigger_correlation_id` would actually change; assigning an identical value stays harmless.

**Reason:** ADR-130 requires an application-level guarantee without database triggers. All normal
write paths (scheduler insert, CLI insert, repository lifecycle mutators) either insert once or
mutate only operational columns, so the guard never fires in legitimate flows.

**Alternatives:** DB triggers — rejected as unnecessary infrastructure; convention-only —
rejected: the contract demands an enforceable guarantee plus regression proof.

**Impact:** Any future writer needing provenance changes must first change ADR-130.

### 2026-08-22 — CLI diagnostics always use ad-hoc windows

**Decision:** Operator CLI invocations always create their own five-minute ad-hoc window and can
never join an existing scheduled six-hour window cohort, even when URL/scenario overlap scheduled
monitoring. The `(checkpoint_window_id, monitored_url_id, scenario_id)` uniqueness constraint
additionally makes kind-mixing within one window/URL/scenario triple impossible.

**Reason:** Keeps diagnostic evidence queryable while making cohort contamination structurally
impossible rather than filter-dependent.

**Alternatives:** Reusing matching scheduled windows for diagnostics — rejected: blurs window
accounting and cadence semantics.

**Impact:** None on scheduled paths; covered by integration assertions on window duration.

### 2026-08-22 — Derivation lineage fails closed against non-scheduled predecessors

**Decision:** `_build_input` filters recorded comparison-lineage predecessors to
`observation_kind = 'SCHEDULED'`; a lineage row pointing at non-scheduled evidence raises
`EventStateError` instead of comparing cohorts.

**Reason:** Defense in depth beyond the enqueue skip and lineage-selection filter: corrupted or
legacy manifests must not silently compare incompatible observations.

**Alternatives:** Trusting selection-time filtering only — rejected: cheap fail-closed check
closes the last reconstruction path.

**Impact:** Existing E1/E2 behavior unchanged (all recorded lineage already points at scheduled
runs); full event lifecycle regression suite passes.

## 19. Discoveries / Surprises

- The compose PostgreSQL volume was never initialized (port conflict on host 5432), so the local
  "pilot" environment holds no historical checkpoint data at all.
- The `(checkpoint_window_id, monitored_url_id, scenario_id)` unique constraint already forbids
  mixing observation kinds within one window/URL/scenario; cohort purity therefore rests on three
  layers: this constraint, the scheduler/CLI write paths, and the derivation filters.
- SQLAlchemy's unit of work does not order inserts across tables without ORM relationships;
  tests must flush explicitly between parent (window) and child (run) inserts.
- The unit-suite failure observed after scheduler/worker smoke runs was environment leakage
  (`DATABASE_URL` exported into pytest), not a code defect; CI runs without those variables.

## 20. Progress Log

### 2026-08-22

Created from the approved architecture-gap reconciliation (ADR-129/ADR-130). Plan drafted READY:
scope, migration behavior, acceptance criteria, and validation are fully defined; no open product
or architecture decision blocks implementation. No implementation has started.

### 2026-08-22 — Autopilot execution started; M0 complete

Branch `agent/implement-ep-018` created from clean `origin/main` `4485f1f`; post-merge CI run
`32580594988` green. Code-path inspection confirmed exactly two writers of `checkpoint_runs`
(scheduler `_run_id`, service `register_and_enqueue`) plus repository lifecycle mutators in
`browser/persistence.py`; derivation inputs flow from `events/persistence.py`
(`load_input`, `load_window_inputs`, `_build_input`); lineage selection lives in
`previous_comparable_selection`.

**Historical run audit (M0 deliverable):** every environment able to hold `checkpoint_runs` data
was inspected:

- compose volume `publisher-intelligence_postgres_data`: contains an uninitialized PostgreSQL
  cluster only (no `publisher` role, no database) — the compose postgres never completed startup;
- two dangling anonymous Docker volumes: not PostgreSQL data directories;
- disposable integration containers used by earlier milestones: destroyed with their volumes;
  contents were CI-style fixtures, never operator evidence;
- host PostgreSQL on 5432: unrelated personal projects (databases `bookit`, `postgres`);
- no staging or production instances exist.

**Conclusion: classification Path A (proven absence).** No historical `checkpoint_runs` rows exist
anywhere; column defaults apply and no backfill statement is included in migration 0017. Proof:
queries and volume listings recorded here and re-checkable via the audit commands above.

### 2026-08-22 — Pre-merge planning correction

Review of PR #19 tightened two contracts. First, trigger provenance must be concrete:
`trigger_correlation_id` is NOT NULL whenever a run is non-scheduled (CHECK-enforced both
directions), and CLI diagnostics generate one fresh invocation UUID per request. Second,
historical rows may no longer be assumed SCHEDULED: M0 now requires an audited historical-run
inspection, and M1 implements one of three evidence-derived classification paths (proven absence /
deterministic LEGACY_CLI reclassification / fail-safe ineligibility marker), with the
unconditional "historically accurate" claim removed. ADR-130 and DATA_MODEL.md were updated to
state the identical contract.

## 20.1 Validation Results

### M0–M3 local validation — 2026-08-22

- `ruff format --check .`: PASS, 196 files.
- `ruff check .`: PASS.
- `mypy app tests scripts migrations/env.py`: PASS, 179 source files.
- `pytest tests/unit`: PASS, 258 tests (+4 new vocabulary/validation tests).
- Clean-database `alembic upgrade head` through `0017_observation_run_kind`: PASS; single head.
- Migration downgrade `-1` then re-upgrade: PASS on a database containing SCHEDULED rows only;
  downgrade guard verified by inspection (raises while non-SCHEDULED rows exist) and covered by
  the constraint test's non-scheduled rows blocking any accidental downgrade path.
- New integration file `tests/integration/test_observation_run_semantics.py`: PASS, 4 tests —
  DB-level provenance constraints (6 violation shapes), CLI distinct concrete identities +
  ad-hoc windows, cohort exclusion (lineage selection, derivation enqueue skip, retry provenance
  preservation, fail-closed lineage reconstruction), ORM immutability (negative + identical-value
  cases).
- Full PostgreSQL integration suite: PASS, 41/41 (37 pre-existing + 4 new), including real
  Chromium checkpoint runs and E1/E2 event lifecycle regression.
- Scheduler `--once` and worker `--once` smoke: PASS.
- Frontend lint/typecheck/test/build: PASS.
- Secret scan, `docker compose config`, `git diff --check`: PASS.

### Correction validation — 2026-08-22

- New downgrade-guard regression test: PASS (refuses `-1` while a DIAGNOSTIC row exists; shared
  database restored to head afterwards).
- Full PostgreSQL integration suite after correction: PASS, 42/42.
- Unit suite without inherited environment variables: PASS, 258.

## 21. Final Outcome / Retrospective

Pending implementation. Complete after M4 with validation results and commit/PR references.
