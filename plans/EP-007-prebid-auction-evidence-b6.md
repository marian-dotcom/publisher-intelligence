# EP-007 — Prebid Auction Evidence B6

**Status:** COMPLETE
**Owner:** Codex / Engineering
**Created:** 2026-08-14
**Updated:** 2026-08-14
**Target milestone:** B6 — Prebid auction evidence
**MVP scope impact:** NO
**New infrastructure category:** NO

## Progress

- [x] M0 — Verify B5 integration and close the B6 contract
- [x] M1 — Add lightweight auction and bidder observation schema
- [x] M2 — Implement passive public-API Prebid observation
- [x] M3 — Persist auction, bidder, targeting-key, and ad-server timing evidence
- [x] M4 — Prove client-side, timeout, server-hidden, absence, and tenancy behavior
- [x] M5 — Complete documentation, final CI, and retrospective

## 1. Purpose and User Outcome

After this plan is complete, a controlled browser checkpoint can show whether Prebid.js was
observable, which bounded auction stages occurred, which configured bidder codes were requested,
which returned/no-bid/timed out, how long observable responses took, and whether an ad-server
request followed the auction. It also records when only a Prebid Server endpoint is visible and
bidder internals are therefore not observable.

This is small synthetic browser evidence, not a production auction analytics warehouse. B6 does
not optimize auction timeouts, rank bidders, estimate revenue, retain bid prices or creative data,
create incidents, assign severity, claim causality, or change publisher/Prebid/GAM configuration.

## 2. Scope

### In

- passive detection of publisher-owned `pbjs` without creating a stub or command queue;
- safe use of public/read-only surfaces such as `getEvents()`, `getConfig()`, and
  `getAdserverTargeting()` when feature-detected;
- bounded Prebid presence/version, installed-module names, configured bidder/ad-unit counts,
  auction timeout, and server-side-configuration presence;
- normalized auction start/end/timeout and bidder request/response/no-bid/timeout/win counts;
- bounded bidder response-time min/max/average from observable event fields;
- local sequential auction keys that never persist raw auction or bid identifiers;
- targeting-key presence only, never targeting values, bid prices, deal IDs, or creative data;
- first observable GAM/ad-server request-start timing after auction activity;
- explicit `NOT_PRESENT`, `NOT_OBSERVABLE`, `OK`, and `ERROR` collector outcomes;
- dedicated lightweight auction/bidder tables, manifest v6, and `prebid-b6-v1` provenance;
- deterministic client-side, timeout, Prebid Server hidden-detail, absent, tenancy, and migration
  coverage.

### Out

- bid-level/revenue analytics, every impression, production analytics adapters, or log ingestion;
- raw request/response bodies, OpenRTB payloads, headers, cookies, storage, query values, or IDs;
- price/floor/deal/creative/line-item conclusions or bidder quality scoring;
- discovery of server-side bidders hidden behind one Prebid Server endpoint;
- auction mutation, `requestBids`, targeting mutation, GPT refresh, ad render, or ad clicks;
- CMP changes (B5), video (B7), performance (B8), events, alerts, incidents, or AI;
- a new service, queue, database, dependency, or production deployment.

## 3. Canonical References

Preserve:

- `AGENTS.md` evidence, browser, security, data-minimization, planning, and validation invariants;
- `PLANS.md` implementation loop;
- `MVP.md` sections 24–25 and B6 acceptance boundary;
- `BROWSER.md` sections 30–33, timing ontology, evaluation cases 11–12, and milestone B6;
- `DOMAIN.md` client/server observability, event ontology, timeout reasoning, targeting propagation,
  and non-causal evidence semantics;
- `DATA_MODEL.md` collector outcomes and lightweight auction/bidder observation tables;
- `DECISIONS.md` Playwright/Chromium and fixed black-box checkpoint decisions;
- `SECURITY.md` hostile-page, URL, identifier, request-body, and evidence-minimization rules;
- `knowledge/DOMAIN_SOURCE_REGISTRY_v1.0.md` official Prebid references;
- completed `plans/EP-006-cmp-consent-evidence-b5.md`.

Current official anchors:

- Prebid `getEvents()` returns emitted event history with event type, arguments, and elapsed time;
- current event history can be bounded by publisher `eventHistoryTTL`, so B6 samples it while the
  page is alive instead of assuming it remains forever;
- bidder timeout is an auction deadline and JavaScript timer execution is approximate;
- Prebid Server has a separate lower timeout inside the client auction window;
- one client-visible Prebid Server endpoint does not reveal hidden server bidder timing/decisions.

Official references:

- https://docs.prebid.org/dev-docs/publisher-api-reference/getEvents.html
- https://docs.prebid.org/dev-docs/publisher-api-reference.html
- https://docs.prebid.org/features/timeouts.html
- https://docs.prebid.org/prebid-server/endpoints/openrtb2/pbs-endpoint-auction.html

## 4. Current State

PR #7 is merged into `main` at `b1de8bd`. B5 now provides isolated scheduled browser scenarios,
configured consent paths, CMP/TCF evidence, relative network timing, B3 normalization, B4 GPT
lifecycle evidence, manifest v5, and independent collector outcomes.

The concrete B6 gaps are:

- no passive Prebid event-history observer;
- no auction/bidder contracts or persistence tables;
- no bounded targeting-key or server-side observability summary;
- no explicit Prebid-to-GAM request timing;
- no timeout/server-hidden deterministic fixtures;
- collector bundle and manifest remain B5/v5.

## 5. Target Behavior

For every checkpoint, B6 will:

1. install a passive init script before navigation without creating `pbjs` or altering its queue;
2. poll for a publisher-owned public API and periodically copy only safe event projections in page
   memory so publisher event-history TTL cannot erase already observed stages;
3. assign transient raw auction IDs to local `auction-001` style keys inside the page and export
   only those local keys;
4. snapshot bounded configuration, modules, bidder/ad-unit counts, event summaries, and targeting
   key names after existing consent and interaction steps;
5. parse auctions and aggregate bidder counts/timing without retaining prices, payloads, or IDs;
6. correlate the first sanitized Google ad-serving request start after auction activity;
7. persist auction/bidder evidence atomically with the checkpoint and expose bounded manifest v6
   evidence;
8. report `NOT_OBSERVABLE` when a recognizable Prebid Server endpoint exists without observable
   client bidder detail, rather than fabricating bidder rows;
9. isolate parser/API failure so raw DOM, screenshots, CMP, GPT, and normalized network evidence
   survive in a `PARTIAL` checkpoint.

## 6. Architecture / Data Flow

```text
Publisher-owned pbjs + sanitized network timing
                 ↓
Read-only event-history sampler in page
                 ↓
Safe local auction keys + bidder aggregates
                 ↓
Targeting-key presence + first GAM request timing
                 ↓
Auction/bidder rows + collector result + manifest v6
```

B6 remains inside the browser modular monolith and reuses Playwright, PostgreSQL, object storage,
jobs, workers, collector runs, domain entities, and existing normalized network identities.

## 7. Files and Modules Affected

Expected additions:

```text
backend/app/browser/prebid.py
backend/migrations/versions/0007_prebid_auction_evidence_b6.py
backend/tests/unit/browser/test_prebid.py
```

Expected modifications:

```text
backend/app/browser/collectors.py
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

- [x] PR #7 merge and exact `main` base verified;
- [x] current public event, timeout, and server observability semantics checked against official
  Prebid documentation;
- [x] no new dependency, infrastructure category, or product/security decision required.

### M1 — Contracts and schema

- add auction and bidder observation contracts/models from the canonical lightweight schema;
- add check constraints, uniqueness, counts, timing, tenant/site/run ownership, and read indexes;
- keep presence/version/config/limitations in the collector summary and manifest rather than adding
  an unnecessary third table;
- bump created checkpoint bundle provenance to `b6-v1`.

Acceptance:

- [x] auction keys are local run identities, not durable cross-checkpoint entities;
- [x] bidder codes map to stable site-owned entities without bid/auction IDs;
- [x] nullable timing remains unknown rather than invented as zero;
- [x] upgrade/downgrade/re-upgrade succeeds in GitHub Actions.

### M2 — Passive safe observer

- feature-detect publisher-owned `pbjs` and public read-only methods;
- sample and sanitize bounded event history inside the hostile page before data crosses into Python;
- collect only event type, local auction key, safe bidder code, elapsed/response timing, timeout,
  counts, module names, and targeting key names;
- never call request, targeting, render, refresh, configuration, analytics, or storage APIs.

Acceptance:

- [x] no `pbjs` global/stub/queue is created or mutated;
- [x] raw event arguments, prices, auction/bid IDs, payloads, and targeting values never persist;
- [x] event-history TTL cannot erase stages already sampled by the observer;
- [x] arbitrary/invalid page values are bounded or rejected;
- [x] non-Prebid pages remain unaffected and complete.

### M3 — Aggregation, timing, persistence, and manifest

- normalize auctions and bidder counts/timing from safe event projections;
- persist stable bidder entities plus specialized auction/bidder observations atomically;
- retain request-start timestamps so auction-end-to-GAM timing can be represented;
- add manifest v6 Prebid output and collector provenance without changing B3–B5 semantics.

Acceptance:

- [x] request/response/no-bid/timeout/win counts are explainable and bounded;
- [x] first GAM request timing is present when observable and remains null otherwise;
- [x] Prebid Server hidden details produce limitation metadata, not invented bidders;
- [x] optional collector error retains all other checkpoint evidence.

### M4 — Validation

- unit-test event sanitization, local keys, aggregation, timing, timeouts, and hidden-server state;
- integration-test one client bidder response, one bidder timeout, targeting-key presence, GAM
  request ordering, server-only `NOT_OBSERVABLE`, no-Prebid safety, and tenant isolation;
- test migration round trip and B1–B5 regressions;
- run backend/frontend/repository validation.

Acceptance:

- [x] deterministic client fixture proves auction and bidder lifecycle counts/timing;
- [x] timeout fixture proves timeout is evidence, not a bidder-quality conclusion;
- [x] server-only fixture proves hidden bidder detail remains absent;
- [x] wrong-tenant reads return no auction/bidder evidence;
- [x] format, lint, typecheck, unit, integration, migration, and build checks pass.

### M5 — Completion

- update durable documentation and this plan with actual results;
- inspect passive behavior, diff scope, identifiers, and secret exposure;
- publish a draft PR and obtain green GitHub Actions.

Acceptance:

- [x] plan is `COMPLETE` only after local and remote validation pass;
- [x] PR states behavior, limitations, safety, tests, and rollback;
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

- 2026-08-14 — Use only publisher-owned, read-only, feature-detected Prebid surfaces; do not create
  or push to a `pbjs` command queue.
- 2026-08-14 — Sanitize events in the page and export local sequential auction keys; raw auction
  and bid identifiers never cross the durable evidence boundary.
- 2026-08-14 — Persist counts and response-time aggregates, not bids/prices/payloads. This remains
  synthetic incident evidence rather than an auction data warehouse.
- 2026-08-14 — Targeting evidence is key presence only. Values such as price buckets, bid IDs,
  deals, and creative information are excluded.
- 2026-08-14 — A server endpoint without client bidder events is `NOT_OBSERVABLE`, and the browser
  does not infer server-side bidders.

## 11. Discoveries / Surprises

- Current Prebid supports event-history TTL, so relying on one final `getEvents()` snapshot can lose
  early stages on a publisher that configures a short retention window.
- The existing B5 network observer has response/failure timing but not explicit request-start
  timing; B6 must retain the request boundary to represent ad-server ordering accurately.
- Unrelated Prebid events may have no auction ID; the parser now accepts only the bounded auction
  event allowlist so it cannot manufacture an `auction-unassigned` observation.
- GAM traffic can precede a later header-bidding auction on the same page; correlation therefore
  selects the first sanitized GAM request at or after each observed auction boundary rather than
  the first GAM request in the whole checkpoint.

## 12. Validation Results

Local validation on 2026-08-14:

- `ruff format --check .` — passed (65 files formatted);
- `ruff check .` — passed;
- `mypy app tests scripts migrations/env.py` — passed (58 source files);
- `pytest tests/unit` — passed (56 tests; one upstream Starlette deprecation warning);
- frontend lint and typecheck — passed;
- frontend Vitest — passed (1 test);
- frontend production build — passed;
- repository secret scan and `git diff --check` — passed;
- GitHub Actions run 31756794343 — passed: backend, frontend, and repository-safety;
- PostgreSQL/MinIO browser integration, deterministic client/timeout/server-only fixtures, and
  migration upgrade/downgrade/re-upgrade — passed in GitHub Actions;
- Draft PR #8: https://github.com/marian-dotcom/publisher-intelligence/pull/8.

Retrospective: the page-side allowlist and local auction-key projection kept raw Prebid arguments
outside the durable boundary, while request-start timestamps made GAM ordering representable
without bodies or query values. Explicit `NOT_OBSERVABLE` server evidence preserved the key
client/server distinction without expanding B6 into log ingestion or auction analytics.

## 13. Rollback

Revert the B6 commits and downgrade migration 0007. The downgrade removes only B6 auction/bidder
tables. B1–B5 checkpoint rows, artifacts, normalized observations, GPT lifecycle, CMP/consent
evidence, and manifest history remain intact.

## 14. Next Step

Review and merge Draft PR #8. The next planned browser milestone is B7 video evidence; it remains
outside EP-007 and should begin with a separate ExecPlan after B6 is integrated into `main`.
