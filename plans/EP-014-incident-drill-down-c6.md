# EP-014 — Validated Incident Drill-Down C6

**Status:** COMPLETE
**Owner:** Codex / Engineering
**Created:** 2026-08-20
**Updated:** 2026-08-20
**Target milestone:** C6 — Incident drill-down
**MVP scope impact:** NO
**New infrastructure category:** NO

## Progress

- [x] M0 — Confirm merged C5 and current provider/query constraints
- [x] M1 — Add the versioned Tier C semantic catalog and strict request validation
- [x] M2 — Add per-connection capability validation and fixed provider execution
- [x] M3 — Add bounded tenant-owned job planning and worker execution
- [x] M4 — Prove counterexamples, regressions, and final validation

## 1. Purpose and User Outcome

After this plan is complete, an active investigation can ask for one of the named C6 breakdowns
and receive a bounded, immutable connector extract. The application maps the semantic request to
an exact versioned GA4, GSC, or GAM definition; neither a user nor an LLM can supply dimensions,
metrics, report JSON, or provider endpoints.

Drill-down results are evidence with source limitations. They do not create an incident, identify
a cause, treat omitted rows as zero, or continue running after the explicit request.

## 2. Scope

### In

- the twelve GA4/GSC/GAM semantic requests listed by `CONNECTORS.md` section 103;
- exact versioned provider dimensions, metrics, data state/report type, and optional page filter;
- per-connection `validatedDrilldowns` capability state;
- optional preconfigured GAM report bindings, preserving strict read-only operation;
- explicit GA4/GSC windows of at most seven inclusive days and GAM `TODAY`/`LAST_7_DAYS`
  profiles;
- a maximum of four distinct drill-down jobs per investigation and eight per connection/UTC day;
- tenant/site/connection ownership, deterministic idempotency, queue/worker execution, immutable
  source-extract provenance, sanitized failures, and unit/PostgreSQL integration coverage.

### Out / Non-Goals

- Incident Engine tables/reasoning, incident lifecycle/UI, automatic anomaly triggers, scheduled
  Tier C queries, arbitrary filters or dimensions, arbitrary LLM/API requests, GAM report creation,
  provider writes, unbounded query expansion, causal conclusions, or long-lived query warehousing.

## 3. Canonical References

- `AGENTS.md`, `PLANS.md`, and completed `plans/EP-013-cross-source-metrics-c5.md`;
- `CONNECTORS.md` sections 11–12, 26–31, 45–47, 70–74, 101–104, and milestone C6;
- `ARCHITECTURE.md` sections 109, 113–115;
- `DATA_MODEL.md` sections 46–48 and 67–72;
- `MVP.md` sections 64–66, 75, and Phase C;
- `SECURITY.md` sections 96, 106, and 121–124.

Official references checked on 2026-08-20:

- https://developers.google.com/analytics/devguides/reporting/data/v1/rest/v1beta/properties/runReport
- https://developers.google.com/analytics/devguides/reporting/data/v1/rest/v1beta/FilterExpression
- https://developers.google.com/webmaster-tools/v1/searchanalytics/query
- https://developers.google.com/webmaster-tools/v1/how-tos/all-your-data
- https://developers.google.com/ad-manager/api/beta/reference/rest/v1/networks.reports
- https://developers.google.com/ad-manager/api/beta/reports

## 4. Current State

PR #14 is merged into `main` at `43d9556`. C1–C5 provide tenant-owned read-only connections,
versioned routine definitions, immutable extracts, normalized metric points, PostgreSQL jobs, and
cross-source derived evidence. GA4/GSC accept only routine definitions. GAM validates only six
preconfigured routine report/profile bindings. There is no Tier C planner or allowlist.

Incident tables are canonical but not implemented yet. C6 therefore carries an opaque UUID
`investigation_id` solely as a budget/idempotency/provenance correlation key; it grants no access
to incident data and will become a foreign key when the incident lifecycle milestone lands.

## 5. Target Behavior

1. A trusted application call names one catalog code, connection, investigation, and bounded
   window/profile; only the page-specific GSC definition accepts one exact page URL parameter.
2. The planner validates the catalog version, provider, ownership, active connection capability,
   parameter schema, window, per-investigation budget, and daily connection budget atomically.
3. It enqueues one idempotent `CONNECTOR_DRILLDOWN` job containing no token or arbitrary query JSON.
4. The worker resolves the catalog entry again and executes only its fixed provider definition.
5. Query provenance records tier, catalog version, investigation ID, exact fixed definition,
   bounded scope, and provider limitation metadata in the immutable source extract.

## 6. Architecture / Data Flow

```text
semantic request → Tier C catalog + capability + budget gate → CONNECTOR_DRILLDOWN job
                                                               ↓
             fixed GA4/GSC query or prevalidated GAM report → source_extract + metric points
```

## 7. Files and Modules Affected

Add `backend/app/connectors/drilldown/`, provider Tier C definition modules, unit tests, one
integration test, and EP-014. Modify the three provider clients/services/validation snapshots,
GAM optional binding handling, worker, process/migration expectations if needed, and README. No
new dependency, database table, external service, secret, or scheduler path is introduced.

## 8. Milestones and Acceptance

### M0 — Contract and current APIs

- [x] branch content matches merged PR #14;
- [x] fixed-filter request fields, GSC row limits, and GAM report compatibility are rechecked.

### M1 — Catalog and validation

- [x] all twelve semantic codes resolve to immutable versioned provider definitions;
- [x] unknown fields, wrong provider, oversized/future windows, invalid page URLs/profiles, and
  stale catalog versions are rejected before enqueue;
- [x] no API endpoint, dimension, metric, filter operator, or JSON fragment is caller-controlled.

### M2 — Capability and execution

- [x] GA4 records only metadata-supported Tier C definitions;
- [x] GSC records the fixed Search/Discover definitions proven by its connection probes;
- [x] GAM runs only optional report/profile bindings whose exact definition fingerprint passed;
- [x] each extract preserves Tier C correlation, fixed query definition, limitations, and maturity.

### M3 — Job and budget boundary

- [x] request planning is tenant/site/connection scoped and idempotent;
- [x] four jobs/investigation and eight jobs/connection/UTC-day are hard server gates;
- [x] Tier C is never scheduled and worker payloads contain no credentials or arbitrary query;
- [x] retries retain the same logical extract and use sanitized provider failure handling.

### M4 — Release gate

- [x] unit/integration tests prove catalog, budgets, tenancy, execution, and counterexamples;
- [x] lint, format, typing, migrations, backend/frontend, security, and CI gates pass;
- [x] plan and README match the validated implementation.

## 9. Final Acceptance Criteria

- [x] every incident query originates from a current allowlisted catalog entry;
- [x] only definitions validated for the exact connection/profile can run;
- [x] windows, pagination/rows, daily cost, and investigation fan-out are bounded;
- [x] GSC query strings remain exact-page, on-demand, tenant-confidential evidence;
- [x] omitted/high-cardinality/thresholded rows remain limitations rather than zeros;
- [x] no LLM-generated provider request or automatic causal conclusion exists.

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

Happy path: all catalog entries, GA4 metadata capability subset, GSC page/device and exact-page
top-query filter, optional GAM binding validation, deterministic job/extract reuse, point
persistence, and tenant isolation.

Counterexamples: unknown code/version/parameter, arbitrary nested JSON, provider mismatch,
unvalidated definition/profile, wrong site/tenant, invalid/outside-property URL, future or >7-day
window, invalid GAM profile, investigation/daily budget exhaustion, malformed job, changed GAM
report fingerprint, quota failure, missing rows, and provider limitations.

Regression: routine connector scheduling/execution, Browser, cross-source metrics, migrations,
frontend, and repository safety.

## 12. Data / Migration Impact

No migration. Job rows are the bounded request lifecycle and `source_extracts` remain the durable
query/evidence provenance. Capability and GAM binding state fit existing connection JSON metadata.
No incident table is partially introduced.

## 13. Security / Privacy Impact

Only exact read-only scopes remain accepted. Runtime tokens never enter jobs or logs. GSC query
rows are collected only for an exact page and a bounded window, remain tenant-owned, and inherit
the documented 90-day raw-medium retention policy. The opaque investigation ID is correlation,
not authorization; tenant/site/connection ownership is independently verified.

## 14. Observability / Failure Handling

Persist catalog/definition version, semantic code, investigation ID, window/profile, cost units,
provider query shape, row/quota/threshold limitations, and sanitized error code/class. Budget and
validation rejections occur before token resolution. Tier C quota failures do not fabricate metric
zeros or automatically establish publisher incidents/causes.

## 15. Rollback Strategy

Stop accepting and processing `CONNECTOR_DRILLDOWN`, revert EP-014 code, and optionally remove
only unreferenced Tier C job/extract/metric rows under retention policy. Routine C1–C5 evidence and
schema remain unchanged.

## 16. Known Risks

- Existing connections require revalidation before new Tier C capabilities are usable.
- GAM remains dependent on administrator-created reports because creation needs broader scope.
- GSC page/query reports expose top rows and may omit privacy-sensitive/low-volume data.
- GA4 page/landing-page cardinality may produce `(other)` and thresholding limitations.
- The investigation correlation is not yet a foreign key; C6 never uses it for authorization.

## 17. Open Decisions

None blocking. GAM administrators may bind only the profiles/definitions they need; absent or
incompatible optional bindings remain unavailable rather than weakening the read-only boundary.

## 18. Decision Log

- 2026-08-20: Reuse jobs and immutable source extracts instead of creating premature incident or
  drill-down tables.
- 2026-08-20: Enforce budgets during the same locked connection transaction as job insertion.
- 2026-08-20: Permit one dynamic value only: an exact GSC page URL in a fixed equality filter.
- 2026-08-20: Keep GAM report creation external and require exact report/profile fingerprints.

## 19. Discoveries / Surprises

- Current GAM REST reporting supports Ads Traffic Navigator definitions but still requires live
  dimension/metric compatibility validation for the selected network.
- Current GA4 `runReport` and GSC Search Analytics both support fixed dimension filters, but their
  omission/cardinality semantics require retained limitations.

## 20. Progress Log

- 2026-08-20: Confirmed PR #14 merged at `43d9556`, created `agent/implement-ep-014`, read the C6,
  security, architecture, and data contracts, and verified current official provider APIs.
- 2026-08-20: Implemented the twelve-entry catalog, version-bound connection capabilities,
  explicit-date/profile gates, exact GSC page filter, optional fingerprinted GAM reports, atomic
  idempotent budgeted planning, general-worker dispatch, provenance, and regression coverage.
- 2026-08-20: Ruff, mypy, 177 unit tests, frontend lint/typecheck/test/build, secret scan,
  integration collection, and diff checks pass. Local PostgreSQL is unavailable, so the new budget
  integration test and complete release gate remain pending in GitHub Actions.
- 2026-08-20: Draft PR #15 CI run 91 passed repository safety, frontend, Alembic, 177 unit tests,
  27 PostgreSQL/MinIO/browser/connector/C5/C6 integration tests, scheduler, and worker. M4 and EP-014
  are complete.

## 21. Final Outcome / Retrospective

EP-014 completes C6 with a fixed, versioned twelve-entry Tier C catalog and bounded on-demand
execution for GA4, GSC, and GAM. Every request is capability-, ownership-, budget-, and
definition-validated before enqueue; workers execute only approved provider shapes and retain
immutable provenance and source limitations. No arbitrary or LLM-generated provider query,
scheduled Tier C collection, provider write, incident conclusion, or causal claim was introduced.

## 22. Validation Results

- Ruff format/check — passed (148 backend files);
- mypy strict — passed (136 source/test files);
- backend unit — 177 passed, with one dependency deprecation warning;
- frontend ESLint/typecheck/Vitest/production build — passed;
- locked dependency sync, secret scan, integration collection (27 tests), and `git diff --check`
  — passed;
- PostgreSQL/MinIO/browser/connector/C5/C6 integration — 27 passed in CI, including the new
  drill-down budget, idempotency, and tenant-isolation coverage;
- Alembic upgrade, scheduler, worker, Docker Compose config, and repository safety — passed in CI;
- Draft PR #15: https://github.com/marian-dotcom/publisher-intelligence/pull/15;
- final CI run 91: https://github.com/marian-dotcom/publisher-intelligence/actions/runs/32409797290.
