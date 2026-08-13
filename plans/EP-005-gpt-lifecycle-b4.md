# EP-005 — GPT Lifecycle Evidence B4

**Status:** COMPLETE
**Owner:** Codex / Engineering
**Created:** 2026-08-14
**Updated:** 2026-08-14
**Target milestone:** B4 — GPT slot lifecycle
**MVP scope impact:** NO
**New infrastructure category:** NO

## Progress

- [x] M0 — Verify B3 integration and close the B4 contract
- [x] M1 — Add expected-slot and GPT observation schema
- [x] M2 — Implement bounded pre-navigation GPT instrumentation
- [x] M3 — Persist expected, discovered, eager, and lazy slot evidence
- [x] M4 — Prove lifecycle semantics, tenancy, and migration behavior
- [x] M5 — Complete documentation, final CI, and retrospective

## 1. Purpose and User Outcome

After this plan is complete, each browser checkpoint can explain how a configured or discovered
Google Publisher Tag slot progressed through the observable client lifecycle. The record preserves
the distinction between expected, defined, requested, responded, rendered, loaded, and viewable
states. Slots configured for a template remain visible when absent, and slots requested only after
the deterministic scroll profile remain distinguishable from eager slots.

This is browser evidence, not incident intelligence. B4 does not create events, severity, alerts,
causal conclusions, revenue estimates, CMP behavior, Prebid auctions, or video diagnostics.

## 2. Scope

### In

- template-owned expected GPT slot records with explicit validity and provenance;
- stable GPT slot identity based on configured/ad-unit path, with DOM element fallback;
- bounded, code-owned instrumentation installed before page navigation;
- discovery of GPT presence, version when safely available, defined slots, sizes, and DOM mapping;
- lifecycle timestamps for `slotRequested`, `slotResponseReceived`, `slotRenderEnded`, `slotOnload`,
  and `impressionViewable`;
- nullable missing stages, render details, and request counts for refreshes;
- expected-but-absent evidence and deterministic lazy-loading observations after B2 scroll steps;
- dedicated append-only GPT observations, manifest v4 output, collector provenance, tenant-scoped reads;
- deterministic local fixture tests, migration round trips, backend quality checks, and regressions.

### Out

- CMP actions (B5), Prebid (B6), video (B7), performance (B8), or live-site test dependencies;
- targeting values, cookies, headers, request/response bodies, creative content, or arbitrary page data;
- ad clicks, configuration mutation, ad refresh initiation, or arbitrary generated browser code;
- event promotion, alerts, incidents, severity, causality, Last Known Good, AI, or frontend work;
- a new service, queue, database, dependency, or production deployment.

## 3. Canonical References

Preserve:

- `AGENTS.md` evidence, browser, security, data minimization, planning, and validation invariants;
- `PLANS.md` implementation loop;
- `MVP.md` browser evidence scope and GPT expected slots;
- `BROWSER.md` GPT lifecycle, testability, evaluation, and B4 milestone requirements;
- `DOMAIN.md` official GPT lifecycle semantics, lazy loading, and failure localization;
- `ARCHITECTURE.md` collector and persistence boundaries;
- `DATA_MODEL.md` domain entity, template expectation, and GPT slot observation contracts;
- `SECURITY.md` hostile-page and evidence-minimization rules;
- `knowledge/DOMAIN_SOURCE_REGISTRY_v1.0.md` official GPT references;
- completed `plans/EP-004-template-aware-browser-evidence-b3.md`.

Contract anchors:

- expected slot identity comes from configured template expectations, never the current page alone;
- `slotRenderEnded` means render completion evidence, not creative load completion;
- missing lifecycle stages remain `NULL`, never zero or inferred;
- deterministic scroll happens before the final GPT snapshot so lazy behavior is observable;
- observer failure cannot erase raw/B3 evidence;
- B4 records facts only and does not manufacture an event or cause.

## 4. Current State

PR #5 is merged into `main` at `c2f22e7`. B3 already stores deterministic normalized DOM,
dependency and JavaScript evidence, stable entities, append-only observations, and template-aware
comparison lineage. The current browser runner installs network/page observers before navigation and
executes the versioned B2 interaction profile before final evidence collection.

The concrete B4 gaps are:

- no template expected-entity table or configured slot loader;
- no dedicated GPT slot observation table/model;
- no pre-navigation GPT listener instrumentation;
- no lifecycle/sizes/render-detail contracts;
- no expected-but-absent merge or lazy-slot fixture;
- manifest and collector bundle remain B3/v3.

## 5. Target Behavior

For every checkpoint, B4 will:

1. load active expected GPT slots for the run template and carry them in the frozen target;
2. install a passive, bounded observer before navigation without creating or configuring GPT;
3. attach documented PubAds event listeners when `googletag` becomes safely observable;
4. inventory defined slots and merge them with configured expectations by stable identity;
5. execute the existing deterministic interaction profile;
6. take a final snapshot that retains each observed stage independently and leaves missing stages
   null;
7. persist one specialized append-only observation per run/slot and expose the same bounded facts
   in manifest v4;
8. classify absence/non-observability explicitly while treating instrumentation errors as partial
   checkpoint evidence, preserving all other artifacts.

## 6. Architecture / Data Flow

```text
Template expected slots
        +
Pre-navigation passive GPT observer
        ↓
Defined slots + lifecycle callbacks
        ↓
Deterministic B2 interactions / lazy request
        ↓
Final bounded snapshot + expected/observed merge
        ↓
GPT domain entities + append-only slot observations
        ↓
Manifest v4 evidence
```

The implementation stays in the browser modular-monolith subsystem and uses existing PostgreSQL,
Playwright/Chromium, object storage, jobs, and worker boundaries.

## 7. Files and Modules Affected

Expected additions:

```text
backend/app/browser/gpt.py
backend/migrations/versions/0005_gpt_lifecycle_b4.py
backend/tests/unit/browser/test_gpt.py
```

Expected modifications:

```text
backend/app/browser/contracts.py
backend/app/browser/models.py
backend/app/browser/persistence.py
backend/app/browser/runner.py
backend/app/browser/service.py
backend/app/browser/scheduling.py
backend/tests/integration/test_browser_checkpoint.py
backend/tests/integration/test_migrations.py
backend/tests/unit/browser/test_persistence.py
README.md
```

## 8. Milestones and Acceptance

### M0 — Integration and contract

- [x] PR #5 merge and exact `main` base verified;
- [x] B4 boundaries and canonical lifecycle stages documented;
- [x] no new dependency, infrastructure category, or product/security decision required.

### M1 — Schema and frozen target

- add `template_expected_entities` and `gpt_slot_observations` with tenant/site/run ownership;
- model stable GPT slot identity and active validity windows;
- load active template expectations into `BrowserTarget`.

Acceptance:

- [x] expected slots are configuration-owned and time-valid;
- [x] observations are unique per run/slot and all lifecycle stages are nullable;
- [x] tenant/site ownership and query indexes are explicit;
- [x] upgrade/downgrade/re-upgrade succeeds in CI.

### M2 — Passive GPT observer

- install a bounded init script before publisher scripts;
- wait for an existing `googletag` object, attach documented listeners through its command queue,
  and inspect PubAds slots without changing publisher configuration;
- sanitize/bound paths, IDs, sizes, event counts, and render identifiers;
- merge expectations without inventing timestamps.

Acceptance:

- [x] no fake GPT global is created and no display/refresh/configuration call is made;
- [x] eager and lazy stages are captured independently;
- [x] repeated requests increment `request_count` without overwriting the first observed stage;
- [x] absent, inaccessible, and technical-error outcomes remain distinct;
- [x] arbitrary targeting and secret-bearing data are not collected.

### M3 — Persistence and manifest

- persist GPT slot domain entities and specialized observations atomically with the checkpoint;
- add tenant-scoped GPT reads;
- expose bounded GPT facts and collector outcome in manifest v4;
- bump the collector bundle to `b4-v1` while retaining B3 normalizer versions.

Acceptance:

- [x] expected-but-absent slots persist with `present=false` and null lifecycle timestamps;
- [x] discovered slots persist even without a configured expectation;
- [x] raw, normalized, and GPT evidence are finalized together;
- [x] B3 normalized evidence and comparisons remain backward compatible.

### M4 — Validation

- unit-test sanitization, stable identity, size conversion, stage preservation, refresh count, and
  expected/observed merge;
- integration-test eager, lazy-after-scroll, expected-absent, tenancy, collector, and manifest facts;
- test migrations and existing backend/frontend regressions.

Acceptance:

- [x] controlled local fixtures prove all lifecycle distinctions without live Google services;
- [x] wrong-tenant GPT reads return no observations;
- [x] no lifecycle timestamp is synthesized as zero;
- [x] format, lint, typecheck, unit, integration, migration, and build checks pass.

### M5 — Completion

- update durable documentation and this plan with actual results;
- inspect diff and secret exposure;
- publish a draft PR and obtain green GitHub Actions.

Acceptance:

- [x] plan status is `COMPLETE` only after local and remote validation pass;
- [x] PR description states scope, semantics, tests, limitations, and rollback path;
- [x] no unrelated changes or hidden blockers remain.

## 9. Validation Commands

```bash
cd backend
UV_CACHE_DIR=/tmp/publisher-intelligence-uv-cache uv run ruff format --check .
UV_CACHE_DIR=/tmp/publisher-intelligence-uv-cache uv run ruff check .
UV_CACHE_DIR=/tmp/publisher-intelligence-uv-cache uv run mypy app
UV_CACHE_DIR=/tmp/publisher-intelligence-uv-cache uv run pytest -m "not integration"
UV_CACHE_DIR=/tmp/publisher-intelligence-uv-cache uv run pytest -m integration

cd ../frontend
corepack pnpm lint
corepack pnpm typecheck
corepack pnpm test
corepack pnpm build
```

## 10. Decision Log

- 2026-08-14 — Use a passive pre-navigation init script that waits for publisher-owned GPT; do not
  create a GPT stub or invoke display/refresh/configuration methods.
- 2026-08-14 — Prefer ad-unit path for stable identity and use DOM element ID only as a fallback;
  creative and line-item IDs are observation details, never identity.
- 2026-08-14 — Store first-seen timestamps per lifecycle stage and a request count. Do not infer
  missing stages or collapse render/onload/viewability.
- 2026-08-14 — Treat no-GPT and API-not-observable as explicit evidence outcomes; only technical
  collector failure degrades an otherwise complete checkpoint to `PARTIAL`.
- 2026-08-14 — Keep B3 normalizer versions unchanged and bump only bundle/manifest/GPT collector
  provenance for semantic compatibility.

## 11. Discoveries / Surprises

- GPT instrumentation must be installed before navigation to avoid losing eager events, but it must
  not pre-create `window.googletag`, because doing so could alter publisher behavior.
- The existing B2 interaction order already places deterministic scroll before the final snapshot,
  which is the correct insertion point for lazy-slot evidence.
- The local Work-mode runtime has neither Docker nor an operational Playwright driver, so real
  PostgreSQL/MinIO/Chromium execution must be completed by the repository's GitHub Actions job.

## 12. Validation Results

- 2026-08-14 — `ruff format --check .`: pass (59 files formatted).
- 2026-08-14 — `ruff check .`: pass.
- 2026-08-14 — `mypy app tests scripts migrations/env.py`: pass (54 source files).
- 2026-08-14 — `pytest tests/unit`: pass (51 tests; one upstream deprecation warning).
- 2026-08-14 — frontend lint, typecheck, Vitest (1 test), and production build: pass.
- 2026-08-14 — repository secret scan and `git diff --check`: pass.
- 2026-08-14 — integration collection: 13 tests collected, including the new real-browser GPT
  fixture; skipped locally as designed because `RUN_INTEGRATION=1` requires Docker services.
- 2026-08-14 — GitHub Actions CI run #41: backend, frontend, and repository-safety all pass.
  Backend includes migration upgrade, downgrade/re-upgrade test, 51 unit tests, 13 integration
  tests, real Chromium GPT fixture, scheduler smoke, and worker smoke.

## 13. Rollback

The code rollback is the B4 commit/PR revert. The migration downgrade drops only B4's two new
tables. B1–B3 checkpoint rows, artifacts, normalized observations, template metadata, and historic
manifests remain intact. No destructive backfill is required.

## 14. Next Step

PR #6 is ready for human review. Mark it ready and merge only after the intended review/branch
protection workflow is satisfied; no additional EP-005 engineering work remains.
