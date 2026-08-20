# EP-012 — Google Ad Manager Read-Only Connector C4

**Status:** COMPLETE
**Owner:** Codex / Engineering
**Created:** 2026-08-20
**Updated:** 2026-08-20
**Target milestone:** C4 — Google Ad Manager
**MVP scope impact:** NO
**New infrastructure category:** NO

## Progress

- [x] M0 — Confirm merged GSC C3 and current GAM API constraints
- [x] M1 — Add fixed GAM definitions and strict read-only capability validation
- [x] M2 — Add asynchronous run, polling, pagination, and normalization
- [x] M3 — Add scheduler/worker execution and tenant-owned persistence
- [x] M4 — Prove fixtures, failure paths, idempotency, and final validation

## 1. Purpose and User Outcome

After this plan is complete, the platform can validate an already-authorized Ad Manager network
and ingest bounded inventory, demand, and direct/programmatic delivery evidence. Every observation
retains the network timezone, currency, report resource, exact dimension/metric definition,
retrieval state, and maturity. Missing or partial report results never become zero or COMPLETE.

GAM evidence localizes the ad-serving and demand chain. It does not prove publisher business
revenue loss, a vendor cause, harmful direct delivery, CMP failure, or browser failure.

## 2. Scope

### In

- exact `https://www.googleapis.com/auth/admanager.readonly` enforcement;
- network discovery with network code, reporting timezone, and ISO-4217 currency;
- predefined `GAM_INVENTORY_HEALTH_V1`, `GAM_DEMAND_HEALTH_V1`, and
  `GAM_DELIVERY_COMPOSITION_V1` definitions;
- validation of tenant-configured, reusable REST report resources against exact dimensions,
  metrics, report type, publisher timezone, currency, and unexpanded compatibility;
- asynchronous report execution, bounded polling, full result pagination up to 10,000 rows/page,
  total-row verification, and explicit partial/failure handling;
- strict parsing of integer/double/string report values and currency-aware eCPM semantics;
- network-local hourly buckets converted to explicit UTC intervals, including DST behavior;
- operational two-hour scheduling and nightly/weekly reconciliation through prevalidated report
  profiles;
- idempotent tenant-owned queue/worker persistence, sanitized failures, and bounded backoff;
- sanitized fixtures and unit/PostgreSQL integration coverage.

### Out / Non-Goals

- OAuth UI, managed production secret integration, report creation/patching, any GAM write scope or
  write method, live Google calls in CI, arbitrary query/report builders, full campaign/order
  warehouse, impression/bidstream logs, financial accounting, Event Engine conclusions, alerts,
  dashboards, C5 cross-source ratios, or C6 incident drill-down;
- expanded compatibility, Ads Traffic Navigator as a required baseline, pricing/restriction
  diagnostics, currency conversion, or raw total revenue health alerts.

## 3. Canonical References

- `AGENTS.md`, `PLANS.md`, and completed `plans/EP-011-gsc-connector-c3.md`;
- `CONNECTORS.md` sections 60–86, 87–115, and milestone C4;
- `MVP.md` sections 38–42 and Phase C;
- `DOMAIN.md` sections 29–37;
- `DATA_MODEL.md`, `ARCHITECTURE.md`, `SECURITY.md`, and accepted `DECISIONS.md` ADR-038/039.

Official references checked on 2026-08-20:

- https://developers.google.com/ad-manager/api/beta/authentication
- https://developers.google.com/ad-manager/api/beta/reference/rest/v1/networks
- https://developers.google.com/ad-manager/api/beta/reference/rest/v1/networks.reports
- https://developers.google.com/ad-manager/api/beta/reference/rest/v1/networks.reports/run
- https://developers.google.com/ad-manager/api/beta/reference/rest/v1/networks.reports.results/fetchRows

## 4. Current State

PR #12 is merged into `main` at `18fa145`. C1–C3 supply tenant-owned connections, immutable
source extracts, canonical metric series, append-only points, execution-time token resolution,
and PostgreSQL-backed jobs. GA4 and GSC are provider adapters behind this shared persistence
boundary. No GAM adapter or GAM worker/scheduler path exists. Existing schema can retain network,
currency, report resource, operation, pagination, and limitations in connection/extract metadata;
no table or migration is required.

The current REST API permits list/get/run/fetch with the read-only scope, but report creation
requires the broader write scope. C4 therefore validates and runs reusable reports that a network
administrator created beforehand; the connector never creates or mutates a report.

## 5. Target Behavior

1. A tenant registers a numeric GAM network code, three fixed cube bindings, and only the
   read-only scope.
2. Validation discovers the exact accessible network and verifies timezone/currency.
3. Each bound report is read, compared against its versioned definition, run asynchronously,
   polled with bounded backoff, and fetched through every page.
4. Rows become source-namespaced GAM points with network-local source time and explicit UTC
   intervals. Money/eCPM values retain currency in the series dimensions and response metadata.
5. Empty reports remain empty. Malformed rows, unexpected definitions, failed operations,
   truncated pagination, and unsupported cubes are explicit connector limitations/failures.
6. The scheduler enqueues only validated cube/profile bindings and never includes credentials.

## 6. Architecture / Data Flow

```text
GAM_EXTRACT job → tenant connection → runtime token → validated report resource
                                                 ↓
                              run → operation poll → all result pages
                                                 ↓
                    source_extract → GAM metric series → metric points
```

## 7. Files and Modules Affected

Add `backend/app/connectors/gam/`, GAM fixtures/unit tests, and one GAM integration test. Modify
the shared registration boundary, general worker, scheduler, README, and this ExecPlan. No new
dependency, table, migration, service, or infrastructure category is added.

## 8. Milestones and Acceptance

### M0 — Contract and official behavior

- [x] branch starts from merged PR #12;
- [x] current scope, network fields, report resources, async execution, polling, pagination, and
  report-creation scope are verified from official Google documentation.

### M1 — Definitions and capability probe

- [x] only the exact read-only scope and numeric network code are accepted;
- [x] all three required cubes have versioned, predefined dimensions and metrics;
- [x] configured report resources belong to the network and match the fixed definitions;
- [x] unsupported or expanded-compatible reports remain explicit capability failures.

### M2 — Async execution and normalization

- [x] report lifecycle separates requested/running/fetching/normalizing/complete metadata;
- [x] every result page is fetched and total row count is verified before COMPLETE;
- [x] rows, network-local hours, integer/double values, currency, and maturity are strict;
- [x] missing rows do not fabricate zero points and partial fetches do not become COMPLETE.

### M3 — Worker and schedules

- [x] two-hour operational and bounded reconciliation jobs are deterministic/idempotent;
- [x] job payloads contain report profile IDs but no credential material;
- [x] quota/provider failures retry with bounded exponential backoff;
- [x] tenant/network/report ownership is revalidated before persistence.

### M4 — Release gate

- [x] unit/integration tests prove happy paths, counterexamples, pagination, and tenant isolation;
- [x] full lint, format, typing, backend/frontend, migration, security, and CI gates pass;
- [x] plan and README match the validated implementation.

## 9. Final Acceptance Criteria

- [x] all production access is strictly read-only and no report mutation method exists;
- [x] every required cube is capability-validated per network before scheduling;
- [x] async completion and all result pages are required for COMPLETE;
- [x] timezone, currency, exact report resource/definition, and maturity are preserved;
- [x] direct/programmatic composition is factual and not labeled good/bad;
- [x] connector/token/tenant failures cannot become business zeros or cross-tenant evidence.

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

Happy path: network discovery, three matching reusable reports, asynchronous operation polling,
multi-page results, empty rows, network-local time conversion, currency-aware eCPM, scheduling,
queue/worker persistence, and idempotent retry.

Failures/counterexamples: wrong scope/network, report outside network, missing cube, changed
dimension/metric order, expanded compatibility, invalid currency/timezone, malformed value/hour,
failed/stuck operation, repeated/invalid page token, row-count mismatch, quota/429/5xx, tenant
mismatch, and token-like fields in job payloads.

Regression: GA4/GSC worker, schedules, series keys, Browser v1, frontend, migration round-trip,
and repository safety remain green.

## 12. Data / Migration Impact

No migration. C4 reuses C1 tables. Currency is part of GAM series dimensions and source-extract
metadata so differently denominated values never share a series. Report resource/definition,
operation/result IDs, total rows, pages, runtime, and lifecycle remain extract provenance.

## 13. Security / Privacy Impact

Only the narrow read-only scope is accepted. Tokens remain in worker memory. Report IDs and
aggregate metrics are tenant-confidential; commercial order/advertiser names are not collected by
the routine cubes. No broader data category, retention policy, or cross-tenant access is added.

## 14. Observability / Failure Handling

Persist connection health, cube capability, sanitized error code/class, report resource,
definition fingerprint, lifecycle, pagination, network time/currency, retrieval, maturity, and
limitations. Never persist/log bearer tokens, authorization headers, provider error bodies, or
arbitrary exception text. Poll initially at five seconds in production with bounded exponential
backoff; tests inject a no-wait sleeper.

## 15. Rollback Strategy

Stop `GAM_EXTRACT` jobs, revert EP-012 changes, and delete/archive only provider `GAM` rows if
policy permits. Existing Browser, GA4, and GSC evidence and migration 0011 remain intact.

## 16. Known Risks

- REST report creation requires the broad scope, so strict read-only onboarding depends on
  preconfigured reusable report resources.
- Dimension/metric compatibility varies by network and remains a live onboarding gate.
- Every routine extract is conservatively PRELIMINARY because a rolling result contains recent
  data; row-level maturity advances older dates to MATURE during later reconciliation.
- MONEY values are network/report currency, not publisher invoicing truth.

## 17. Open Decisions

None blocking. A future onboarding UI may guide a network administrator through report creation,
but it must remain outside the connector credential and C4 runtime.

## 18. Decision Log

- 2026-08-20: Use REST v1 reusable reports only; report create/patch is excluded because those
  methods require the broader write scope.
- 2026-08-20: Reuse C1 storage and place currency in GAM series identity/provenance instead of
  introducing a financial ledger or FX model.
- 2026-08-20: Keep expanded compatibility off because it can collapse reservation semantics.
- 2026-08-20: Mark rolling extracts PRELIMINARY at extract level and retain row-level maturity so
  one recent day cannot overstate the maturity of the complete result.

## 19. Discoveries / Surprises

- Google added the narrow read-only scope in May 2026; current list/get/run/fetch methods accept
  it, while report creation still requires the broad `admanager` scope.
- REST report result pages default to 1,000 and cap at 10,000 rows; the first page alone exposes
  total row count and fixed date ranges.

## 20. Progress Log

- 2026-08-20: Confirmed PR #12 merged at `18fa145`, created `agent/implement-ep-012`, read the
  connector/domain/security contracts, and verified current official GAM REST scope, network,
  definition, async operation, result pagination, timezone, and currency behavior.
- 2026-08-20: Implemented the strict six-report capability gate, three versioned C4 cubes,
  asynchronous polling/full pagination, timezone/currency-aware normalization, row maturity,
  deterministic schedules, GAM worker path, sanitized fixtures, and PostgreSQL integration test.
- 2026-08-20: Locked sync, Ruff, mypy strict, 158 unit tests, frontend lint/typecheck/test/build,
  secret scan, offline migration DDL, integration collection, and diff checks pass. Docker is not
  installed locally, so the PostgreSQL execution and CI release gate remain pending.
- 2026-08-20: Draft PR #13 CI run 81 passed repository safety, frontend, migration 0011, 158 unit
  tests, 25 PostgreSQL/MinIO/browser/GA4/GSC/GAM integration tests, scheduler, and worker. M4 and
  EP-012 are complete.

## 21. Final Outcome / Retrospective

EP-012 completes the GAM C4 aggregate read-only connector. The connector can validate and run
three factual aggregate evidence cubes without report mutation, preserve complete asynchronous
provenance, and prevent empty/partial responses from becoming business zeros. Network timezone,
currency, row-level maturity, report definition identity, and complete pagination remain attached
to immutable source evidence without introducing provider writes or causal conclusions.

## 22. Validation Results

- Ruff format/check — passed (123 backend files);
- mypy strict — passed (112 source/test files);
- backend unit — 158 passed, with one dependency deprecation warning;
- backend integration — 25 passed, including GAM queue/worker/persistence, reconciliation,
  idempotency, and tenant isolation;
- frontend ESLint/typecheck/Vitest/production build — passed;
- locked dependency sync, secret scan, offline migration DDL, and `git diff --check` — passed;
- Docker Compose config, scheduler, worker, migration, and repository safety — passed in CI;
- Draft PR #13: https://github.com/marian-dotcom/publisher-intelligence/pull/13;
- final CI run 81: https://github.com/marian-dotcom/publisher-intelligence/actions/runs/32399091458.

## 23. Next Step

Review and merge Draft PR #13. After merge, begin C5 cross-source derivation in a separate
ExecPlan, reusing Browser, GA4, GSC, and GAM evidence without promoting raw observations directly
to causal conclusions.
