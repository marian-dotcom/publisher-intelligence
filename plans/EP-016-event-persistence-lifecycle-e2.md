# EP-016 — Event Persistence and Lifecycle E2

**Status:** COMPLETE
**Owner:** Codex / Engineering
**Created:** 2026-08-21
**Updated:** 2026-08-21
**Target milestone:** E2 — Persistence + dedupe + lifecycle
**MVP scope impact:** NO
**New infrastructure category:** NO

## Progress

- [x] M0 — Confirm merged E1 baseline and fix the E2 semantic boundary
- [x] M1 — Complete the versioned rule and lifecycle persistence contracts
- [x] M2 — Confirm and aggregate the deferred browser candidates
- [x] M3 — Deduplicate, update, and resolve active conditions atomically
- [x] M4 — Integrate retry-safe E2 derivation with the existing worker
- [x] M5 — Prove lifecycle counterexamples, migrations, regressions, and release readiness

## 1. Purpose and User Outcome

After this plan is complete, repeated browser checkpoints can promote the three E1-deferred
signals using deterministic, event-specific confirmation rules. Confirmed JavaScript and expected
GPT-slot conditions create one active event, attach later supporting evidence to that event, and
resolve only after a comparable recovery observation. Confirmed noindex changes remain point facts
rather than being given a false condition lifecycle.

Multi-URL observations can produce one template-scoped event with references to every supporting
URL instead of one noisy row per page. Every event retains evidence-supported scope, severity,
rule version, and occurrence uncertainty. No checkpoint difference becomes an alert, incident, or
causal claim merely because it was persisted.

## 2. Scope

### In

- replace the E1 placeholder confirmation value with the canonical, versioned confirmation modes
  needed by the existing browser rules;
- enrich the fixed code registry with event kind, subject/scope policy, confirmation policy,
  rule-specific aggregation threshold, severity policy, resolution policy, dedupe strategy,
  domain references, and rule/schema version;
- confirm `JS_ERROR_STARTED` only after the same normalized fingerprint is present in two
  consecutive comparable checkpoints;
- confirm `GPT_EXPECTED_SLOT_MISSING` from at least two valid representative URLs in the same
  completed checkpoint window, template, scenario, and expected-slot identity;
- persist a single-page `NOINDEX_ADDED` as a narrow point event only from complete, comparable
  rendered SEO evidence; aggregate a template-scoped noindex event only when at least two valid
  representative URLs corroborate it in a completed checkpoint window;
- preserve `THIRD_PARTY_DEPENDENCY_ADDED/REMOVED`, `CANONICAL_CHANGED`, and narrow noindex changes
  as `RECORDED` point events that never resolve;
- add deterministic active-condition identity, a concurrency-safe partial uniqueness constraint,
  repeated evidence attachment, scope/severity updates, and recovery transitions for condition
  events;
- preserve start occurrence windows separately from confirmation time and retain recovery windows
  in structured lifecycle details plus recovery evidence;
- use the existing `DERIVE_BROWSER_EVENTS` job, checkpoint windows, normalized observations, and
  PostgreSQL transaction boundary; no candidate table or new worker/queue is introduced;
- unit and PostgreSQL integration coverage for confirmation, aggregation, dedupe, resolution,
  time bounds, evidence ownership, idempotency, and concurrency.

### Out / Non-Goals

- a new browser validation-run model or out-of-band `IMMEDIATE_SECOND_CHECK` orchestration; a
  single observation that would require broad/high-risk scope remains narrow or unconfirmed;
- new event families/codes such as `NOINDEX_REMOVED`, public robots/ads.txt checks from E3, metric
  anomalies from E4, deeper ad-stack rules from E5, or routing from E6;
- Timeline/Home APIs or UI, attention state, alert eligibility, email/Slack delivery, Weekly Brief,
  incident creation, event relations, causal scoring, or LLM authority;
- database-editable rules, user-supplied thresholds, backfilling all historical checkpoints,
  Kafka/streaming infrastructure, a workflow engine, or a new dependency;
- mutating original trigger facts when an active condition receives new evidence or resolves.

## 3. Canonical References

- `AGENTS.md` sections 7, 10, 15–18, and 28;
- `PLANS.md` sections 1, 4–11, 20–31, 55, 62–66, and 71–76;
- `MVP.md` sections 43–47 and 104–106;
- `EVENTS.md` invariants 001–010; sections 3–21, 24–33, 60–61, 66, 89–92,
  examples 110–113, test matrix EV-001–EV-020, and milestone E2;
- `DOMAIN.md` failure modes F-SEO-002/003, F-GPT-001, and F-BR-001/002;
- `BROWSER.md` checkpoint lineage, observer-version, completeness, and representative-template
  contracts used by E1;
- `DATA_MODEL.md` sections 56–58, 94–98, 108–109, event indexes, and required event/evidence tests;
- `ARCHITECTURE.md` sections 40–43;
- `SECURITY.md` tenant isolation, background-job, logging, and `CORE_LONG` event-retention rules;
- accepted ADR-023 through ADR-027, ADR-029, and ADR-040 through ADR-043 in `DECISIONS.md`;
- completed `plans/EP-015-semantic-browser-events-e1.md`.

## 4. Current State

EP-015 is merged into `main` at `fc2788d` and CI run #100 passed. E1 provides a fixed six-rule
registry, deterministic candidate evaluation, exact predecessor lineage, occurrence windows,
`event_definitions`, `events`, `event_evidence_refs`, and atomic `DERIVE_BROWSER_EVENTS` jobs.

Only `SINGLE_STRONG_OBSERVATION` dependency/canonical candidates currently persist. The registry
uses `REQUIRES_E2_CONFIRMATION` for JavaScript errors, rendered noindex, and missing expected GPT
slots, so those candidates are counted but discarded. Persisted point events use the noncanonical
status `OBSERVED`. There is no active-condition identity, uniqueness guard, evidence-update path,
resolution path, multi-URL query, or rule-specific severity calculation. Migration head is `0013`.

The immutable evidence needed by E2 already exists in checkpoint runs, checkpoint windows,
`js_error_observations`, `seo_observations`, `gpt_slot_observations`, monitored URLs, templates,
scenarios, and domain entities. E2 therefore does not need a durable candidate table.

## 5. Target Behavior

1. The fixed registry declares point versus condition semantics and all confirmation, aggregation,
   severity, resolution, and dedupe inputs. Jobs and tenants cannot override them.
2. A derivation loads only tenant-owned, complete/comparable evidence and evaluates both semantic
   transitions and the current condition state. Incomplete windows, incompatible collectors,
   truncated evidence, invalid runs, and missing expected-slot configuration fail closed.
3. `JS_ERROR_STARTED` confirms on the second consecutive comparable checkpoint carrying the same
   fingerprint. Its start occurrence window remains the last known clean observation through the
   first affected observation; `detected_at` records the later confirmation observation.
4. `GPT_EXPECTED_SLOT_MISSING` confirms only when at least two valid URLs corroborate the same
   expected slot for the same template/scenario in a completed window. One aggregated active event
   links each qualifying slot/checkpoint observation and records affected/valid URL counts.
5. A rendered noindex on one exact URL creates only a narrow `RECORDED` point event with
   rule-derived LOW/MEDIUM severity. Template scope and CRITICAL severity require at least two
   valid corroborating URLs; one page can never be labeled template-wide or site-wide.
6. An active condition is selected by a deterministic hash of tenant/site, event code, stable
   subject, normalized scope, and condition identity. Reprocessing or concurrent jobs can create
   at most one active row for that identity.
7. Repeated affected observations append idempotent `SUPPORTING` evidence and may update only
   lifecycle metadata, evidence-supported scope, latest observation, blast radius, and severity.
   Original trigger bounds, trigger details, and trigger evidence remain unchanged.
8. Comparable recovery changes `ACTIVE` to `RESOLVED`, sets `ended_at` to the recovery-confirmation
   observation time, records conservative recovery bounds in `details.lifecycle`, and attaches
   `RECOVERY` evidence. A later recurrence creates a new active event.
9. Existing E1 `OBSERVED` point rows migrate to `RECORDED`; point events are never resolved or
   reused as active conditions.

## 6. Rule Decisions for E2

| Event code | Kind | Confirmation | Dedupe / aggregation | Resolution | Severity |
|---|---|---|---|---|---|
| `JS_ERROR_STARTED` | CONDITION | `TWO_CONSECUTIVE_CHECKPOINTS` for the same fingerprint and comparable URL/scenario | One active event per fingerprint + normalized URL/template/scenario scope; attach later observations | One comparable clean checkpoint after an active condition | LOW/MEDIUM from narrow scope and deterministic rule factors |
| `GPT_EXPECTED_SLOT_MISSING` | CONDITION | `MULTI_URL_CORROBORATION`, initially at least 2 valid affected URLs | One active event per expected slot + template/scenario; store numerator/denominator and all evidence refs | Corroborated healthy state across at least 2 valid representative URLs | MEDIUM/HIGH/CRITICAL from affected scope and blast radius |
| `NOINDEX_ADDED` | POINT | Strong exact rendered transition for page scope; at least 2 valid URLs for template aggregation | One deterministic point event per transition; aggregate same-window template evidence | None; reverse change is a separate future point event | LOW/MEDIUM page scope; CRITICAL only for corroborated broad scope |
| Existing E1 dependency/canonical rules | POINT | `SINGLE_STRONG_OBSERVATION` | Existing deterministic transition identity | None | Existing versioned default |

The value `2` is rule-local versioned configuration for the initial GPT/noindex corroboration
rules, not a global percentage. The implementation records both affected and valid URL counts so
pilot calibration can revise a later rule version without rewriting evidence or claiming a
majority not supported by the sample.

## 7. Architecture / Data Flow

```text
completed checkpoint + immutable normalized observations
  → tenant/comparability/completeness gates
  → fixed rule evaluation and current-condition state
  → consecutive-checkpoint or completed-window confirmation
  → normalize subject/scope + deterministic condition key
  → create RECORDED point event, upsert ACTIVE condition, or resolve ACTIVE condition
  → append controlled evidence references
```

Per-run derivation remains the only job path. Multi-URL promotion executes only after the relevant
checkpoint window is `COMPLETE`; the final run already guarantees a derivation job, so no second
queue handoff is required. A PostgreSQL partial unique index is the final concurrency guard for
active conditions. Deterministic IDs and evidence-reference uniqueness keep retries idempotent.

## 8. Files and Modules Affected

### Existing

- `backend/app/events/contracts.py`
- `backend/app/events/registry.py`
- `backend/app/events/evaluator.py`
- `backend/app/events/models.py`
- `backend/app/events/persistence.py`
- `backend/app/events/service.py`
- `backend/app/browser/models.py` and `backend/app/browser/persistence.py` only if a bounded query
  helper is needed; no collector behavior changes;
- `backend/tests/unit/events/test_registry.py`
- `backend/tests/unit/events/test_evaluator.py`
- `backend/tests/unit/events/test_worker.py`
- `backend/tests/integration/test_browser_checkpoint.py`
- `backend/tests/integration/test_migrations.py`
- `README.md`

### To create

- `backend/app/events/lifecycle.py`
- `backend/migrations/versions/0014_event_persistence_lifecycle_e2.py`
- `backend/tests/unit/events/test_lifecycle.py`
- `backend/tests/integration/test_event_lifecycle.py`

Paths may be adjusted to preserve existing module boundaries. Any material scope or schema change
must be recorded in this plan before implementation continues.

## 9. Data and Migration Contract

Migration `0014` will:

- convert existing `events.status='OBSERVED'` rows to `RECORDED`;
- replace the status check with `RECORDED`, `ACTIVE`, `RESOLVED`, and `SUPERSEDED`;
- add nullable `condition_key` (a bounded deterministic digest) used only for condition events;
- add a partial unique index on `(tenant_id, condition_key)` where `status='ACTIVE'` and
  `condition_key IS NOT NULL`;
- add tenant/site/start and tenant/site/status/start indexes required by the canonical Timeline
  lookup shapes without adding speculative indexes;
- update the six definition mirrors to the E2 registry/schema version without making database
  metadata authoritative.

Lifecycle metadata remains bounded structured JSON under `details.lifecycle`, including latest
observed time, supporting count, affected/valid URL counts, blast radius, and recovery bounds. The
original `details.subject`, `before`, `after`, occurrence bounds, and trigger references are not
rewritten. No raw evidence table changes and no historical checkpoint backfill are required.

The downgrade is allowed only after operator review. It removes the E2 indexes/column, converts
`RECORDED` back to `OBSERVED`, and can proceed only when no `ACTIVE` or `RESOLVED` condition rows
exist; it must fail explicitly rather than silently deleting or flattening condition history.

## 10. Milestones and Acceptance

### M0 — Contract and repository inspection

Goal: fix E2 against merged E1 and the canonical point/condition semantics.

Acceptance:
- [x] branch starts clean from remote `main` merge commit `fc2788d`;
- [x] E1 registry, evaluator, persistence, worker, observation tables, checkpoint windows,
  migrations, and tests are inspected;
- [x] `NOINDEX_ADDED` remains a point event; JS and GPT missing-slot events are conditions;
- [x] E2 excludes alerts, UI, incidents, metrics, public configuration, LLMs, and new
  infrastructure.

Validation:
```bash
git status --short --branch
git rev-parse HEAD
```

Expected observable result: `agent/implement-ep-016` is clean and based on `origin/main`.

### M1 — Versioned rule and lifecycle persistence contracts

Goal: make event kind, confirmation, severity, resolution, and active identity explicit.

Implementation:
- replace the placeholder confirmation literal with controlled canonical modes and typed policies;
- add the E2 policy fields to immutable rule definitions and validate every registry entry;
- normalize subjects/scopes with stable serialization and derive a digest that contains no raw URL
  or sensitive value;
- implement migration `0014`, canonical statuses, active-condition uniqueness, and required
  indexes;
- preserve E1 deterministic point IDs while changing new point-row status to `RECORDED`.

Acceptance:
- [x] every rule declares kind, confirmation, severity, resolution, dedupe, schema, and source
  version;
- [x] arbitrary job/API rule input remains impossible;
- [x] only condition events can carry `condition_key` or status `ACTIVE/RESOLVED`;
- [x] existing E1 rows migrate losslessly from `OBSERVED` to `RECORDED`;
- [x] concurrent active duplicates are rejected by PostgreSQL, not only application code.

Validation:
```bash
uv --directory backend run pytest tests/unit/events/test_registry.py
uv --directory backend run pytest tests/unit/events/test_lifecycle.py
uv --directory backend run pytest tests/integration/test_migrations.py
```

Expected observable result: the registry and schema express canonical lifecycle semantics and
upgrade/downgrade tests preserve pre-E2 point history.

### M2 — Confirmation and multi-URL aggregation

Goal: promote only evidence that satisfies its event-specific E2 rule.

Implementation:
- load the additional predecessor needed for two-checkpoint JS confirmation while preserving the
  original healthy-to-first-affected window;
- load valid runs/observations for the current completed checkpoint window, grouped by exact
  tenant/site/template/scenario and stable subject;
- reject invalid statuses, missing expected configuration, incomplete window membership,
  incompatible collector/normalizer versions, truncated absence evidence, and unordered times;
- aggregate qualifying GPT/noindex observations into one candidate with deterministic scope,
  affected/valid counts, and individual evidence references;
- calculate severity and blast radius only from observed scope; never infer site-wide scope from a
  single URL.

Acceptance:
- [x] one JS occurrence, one missing GPT slot, or an incomplete window persists no condition;
- [x] the same JS fingerprint in two comparable checkpoints confirms once with the first-change
  occurrence window and later detection time;
- [x] two valid template URLs missing the same expected slot create one aggregated candidate;
- [x] unrelated template/scenario/slot observations never corroborate each other;
- [x] page-level noindex stays narrow, while corroborated template noindex can become CRITICAL;
- [x] all thresholds and severity inputs come from the fixed versioned rule.

Validation:
```bash
uv --directory backend run pytest tests/unit/events/test_evaluator.py
uv --directory backend run pytest tests/unit/events/test_lifecycle.py
```

Expected observable result: deterministic fixtures prove both positive confirmation and every
important fail-closed counterexample without browser, provider, or LLM calls.

### M3 — Active dedupe, evidence updates, and resolution

Goal: maintain one truthful condition lifecycle instead of producing checkpoint spam.

Implementation:
- atomically select/create the active row by tenant and deterministic condition key;
- attach typed `TRIGGER_BEFORE`, `TRIGGER_AFTER`, `SUPPORTING`, and `RECOVERY` references after
  validating each source table and tenant/site ownership;
- update only allowed lifecycle/scope/severity fields for repeated support;
- resolve JS on comparable clean evidence and aggregated GPT absence only on corroborated healthy
  evidence meeting the same validity floor;
- retain conservative recovery bounds in details and use the recovery-confirmation observation for
  `ended_at` without claiming that it is the exact recovery instant;
- create a new condition event, with new trigger evidence, if the same identity recurs later.

Acceptance:
- [x] repeated affected checkpoints create no duplicate active event or evidence ref;
- [x] concurrent/retried derivations converge on one active event;
- [x] scope expansion may raise severity; unsupported contraction never silently lowers history;
- [x] recovery resolves only the matching tenant/site/subject/scope condition;
- [x] point events never enter the condition update/resolution path;
- [x] recurrence after resolution creates a distinct event.

Validation:
```bash
uv --directory backend run pytest tests/unit/events/test_lifecycle.py
RUN_INTEGRATION=1 uv --directory backend run pytest tests/integration/test_event_lifecycle.py
```

Expected observable result: an affected → repeated → recovered → recurrent sequence yields two
condition rows, one resolved and one active, with complete immutable evidence linkage.

### M4 — Existing-worker execution and tenant safety

Goal: make E2 reliable under current asynchronous execution and checkpoint-window ordering.

Implementation:
- keep the existing exact `DERIVE_BROWSER_EVENTS` payload and rule-versioned job identity;
- treat expected insufficient evidence as successful structured skip/pending outcomes, not errors;
- ensure the completed-window derivation can aggregate earlier runs regardless of job order;
- retain bounded retries for transient database failures and sanitized logs/counters;
- verify that event failure cannot change raw checkpoint status or evidence.

Acceptance:
- [x] no browser rerun, provider call, external request, or new job type occurs;
- [x] at least one derivation after window completion evaluates the complete valid cohort;
- [x] malformed and cross-tenant jobs fail closed without foreign reads/writes;
- [x] worker retries are idempotent across create/update/resolve actions;
- [x] unsupported confirmation and incomplete evidence never fabricate a row.

Validation:
```bash
uv --directory backend run pytest tests/unit/events/test_worker.py
RUN_INTEGRATION=1 uv --directory backend run pytest tests/integration/test_event_lifecycle.py
```

Expected observable result: the general worker derives E2 state safely from persisted evidence
under reordered and repeated execution.

### M5 — Release gate

Goal: prove E2 correctness, migrations, regressions, documentation, and repository safety.

Acceptance:
- [x] positive, negative, noisy, ordering, aggregation, lifecycle, concurrency, idempotency,
  time-window, and cross-tenant tests pass;
- [x] migration upgrade/downgrade and E1 point-event compatibility pass;
- [x] all browser, connector, metric, incident-drill-down, worker, scheduler, frontend, and security
  regressions pass;
- [x] README and this living plan match validated behavior;
- [x] no alert, incident, causal, UI, or LLM behavior is introduced.

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

Expected observable result: CI proves E2 without E1 or platform regressions and the plan can be
marked COMPLETE.

## 11. Final Acceptance Criteria

- [x] event kind and confirmation are fixed, explicit, versioned, and deterministic;
- [x] point rows are `RECORDED`; condition rows follow `ACTIVE → RESOLVED` or `SUPERSEDED` only;
- [x] one active condition identity cannot produce duplicate rows under retry or concurrency;
- [x] supporting and recovery evidence is append-only and tenant/site validated;
- [x] original trigger evidence, details, and occurrence bounds are never rewritten;
- [x] confirmation time is not substituted for the first-change occurrence window;
- [x] multi-URL aggregation never crosses tenant, site, template, scenario, subject, or valid window;
- [x] severity is separate from observation confidence, alertability, and causal relevance;
- [x] one URL never implies broad scope or a template/site-wide critical claim;
- [x] recovery is evidence-backed, recurrence creates a new event, and point events never resolve;
- [x] raw evidence remains immutable and no candidate, alert, incident, or cause is fabricated.

## 12. Test Cases

Happy path:
- E1 point transition persists with `RECORDED` and unchanged deterministic identity;
- JS clean → affected → affected creates one active event with the original occurrence window;
- later affected JS checkpoint appends support; clean comparable checkpoint resolves it;
- same JS fingerprint after resolution creates a new active row;
- two valid article URLs missing the same expected slot create one template/scenario event;
- later valid corroborated GPT recovery resolves that single aggregate event;
- one exact URL gains noindex as a narrow point fact; corroborated URLs aggregate broad scope.

Counterexamples:
- no predecessor; only one noisy JS observation; nonconsecutive or incompatible JS evidence;
- checkpoint/site/browser failure, partial relevant collector, unordered time, or truncated absence;
- checkpoint window not complete; one valid GPT URL; missing expected-slot configuration;
- same slot across different tenant/site/template/scenario/device/consent contexts;
- one URL used to claim template/site scope; invalid denominator or user-supplied threshold;
- one recovered URL used to resolve a multi-URL condition; stale/out-of-order recovery;
- duplicate worker, concurrent confirmation, repeated support, repeated recovery, and replay;
- wrong evidence kind/source ID, cross-tenant source/event, arbitrary relation, or condition key;
- attempt to resolve/activate a point event or mutate original trigger fields.

Regression:
- E1 dependency and canonical point events and their evidence references;
- B1–B8 checkpoint collection, comparison lineage, and immutable observations;
- C1–C6 connectors, metrics, and incident drill-down;
- migration round-trip, scheduler, general/browser workers, frontend, and security gates.

## 13. Security / Privacy Impact

E2 derives additional `CORE_LONG` event state from already authorized tenant-confidential browser
evidence. It adds no credential, provider permission, external request, raw user data, LLM context,
or retention class. Condition keys are one-way digests over normalized identifiers and do not expose
raw URLs in indexes or logs.

Every observation, active-event, and evidence-reference query independently constrains tenant and
site ownership. The job still carries only checkpoint UUID under its tenant lease. Logs contain
IDs, rule bundle version, counts, lifecycle action, skip/failure class, and duration—not DOM,
messages, URLs with query strings, cookies, headers, stack samples, or secrets.

## 14. Observability / Failure Handling

Record candidate, confirmed, created, reused, evidence-attached, resolved, unsupported, and skipped
counts plus reason codes, rule version, checkpoint/window/tenant/site IDs, duration, and retry
attempt. Insufficient corroboration, incomplete windows, unchanged support, and no matching active
condition are expected deterministic outcomes, not publisher failures.

Ownership mismatch, malformed source references, invalid lifecycle transitions, and rule mismatch
fail closed. Unique-index races are resolved by reloading the winning active event and applying the
same idempotent evidence update. Transient database/runtime failures retry through existing job
fencing/backoff. Event failure never changes checkpoint evidence or status.

## 15. Rollback Strategy

Disable E2 promotion/update handling while leaving E1 point derivation available, then revert the
E2 code. Downgrade `0014` only after verifying there are no `ACTIVE` or `RESOLVED` rows; otherwise
retain the forward-compatible schema and stop E2 processing rather than delete condition history.
Raw browser observations and E1 point events remain available for a later fixed-rule reprocess.

## 16. Known Risks

- Per-run jobs can execute before a window completes; aggregation must wait for `COMPLETE`, while
  the final persisted run/job guarantees a later complete-cohort evaluation.
- A partial unique index prevents duplicate active rows but update races still require transactional
  reload and idempotent evidence insertion.
- Template/scenario identity is only as trustworthy as monitored-URL configuration; E2 must not
  infer a majority or site-wide condition beyond configured valid representatives.
- Two-checkpoint JS confirmation delays detection at six-hour cadence; this is intentional for
  noisy runtime errors and must remain distinct from future critical immediate validation.
- Resolution from absence is unsafe when evidence is partial/truncated/incompatible; those cases
  must leave the event active and emit a skip reason.
- Existing E1 point rows use `OBSERVED`; the data migration and every reader must change together.

## 17. Open Decisions

None blocking. The initial multi-URL floor is two valid corroborating URLs and is stored in the
versioned rule rather than exposed as tenant configuration. Immediate out-of-band validation is
explicitly deferred; E2 never broadens a single observation to compensate.

## 18. Decision Log

- 2026-08-21: Follow canonical EVENTS milestone E2 after merged EP-015/E1.
- 2026-08-21: Reuse immutable checkpoint history for confirmation instead of introducing a
  candidate table or event-stream infrastructure.
- 2026-08-21: Add a bounded `condition_key` plus a partial unique active index because application
  checks alone cannot guarantee dedupe under concurrent checkpoint jobs.
- 2026-08-21: Keep `NOINDEX_ADDED` as a point event; broad scope requires corroboration and point
  reversal taxonomy remains outside this milestone.
- 2026-08-21: Store recovery uncertainty in structured lifecycle details and evidence references;
  `ended_at` is the recovery-confirmation observation, not a claim of exact recovery time.
- 2026-08-21: Use rule-local count thresholds and retain numerator/denominator rather than inventing
  a global template-majority percentage before pilot calibration.

## 19. Discoveries / Surprises

- E1 already persists all three specific source observation types needed for E2, so safe lifecycle
  support is primarily a query/transaction/rule problem rather than a collector expansion.
- The current `OBSERVED` status conflicts with the canonical `RECORDED` point lifecycle and must be
  corrected before condition statuses are introduced.
- The existing worker is per checkpoint, but checkpoint-window completion plus the final run's
  atomic derivation job supplies a minimal complete-cohort aggregation trigger.
- E1 candidate persistence currently resolves non-SEO subjects through generic domain-entity
  observations; E2 must link JS and GPT candidates to their explicit observation tables.

## 20. Progress Log

- 2026-08-21: Implemented the E2 typed rule registry, canonical statuses, deterministic condition
  keys, migration `0014_event_lifecycle_e2`, fixed severity policies, and E1-compatible point IDs.
- 2026-08-21: Implemented two-checkpoint JS confirmation, completed-window GPT/noindex aggregation,
  active dedupe/support, evidence-backed resolution/reopening, typed source references, scope
  ownership validation, and updated worker observability without a new job type or dependency.
- 2026-08-21: Added unit and PostgreSQL integration coverage for pending/confirmed conditions,
  incompatible observers, multi-URL isolation, one-URL non-resolution, concurrent dedupe,
  repeated support, recovery, recurrence, noindex aggregation, migration constraints, and tenant
  ownership.
- 2026-08-21: Ruff, mypy, all 195 unit tests, frontend lint/typecheck/test/build, secret scan,
  `git diff --check`, and offline Alembic upgrade/downgrade SQL pass. PostgreSQL integration could
  not execute locally because no server is available at `localhost:5432`; Docker is not installed,
  so M1/M3/M4 database acceptance and the final M5 gate remain pending CI.
- 2026-08-21: Implementation approved; marked EP-016 IN_PROGRESS and began M1 without staging,
  committing, pushing, or opening a PR.
- 2026-08-21: Confirmed EP-015 PR #16 merged into `main` at `fc2788d`; CI #100 passed.
- 2026-08-21: Created clean branch `agent/implement-ep-016` from `origin/main` and inspected the
  canonical E2 contracts, E1 implementation, observation schema, worker path, migrations, and tests.
- 2026-08-21: Fixed point/condition semantics, confirmation and aggregation boundaries, schema
  migration, concurrency guard, resolution rules, counterexamples, rollback, and validation gates;
  marked EP-016 READY for implementation approval.
- 2026-08-21: Published the initial E2 implementation. CI #102 identified only an ordering defect in
  the new integration-test fixture: checkpoint runs could flush before their referenced checkpoint
  windows. Added explicit window flushes before run insertion and published the focused correction.
- 2026-08-21: Push CI #103 and Draft PR CI #104 passed backend, frontend, and repository-safety.
  Opened Draft PR #17 and marked M1–M5 plus EP-016 COMPLETE.

## 21. Final Outcome / Retrospective

EP-016 completes deterministic E2 lifecycle handling for the browser events deferred by E1.
Persistent JavaScript errors now require two comparable checkpoints; missing expected GPT slots
require corroboration across valid representative URLs; and noindex remains a point fact whose
scope broadens only with multi-URL evidence. Confirmed conditions deduplicate under concurrency,
retain immutable trigger provenance, accumulate supporting evidence, resolve conservatively, and
reopen as new events after recurrence. The implementation reuses the existing PostgreSQL job and
worker boundary and introduces no alert, incident, LLM, UI, or infrastructure authority.

## 22. Validation Results

- Planning baseline: local branch is clean at remote `main` merge commit `fc2788d` before this plan;
- EP-015 final CI run #100 passed;
- dependency lock sync passes with 51 packages checked;
- Ruff format/check and mypy pass across app, tests, scripts, and migrations;
- backend unit suite: 195 passed with one existing Starlette deprecation warning;
- Alembic offline upgrade reaches `0014_event_lifecycle_e2`; targeted downgrade SQL to `0013`
  also generates successfully, including the condition-history safety guard;
- frontend ESLint, TypeScript, Vitest (1 passed), and Next.js production build pass;
- repository secret scan and `git diff --check` pass;
- PostgreSQL remained unavailable locally, but GitHub Actions executed the full database-backed
  suite: 30 integration tests passed, including migrations, concurrent dedupe, evidence ownership,
  resolution, recurrence, scheduler, and worker gates;
- push CI #103 passed for commit `737f451`;
- Draft PR #17 CI #104 passed backend, frontend, and repository-safety;
- implementation PR: https://github.com/marian-dotcom/publisher-intelligence/pull/17;
- final validated CI: https://github.com/marian-dotcom/publisher-intelligence/actions/runs/32423620886.

## 23. Next Step

After authorization, publish this final ExecPlan update and mark PR #17 Ready for review. Review
and merge the PR, then start the next approved milestone from the canonical roadmap.
