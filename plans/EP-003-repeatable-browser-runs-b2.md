# EP-003 — Repeatable Browser Runs B2

**Status:** COMPLETE
**Owner:** Codex / Engineering  
**Created:** 2026-08-14  
**Updated:** 2026-08-14  
**Target milestone:** B2 — Repeatable 6-hour-compatible browser run  
**MVP scope impact:** NO  
**New infrastructure category:** NO

## Progress

- [x] M0 — Inspect merged B1 and close the B2 contract
- [x] M1 — Add immutable interaction-profile and complete device-scenario configuration
- [x] M2 — Materialize idempotent six-hour windows and scheduled jobs
- [x] M3 — Execute frozen desktop/mobile profiles and deterministic interactions
- [x] M4 — Preserve comparable manifests and checkpoint-window lifecycle
- [x] M5 — Prove repeatability, scheduling, migration, security, and browser behavior
- [x] M6 — Complete documentation, final CI, and retrospective

## 1. Purpose and User Outcome

After this plan is complete, one configured public publisher URL will no longer require an operator
to create every checkpoint manually. The scheduler will create one controlled desktop run and one
controlled mobile run in each stable six-hour site window. Each run will use an immutable,
versioned scenario and interaction profile, record exactly what it did, and remain directly
comparable with the previous run produced by the same URL and scenario.

This is the second product proof: the B1 observation becomes repeatable operational memory rather
than a one-off browser capture. It still produces evidence only. It does not create diffs, events,
alerts, incident conclusions, or AI interpretation.

## 2. Scope

### In

- four stable checkpoint windows per site-local day: 00:00, 06:00, 12:00, and 18:00;
- idempotent materialization of each active monitored URL × active core scenario within a window;
- a frozen desktop core scenario and a frozen mobile core scenario;
- complete versioned device provenance: viewport, scale factor, user agent, mobile/touch flags,
  locale, timezone, cache mode, and scenario version;
- a versioned interaction profile containing a bounded ordered step list;
- deterministic B2 actions: bounded wait, percentage scroll, and explicit inspection marker;
- recorded target/actual scroll position, document height, action timing, and action result;
- deterministic staggering of jobs inside the six-hour window to avoid publisher bursts;
- checkpoint-window status derived from its child runs;
- a query/repository path that selects the previous comparable run by monitored URL and exact
  scenario identity without creating semantic diffs;
- migration, unit, PostgreSQL/MinIO/Chromium integration tests, scheduler smoke, and documentation.

### Out

- consent discovery or Accept/Reject actions (B5);
- template discovery, URL rotation, normalized DOM, script/network fingerprints, or semantic diff
  output (B3);
- GPT, Prebid, CMP, video, SEO, performance, visual-AI, event, alert, or incident logic;
- returning-user/cache scenarios, authenticated pages, paywall bypass, geo proxies, throttling,
  browser farms, or additional browser/device matrices;
- ad clicking, form submission, arbitrary selectors, arbitrary JavaScript, or LLM-generated steps;
- production deployment or network-level egress infrastructure.

## 3. Canonical References

Read and preserve:

- `AGENTS.md` sections 7–8, 13–21, 25, 28–32;
- `PLANS.md` sections 8–25, 27–39, 63–76;
- `MVP.md` sections 9–21 and 75;
- `BROWSER.md` invariants and sections 3–19, 45–47, 56–65, 75–86;
- `ARCHITECTURE.md` sections 16–31, 81–84, 97–101, 130, 133, 136, 142, 148;
- `DATA_MODEL.md` sections 16–24, 95–96, 100–105, 120–128, 135–138;
- `SECURITY.md` sections 40–72, 97–107, 133–142, 187, 191–192;
- `DECISIONS.md` ADR-008–020 and ADR-021–023;
- completed `plans/EP-002-browser-checkpoint-b1.md`.

Contract anchors:

- every configured core URL receives one observation in each six-hour site window;
- checkpoint evidence and observer definitions remain immutable/versioned;
- desktop and mobile are the only core device classes;
- interaction is deterministic, bounded, explicit, and never clicks ads;
- a site failure is evidence; a browser/runtime failure is monitor failure;
- synthetic evidence is not represented as real-user truth.

## 4. Current State

EP-002 is merged into `main` in PR #3. The repository now contains:

- real Playwright/Chromium execution in a separate browser worker;
- one fresh non-persistent context per B1 run;
- initial URL, redirect, and subresource SSRF enforcement;
- tenant-scoped browser configuration, checkpoint, attempt, collector, and artifact tables;
- private S3-compatible artifacts and an immutable manifest;
- bounded waits, technical-only retry, and typed final statuses;
- an operator command that registers one URL and immediately enqueues one desktop B1 run;
- deterministic local fixtures and green PostgreSQL/MinIO/real-Chromium CI coverage.

The remaining B2 gaps are concrete:

- the scheduler still enqueues only the EP-001 bootstrap no-op;
- B1 creates an ad-hoc five-minute window at the current instant;
- only `core_desktop_v1` exists and its device provenance is viewport-only;
- no `interaction_profiles` table or scenario/profile relationship exists;
- the runner performs only navigation, stabilization, and screenshots;
- there is no bounded, typed interaction executor;
- checkpoint windows are not summarized after child-run completion;
- comparable predecessor selection is not exposed or tested.

## 5. Target Behavior

Given one active monitored URL on a site configured for `Europe/Bucharest`, a scheduler tick inside
the 12:00–18:00 local window will:

1. resolve the canonical 12:00 local window and store its UTC bounds;
2. create that site window once, even if two schedulers or repeated ticks race;
3. create exactly two runs: frozen core desktop and frozen core mobile;
4. enqueue exactly one idempotent job per run, staggered deterministically inside the window;
5. allow the browser worker to execute each run in a fresh context with its exact stored profile;
6. navigate, capture initial viewport evidence, perform configured bounded scroll steps, capture raw
   DOM and the full-page screenshot last, and persist a manifest containing every action;
7. finalize the window from child-run states without describing site health as scheduler health;
8. return the previous finalized run only when URL and exact scenario ID match.

Repeated scheduler ticks must create no duplicate window, run, or job. A mobile result must never be
selected as the desktop predecessor. A newer scenario version starts a new comparison lineage.

## 6. Architecture / Data Flow

```text
Scheduler tick
    ↓
Six-hour window resolver (site timezone)
    ↓
Checkpoint scheduling service
    ├──→ PostgreSQL window + URL/scenario runs (idempotent)
    └──→ PostgreSQL jobs (deterministically staggered)
              ↓
Browser worker
    ↓
Frozen scenario + interaction profile
    ↓
Fresh Chromium context → bounded action executor → B1 collectors/artifacts
    ↓
Private object storage + atomic PostgreSQL finalization
    ↓
Window status summary + comparable predecessor lookup
```

The API remains outside browser execution. Scheduler code materializes business identities and
jobs; it does not run Chromium. The existing queue remains the only queue.

## 7. Files and Modules Affected

Likely existing files:

```text
backend/app/browser/contracts.py
backend/app/browser/models.py
backend/app/browser/persistence.py
backend/app/browser/runner.py
backend/app/browser/service.py
backend/app/browser_cli.py
backend/app/browser_worker.py
backend/app/config/settings.py
backend/app/scheduler.py
backend/tests/unit/browser/
backend/tests/integration/test_browser_checkpoint.py
backend/tests/integration/test_migrations.py
.env.example
.github/workflows/ci.yml
README.md
```

Likely additions:

```text
backend/app/browser/interactions.py
backend/app/browser/scheduling.py
backend/migrations/versions/0003_repeatable_browser_runs_b2.py
backend/tests/unit/browser/test_interactions.py
backend/tests/unit/browser/test_scheduling.py
```

Names may be simplified after implementation inspection, but scheduling, interaction execution,
and persistence responsibilities must remain separate.

## 8. Milestones

### M0 — Inspect merged B1 and close the B2 contract

Goal: define the smallest B2 slice without pulling B3–B8 work forward.

Implementation:

- inspect the merged schema, scheduler, runner, queue, fixtures, and CI;
- reconcile B2 with the accepted six-hour/device/interaction decisions;
- record data, security, retry, and validation boundaries in this plan.

Acceptance:

- [x] current B1 behavior and exact B2 gaps are documented;
- [x] no new infrastructure/dependency or unresolved product decision blocks B2;
- [x] consent, normalization/diff, and publisher-specific collectors remain out of scope.

Validation:

```bash
git status --short
git diff --check
```

Expected observable result: this self-contained plan was ready for implementation to resume
without chat history.

### M1 — Immutable interaction profile and complete device scenarios

Goal: make every B2 observer configuration explicit and versioned.

Implementation:

- add `interaction_profiles` with tenant/site ownership, code, version, bounded JSON steps,
  lifecycle timestamps, and uniqueness constraints;
- add a nullable `interaction_profile_id` and retirement metadata to browser scenarios using a
  backwards-compatible migration;
- preserve historic `core_desktop_v1` unchanged and retire it from new scheduling;
- create new active frozen B2 desktop and mobile scenario definitions rather than mutating B1;
- validate allowed profile fields and supported interaction step contracts at application boundary.

Acceptance:

- [x] old B1 checkpoints still resolve their original scenario unchanged;
- [x] active desktop/mobile scenarios contain complete frozen device provenance;
- [x] interaction profile version or material device behavior cannot change in place;
- [x] tenant/site mismatch between scenario and interaction profile is rejected;
- [x] migration upgrade/downgrade/re-upgrade passes on a clean database.

Validation:

```bash
uv --directory backend run pytest tests/unit/browser -k "scenario or interaction"
RUN_INTEGRATION=1 uv --directory backend run pytest tests/integration/test_migrations.py
```

Expected observable result: PostgreSQL can represent two comparable core device scenarios and one
bounded action program without rewriting B1 history.

### M2 — Idempotent six-hour scheduler

Goal: turn active monitor configuration into exactly one run per core scenario per window.

Implementation:

- resolve 00/06/12/18 local wall-clock windows with `zoneinfo` and persist UTC instants;
- materialize windows/runs using existing unique identities and conflict-safe repository methods;
- enqueue missing run jobs with stable idempotency keys;
- stagger `scheduled_at` deterministically by site, URL priority, and scenario within window bounds;
- make repeated ticks and concurrent scheduler attempts safe;
- retain the explicit operator enqueue path for diagnostics without confusing it with cadence.

Acceptance:

- [x] one active URL produces exactly desktop + mobile runs in a due window;
- [x] repeated/concurrent ticks create no duplicates;
- [x] inactive URLs/sites/scenarios are skipped;
- [x] scheduled timestamps remain correct across `Europe/Bucharest` DST transitions;
- [x] jobs are spread within the window and contain identifiers only;
- [x] a scheduler restart can enqueue an existing PENDING run whose job was never created.

Validation:

```bash
uv --directory backend run pytest tests/unit/browser/test_scheduling.py
RUN_INTEGRATION=1 uv --directory backend run pytest tests/integration -k scheduling
uv --directory backend run python -m app.scheduler --once
```

Expected observable result: four idempotent site windows per local day can drive bounded background
work without a browser storm.

### M3 — Frozen device execution and deterministic interactions

Goal: execute exactly the stored scenario instead of reconstructing behavior from global defaults.

Implementation:

- extend `BrowserTarget` with frozen device and interaction configuration;
- create contexts from stored viewport, user agent, scale factor, mobile/touch, locale, and timezone;
- add a typed action executor for bounded wait, percentage scroll, and inspection markers only;
- record requested/actual position, document height, timing, outcome, and limitations per action;
- retain viewport capture before interactions and full-page capture after all runtime evidence;
- keep every wait, page height, step count, popup, request, and overall run bounded.

Acceptance:

- [x] desktop and mobile fixture runs expose distinct stored environment provenance;
- [x] repeated execution of the same fixture/profile yields the same ordered action contract;
- [x] scroll steps record target and actual values without random/human-like behavior;
- [x] an unsupported or malformed step fails safely before arbitrary page execution;
- [x] action failure yields explicit partial/timeout evidence without discarding prior artifacts;
- [x] no action can click an ad, submit a form, or execute arbitrary JavaScript from configuration.

Validation:

```bash
uv --directory backend run pytest tests/unit/browser/test_interactions.py
RUN_INTEGRATION=1 uv --directory backend run pytest tests/integration/test_browser_checkpoint.py
```

Expected observable result: both core device classes execute a reproducible, auditable visit whose
manifest explains exactly how the page was changed by the observer.

### M4 — Comparable manifests and window lifecycle

Goal: make repeated runs operationally usable without implementing B3 semantic diffs.

Implementation:

- update manifest schema/version with complete scenario and interaction provenance;
- add repository lookup for the previous finalized run with the same tenant, monitored URL, and
  exact scenario identity;
- summarize checkpoint-window status from child-run states and completion;
- expose comparison lineage identifiers/limitations, not comparison conclusions;
- preserve immutable finalized checkpoint rows and artifacts.

Acceptance:

- [x] desktop never selects mobile as predecessor;
- [x] a new scenario version does not compare against the old observer definition;
- [x] predecessor selection is tenant-scoped and ordered by scheduled/actual time deterministically;
- [x] window `COMPLETE` means all child observations finalized, not that every page was healthy;
- [x] mixed finalized/non-finalized child states yield an explicit operational window state;
- [x] finalization cannot overwrite an existing completed run.

Validation:

```bash
uv --directory backend run pytest tests/unit/browser -k "comparable or window"
RUN_INTEGRATION=1 uv --directory backend run pytest tests/integration -k "comparable or window"
```

Expected observable result: downstream B3 can ask for two compatible checkpoints without guessing
observer identity or scheduler state.

### M5 — Repeatability, security, and integration proof

Goal: prove the entire B2 behavior with controlled infrastructure.

Implementation:

- extend fixtures with deterministic page height and lazy content triggered by scroll;
- run two windows for both device scenarios and verify persistence/action order/predecessors;
- add inactive config, duplicate tick, DST, retry, action-timeout, SSRF, and tenant-boundary cases;
- keep Chromium/MinIO/PostgreSQL integration authoritative in CI.

Acceptance:

- [x] two windows produce four immutable runs and no duplicates;
- [x] all artifact hashes and manifest references resolve;
- [x] SSRF and private-subresource protections remain green during interaction;
- [x] cross-tenant scheduling, scenario, run, predecessor, and artifact access is denied;
- [x] site 503 remains `SITE_ERROR` and is not retried away;
- [x] browser/runtime failure still preserves attempts and retries at most once;
- [x] scheduled workload and action budgets remain bounded.

Validation:

```bash
uv --directory backend run ruff format --check .
uv --directory backend run ruff check .
uv --directory backend run mypy app tests scripts migrations/env.py
uv --directory backend run pytest tests/unit
RUN_INTEGRATION=1 uv --directory backend run pytest tests/integration
```

Expected observable result: controlled real Chromium proves repeatable desktop/mobile runs across
two six-hour windows with private persisted evidence.

### M6 — Documentation, final CI, and retrospective

Goal: leave a reproducible operating path and a truthful completion record.

Implementation:

- document B2 scenario/profile behavior, scheduler cadence, manual diagnostic path, and limitations;
- update `.env.example`, README, and this plan with exact commands/results;
- inspect final diff, secret scan, migration, frontend regression, and GitHub Actions;
- mark `COMPLETE` only after final branch CI is green.

Acceptance:

- [x] docs distinguish scheduled monitoring from manual diagnostic enqueue;
- [x] docs state synthetic evidence and production network-egress limitations;
- [x] no temporary screenshots, profiles, traces, secrets, or generated build artifacts are committed;
- [x] all local supported checks and final GitHub Actions pass;
- [x] retrospective records deviations, limitations, and the exact next B3 step.

Validation:

```bash
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend test
pnpm --dir frontend build
python scripts/check_secrets.py
docker compose config
git diff --check
git status --short
```

Expected observable result: EP-003 is reviewable, reproducible, and ready to merge without hidden
validation claims.

## 9. Final Acceptance Criteria

- [x] each active core URL receives exactly one desktop and one mobile run in each due six-hour
  site-local window;
- [x] repeated or concurrent scheduler ticks are idempotent;
- [x] execution is staggered and bounded rather than bursty;
- [x] scenario and interaction definitions are immutable/versioned and fully represented in
  checkpoint provenance;
- [x] deterministic actions are recorded in order with target/actual state and no arbitrary code;
- [x] initial viewport evidence precedes interaction and final full-page capture remains last;
- [x] two same-URL/same-scenario runs form a valid comparison lineage;
- [x] different device/scenario versions never become silent comparators;
- [x] finalized evidence, artifact hashes, attempt history, and tenant ownership remain intact;
- [x] window status describes observer completion separately from publisher health;
- [x] site/browser/timeout/blocked/partial/complete semantics remain distinct;
- [x] no consent, ad clicking, stealth, authentication, event, incident, or AI scope is introduced;
- [x] migration, local supported checks, and authoritative GitHub Actions pass.

## 10. Final Validation

```bash
uv --directory backend sync --all-groups --locked
uv --directory backend run playwright install chromium
uv --directory backend run ruff format --check .
uv --directory backend run ruff check .
uv --directory backend run mypy app tests scripts migrations/env.py
uv --directory backend run pytest tests/unit

docker compose config
docker compose up -d postgres minio minio-init
uv --directory backend run alembic upgrade head
RUN_INTEGRATION=1 uv --directory backend run pytest tests/integration

pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend test
pnpm --dir frontend build

python scripts/check_secrets.py
git diff --check
git status --short
```

Local Docker/Chromium limitations must be reported accurately. GitHub Actions remains authoritative
for any integration that the hosted runtime cannot execute.

## 11. Test Cases

### Happy path

- scheduler resolves the current local six-hour site window;
- one URL yields desktop and mobile runs/jobs exactly once;
- both workers persist screenshots, DOM, action evidence, complete profile provenance, and manifest;
- next window selects the matching previous run for each scenario.

### Failure and partial paths

- repeated/concurrent scheduler invocation creates no duplicates;
- queue insertion interruption is recovered by the next tick;
- malformed timezone/configuration is isolated and logged without stopping other sites;
- unsupported action is rejected before browser execution;
- bounded action timeout preserves prior evidence and yields explicit status;
- page 503 is finalized as site evidence;
- Chromium/storage failure follows existing technical retry semantics.

### Edge and regression paths

- Bucharest DST transitions map wall-clock windows to correct UTC instants;
- inactive/retired URL or scenario is not scheduled;
- mobile/desktop and scenario-version lineages never cross;
- historic B1 scenario/checkpoints remain readable after migration;
- top-level redirect and hostile private subresource remain blocked;
- action manifest contains no query secrets, cookie values, headers, bodies, or arbitrary DOM data;
- tenant A cannot schedule, load, compare, or retrieve tenant B evidence.

## 12. Data / Migration Impact

Add `interaction_profiles` as defined by `DATA_MODEL.md` section 16:

```text
id, tenant_id, site_id, code, version, description, steps, created_at, retired_at
```

Extend `browser_scenarios` with the minimum B2 relationship/lifecycle metadata:

```text
interaction_profile_id nullable FK
retired_at nullable
```

The frozen device fields remain in the existing versioned `device_profile` JSONB because they are
configuration/provenance, not cross-run query facts. Add constraints/indexes for active profile and
scenario lookup. Do not modify or delete finalized B1 checkpoint evidence. The old desktop B1
scenario remains readable and is retired only from future scheduling; new behavior receives a new
scenario identity/version.

Downgrade is permitted only in disposable local/CI databases. After pilot evidence exists, rollback
means disabling B2 scheduling and reverting application behavior, not destructively removing
checkpoint/profile history.

## 13. Security / Privacy Impact

B2 does not add a new data category or external service. It increases execution frequency and page
interaction, so it must preserve and test:

- explicit configured-site authorization and tenant ownership;
- fresh disposable contexts and frozen synthetic identity;
- blocked permissions/downloads/popups and enabled Chromium sandbox;
- top-level, redirect, and subresource SSRF controls throughout scroll-triggered requests;
- low concurrency, deterministic staggering, bounded step/request/time budgets;
- no ad click, form submission, arbitrary selector, or arbitrary JavaScript step;
- sanitized URLs and absence of cookies, headers, bodies, secrets, or raw DOM in logs/action JSON;
- private encrypted object storage and existing evidence retention classes.

Application SSRF defense remains insufficient against DNS rebinding by itself. Production
network-level egress enforcement remains a prerequisite before untrusted pilot traffic; this plan
does not claim to provide that infrastructure.

## 14. Observability / Failure Handling

Structured scheduler/browser logs may include:

```text
tenant_id, site_id, checkpoint_window_id, checkpoint_run_id, scenario_id,
interaction_profile_id, job_id, scheduled_for, stage, duration_ms, status, error_class
```

They must not include full query strings, page content, job payload dumps, cookies, headers, or
secrets. Track counts for windows/runs/jobs created versus reused, execution lag, device/scenario,
action result, window completion, and existing browser status taxonomy.

Retry only technical browser/storage/lease failures, at most once. Do not retry away `SITE_ERROR`,
`BLOCKED`, an intentional partial observation, or a completed action sequence. Every attempt and
partial artifact remains preserved.

## 15. Rollback Strategy

1. stop the scheduler/browser worker or disable B2 scenario status for new scheduling;
2. preserve all windows, runs, attempts, manifests, profiles, and artifacts already created;
3. revert B2 application commits while leaving the additive migration in place after real evidence;
4. in disposable local/CI only, downgrade `0003` and re-run `0002` migration validation;
5. resume the B1 manual diagnostic path if needed.

Rollback must never delete finalized evidence or silently reactivate the old scenario as if it were
comparable with B2.

## 16. Known Risks

- desktop + mobile doubles core run count and site/storage cost;
- DST makes site-local wall-clock windows non-uniform in UTC;
- dynamic document height limits exact percentage-scroll comparability;
- scroll can trigger additional ad/network activity and must remain polite and bounded;
- mobile emulation can change when an unfrozen device descriptor is upgraded;
- scheduler/queue writes are not one distributed transaction and require reconciliation by
  idempotent repeated ticks;
- application-level SSRF interception still needs production network egress enforcement.

## 17. Open Decisions

None blocking. Exact desktop/mobile field values, stagger interval, and bounded wait profiles are
ordinary implementation calibration. Freeze them in versioned configuration, record them in the
plan, and adjust only through new versions if pilot evidence later requires change.

## 18. Decision Log

### 2026-08-14 — Preserve B1 observer identity

Decision: do not attach new interactions to historic `core_desktop_v1` in place. Retire it from new
scheduling and create new versioned B2 scenarios.

Reason: changing a scenario that already produced evidence would create false before/after
differences and violate mandatory observer provenance.

### 2026-08-14 — B2 prepares comparison but does not compute diffs

Decision: implement exact comparable predecessor selection only. Stable DOM/network normalization
and semantic diff output remain B3.

Reason: B2 proves repeatable collection; interpreting differences is a separate coherent outcome.

### 2026-08-14 — No consent action in B2

Decision: the B2 action executor supports wait, deterministic scroll, and inspection markers only.

Reason: `BROWSER.md` assigns CMP behavior and safe consent adapters to B5. Random or generic button
clicking would expand security and product scope.

## 19. Discoveries / Surprises

- B1 already satisfies several B2 prerequisites: isolated contexts, scenario/run identity, private
  object storage, checkpoint persistence, attempt history, and provenance scaffolding.
- The canonical B2 milestone still requires real scheduling, mobile identity, and deterministic
  interactions; adding another ad-hoc CLI run would not satisfy the six-hour contract.
- Existing `core_desktop_v1` has already produced evidence without interaction steps, so extending
  it in place would corrupt comparison semantics.
- PostgreSQL rejects an unscoped `FOR UPDATE` when the target query includes the nullable side of
  the interaction-profile outer join. Locking only `checkpoint_runs` preserves fencing semantics.
- Integration fixtures must derive due windows from the current instant: a fixed historic window
  correctly excludes a newly registered monitored URL whose `valid_from` is later.

## 20. Progress Log

### 2026-08-14 — M0 complete; implementation started

PR #3 and EP-002 were confirmed merged into `main`. Repository contracts, schema, queue, scheduler,
runner, worker, fixtures, and tests were inspected. B2 scope was closed around six-hour idempotent
scheduling, two frozen device profiles, deterministic scroll interactions, window lifecycle, and
exact predecessor selection. No new dependency, infrastructure category, or user decision is
required. M1 is next.

### 2026-08-14 — M1–M4 implementation complete; integration validation pending

Added the additive `0003` migration, tenant/site-owned immutable interaction profiles, retired B1
scenario lifecycle, and frozen B2 desktop/mobile configurations. The scheduler now resolves
site-local 00/06/12/18 windows with DST-aware UTC bounds, materializes conflict-safe runs, and
enqueues stable staggered jobs. The browser runner now executes only typed bounded wait/scroll/
inspection steps, records requested and actual scroll state, and persists manifest v2 with exact
scenario/profile provenance and comparable-predecessor identity. Window state is summarized from
all child runs rather than finalized by the first child.

Local supported validation:

- Ruff format and lint: passed;
- strict mypy: passed;
- backend unit suite: 38 passed;
- frontend lint, typecheck, Vitest, and production build: passed;
- secret scan and `git diff --check`: passed.

Docker is not installed in this runtime, so clean PostgreSQL migration, MinIO persistence, and real
Chromium repeatability tests were not claimed locally. The following authoritative GitHub Actions
run supplied that coverage before M1–M5 acceptance was closed.

### 2026-08-14 — M5–M6 complete; authoritative CI green

GitHub Actions CI run #29 completed successfully for commit
`0ee80879c9ae1913c19fe2353815856ad79845f6`. The backend job installed Chromium, applied the full
Alembic chain, started PostgreSQL and MinIO, passed 38 unit tests and all 12 integration tests, and
completed scheduler/worker smoke commands. Frontend lint, typecheck, Vitest, and production build
passed, as did repository secret scanning, Compose validation, and diff hygiene.

Two CI-only defects were corrected without expanding scope: the checkpoint attempt query now locks
only its primary `checkpoint_runs` row when loading an optional interaction profile, and the
repeatability fixture derives its two consecutive six-hour windows from the current UTC instant.
Both corrections retain the intended production contracts and are covered by the green real-
infrastructure integration suite.

## 21. Final Outcome / Retrospective

EP-003 delivers the B2 product proof: each active monitored URL can be materialized idempotently as
one frozen desktop and one frozen mobile observation per site-local six-hour window. Runs execute a
bounded, versioned interaction profile, retain exact device/action provenance, summarize their
window lifecycle, and expose only exact-scenario predecessor lineage for the future diff stage.

The implementation deliberately stops before B3 interpretation. It does not normalize DOM or
network evidence, compute semantic differences, create events/incidents, interact with consent
controls, or add AI conclusions. Historic B1 evidence remains readable and is never silently
treated as comparable with the new observer definitions.

Validation is complete for the supported local checks and the authoritative GitHub environment.
The remaining operational limitation is unchanged: application request interception is not a
substitute for production network-level egress enforcement against DNS rebinding. B3 should next
add stable DOM/network normalization and explainable comparison output on top of the exact lineage
created here, without changing B2 observer identities in place.
