# EP-009 — Synthetic Performance Evidence B8

**Status:** IN_PROGRESS
**Owner:** Codex / Engineering
**Created:** 2026-08-14
**Updated:** 2026-08-14
**Target milestone:** B8 — Synthetic performance
**MVP scope impact:** NO
**New infrastructure category:** NO

## Progress

- [x] M0 — Verify B7 integration and close the B8 measurement contract
- [x] M1 — Add a lightweight PerformanceObserver collector and strict parser
- [x] M2 — Persist canonical synthetic performance evidence and manifest v8
- [ ] M3 — Prove deterministic performance, absence, failure, migration, and tenancy behavior
- [ ] M4 — Complete documentation, final CI, and retrospective

## 1. Purpose and User Outcome

After this plan is complete, every successful controlled browser checkpoint can preserve a small,
comparable synthetic performance observation: navigation timings, the last valid observable LCP
candidate, CLS session-window score, an interaction-latency proxy when qualifying interactions
exist, long-task totals, and bounded resource/DOM summary context.

B8 completes Browser v1 without becoming Lighthouse or real-user monitoring. Every stored value is
explicitly `synthetic_browser`, collector-versioned, scenario-bound, and unable to masquerade as a
field p75 Core Web Vital or a Google ranking conclusion.

## 2. Scope

### In

- a small init script installed before navigation using native `PerformanceObserver` and
  Performance Timeline APIs;
- navigation TTFB, DOMContentLoaded, and load-event timing where observable;
- the latest foreground LCP candidate observed before the bounded checkpoint snapshot;
- CLS calculated from unexpected layout shifts with the standard one-second gap/five-second
  session-window rule;
- an explicitly labeled Event Timing worst-observed-interaction proxy only when qualifying
  interactions exist;
- long-task count and total duration when the API is supported;
- bounded aggregate resource timing context without URLs and a bounded DOM node count;
- strict hostile-page parsing, finite/non-negative bounds, API-support metadata, measurement
  limitations, and observer contamination restraint;
- canonical `synthetic_performance_observations` persistence, tenant read isolation, migration
  0009, manifest v8, bundle `b8-v1`, and collector `performance-b8-v1` provenance;
- deterministic layout-shift/long-task fixture, ordinary-page regression, migration round trip,
  parser counterexamples, collector failure, and tenant-boundary coverage.

### Out / Non-Goals

- Lighthouse, PageSpeed Insights, trace archives, CPU/network throttling, performance budgets, or a
  general audit product;
- real-user monitoring, CrUX ingestion, field p75 values, publisher RUM, or merging synthetic and
  field evidence;
- forced clicks or arbitrary interactions solely to manufacture INP; a missing proxy stays null;
- raw resource URLs, names, query values, response bodies, initiator stacks, DOM element identity,
  layout-shift node identity, or long-task attribution details;
- soft-navigation measurement, cross-origin iframe aggregation, BFCache/prerender special handling,
  or proprietary performance SDKs;
- automatic good/poor verdicts, anomaly/event creation, alerting, SEO/ranking causality, incident
  attribution, connectors, or production rollout;
- new dependencies, services, databases, browser engines, or CDP as the default architecture.

## 3. Canonical References

Preserve:

- `AGENTS.md` evidence, browser, minimization, security, validation, and planning invariants;
- `PLANS.md` milestone and living-document contract;
- `MVP.md` sections 31, 100–103, and the constrained commercial-MVP boundary;
- `BROWSER.md` sections 42–44, 54, 57, 73, EVAL-BR-010, milestones B8, and Browser v1 acceptance;
- `DOMAIN.md` sections 13–14 and the synthetic-versus-field prohibition;
- `DATA_MODEL.md` section 44 and invariant DM-019;
- `ARCHITECTURE.md` modular collector and partial-checkpoint behavior;
- `DECISIONS.md` Playwright/Chromium, bounded browser evidence, and KISS decisions;
- `SECURITY.md` hostile-page parsing, browser isolation, minimization, and tenant ownership;
- completed `plans/EP-008-video-player-evidence-b7.md`.

Current official anchors:

- LCP is emitted as successive candidates; the last observable candidate is usually useful but is
  not automatically identical to the full field metric, especially for iframes/background state;
- CLS is the largest session-window sum, using gaps below one second and a maximum five-second
  window, and excludes shifts associated with recent user input;
- INP is a full-visit interaction metric. B8 therefore stores only a clearly named bounded proxy
  when Event Timing exposes qualifying interactions;
- native Performance Timeline/Observer APIs are sufficient for this milestone; no trace or CDP
  architecture is required.

Official references:

- https://web.dev/articles/lcp
- https://web.dev/articles/cls
- https://web.dev/articles/inp
- https://www.w3.org/TR/performance-timeline/
- https://www.w3.org/TR/navigation-timing-2/
- https://www.w3.org/TR/resource-timing-2/
- https://w3c.github.io/longtasks/
- https://w3c.github.io/event-timing/

## 4. Current State

PR #9 is merged into `main` at `9f21d5f`. B1–B7 provide isolated desktop/mobile Chromium
scenarios, deterministic waits/scrolls, screenshots/DOM/network/errors, normalized comparisons,
GPT/CMP/Prebid/video evidence, PostgreSQL/object-storage persistence, partial failure, six-hour
scheduling, manifest v7, and collector bundle `b7-v1`.

The concrete B8 gaps are:

- no pre-navigation native performance observer;
- no canonical navigation/LCP/CLS/interaction-proxy/long-task observation;
- no `synthetic_performance_observations` table or tenant read path;
- no performance section in the manifest;
- no EVAL-BR-010 deterministic fixture proving synthetic provenance and limitations;
- collector bundle and manifest remain B7/v7.

## 5. Target Behavior

For every checkpoint that reaches page collection, B8 will:

1. install a bounded native observer before navigation, with no page mutation or heavy framework;
2. retain only numeric entries required to calculate LCP candidate, CLS session windows,
   interaction proxy, and long-task aggregates;
3. snapshot navigation/resource/DOM summaries after the configured interaction sequence and before
   DOM serialization/full-page screenshot work can contaminate the measurement window;
4. parse the page-owned payload as untrusted input, rejecting non-finite, negative, oversized, or
   structurally invalid values;
5. persist one canonical row per checkpoint with source `synthetic_browser` in metadata;
6. store null for unavailable metrics rather than zero, while preserving bounded limitation codes;
7. expose the same observation in manifest v8 with collector and scenario provenance;
8. mark a technical collector failure as checkpoint `PARTIAL` while retaining B1–B7 evidence.

## 6. Architecture / Data Flow

```text
Native PerformanceObserver before navigation
                    ↓
Bounded LCP / layout-shift / event / long-task samples
                    ↓
Navigation + resource + DOM aggregate snapshot
                    ↓
Strict Python parser and CLS session-window calculation
                    ↓
Canonical PostgreSQL row + manifest v8 performance section
```

B8 remains in the browser modular monolith and reuses Playwright, Chromium, scenarios,
interactions, PostgreSQL, jobs, workers, and existing checkpoint provenance.

## 7. Files and Modules Affected

Expected additions:

```text
backend/app/browser/performance.py
backend/migrations/versions/0009_synthetic_performance_b8.py
backend/tests/unit/browser/test_performance.py
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

No dependency or infrastructure file should change.

## 8. Milestones and Acceptance

### M0 — Integration, standards, and contract

Goal: start from merged B7 and close the smallest canonical B8 behavior.

Acceptance:

- [x] PR #9 is merged and branch starts at exact `origin/main`;
- [x] B8 remains synthetic evidence, not field CWV, Lighthouse, event, or SEO causality;
- [x] no new dependency, service, CDP default, permission, or infrastructure category is needed;
- [x] LCP candidate, CLS session window, and interaction proxy limitations are explicit.

### M1 — Lightweight collector and parser

Goal: observe bounded performance entries without materially altering the page.

Implementation:

- add a pre-navigation init script using feature-detected PerformanceObserver entry types;
- retain bounded LCP, unexpected layout shifts, interaction durations, and long-task samples;
- snapshot navigation, resource aggregates, DOM node count, visibility, and support metadata;
- parse all values defensively and calculate CLS session windows in Python;
- return explicit `OK`, `NOT_OBSERVABLE`, or `ERROR` collector status.

Acceptance:

- [x] observer does not mutate page content, click, scroll, throttle, trace, or use CDP;
- [x] no URL, query, resource name, DOM identity, or attribution stack leaves the page;
- [x] CLS uses maximum standard session-window sum and ignores recent-input shifts;
- [x] INP stays null without qualifying interactions and uses a named proxy otherwise;
- [x] unsupported APIs produce null plus limitation, not fabricated zero;
- [x] hostile/non-finite/negative/oversized values are rejected or bounded.

### M2 — Schema, persistence, and manifest

Goal: persist one unmistakably synthetic performance record per checkpoint.

Implementation:

- add the canonical table and migration 0009 with non-negative constraints and one-row uniqueness;
- persist the observation atomically with checkpoint finalization;
- add tenant-scoped reads;
- expose manifest v8 performance evidence and `performance-b8-v1` collector provenance;
- bump new runs to bundle `b8-v1`.

Acceptance:

- [x] schema matches `DATA_MODEL.md` section 44;
- [x] source is always `synthetic_browser` and cannot be mistaken for field p75;
- [x] unavailable values remain nullable;
- [ ] wrong-tenant reads return no performance evidence;
- [ ] migration upgrade/downgrade/re-upgrade succeeds;
- [ ] older manifest/checkpoint rows remain immutable.

### M3 — Deterministic validation

Goal: prove B8 observable behavior, failure restraint, and regression safety.

Implementation:

- add a controlled fixture with a real unexpected layout shift, an observable long task, LCP
  candidate, navigation/resource timings, and no qualifying user interaction;
- verify the persisted row and manifest use synthetic provenance;
- verify ordinary fixtures remain complete and non-performance collectors regress cleanly;
- verify collector error makes the checkpoint partial without losing B1–B7 evidence;
- run backend/frontend/repository checks and migration round trip.

Acceptance:

- [ ] EVAL-BR-010 observes non-zero synthetic CLS without a field-CWV claim;
- [ ] navigation, LCP candidate, long-task, resource summary, and DOM count are bounded;
- [ ] INP proxy is null and explicitly limited when no qualifying interaction exists;
- [ ] collector failure preserves the rest of the checkpoint as `PARTIAL`;
- [ ] tenant isolation and migration inventory pass;
- [ ] format, lint, typecheck, unit, integration, migration, build, and secret checks pass.

### M4 — Completion

Goal: leave Browser v1 reviewable, reproducible, and safely reversible.

Implementation:

- update README and this plan with actual behavior/results;
- inspect observer weight, provenance, minimization, failure status, and diff scope;
- publish one Draft PR and obtain green GitHub Actions.

Acceptance:

- [ ] plan becomes `COMPLETE` only after local and remote validation pass;
- [ ] PR states behavior, limitations, safety, tests, and rollback;
- [ ] no unrelated change, accidental secret, or hidden blocker remains.

## 9. Final Acceptance Criteria

- [ ] every collectable checkpoint has one versioned synthetic performance observation;
- [ ] navigation/LCP/CLS/interaction proxy/long tasks preserve null-versus-zero semantics;
- [ ] resource timing is aggregate-only and contains no resource identity;
- [ ] synthetic provenance and scenario/environment metadata are explicit;
- [ ] performance collector failure retains B1–B7 evidence as `PARTIAL`;
- [ ] tenant ownership, migration round trip, and regressions pass;
- [ ] manifest v8 and bundle `b8-v1` are documented and tested;
- [ ] no field p75, ranking, causality, or Lighthouse claim is introduced.

## 10. Final Validation

```bash
UV_CACHE_DIR=/tmp/publisher-intelligence-uv-cache uv --directory backend run ruff format --check .
UV_CACHE_DIR=/tmp/publisher-intelligence-uv-cache uv --directory backend run ruff check .
UV_CACHE_DIR=/tmp/publisher-intelligence-uv-cache uv --directory backend run mypy app tests scripts migrations/env.py
UV_CACHE_DIR=/tmp/publisher-intelligence-uv-cache uv --directory backend run pytest tests/unit
RUN_INTEGRATION=1 UV_CACHE_DIR=/tmp/publisher-intelligence-uv-cache uv --directory backend run pytest tests/integration
COREPACK_HOME=/tmp/publisher-intelligence-corepack corepack pnpm@11.16.0 --dir frontend lint
COREPACK_HOME=/tmp/publisher-intelligence-corepack corepack pnpm@11.16.0 --dir frontend typecheck
COREPACK_HOME=/tmp/publisher-intelligence-corepack corepack pnpm@11.16.0 --dir frontend test
COREPACK_HOME=/tmp/publisher-intelligence-corepack corepack pnpm@11.16.0 --dir frontend build
python scripts/check_secrets.py
git diff --check
```

## 11. Test Cases

Happy path:

- real Chromium emits navigation, LCP, layout-shift, long-task, and resource entries;
- CLS is non-zero and computed from validated shift samples;
- one canonical row and manifest section preserve identical bounded semantics.

Failures and counterexamples:

- missing PerformanceObserver entry type returns null plus limitation;
- no qualifying interaction returns null INP proxy rather than zero;
- backgrounded observation invalidates LCP/CLS candidates;
- hostile NaN/infinity/negative/oversized arrays cannot reach persistence;
- evaluate failure returns collector `ERROR` and checkpoint `PARTIAL`.

Regression and tenancy:

- existing ordinary/GPT/CMP/Prebid/video fixtures remain complete;
- no resource URL or query secret appears in manifest/database metadata;
- wrong-tenant performance query returns no row;
- migration clean upgrade/downgrade/re-upgrade adds only the B8 table.

## 12. Data / Migration Impact

Migration 0009 adds only `synthetic_performance_observations` from `DATA_MODEL.md` section 44:

- UUID primary key plus tenant/site/checkpoint ownership;
- one row per checkpoint;
- nullable LCP/CLS/INP proxy/navigation timings;
- nullable long-task count/total;
- collector version, timestamp, and bounded metadata;
- tenant/checkpoint read index and non-negative constraints.

No backfill is required. Old manifest v1–v7 checkpoints remain immutable. Downgrade removes only
the B8 table.

## 13. Security / Privacy Impact

B8 adds no credentials, production access, external service, or user data. The page remains hostile.

Mitigations:

- payload is parsed as untrusted input with type, finite, sign, count, and size bounds;
- observer uses platform APIs and small arrays only;
- raw URLs, resource names, query values, DOM identities, task attribution, and bodies are excluded;
- aggregate initiator categories use a fixed allowlist;
- no click, arbitrary page action, trace, CDP session, or stored browser profile is introduced;
- writes and reads remain server-side tenant-owned.

## 14. Observability / Failure Handling

Collector type: `SYNTHETIC_PERFORMANCE`  
Collector version: `performance-b8-v1`

Outcomes:

- `OK`: navigation or supported performance evidence was safely observed;
- `NOT_OBSERVABLE`: the page-side API/snapshot is unavailable or yields no valid evidence;
- `ERROR`: collector attach/evaluation failed.

`ERROR` contributes to checkpoint `PARTIAL`. Individual missing metrics do not. Limitation codes
explain unsupported APIs, no qualifying interaction, background state, absent LCP candidate, and
incomplete load timing without sensitive page values.

## 15. Rollback Strategy

Revert B8 commits and downgrade migration 0009. The downgrade removes only synthetic performance
rows. B1–B7 checkpoint evidence and manifest versions remain intact.

## 16. Known Risks

- observer APIs and exact metric definitions can evolve with Chromium;
- LCP and CLS inside cross-origin iframes are not aggregated by this top-frame collector;
- the bounded synthetic lifetime is shorter and more deterministic than a real user visit;
- ad/creative randomness, device/network differences, caches, and consent paths can change values;
- instrumentation and Playwright activity may add small measurement overhead;
- no user interaction means INP proxy is frequently unavailable by design.

## 17. Open Decisions

None blocking. Field CWV connectors, performance event thresholds, soft navigations, richer
attribution, and explicit diagnostic interactions remain future, separately approved work.

## 18. Decision Log

- 2026-08-14 — Use native PerformanceObserver/Timeline APIs; do not add Lighthouse, web-vitals,
  tracing, or CDP architecture for B8.
- 2026-08-14 — Compute CLS from bounded validated unexpected-shift samples using standard session
  windows.
- 2026-08-14 — Store only a named Event Timing proxy when qualifying interactions exist; never
  label a forced or absent interaction as INP.
- 2026-08-14 — Persist aggregate resource timing context without URLs or initiator stacks.
- 2026-08-14 — Keep classification/anomaly/field comparison outside B8.

## 19. Discoveries / Surprises

- The existing deterministic interaction profile already creates a bounded measurement lifetime
  through stabilization and scroll waits; B8 needs no new scenario behavior.
- The canonical table already provides all first-class columns needed; resource/DOM context can
  remain bounded metadata.
- Current official guidance explicitly warns that raw LCP/CLS APIs and synthetic lab lifetimes can
  differ from field metrics, reinforcing the required provenance boundary.
- This workspace can run parser/unit/frontend checks but its local Playwright driver closes during
  initialization and Docker is unavailable, so real Chromium/PostgreSQL/MinIO behavior must be
  proven by the repository's GitHub Actions integration job.

## 20. Progress Log

- 2026-08-14 — PR #9 merge verified at `9f21d5f`; branch `agent/implement-ep-009` created from
  exact `origin/main`.
- 2026-08-14 — Canonical B8 contracts and current official LCP/CLS/INP/Performance Timeline
  guidance reviewed; M0 complete and implementation boundary closed.
- 2026-08-14 — M1–M2 implemented: native observer, strict parser, standard CLS windows,
  interaction proxy semantics, migration 0009, atomic persistence, tenant read path, manifest v8,
  and bundle `b8-v1`.
- 2026-08-14 — Local Ruff, mypy, all 63 backend unit tests, frontend
  lint/typecheck/test/build, secret scan, and diff check passed. Real browser/database integration
  remains for GitHub Actions.

## 21. Validation Results

Local validation on 2026-08-14:

- `ruff format --check .` — passed (71 files);
- `ruff check .` — passed;
- `mypy app tests scripts migrations/env.py` — passed (62 source files);
- `pytest tests/unit` — passed (63 tests; one upstream Starlette deprecation warning);
- frontend lint, typecheck, Vitest, and production build — passed;
- repository secret scan and `git diff --check` — passed;
- Playwright/PostgreSQL/MinIO integration and migration round trip — pending GitHub Actions because
  Docker is unavailable and the local Playwright driver cannot initialize in this workspace.

## 22. Final Outcome / Retrospective

Pending implementation and validation.

## 23. Next Step

Commit the B8 implementation, publish a Draft PR, and use GitHub Actions to validate the real
layout-shift/long-task fixture, collector failure, tenancy, and migration round trip.
