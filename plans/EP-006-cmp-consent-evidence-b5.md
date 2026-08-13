# EP-006 — CMP and Consent Evidence B5

**Status:** COMPLETE
**Owner:** Codex / Engineering
**Created:** 2026-08-14
**Updated:** 2026-08-14
**Target milestone:** B5 — CMP and consent phases
**MVP scope impact:** NO
**New infrastructure category:** NO

## Progress

- [x] M0 — Verify B4 integration and close the B5 contract
- [x] M1 — Add consent scenario and structured CMP evidence schema
- [x] M2 — Implement passive TCF observation and configured consent action
- [x] M3 — Persist pre/post dependency effects and visual evidence
- [x] M4 — Prove Accept, Reject, unavailable, tenancy, and migration behavior
- [x] M5 — Complete documentation, final CI, and retrospective

## 1. Purpose and User Outcome

After this plan is complete, a controlled browser checkpoint can show whether a CMP/TCF interface
was present and ready, what the synthetic browser observed before a decision, whether its configured
primary consent action succeeded, and how the bounded dependency/request pattern changed afterward.
A separately configured Reject canary path records a legitimate alternative request pattern without
calling it a failure.

This is consent/runtime evidence, not legal advice or incident intelligence. B5 does not assess CMP
policy compliance, decode personal consent choices into a user profile, create events, assign
severity, claim causality, or modify publisher/CMP configuration.

## 2. Scope

### In

- versioned scenario `consent_path` with `PRIMARY`, `REJECT`, and `NONE` semantics;
- core desktop/mobile primary path and an unscheduled mobile Reject canary scenario;
- passive pre-navigation detection of `__tcfapi`, CMP readiness, TCF event status, GDPR scope,
  safe CMP identifiers/versions, TC String hash, and bounded error codes;
- current TCF API usage through `ping`, `addEventListener`, and listener cleanup where possible;
- publisher/template-configured manual selectors for Accept/Reject and an optional ready selector;
- conservative action resolution: configured selector or `action_unavailable`, never a random click;
- pre-consent and post-action viewport artifacts where CMP evidence is present;
- checkpoint-level `cmp_observations` and normalized pre/post dependency summaries;
- manifest v5 consent evidence and `cmp-b5-v1` collector provenance;
- deterministic Accept/Reject/unavailable fixtures, tenancy checks, migration round trip, and
  B1–B4 regressions.

### Out

- a universal CMP selector catalog, computer vision, text guessing, or reverse engineering every UI;
- legal/compliance judgments, vendor eligibility conclusions, raw TC String long-term storage, or
  collection of cookies/local storage;
- Reject on every URL every six hours, new geography/proxy infrastructure, or returning-user state;
- Prebid auction evidence (B6), video (B7), performance (B8), events, alerts, incidents, or AI;
- form submission outside the configured CMP action, ad clicks, or configuration writes;
- a new service, queue, database, dependency, or production deployment.

## 3. Canonical References

Preserve:

- `AGENTS.md` evidence, browser, security, data-minimization, planning, and validation invariants;
- `PLANS.md` implementation loop;
- `MVP.md` sections 13–15, 26, Phase B, and limited consent scenario contract;
- `BROWSER.md` scenario matrix, navigation protocol, screenshots, CMP detection/action/phases,
  timing, eval cases, security rules, and B5 milestone;
- `DOMAIN.md` current TCF v2.3 context, consent observability, timing, and failure localization;
- `DATA_MODEL.md` browser scenario, CMP observation, dependency phase, and artifact contracts;
- `DECISIONS.md` ADR-013 through ADR-015;
- `SECURITY.md` hostile-page, confidential evidence, and no personal-session constraints;
- `knowledge/DOMAIN_SOURCE_REGISTRY_v1.0.md` official TCF and Prebid consent references;
- completed `plans/EP-005-gpt-lifecycle-b4.md`.

Current external anchors:

- IAB CMP API v2 requires `ping`, `addEventListener`, and `removeEventListener`; `getTCData` is
  deprecated and will not be used;
- TCF technical/policy/CMP software versions remain separate;
- Prebid consent timeouts do not turn undiscoverable CMP APIs into a later polling contract;
- TCF v2.3 is the current technical context in the canonical domain model.

## 4. Current State

PR #6 is merged into `main` at `fcb3a00`. B4 now provides a pre-navigation GPT observer, stable
slot expectations and lifecycle observations, deterministic scroll, append-only evidence,
manifest v4, and a real Chromium fixture. The current B2 core desktop/mobile scenarios do not carry
consent identity, the runner takes only one initial viewport screenshot, and network observations do
not retain relative timestamps.

The concrete B5 gaps are:

- no scenario `consent_path` or Reject canary configuration;
- no safe configured consent adapter contract;
- no passive TCF readiness/event observer;
- no distinct pre/post screenshots or consent action evidence;
- no CMP observation or consent-phase dependency tables;
- no pre/post request boundary or manifest consent section;
- collector bundle remains B4/v4.

## 5. Target Behavior

For each core fresh-context checkpoint, B5 will:

1. carry the scenario's frozen consent path and validated template adapter into `BrowserTarget`;
2. install passive TCF listeners before navigation without creating a CMP stub;
3. stabilize, snapshot CMP/TCF pre-consent state, and capture a pre-consent viewport when present;
4. click only the configured Accept/Reject selector for the scenario;
5. record action start/completion/status and wait a bounded post-action stabilization interval;
6. snapshot the post-action TC state and capture a post-consent viewport;
7. execute the existing deterministic interaction profile and B4 GPT final snapshot;
8. persist one CMP observation plus normalized dependency summaries split at action start;
9. preserve missing/late/unavailable states explicitly and degrade to `PARTIAL` only when a present
   CMP cannot complete the configured required action.

If neither CMP API nor configured UI is present, the collector records `NOT_PRESENT` and the rest of
the checkpoint may remain `COMPLETE`. Reject is represented as a valid configured path, not as an
error or negative publisher outcome.

## 6. Architecture / Data Flow

```text
Frozen scenario + template consent adapter
                ↓
Pre-navigation passive TCF listener
                ↓
Pre-consent API/UI/network snapshot + screenshot
                ↓
Configured PRIMARY or REJECT action
                ↓
Post-action TCF/network snapshot + screenshot
                ↓
Existing scroll + GPT/B3 evidence
                ↓
CMP observation + phase dependency summaries + manifest v5
```

B5 remains inside the browser modular monolith and reuses PostgreSQL, Playwright/Chromium, object
storage, jobs, workers, normalized dependency identities, and the existing scenario scheduler.

## 7. Files and Modules Affected

Expected additions:

```text
backend/app/browser/cmp.py
backend/migrations/versions/0006_cmp_consent_evidence_b5.py
backend/tests/unit/browser/test_cmp.py
```

Expected modifications:

```text
backend/app/browser/contracts.py
backend/app/browser/collectors.py
backend/app/browser/models.py
backend/app/browser/persistence.py
backend/app/browser/runner.py
backend/app/browser/service.py
backend/app/browser/scheduling.py
backend/app/config/settings.py
backend/tests/integration/test_browser_checkpoint.py
backend/tests/integration/test_migrations.py
backend/tests/unit/browser/test_persistence.py
README.md
```

## 8. Milestones and Acceptance

### M0 — Integration and contract

- [x] PR #6 merge and exact `main` base verified;
- [x] current TCF API and B5 boundaries documented from canonical/official sources;
- [x] no new dependency, infrastructure category, or product/security decision required.

### M1 — Scenario and persistence schema

- add versioned consent path to browser scenarios and frozen targets;
- add dedicated CMP and phase dependency observation tables;
- add bounded settings for discovery, action, and post-action stabilization;
- configure core scenarios as `PRIMARY`, legacy diagnostic as `NONE`, and Reject mobile canary
  without adding it to the six-hour scheduler allowlist.

Acceptance:

- [x] scenario identity distinguishes primary/reject behavior;
- [x] existing scenario rows migrate deterministically;
- [x] CMP evidence is unique per checkpoint and lifecycle/timing fields remain nullable;
- [x] dependency phase evidence is unique per run/phase/dependency and tenant-scoped;
- [x] upgrade/downgrade/re-upgrade succeeds.

### M2 — Passive TCF observer and configured action

- install a bounded init script that waits for publisher-owned `__tcfapi`;
- call current mandatory API commands and retain only safe bounded fields plus TC String SHA-256;
- validate adapter configuration and select only the configured action selector;
- record present, ready, action completed/unavailable/timeout/error, and post-action states.

Acceptance:

- [x] no CMP global/stub is created and deprecated `getTCData` is absent;
- [x] no raw TC String, cookie, local storage, targeting, or arbitrary UI text is retained;
- [x] no click occurs without an exact configured selector;
- [x] Reject completion is valid evidence, not collector/checkpoint failure;
- [x] a present CMP with a required unavailable action produces partial evidence.

### M3 — Phase evidence, screenshots, and manifest

- timestamp network observations relative to the attached pre-navigation observer;
- normalize request/error counts and first request timing into PRE/POST phase evidence;
- persist CMP identity when safely available and dependency observations atomically;
- add pre/post viewport artifacts and manifest v5 consent output;
- bump only bundle/CMP provenance while retaining B3/B4 collector semantics.

Acceptance:

- [x] pre/post request patterns are explainable without duplicating raw network logs;
- [x] screenshots and action records reveal what the browser did and when;
- [x] B3 normalized state, B4 GPT slots, and prior artifact behavior remain intact;
- [x] collector failure cannot erase already observed browser evidence.

### M4 — Validation

- unit-test adapter validation, TCF parsing/hashing, absent/unavailable states, and phase aggregation;
- integration-test Accept triggers post-consent ad requests and Reject yields a different valid
  request pattern;
- test wrong-tenant reads, migration round trip, no-config safety, and existing browser behavior;
- run backend/frontend/repository validation.

Acceptance:

- [x] controlled fixtures prove Accept, Reject, API/UI timing, and phase differences;
- [x] wrong-tenant CMP/dependency reads return no evidence;
- [x] ordinary non-CMP pages remain complete and no extra UI click is attempted;
- [x] format, lint, typecheck, unit, integration, migration, and build checks pass.

### M5 — Completion

- update durable documentation and this plan with actual results;
- inspect diff, action safety, and secret exposure;
- publish a draft PR and obtain green GitHub Actions.

Acceptance:

- [x] plan is `COMPLETE` only after local and remote validation pass;
- [x] PR states behavior, safety boundary, tests, limitations, and rollback;
- [x] no unrelated changes or hidden blockers remain.

## 9. Validation Commands

```bash
cd backend
UV_CACHE_DIR=/tmp/publisher-intelligence-uv-cache uv run ruff format --check .
UV_CACHE_DIR=/tmp/publisher-intelligence-uv-cache uv run ruff check .
UV_CACHE_DIR=/tmp/publisher-intelligence-uv-cache uv run mypy app tests scripts migrations/env.py
UV_CACHE_DIR=/tmp/publisher-intelligence-uv-cache uv run pytest tests/unit
RUN_INTEGRATION=1 UV_CACHE_DIR=/tmp/publisher-intelligence-uv-cache uv run pytest tests/integration

cd ../frontend
COREPACK_HOME=/tmp/publisher-intelligence-corepack corepack pnpm lint
COREPACK_HOME=/tmp/publisher-intelligence-corepack corepack pnpm typecheck
COREPACK_HOME=/tmp/publisher-intelligence-corepack corepack pnpm test
COREPACK_HOME=/tmp/publisher-intelligence-corepack corepack pnpm build
```

## 10. Decision Log

- 2026-08-14 — Use `ping` and `addEventListener`, with `removeEventListener` cleanup where possible;
  do not use deprecated `getTCData`.
- 2026-08-14 — The initial B5 action adapter is publisher/template-configured manual selectors.
  Unknown/generic UI remains unavailable rather than guessed.
- 2026-08-14 — Core desktop/mobile scenarios use `PRIMARY`; Reject is a mobile canary configuration
  excluded from the existing six-hour scheduler allowlist.
- 2026-08-14 — Hash the TC String and retain only safe CMP/TCF state; raw consent strings and
  browser storage are not durable evidence.
- 2026-08-14 — Split dependency summaries at action start so requests initiated by the consent
  click are post-action evidence even if the click promise completes later.

## 11. Discoveries / Surprises

- The current IAB API deprecates `getTCData`; event listeners are the authoritative way to receive
  current TC data and changes.
- Existing B2 scenario selection already uses a strict code allowlist, so a Reject canary scenario
  can be configured without accidentally multiplying six-hour runs.
- The local work environment has no Docker executable, so PostgreSQL/MinIO migration and real
  browser integration tests must run in GitHub Actions; this is recorded as unverified locally,
  not as a local pass.

## 12. Validation Results

- `ruff format --check .`: passed across 62 Python files.
- `ruff check .`: passed.
- `mypy app tests scripts migrations/env.py`: passed across 56 source files.
- `pytest tests/unit`: 54 passed; one dependency deprecation warning.
- frontend `lint`, `typecheck`, `test`, and production `build`: passed; Vitest 1 passed.
- `alembic heads`: one head, `0006_cmp_consent_b5`.
- local integration/migration round trip: not run because Docker is unavailable in this runtime;
  GitHub Actions supplied that required validation gate.
- GitHub Actions CI run #47: backend, frontend, and repository-safety passed. Backend includes 54
  unit tests, 16 PostgreSQL/MinIO/Chromium integration tests, migration
  upgrade/downgrade/re-upgrade, scheduler smoke, and worker smoke.

## 13. Rollback

Revert the B5 commits and downgrade migration 0006. The downgrade removes only B5 CMP/phase tables
and the scenario consent-path column. B1–B4 checkpoint rows, artifacts, normalized observations,
GPT lifecycle evidence, and manifest history remain intact.

## 14. Next Step

PR #7 is green and ready for human review. Mark it ready and merge only after the intended
review/branch-protection workflow is satisfied; no additional EP-006 engineering work remains.
