# EP-015 — Semantic Browser Events E1

**Status:** IN_PROGRESS
**Owner:** Codex / Engineering
**Created:** 2026-08-20
**Updated:** 2026-08-20
**Target milestone:** E1 — Semantic browser diffs
**MVP scope impact:** NO
**New infrastructure category:** NO

## Progress

- [x] M0 — Confirm merged C6, E1 boundary, and current browser evidence
- [x] M1 — Add compact rendered SEO evidence and canonical event persistence
- [x] M2 — Add the versioned E1 registry and deterministic candidate evaluation
- [x] M3 — Persist only confirmed point events with exact evidence references
- [x] M4 — Add atomic background execution and tenant-safe reprocessing
- [ ] M5 — Prove counterexamples, migrations, regressions, and final validation

## 1. Purpose and User Outcome

After this plan is complete, every newly completed comparable browser checkpoint can be evaluated
against its explicit predecessor by a deterministic Event Engine. The platform can record a small
set of confirmed dependency and canonical state transitions as auditable operational events, while
producing but not persisting candidates that still require E2 confirmation or aggregation.

Every persisted event preserves the before/after checkpoint evidence and the bounded occurrence
window. A raw diff, one noisy error, one missing slot, or an observer-version change does not
automatically become an event, alert, incident, or cause.

## 2. Scope

### In

- compact rendered page-level SEO evidence for title hash, meta robots, canonical URL, final URL,
  HTTP status, redirect count, and explicit collector/version provenance;
- the canonical `event_definitions`, `events`, and `event_evidence_refs` persistence boundary;
- a version-controlled E1 rule registry for:
  - `THIRD_PARTY_DEPENDENCY_ADDED`;
  - `THIRD_PARTY_DEPENDENCY_REMOVED`;
  - `JS_ERROR_STARTED`;
  - `NOINDEX_ADDED`;
  - `CANONICAL_CHANGED`;
  - `GPT_EXPECTED_SLOT_MISSING`;
- exact previous-run lineage, comparable collector/normalizer/scenario checks, truncation gates,
  deterministic candidates, narrow evidence-supported scope, and bounded summaries/details;
- persistence only for E1 candidates whose rule declares `SINGLE_STRONG_OBSERVATION` and whose
  comparison uses the exact monitored URL; candidates requiring another checkpoint, an immediate
  validation, or multi-URL corroboration remain non-durable until E2;
- deterministic IDs/idempotent reprocessing, immutable evidence references, and occurrence
  windows from the previous observation time to the current observation time;
- one tenant-owned `DERIVE_BROWSER_EVENTS` job inserted atomically with successful checkpoint
  finalization and executed by the existing general worker;
- unit and PostgreSQL integration coverage for positive, negative, noisy, provenance, and
  cross-tenant cases.

### Out / Non-Goals

- E2 active-condition deduplication, repeated-evidence attachment, resolution, multi-URL/template
  aggregation, severity overrides, or immediate second-check orchestration;
- E3 robots.txt/ads.txt collection and public-configuration events;
- E4 metric baselines/anomalies, E5 deeper GPT/CMP/Prebid/video/policy events, or E6 routing;
- Timeline/Home APIs or UI, immediate notifications, Weekly Brief, external/manual events, event
  relations, Last Known Good, Incident Engine behavior, LLM classification, or causal claims;
- a database-editable rule builder, Kafka/streaming infrastructure, graph database, new scheduler
  service, or a new dependency.

## 3. Canonical References

- `AGENTS.md` sections 7, 10, 15–18, and 28;
- `PLANS.md` sections 1, 8–11, 20–31, 55, 62–66, and 71–76;
- `MVP.md` sections 43–47, 100, 104–106, and the initial event subset in section 105;
- `EVENTS.md` invariants 001–010; sections 3–18, 24–31, 47–50, 57–61, 66, 89–90,
  examples 110–113, and milestone E1;
- `DOMAIN.md` sections 9–12, 20–22, 38–39, 78–82, and failure modes F-SEO-002/003,
  F-GPT-001, F-BR-001/002;
- `BROWSER.md` invariants 002, 005–007 and sections 41, 57–61, 67–69, 75–78;
- `DATA_MODEL.md` sections 41, 56–58, 94–98, 101–106, 108, 117, 120, 125–126,
  and required tests DM-015/016/021/022/023;
- `ARCHITECTURE.md` sections 40–43;
- `SECURITY.md` sections 10–18, 97–99, 105–107, 129, 133, 187–188;
- accepted ADR-023 through ADR-027 and ADR-029 in `DECISIONS.md`;
- completed `plans/EP-014-incident-drill-down-c6.md`.

## 4. Current State

PR #15 is merged into `main` at `5386998`. Browser B1–B8 persists immutable checkpoints,
collector runs, normalized DOM/script/network/error state, domain entities, JavaScript-error
observations, expected GPT slot observations, exact-scenario comparison lineage, and a bounded raw
comparison in each manifest. C1–C6 provides connector and drill-down evidence but is outside E1.

`backend/app/browser/comparison.py` currently emits structural, presence, and dependency-status
diffs only into the checkpoint manifest. It rejects incompatible normalizer versions but no Event
Engine consumes that output. Page-level rendered SEO directives are not yet modeled in
`seo_observations`; `event_definitions`, `events`, and `event_evidence_refs` do not exist. The
general worker already supports tenant-owned idempotent jobs and can host one additional derived
handler. Migration head is `0012`.

## 5. Target Behavior

1. Checkpoint finalization persists compact rendered SEO evidence and atomically inserts one
   idempotent `DERIVE_BROWSER_EVENTS` job containing only `checkpoint_run_id`.
2. The general worker loads the current run and its recorded predecessor inside the same tenant,
   then revalidates site, exact scenario, exact monitored URL, final status, collector status,
   normalizer version, observation time ordering, and non-truncated absence evidence.
3. The fixed E1 registry maps normalized before/after states to deterministic candidates. The
   caller/job cannot supply an event code, severity, comparator, rule JSON, or evidence reference.
4. `THIRD_PARTY_DEPENDENCY_ADDED/REMOVED` and `CANONICAL_CHANGED` may persist when their fixed rule
   and single-observation gates pass. Each uses a deterministic event ID and links both the previous
   and current evidence.
5. `JS_ERROR_STARTED`, `NOINDEX_ADDED`, and `GPT_EXPECTED_SLOT_MISSING` are evaluated and tested,
   but remain unpersisted when their declared E2 confirmation mode is not satisfied. They do not
   create placeholder rows, alerts, or misleading Timeline facts.
6. Reprocessing the same checkpoint/rule version creates no duplicate event or evidence link.

## 6. Architecture / Data Flow

```text
browser checkpoint transaction
  → normalized state + SEO observation + DERIVE_BROWSER_EVENTS job
  → exact predecessor and collector/version gates
  → fixed E1 registry + semantic candidates
  → confirmation gate
  → event + before/after evidence refs (confirmed point changes only)
```

The browser collector remains a source of normalized observations. Event semantics live only in
`app/events/`. The PostgreSQL jobs table is the transactionally inserted handoff; no new queue or
streaming system is introduced.

## 7. Files and Modules Affected

### Existing

- `backend/app/browser/contracts.py`
- `backend/app/browser/runner.py`
- `backend/app/browser/models.py`
- `backend/app/browser/persistence.py`
- `backend/app/db/base.py`
- `backend/app/worker.py`
- `backend/tests/integration/test_browser_checkpoint.py`
- `backend/tests/integration/test_migrations.py`
- `backend/tests/unit/test_processes.py`
- `README.md`

### To create

- `backend/app/browser/seo.py`
- `backend/app/events/__init__.py`
- `backend/app/events/contracts.py`
- `backend/app/events/registry.py`
- `backend/app/events/evaluator.py`
- `backend/app/events/models.py`
- `backend/app/events/persistence.py`
- `backend/app/events/service.py`
- `backend/migrations/versions/0013_semantic_browser_events_e1.py`
- `backend/tests/unit/browser/test_seo.py`
- `backend/tests/unit/events/__init__.py`
- `backend/tests/unit/events/test_registry.py`
- `backend/tests/unit/events/test_evaluator.py`
- `backend/tests/unit/events/test_worker.py`
- `backend/tests/integration/test_semantic_browser_events.py`

Paths may be adjusted only to preserve current module boundaries; any material change must be
recorded in this plan.

## 8. Milestones and Acceptance

### M0 — Contract and repository inspection

Goal: fix the E1 boundary against merged C6 and the actual B1–B8 evidence model.

Acceptance:
- [x] branch starts at remote `main` merge commit `5386998`;
- [x] current comparison lineage, observation tables, worker, migration head, and E1 contracts are
  inspected;
- [x] E1 excludes metric anomalies, routing, lifecycle/resolution, alerts, Incident/LLM behavior,
  and public config.

Validation:
```bash
git status --short --branch
git rev-parse HEAD
```

Expected observable result: `agent/implement-ep-015` is clean and based on `origin/main`.

### M1 — Rendered SEO evidence and persistence schema

Goal: supply the compact missing page-level SEO state and canonical E1 relational boundary.

Implementation:
- collect/normalize bounded title hash, meta robots directive set, canonical URL, final URL/status,
  redirect count, and collector version without storing another document body;
- add tenant-owned `seo_observations`, `events`, and `event_evidence_refs`, plus the global
  `event_definitions` mirror;
- enforce status/severity/time-precision values, valid occurrence bounds, source-reference
  uniqueness, tenant/site foreign keys, and Timeline-oriented indexes;
- seed only the six version-controlled E1 definitions and register all models centrally.

Acceptance:
- [x] rendered SEO state is explicit, bounded, versioned, and linked to one checkpoint;
- [x] events distinguish started/detected/created time and observation confidence from risk;
- [ ] migration upgrade/downgrade preserves existing checkpoint and connector evidence;
- [x] no event rule is editable from tenant data or API input.

Validation:
```bash
uv --directory backend run pytest tests/unit/browser/test_seo.py
uv --directory backend run pytest tests/integration/test_migrations.py
```

Expected observable result: migration `0013` creates the E1 tables/constraints and browser fixtures
persist compact SEO observations.

### M2 — Registry and deterministic candidate evaluation

Goal: translate only comparable normalized transitions into fixed, auditable candidates.

Implementation:
- define immutable E1 registry entries with family, kind, sources, diff operator, confirmation,
  default severity, evidence kinds, scope policy, domain refs, and rule/schema version;
- evaluate dependency entity presence, JS error fingerprints, SEO directives/canonical, and
  expected GPT slot presence from persisted observations;
- require exact tenant/site/scenario/URL lineage, compatible collectors/normalizers, valid statuses,
  ordered observation times, and complete/non-truncated absence evidence;
- return explicit skip reasons for no predecessor, incompatible observer, invalid source state,
  truncated evidence, unchanged state, unsupported confirmation, and ownership mismatch.

Acceptance:
- [x] arbitrary event codes/rules/metadata cannot enter evaluation;
- [x] observer changes, browser errors, site errors used as structural baselines, and truncated
  removals produce no candidate;
- [x] one noisy JS error, one noindex, and one missing expected GPT slot do not bypass their fixed
  confirmation strategies;
- [x] candidate scope never broadens one URL into site-wide evidence.

Validation:
```bash
uv --directory backend run pytest tests/unit/events/test_registry.py
uv --directory backend run pytest tests/unit/events/test_evaluator.py
```

Expected observable result: sanitized fixtures yield stable candidates and explicit conservative
skips without any provider, browser, or LLM call.

### M3 — Confirmed point-event persistence and provenance

Goal: persist only E1 single-strong point transitions with immutable source links.

Implementation:
- derive deterministic event and evidence-reference IDs from tenant, rule version, current and
  previous checkpoint, event code, subject, and normalized scope;
- persist confirmed dependency add/remove and canonical changes idempotently;
- store `occurred_after_at` from the previous evidence and `occurred_before_at` from the current
  evidence with `time_precision=WINDOW`;
- link both before and after checkpoint/observation evidence after application-level ownership
  validation;
- use factual deterministic summaries and minimal before/after details only.

Acceptance:
- [x] every persisted event has at least one previous and one current evidence reference;
- [x] identical reprocessing creates neither duplicate events nor duplicate refs;
- [x] reverse transitions remain separate facts and never rewrite the earlier event;
- [x] event severity/observation confidence are not stored as causal confidence or alert state.

Validation:
```bash
uv --directory backend run pytest tests/unit/events/test_evaluator.py
RUN_INTEGRATION=1 uv --directory backend run pytest tests/integration/test_semantic_browser_events.py
```

Expected observable result: one exact comparable dependency/canonical transition produces one
auditable point event; reprocessing reports idempotent reuse.

### M4 — Atomic job handoff and worker execution

Goal: evaluate every finalized checkpoint without coupling event rules to browser collection.

Implementation:
- insert one low-priority `DERIVE_BROWSER_EVENTS` job inside the successful checkpoint-finalization
  transaction, using a rule-versioned idempotency key;
- validate that the worker payload contains exactly `checkpoint_run_id` and matches job tenant;
- execute the Event service in the general worker with bounded retry/sanitized error handling;
- ensure event-processing failure cannot turn a successful publisher checkpoint into a publisher
  `SITE_ERROR` or mutate its raw evidence.

Acceptance:
- [x] checkpoint evidence and event-job handoff commit atomically;
- [x] malformed/cross-tenant jobs fail without reading or writing another tenant;
- [x] retries are idempotent and do not rerun Chromium;
- [x] unsupported candidates complete successfully with skip counts rather than fabricated events.

Validation:
```bash
uv --directory backend run pytest tests/unit/events/test_worker.py
RUN_INTEGRATION=1 uv --directory backend run pytest tests/integration/test_semantic_browser_events.py
```

Expected observable result: the existing general worker derives E1 events from persisted evidence
without browser execution or external calls.

### M5 — Release gate

Goal: prove E1 correctness, counterexamples, migrations, regressions, and documentation.

Acceptance:
- [ ] positive, negative, noisy, version-change, truncation, idempotency, time-window, and
  cross-tenant tests pass;
- [ ] migration round-trip and all browser/connector/metric regressions pass;
- [ ] Ruff, mypy, backend/frontend, security, worker, scheduler, and repository safety gates pass;
- [ ] plan and README match the validated implementation.

Validation:
```bash
uv --directory backend sync --all-groups --locked
uv --directory backend run ruff format --check .
uv --directory backend run ruff check .
uv --directory backend run mypy app tests scripts migrations/env.py
uv --directory backend run pytest tests/unit
RUN_INTEGRATION=1 uv --directory backend run pytest tests/integration
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend test -- --run
pnpm --dir frontend build
make secret-scan
docker compose config
git diff --check
```

Expected observable result: CI proves E1 without regressions and the plan can be marked COMPLETE.

## 9. Final Acceptance Criteria

- [ ] raw checkpoint state remains distinct from semantic candidate and persisted event;
- [ ] every rule and comparator is fixed/versioned in code and mirrored in the registry;
- [ ] only exact comparable evidence produces a persisted E1 event;
- [ ] occurrence windows preserve six-hour uncertainty rather than using detection time as fact;
- [ ] missing/truncated/incompatible/error evidence cannot fabricate a removal or missing condition;
- [ ] unconfirmed JS/noindex/GPT candidates do not enter operational history prematurely;
- [ ] persisted events carry narrow scope, factual language, and traceable before/after evidence;
- [ ] event derivation is tenant-owned, idempotent, retry-safe, and independent of LLM/provider
  authority;
- [ ] no event is called an incident, cause, alert, or metric anomaly.

## 10. Validation Commands

```bash
uv --directory backend sync --all-groups --locked
uv --directory backend run ruff format --check .
uv --directory backend run ruff check .
uv --directory backend run mypy app tests scripts migrations/env.py
uv --directory backend run pytest tests/unit
RUN_INTEGRATION=1 uv --directory backend run pytest tests/integration
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend test -- --run
pnpm --dir frontend build
make secret-scan
docker compose config
git diff --check
```

## 11. Test Cases

Happy path:
- same URL/scenario/version dependency addition/removal and canonical change;
- two-sided evidence links, exact subject/scope, bounded time window, deterministic summary;
- atomic event-job creation, worker execution, and idempotent replay.

Counterexamples:
- no predecessor; template-rotation fallback; scenario mismatch; incompatible normalizer/collector;
- browser/site error used as structural baseline; failed relevant collector; unordered timestamps;
- truncated dependency sets used to infer absence; unchanged state; first-ever observation;
- one JS error, one noindex, or one missing expected GPT slot without required confirmation;
- arbitrary event code/payload metadata; missing/wrong evidence kind; tenant/site mismatch;
- reprocessing, job retry, and reverse transition after a prior point event.

Regression:
- B1–B8 immutable artifacts/observations/comparison lineage;
- C1–C6 connector and metric jobs;
- migration upgrade/downgrade, scheduler, general worker, browser worker, frontend, and security.

## 12. Data / Migration Impact

Migration `0013` adds `seo_observations`, `event_definitions`, `events`, and
`event_evidence_refs`, their tenant/site ownership, exact temporal/status constraints, provenance
uniqueness, and Timeline lookup indexes. It seeds only the six E1 definition mirrors. Existing
checkpoint/connector/metric rows remain unchanged.

The downgrade removes only E1 derived events/refs/definitions and SEO observations after explicit
operator review; it never deletes checkpoint artifacts, normalized browser evidence, source
extracts, or metric history. No backfill is required for E1 release. Historical checkpoints may be
reprocessed later under an explicit versioned backfill plan.

## 13. Security / Privacy Impact

This adds tenant-confidential normalized SEO state and derived event history already authorized by
MVP/browser contracts. It introduces no credential, provider scope, raw user data, new external
request, LLM context, or retention category. Events/SEO use `CORE_LONG`; raw DOM retention remains
unchanged.

Every lookup and insert independently verifies tenant/site ownership. The job carries only tenant
ID and checkpoint UUID. Canonical values and summaries are bounded; logs include IDs, rule version,
counts, skip/error class, and duration, never raw DOM, query strings, cookies, headers, or secrets.
Cross-tenant regression tests are mandatory.

## 14. Observability / Failure Handling

Record job/checkpoint/tenant/site IDs, event rule bundle version, candidate/persisted/skip counts,
skip reason counts, duration, retry attempt, and sanitized failure class. Expected non-events are
successful skips, not errors.

Malformed payload, ownership mismatch, incompatible evidence, and unsupported confirmation fail
closed. Database/runtime failures may retry through existing job fencing/backoff. A failed event
job never changes checkpoint status and never masquerades as publisher/site failure.

## 15. Rollback Strategy

Stop/disable `DERIVE_BROWSER_EVENTS` handling, revert E1 code, and downgrade migration `0013` only
after confirming no downstream reference depends on E1 derived rows. Raw browser and connector
evidence remains intact and can be reprocessed with the previous/new rule version. No collector or
provider rollback is required beyond removing the compact SEO observation path if necessary.

## 16. Known Risks

- Existing normalized comparison lists are bounded; truncation must fail closed for absence.
- Same-template URL rotation is useful lineage but can confuse content-specific state, so E1 does
  not persist its candidates without later corroboration.
- Script and network observations can describe related dependencies; the rule/subject identity must
  avoid duplicate user-facing facts without collapsing distinct evidence.
- Canonical normalization must preserve meaningful targets without retaining unsafe/unbounded URL
  material.
- Atomic job insertion touches browser finalization; migration/integration tests must prove raw
  checkpoint persistence remains independent and idempotent.
- E1 deliberately leaves high-value conditions unpersisted until E2 confirmation. This is a
  product-safety constraint, not incomplete handling.

## 17. Open Decisions

None blocking. E1 uses the canonical EVENTS confirmation modes and defers confirmation strategies
that require state across additional runs/URLs to E2. It does not weaken those rules to produce a
larger event count.

## 18. Decision Log

- 2026-08-20: Follow current MVP Phase D and EVENTS milestone E1 rather than the explicitly
  non-locked historical sequence in `PLANS.md` section 76.
- 2026-08-20: Keep event rules in version-controlled Python and use PostgreSQL only as a reporting
  mirror and derived operational history.
- 2026-08-20: Persist only exact-URL `SINGLE_STRONG_OBSERVATION` point transitions in E1; retain
  noisy/high-risk/multi-URL signals as non-durable candidates until E2 can satisfy their canonical
  confirmation contracts.
- 2026-08-20: Insert the event-derivation job in the same PostgreSQL transaction as checkpoint
  finalization rather than adding an external queue or risking a handoff gap.

## 19. Discoveries / Surprises

- B3 already creates exact predecessor lineage and normalized script/network/error comparisons,
  so E1 can consume existing evidence rather than introduce another generic diff engine.
- The canonical data model requires compact `seo_observations`, but B1–B8 currently retain SEO
  directives only indirectly in normalized DOM/raw evidence; E1 must close that gap before safe SEO
  events.
- The canonical E1 list includes condition candidates whose confirmation belongs to E2. Persisting
  them from one checkpoint would violate quiet-by-default and event-specific confirmation rules.

## 20. Progress Log

- 2026-08-20: Implementation approved; marked EP-015 IN_PROGRESS and began M1 without staging,
  committing, pushing, or opening a PR.
- 2026-08-20: Implemented M1–M4: compact rendered SEO evidence, migration `0013`, the fixed
  six-rule registry, conservative candidate evaluation, deterministic confirmed-event/evidence
  persistence, atomic job handoff, and general-worker execution.
- 2026-08-20: Ruff and mypy pass; all 186 backend unit tests plus 9 targeted E1 tests pass.
  PostgreSQL integration execution is pending because no local PostgreSQL server is available;
  offline Alembic SQL generation through `0013` passes.
- 2026-08-20: Confirmed PR #15 merged at `5386998`, fetched remote `main`, created
  `agent/implement-ep-015` from `origin/main`, and inspected Phase D/E1 contracts, browser evidence,
  comparison lineage, persistence, migrations, job workers, security, and event data-model gaps.
- 2026-08-20: Reviewed the draft against the planning contract, fixed the E1/E2 confirmation
  boundary, validated scope/commands/rollback/security, and marked EP-015 READY.

## 21. Final Outcome / Retrospective

Pending implementation and validation.

## 22. Validation Results

- Planning baseline: local branch is clean at remote `main` merge commit `5386998`;
- EP-014 final CI run 93 passed before this branch was created;
- Ruff check and mypy pass for the implemented backend and tests;
- backend unit suite: 186 passed; targeted E1 suite: 9 passed;
- Alembic offline upgrade SQL generation reaches `0013` and emits all four tables plus six seeds;
- PostgreSQL integration tests are blocked locally by connection refusal on localhost:5432;
- Docker validation is unavailable because the Docker CLI is not installed.

## 23. Next Step

Complete M5 regression and repository safety gates, then run PostgreSQL integration/round-trip in
CI or an environment with the project services available before marking this plan COMPLETE.
