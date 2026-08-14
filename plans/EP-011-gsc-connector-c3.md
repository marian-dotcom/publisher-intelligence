# EP-011 — Google Search Console Read-Only Connector C3

**Status:** COMPLETE
**Owner:** Codex / Engineering
**Created:** 2026-08-14
**Updated:** 2026-08-14
**Target milestone:** C3 — Google Search Console
**MVP scope impact:** NO
**New infrastructure category:** NO

## Progress

- [x] M0 — Verify merged GA4 C2 and close the GSC contract against current official docs
- [x] M1 — Generalize the C1 repository boundary without changing GA4 semantics
- [x] M2 — Add strict read-only GSC definitions, client, and normalization
- [x] M3 — Add validation, schedules, worker execution, and URL Inspection on demand
- [x] M4 — Prove fixtures, tenancy, idempotency, maturity, and final CI

## 1. Purpose and User Outcome

After this plan is complete, the platform can validate an already-authorized Search Console
property and ingest bounded Search and Discover performance evidence. Search and Discover remain
different source-native series, every Pacific-time bucket is mapped to an explicit UTC interval,
and fresh/incomplete evidence remains visibly preliminary until a later finalized extract is
stored separately.

GSC evidence describes Google-reported visibility and clicks. It does not prove a technical SEO
cause, penalty, external update, demand change, Discover eligibility change, or browser health.

## 2. Scope

### In

- exact `https://www.googleapis.com/auth/webmasters.readonly` enforcement;
- exact preservation of Domain (`sc-domain:`) and URL-prefix property identifiers;
- `sites.list` permission/capability validation and safe short `web` / `discover` probes;
- predefined `GSC_SEARCH_DAILY_V1`, `GSC_DISCOVER_DAILY_V1`, and
  `GSC_SEARCH_HOURLY_V1` definitions;
- bounded Search Analytics pagination using at most 25,000 rows per request and the documented
  50,000-row-per-day-per-type ceiling;
- strict row parsing for clicks, impressions, CTR, and position;
- `final`, `all`, and `hourly_all` handling with `first_incomplete_date/hour` metadata;
- Pacific (`America/Los_Angeles`) source-time preservation and UTC conversion;
- mature daily seven-day reconciliation and four-hour preliminary operational scheduling;
- idempotent tenant-owned queue/worker ingestion, sanitized failures, and source limitations;
- bounded on-demand URL Inspection persisted as a source extract with no invented metric points;
- sanitized fixtures and unit/PostgreSQL integration coverage.

### Out / Non-Goals

- OAuth UI, production secret-manager integration, write scopes/methods, sitemap submission, or
  live Google calls in CI;
- continuous query-string warehousing, arbitrary page/query builders, Google News/image/video,
  Event Engine anomaly creation, incident conclusions, alerts, dashboards, or LLM-built queries;
- continuous URL Inspection, live URL testing, ranking/penalty/Discover recovery conclusions;
- GAM C4, cross-source C5 metrics, and Tier C catalog expansion beyond URL Inspection.

## 3. Canonical References

- `AGENTS.md`, `PLANS.md`, and completed `plans/EP-010-ga4-connector-c2.md`;
- `CONNECTORS.md` invariants, GSC sections 37–58, shared sections 87–114, and milestone C3;
- `MVP.md` Search Console sections 35–36 and Phase C;
- `DOMAIN.md` Search Console/Discover semantics and prohibited conclusions;
- `DATA_MODEL.md`, `ARCHITECTURE.md`, `SECURITY.md`, and accepted `DECISIONS.md` ADR-031/036.

Official references checked on 2026-08-14:

- https://developers.google.com/webmaster-tools/v1/searchanalytics/query
- https://developers.google.com/webmaster-tools/v1/how-tos/all-your-data
- https://developers.google.com/webmaster-tools/limits
- https://developers.google.com/webmaster-tools/v1/sites/list
- https://developers.google.com/webmaster-tools/v1/urlInspection.index/inspect

## 4. Current State

PR #11 is merged into `main` at `26ff664`. C1 supplies tenant-owned connections, immutable source
extracts, canonical metric series, append-only points, an execution-time token resolver, and the
PostgreSQL job lifecycle. The C1 repository currently hard-codes `GA4` in registration,
extraction, scheduling, and series keys, so only that narrow boundary must become provider-aware.
No new table is required for GSC aggregate metrics or URL Inspection provenance. Migration 0011
only widens `metric_points.source_time` from 20 to 64 characters so the exact ISO offset-hour
label returned by GSC can be retained without truncation.

## 5. Target Behavior

1. A tenant registers an exact GSC property identifier with only the read-only scope and secret
   reference.
2. Validation confirms the property appears in `sites.list`, rejects unverified access, then runs
   bounded one-day `web` and `discover` probes; zero Discover rows are accepted.
3. Named definitions produce canonical query provenance and paginate only within fixed bounds.
4. Daily rows become source-namespaced `gsc.web.*` or `gsc.discover.*` points; hourly rows carry
   `PRELIMINARY` when at or after `first_incomplete_hour`.
5. Missing rows produce no points. Top-row and row-cap limits remain explicit limitations.
6. The scheduler stores final daily reconciliation separately from fresh operational extracts.
7. URL Inspection is on demand, tenant/property-bound, quota-isolated, and persists sanitized
   status evidence without affecting routine Search Analytics health on quota failure.

## 6. Architecture / Data Flow

```text
GSC_EXTRACT job → tenant connection → runtime token → fixed Search Analytics query
                                                ↓
                         pagination + defensive normalization
                                                ↓
               source_extract → GSC metric series → metric points

on-demand URL Inspection → tenant/property validation → source_extract metadata
```

## 7. Files and Modules Affected

Add `backend/app/connectors/gsc/`, GSC fixtures/unit tests, one GSC integration test, and migration
0011. Modify the shared connector repository/model, general worker, scheduler, README, and this
ExecPlan. No dependency, table, service, or infrastructure category is added.

## 8. Milestones and Acceptance

### M0 — Contract and official behavior

- [x] branch starts from merged PR #11;
- [x] current request/response fields, permission discovery, quotas, pagination, and inspection
  endpoint are verified from official Google documentation.

### M1 — Provider-aware C1 reuse

- [x] registration, ownership, source, series key, and schedulable selection use the validated
  provider instead of a GA4 constant;
- [x] all existing GA4 tests and semantics remain green.

### M2 — GSC adapter and normalization

- [x] exact read-only scope/property identifiers and fixed definitions are enforced;
- [x] Search and Discover metrics remain distinct;
- [x] pagination, top-row/row-cap limitations, incomplete metadata, and Pacific time are retained;
- [x] malformed or missing rows cannot fabricate zero points.

### M3 — Execution and schedules

- [x] validation requires an accessible property and safe probes;
- [x] four-hour fresh and daily seven-day mature runs are deterministic and idempotent;
- [x] worker payloads contain no credential material and retry classified provider errors;
- [x] on-demand URL Inspection is bounded and isolated from routine extraction health.

### M4 — Release gate

- [x] unit/integration tests prove happy paths, counterexamples, tenant isolation, and history;
- [x] full lint, format, typing, backend/frontend, migration, security, and CI gates pass;
- [x] plan and README match the validated implementation.

## 9. Final Acceptance Criteria

- [x] Search and Discover are separate, versioned source metric series.
- [x] `final/all/hourly_all`, incomplete metadata, and Pacific/UTC intervals are correct.
- [x] pagination is bounded and completeness limitations are explicit.
- [x] retry/reconciliation is idempotent and preliminary history is never overwritten.
- [x] connector/token/tenant failures cannot become business zeros or cross-tenant evidence.
- [x] URL Inspection is read-only, on demand, quota-isolated, and provenance-preserving.

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

Happy path: property validation, zero-row Discover probe, final Search/Discover daily extracts,
hourly incomplete extraction, paging, mature reconciliation, and on-demand URL inspection.

Failures/counterexamples: wrong scope, unverified/missing property, malformed property ID or row,
invalid/negative/non-finite metric, pagination beyond bounds, quota/429/5xx, invalid incomplete
metadata, tenant mismatch, token in job payload, and URL outside the property.

Regression: GA4 worker/schedules/series keys remain unchanged; migration round-trip, Browser v1,
frontend, and repository safety remain green.

## 12. Data / Migration Impact

Migration 0011 non-destructively widens `metric_points.source_time` from 20 to 64 characters for
exact offset-hour labels. GSC otherwise uses the C1 tables introduced by migration 0010. Source
extracts and metric points are append-only by logical run; rollback removes only GSC rows after
jobs are stopped. Downgrade to 0010 is safe only after any source labels longer than 20 characters
are removed or archived.

## 13. Security / Privacy Impact

Only the narrow read-only scope is accepted. Tokens remain in worker memory. Routine definitions
exclude the privacy-sensitive query dimension. Property URLs, page URLs, aggregate metrics, and
inspection status are tenant-confidential and never shared across tenants.

## 14. Observability / Failure Handling

Persist connection health, sanitized error code/class, exact definition, data state, pagination,
response aggregation, incomplete-data boundary, limitations, retrieval, and source timezone.
Never persist/log bearer tokens, authorization headers, provider error bodies, or arbitrary
exception text.

## 15. Rollback Strategy

Stop `GSC_EXTRACT` jobs, revert EP-011 commits, and delete/archive only provider `GSC` rows if
policy permits. Migration 0010 and GA4 evidence remain intact. Migration 0011 may stay applied;
if downgraded, first ensure no `source_time` value exceeds 20 characters.

## 16. Known Risks

- GSC returns top rows rather than a complete raw log; limitation metadata must remain visible.
- Fresh/hourly data can change and cannot independently drive critical conclusions.
- Domain and URL-prefix properties have different containment semantics.
- Provider API details and quotas are platform-current and require versioned review.

## 17. Open Decisions

None blocking. Production OAuth/managed secrets remain a later security-reviewed onboarding
slice, as already recorded in EP-010.

## 18. Decision Log

- 2026-08-14: Reuse C1 without a new schema and generalize only provider constants.
- 2026-08-14: Keep routine metrics at date/device and fresh Search at hour/device; page/query
  high-cardinality work remains Tier C.
- 2026-08-14: Treat URL Inspection as on-demand source-extract evidence, not a metric or routine
  scheduler job.
- 2026-08-14: Widen the existing source-time label column instead of truncating GSC's official
  ISO offset-hour key; the migration changes no table ownership or metric semantics.

## 19. Discoveries / Surprises

- Current official Search Analytics documentation was updated 2026-08-11 and explicitly returns
  incomplete boundaries in `America/Los_Angeles`.
- The official maximum remains 25,000 rows per request and 50,000 exposed rows per day per type;
  even complete pagination is not a raw-log completeness guarantee.

## 20. Progress Log

- 2026-08-14: Confirmed PR #11 merged at `26ff664`, created `agent/implement-ep-011`, read the
  connector contracts, and verified current official GSC endpoints, scope, metadata, pagination,
  quotas, permission discovery, and URL Inspection behavior.
- 2026-08-14: Implemented provider-aware C1 persistence, strict GSC definitions/client/parser,
  per-row maturity, scheduler/worker execution, on-demand URL Inspection, migration 0011,
  sanitized fixtures, and unit/PostgreSQL integration coverage. Ruff, mypy strict, 141 unit
  tests, locked sync, frontend lint/typecheck/test/build, secret scan, offline migration DDL, and
  diff checks pass. Docker/PostgreSQL is unavailable locally, so the integration and migration
  round-trip remain the GitHub Actions release gate.
- 2026-08-14: Draft PR #12 CI run 76 passed repository safety, frontend, migration 0011, 141 unit
  tests, 24 PostgreSQL/MinIO/browser/GA4/GSC integration tests, scheduler, and worker. M4 and
  EP-011 are complete.

## 21. Final Outcome / Retrospective

EP-011 completes the GSC C3 aggregate read-only connector. A validated Search Console property can
now produce separate Search and Discover evidence through the existing scheduler, queue, worker,
PostgreSQL, and tenant boundary. Final, fresh daily, and hourly data states retain source-native
incomplete boundaries, Pacific labels, explicit UTC intervals, row-level maturity, pagination,
and completeness warnings. Missing rows remain missing.

The implementation adds no provider write method, broad scope, live test credential, continuous
query warehouse, arbitrary report builder, or causal conclusion. URL Inspection remains bounded,
on demand, and current-view-only; its quota failure cannot disable routine Search Analytics.

## 22. Validation Results

- Ruff format/check — passed (110 backend files);
- mypy strict — passed (99 source/test files);
- backend unit — 141 passed;
- backend integration — 24 passed, including GSC queue/worker/persistence, Search/Discover
  separation, row maturity, URL Inspection, tenant isolation, migration round trip, Chromium,
  PostgreSQL, and MinIO;
- migration 0011 clean upgrade and upgrade/downgrade/upgrade round trip — passed;
- frontend lint/typecheck/Vitest/build — passed;
- locked dependency sync, secret scan, Docker Compose config, and `git diff --check` — passed;
- scheduler and general worker smoke checks — passed;
- Draft PR #12: https://github.com/marian-dotcom/publisher-intelligence/pull/12;
- CI run 76: https://github.com/marian-dotcom/publisher-intelligence/actions/runs/31790267249.

## 23. Next Step

Review and merge Draft PR #12. After merge, begin GAM C4 in a separate ExecPlan, reusing the C1
lifecycle while preserving network timezone, currency, report compatibility, async execution,
pagination, and direct/programmatic composition.
