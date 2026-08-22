# EP-018 — Observation Run Semantics & Trigger Provenance

**Status:** READY
**Owner:** Codex / Engineering
**Created:** 2026-08-22
**Updated:** 2026-08-22
**Target milestone:** ADR-130 browser run taxonomy
**MVP scope impact:** NO
**New infrastructure category:** NO

## Progress

- [ ] M0 — Baseline verification and contract inspection
- [ ] M1 — Migration 0017: run kind and trigger provenance on checkpoint runs
- [ ] M2 — Scheduler, worker, and CLI behavior for observation kinds
- [ ] M3 — Cohort purity: lineage, event derivation, and window aggregation exclusion
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
- CLI diagnostic registration creates `DIAGNOSTIC` runs with persistent provenance;
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
   `SCHEDULED` always. The CLI diagnostic path writes `DIAGNOSTIC` plus provenance. Nothing today
   writes `INCIDENT_DIAGNOSTIC`; it exists in the vocabulary so I1 needs no migration.
2. Non-scheduled runs record persistent provenance at creation: a controlled `trigger_source`
   (e.g., `OPERATOR_CLI`) and a nullable correlation identifier for the requesting object.
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
  trigger_source='OPERATOR_CLI'
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

### M0 — Baseline verification

Goal: bind EP-018 to merged EP-017 main and current behavior.

Acceptance:

- [ ] branch starts from clean `origin/main`; post-merge CI green;
- [ ] lineage/derivation/window code paths inspected and recorded in this plan;
- [ ] confirm no other writer creates checkpoint runs besides scheduler and CLI service.

Validation:

```bash
git status --short --branch && git rev-parse HEAD origin/main
gh run list --branch main --limit 1
```

### M1 — Migration 0017 and model changes

Goal: durable kind/provenance before behavior changes.

Implementation:

- `checkpoint_runs.observation_kind`: text NOT NULL, server default `'SCHEDULED'`, CHECK constraint
  limited to `('SCHEDULED','DIAGNOSTIC','INCIDENT_DIAGNOSTIC')`;
- `checkpoint_runs.trigger_source`: text NULL, bounded CHECK-controlled vocabulary (initial value:
  `'OPERATOR_CLI'`); CHECK: `observation_kind='SCHEDULED'` implies NULL, non-scheduled implies
  NOT NULL;
- `checkpoint_runs.trigger_correlation_id`: uuid NULL (no foreign key by design — see Decision
  Log); CHECK: required only when a source provides one, never for SCHEDULED;
- SQLAlchemy model mirrors constraints exactly; partial index supporting future per-kind queries
  only if a query path needs it (avoid speculative indexes);
- backfill: none required — default classifies all existing rows as SCHEDULED (historically true:
  all production rows originate from the scheduler; the single legacy CLI pilot run predates any
  incident use and its reclassification is unnecessary);
- downgrade drops the added columns; downgrade refuses if any non-SCHEDULED row exists
  (fail-closed evidence safety).

Acceptance:

- [ ] upgrade/downgrade/upgrade passes from clean database;
- [ ] constraint violations rejected at database level (kind, source-implied-null rules);
- [ ] existing integration suite passes unchanged with defaults.

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

- [ ] scheduler pass produces SCHEDULED rows only;
- [ ] CLI registration produces DIAGNOSTIC rows with provenance;
- [ ] invalid kind/source combinations fail closed without enqueueing network work;
- [ ] job retry does not mutate kind/provenance.

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
- [ ] non-scheduled runs carry persistent, auditable trigger provenance;
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

- unknown kind or source rejected before job insert;
- non-scheduled run missing trigger source rejected by database constraint;
- downgrade attempted while a DIAGNOSTIC row exists fails closed;
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
No data backfill (default SCHEDULED is historically accurate). Downgrade drops columns but refuses
to proceed while any non-SCHEDULED row exists — evidence is never rewritten or deleted to enable a
downgrade. No changes to `checkpoint_windows`, artifacts, events, or public-config tables.

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

**Decision:** Store `trigger_source` (controlled string) and nullable
`trigger_correlation_id` (uuid, no FK) rather than a hard FK into `jobs`.

**Reason:** The jobs table is operational infrastructure with independent lifecycle/retention
(ADR-096); evidence rows must never block or depend on queue cleanup. Correlation remains
auditable by value.

**Alternatives:** FK to `jobs.id` — rejected for retention coupling; JSONB blob — rejected: core
semantics stay typed relational columns (ADR-027).

**Impact:** Cross-referencing requires an index-by-value lookup later; acceptable at MVP scale.

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

## 19. Discoveries / Surprises

To be recorded during implementation.

## 20. Progress Log

### 2026-08-22

Created from the approved architecture-gap reconciliation (ADR-129/ADR-130). Plan drafted READY:
scope, migration behavior, acceptance criteria, and validation are fully defined; no open product
or architecture decision blocks implementation. No implementation has started.

## 21. Final Outcome / Retrospective

Pending implementation. Complete after M4 with validation results and commit/PR references.
