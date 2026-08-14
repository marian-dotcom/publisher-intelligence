# EP-010 — GA4 Read-Only Connector C1/C2

**Status:** COMPLETE
**Owner:** Codex / Engineering
**Created:** 2026-08-14
**Updated:** 2026-08-14
**Target milestone:** C1/C2 — Connection framework and GA4
**MVP scope impact:** NO
**New infrastructure category:** NO

## Progress

- [x] M0 — Verify merged Browser v1 and close the GA4 contract against current official docs
- [x] M1 — Add connection, immutable extract, series, and point persistence
- [x] M2 — Add the strict read-only GA4 provider adapter and versioned report definitions
- [x] M3 — Add execution, reconciliation, health, and bounded retry behavior
- [x] M4 — Prove fixtures, migrations, tenancy, documentation, and final CI

## 1. Purpose and User Outcome

After this plan is complete, the platform can validate an already-authorized GA4 property and
ingest a small, predefined set of aggregate traffic and behavior reports without requiring live
credentials in tests. Operators can trace every metric point back to the exact property, query,
source-local period, retrieval, freshness status, connector version, and response limitations.

This is measurement evidence, not physical traffic truth or an incident conclusion. A connector
failure, missing row, thresholded response, or preliminary period must never become a zero-value
publisher event.

## 2. Scope

### In

- C1 database records for tenant-owned data connections, immutable source extracts, metric series,
  and append-only metric points;
- an execution-time secret resolver contract whose durable input is only a secret reference;
- enforcement of the single GA4 MVP scope
  `https://www.googleapis.com/auth/analytics.readonly`;
- Google Analytics Data API v1beta metadata and `runReport` transport with bounded timeouts and no
  token/error-body logging;
- property metadata validation and a one-day, low-cardinality connection probe;
- predefined `GA4_TRAFFIC_HOURLY_V1` and `GA4_BEHAVIOR_DAILY_V1` report definitions;
- strict response/header/row parsing, property timezone conversion, source-native names, canonical
  series keys, and units;
- preservation of `dataLossFromOtherRow`, thresholding, sampling, schema restrictions, row count,
  and property quota metadata where supplied;
- preliminary operational extracts, mature reconciliation/backfill extracts, immutable history,
  idempotent retry keys, connection health updates, and classified provider errors;
- sanitized complete/thresholded/quota fixtures plus unit and PostgreSQL integration coverage.

### Out / Non-Goals

- OAuth consent/callback UI, Google client registration, a production secret-manager provider, or
  accepting credentials in source, CLI arguments, job payloads, fixtures, logs, or test output;
- arbitrary report builders, realtime/funnel/audience APIs, user-level exports, ecommerce defaults,
  event anomaly creation, incident conclusions, dashboards, alerts, or LLM-selected API queries;
- page/landing-page high-cardinality reports, custom publisher dimension mapping, GSC, GAM, and
  cross-source derived metrics;
- service accounts, domain-wide delegation, write scopes, write methods, or production deployment.

## 3. Canonical References

Read and preserve:

- `AGENTS.md`, `MVP.md` sections 32–34 and 100–103;
- `CONNECTORS.md` invariants, GA4 sections 16–36, shared lifecycle/error sections 87–110,
  `CONN-GA4-001`–`007`, and milestones C1/C2;
- `DOMAIN.md` GA4 measurement and decomposition semantics;
- `DATA_MODEL.md` sections 45–51, 85, 111, 120, and tenant/query invariants;
- `ARCHITECTURE.md` sections 32–37, failure isolation, jobs, transactions, and connector fixtures;
- `SECURITY.md` sections 26–37 and 177;
- accepted `DECISIONS.md` ADR-031–035 and ADR-091;
- `PLANS.md` connector planning and validation contract;
- completed `plans/EP-009-synthetic-performance-b8.md`.

Current official anchors checked on 2026-08-14:

- `properties.runReport` is POST
  `https://analyticsdata.googleapis.com/v1beta/properties/{id}:runReport`;
- `properties.getMetadata` is GET
  `https://analyticsdata.googleapis.com/v1beta/properties/{id}/metadata`;
- both accept the narrow read-only Analytics OAuth scope;
- `returnPropertyQuota=true` requests quota state; response metadata carries property timezone and
  thresholding, while the report response can carry other-row data loss;
- `dateHour`, `deviceCategory`, `sessionDefaultChannelGroup`, `activeUsers`, `sessions`,
  `screenPageViews`, and `engagedSessions` remain current Data API fields.

Official references:

- https://developers.google.com/analytics/devguides/reporting/data/v1/rest/v1beta/properties/runReport
- https://developers.google.com/analytics/devguides/reporting/data/v1/rest/v1beta/properties/getMetadata
- https://developers.google.com/analytics/devguides/reporting/data/v1/rest/v1beta/ResponseMetaData
- https://developers.google.com/analytics/devguides/reporting/data/v1/rest/v1beta/PropertyQuota
- https://developers.google.com/analytics/devguides/reporting/data/v1/api-schema
- https://developers.google.com/analytics/devguides/reporting/data/v1/quotas

## 4. Current State

PR #10 is merged into `main` at `c74ade6`. Browser v1 B1–B8 is complete. The repository has a
PostgreSQL job queue, scheduler, worker, tenant/site ownership, migrations through 0009, and
integration infrastructure, but it has no connector package, connection/source-extract/metric
tables, token-resolution contract, provider transport, normalized business metrics, or connector
job handler.

## 5. Target Behavior

Given a tenant-owned site and GA4 connection containing only a property ID, the exact read-only
scope, and a secret reference, the connector will:

1. resolve a short-lived access token in worker memory through an injected secret resolver;
2. fetch property metadata and reject missing required dimensions or metrics;
3. execute only a named version-controlled report definition over a bounded period;
4. treat all provider JSON as untrusted and require exact header/row cardinality;
5. convert GA4 source-local date/hour or date buckets to explicit UTC intervals while preserving
   the IANA source timezone;
6. insert an immutable source extract and append points linked to canonical metric series;
7. retain preliminary and later mature extracts separately;
8. update connection health separately from publisher metrics and classify retryable quota/5xx
   failures without storing provider bodies or credentials.

An omitted row creates no point. Thresholding or `(other)` aggregation adds a quality limitation;
it never creates fabricated zeros.

## 6. Architecture / Data Flow

```text
GA4_EXTRACT job (connection + definition + period + run key)
                              ↓
Tenant-bound connection + execution-time secret resolver
                              ↓
Metadata/probe or predefined Data API v1beta runReport
                              ↓
Strict response parser + source-timezone interval normalization
                              ↓
Immutable source_extract + canonical series + append-only points
                              ↓
Connection health / retry classification (separate from publisher health)
```

The provider client stays behind connector contracts. Tests inject deterministic transports and
secret resolvers; live Google access is neither needed nor permitted in CI.

## 7. Files and Modules Affected

Expected additions:

```text
backend/app/connectors/core/contracts.py
backend/app/connectors/core/persistence.py
backend/app/connectors/ga4/client.py
backend/app/connectors/ga4/definitions.py
backend/app/connectors/ga4/normalization.py
backend/app/connectors/ga4/service.py
backend/app/connectors/models.py
backend/migrations/versions/0010_ga4_connector_c2.py
backend/tests/fixtures/connectors/ga4/*.json
backend/tests/unit/connectors/ga4/*.py
backend/tests/integration/test_ga4_connector.py
```

Expected modifications:

```text
backend/app/worker.py
backend/migrations/env.py
backend/tests/integration/test_migrations.py
backend/pyproject.toml
backend/uv.lock
README.md
```

No new service, database, queue, secret value, Google credential, or infrastructure category is
introduced.

## 8. Milestones and Acceptance

### M0 — Contract and current provider validation

- [x] branch starts from exact merged Browser v1 `origin/main`;
- [x] official current endpoints, fields, metadata, quotas, and scope are verified;
- [x] GA4 evidence remains source-namespaced measurement telemetry;
- [x] live credentials and OAuth UI are not required for deterministic implementation/tests.

### M1 — C1 persistence

- [x] schema and models implement tenant-owned connections, immutable extracts, canonical series,
  and provenance-linked points;
- [x] DB rows store a secret reference and granted scopes but never tokens;
- [x] unique constraints distinguish retry idempotency from later reconciliation;
- [x] tenant mismatch and cross-tenant reads/writes fail closed.

### M2 — GA4 adapter and normalization

- [x] only metadata GET and report POST are exposed by the MVP client;
- [x] exact read-only scope and numeric property resource are validated;
- [x] metadata discovery validates required fields before a small probe succeeds;
- [x] hourly traffic and daily behavior definitions are frozen and canonical;
- [x] headers, values, timezone, response limitations, sampling, restrictions, and quota are parsed
  defensively;
- [x] missing rows remain missing and ratios/counts preserve source semantics and units.

### M3 — Execution, reconciliation, health, and retry

- [x] a tenant-bound job payload contains IDs/period/run key only, never a token;
- [x] operational extraction is preliminary and later reconciliation is mature and append-only;
- [x] retry of the same logical run cannot duplicate an extract/points;
- [x] 429/quota and 5xx errors are bounded retryable failures; auth/permission/schema failures are
  terminal until configuration changes;
- [x] connection status/health changes cannot create business metric zeros or anomaly events.

### M4 — Evidence and release gate

- [x] sanitized fixtures cover complete, thresholded/other-row, and malformed responses; provider
  tests cover classified quota failures;
- [x] tests cover contract, parsing, connection validation, idempotency, reconciliation, migration,
  and tenant isolation;
- [x] README explains the connector boundary and no-credential fixture workflow;
- [x] locked install, lint, format, type checking, unit, integration, frontend, secret scan,
  Compose config, and `git diff --check` pass.

## 9. Final Acceptance Criteria

- [x] C1 persistence and C2 GA4 reports are end-to-end through the existing job queue/worker.
- [x] Every point traces to an immutable extract and exact canonical query definition.
- [x] Only aggregate read-only GA4 data is accepted; no token reaches durable evidence/logs/jobs.
- [x] Property timezone, freshness, source fields, connector/semantics versions, and quality limits
  are retained.
- [x] Preliminary and mature extracts coexist; missing/failed/thresholded data is never silently
  zero.
- [x] All deterministic and CI checks pass.

## 10. Final Validation

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

- complete metadata and probe validate a connection;
- hourly and daily fixtures normalize into explicit UTC intervals and namespaced series;
- a later mature reconciliation preserves the earlier preliminary extract.

Failures/counterexamples:

- wrong/broader/missing scope; malformed property resource; inaccessible property;
- required metadata field absent or response header order/cardinality mismatch;
- invalid date/hour, timezone, non-finite/negative count, malformed ratio, or row value count;
- thresholding/other-row/sampling produces limitations but no fabricated rows;
- quota/429/5xx is retryable; permission/schema failure is terminal and token/provider body is
  absent from errors;
- duplicate scheduled run is idempotent; a distinct reconciliation run is append-only;
- connection/site/tenant mismatch cannot read or write another tenant's data.

Regression:

- browser workers and schedules remain isolated;
- general bootstrap job still completes;
- migration downgrade/upgrade round trip remains valid;
- frontend and existing 63 unit tests remain green.

## 12. Data / Migration Impact

Migration 0010 creates `data_connections`, `source_extracts`, `metric_series`, and `metric_points`.
Normalized points and extract metadata are long-lived. Raw connector payloads are not persisted in
this milestone. Downgrade drops only these new connector tables after `metric_points` first.

## 13. Security / Privacy Impact

Security impact is constrained and positive: the connector enforces the narrow read-only scope,
keeps tokens behind an execution-time protocol, persists only a secret reference, rejects token
material in jobs, and stores aggregate reports only. The concrete production secret manager and
OAuth web flow require a later security-reviewed onboarding slice.

## 14. Observability / Failure Handling

Connection status, last attempt/success/error, sanitized error class/code, extract status,
freshness, response limitations, sampling, row count, and quota status are observable. Provider
response bodies, bearer tokens, refresh tokens, authorization headers, and arbitrary exception
text are not logged or persisted.

## 15. Rollback Strategy

Revert the implementation and downgrade migration 0010. The downgrade removes only connector
records and normalized GA4 metrics; Browser v1 evidence and jobs remain intact. In production,
stop GA4 jobs before downgrade and retain/export connector evidence according to policy.

## 16. Known Risks

- GA4 custom/property schemas differ; core fields are validated at connection time.
- Source-local hourly labels around DST can be ambiguous; the source label and timezone remain in
  provenance and the normalizer applies one documented fold consistently.
- API schemas/quotas change; named definitions and connector versions prevent silent semantic
  mutation.
- This slice accepts already-resolved access tokens through an interface but does not yet prove
  production token refresh or OAuth callback behavior.

## 17. Open Decisions

None blocking. A future ExecPlan must select the production secret manager and implement the web
OAuth lifecycle before pilot credentials are connected.

## 18. Decision Log

- 2026-08-14: Implement C1 persistence with C2 because GA4 points cannot satisfy provenance,
  missingness, freshness, tenancy, or reconciliation invariants without the shared model.
- 2026-08-14: Use Data API v1beta REST behind an injectable transport; this keeps the adapter small,
  testable, and aligned with official methods without introducing the broad generated SDK.
- 2026-08-14: Add `httpx` as a runtime dependency for bounded async HTTPS; tests never call Google.
- 2026-08-14: Freeze traffic hourly and behavior daily cubes; page/custom-dimension reports remain
  outside this first connector slice.

## 19. Discoveries / Surprises

- The repository roadmap numbering moved as Browser B5–B8 received dedicated plans; the next free
  identifier is EP-010 even though the original illustrative sequence used a different number.
- Initial CI run 67 exposed test-fixture insert ordering: the ORM models intentionally have no
  relationship graph, so adding tenant, publisher, and site in one flush did not guarantee the FK
  order. The fixture now flushes each ownership level explicitly; production code was unaffected.
- CI run 69 then reached the repository and exposed SQLAlchemy's reserved declarative `metadata`
  name in an ORM insert keyword. The column was already safely mapped as `connection_metadata`;
  the insert now uses that mapped attribute and a compile-time regression test protects it.

## 20. Progress Log

- 2026-08-14: Confirmed PR #10 merged at `c74ade6`, created `agent/implement-ep-010`, read the
  connector/security/data/architecture contracts, and validated current official GA4 references.
- 2026-08-14: Added migration 0010, C1 repositories, strict GA4 metadata/report adapter, hourly and
  daily normalizers, local/test-only execution-time token resolver, scheduler/worker integration,
  sanitized fixtures, and 36 new unit tests. Ruff, mypy strict, 99 unit tests, frontend checks,
  secret scan, locked dependency sync, offline PostgreSQL DDL generation, and diff checks pass.
  Docker is unavailable in the local runner, so live PostgreSQL/MinIO integration and migration
  round-trip remain the GitHub Actions release gate.
- 2026-08-14: Draft PR #11 published. Initial CI run 67 passed frontend, repository safety,
  migration 0010, static checks, and unit tests, then identified only the GA4 integration fixture's
  tenant→publisher insert ordering. Added explicit ownership-level flushes and republished.
- 2026-08-14: CI run 69 passed the fixture and reached connection registration, identifying the
  reserved ORM `metadata` keyword. Updated the insert to `connection_metadata`, added a direct
  SQLAlchemy compilation regression test, and republished.
- 2026-08-14: CI run 71 passed all release gates: repository safety, frontend, 99 unit tests,
  migration 0010, 23 PostgreSQL/MinIO/browser/GA4 integration tests, scheduler, and worker. M4 and
  EP-010 complete.

## 21. Final Outcome / Retrospective

EP-010 completes C1 and the GA4 C2 aggregate read-only connector. A validated property can now
produce hourly traffic and daily behavior evidence through the existing queue, worker, scheduler,
PostgreSQL, and tenant boundary. Every point retains exact definition, source time/timezone,
freshness, connector/semantics version, response limitations, and immutable extract provenance.

The implementation never introduces a provider write method, write scope, live test credential,
user-level export, arbitrary report builder, or causal conclusion. Missing/thresholded data remains
missing or limited, and a provider failure degrades connector health without inventing business
zeros. Production OAuth onboarding and a managed secret provider remain explicit future work.

## 22. Validation Results

- Ruff format/check — passed (95 files);
- mypy strict — passed (85 source files);
- backend unit — 99 passed;
- backend integration — 23 passed, including GA4 queue/worker/persistence, tenant isolation,
  preliminary→mature reconciliation, migration round trip, Chromium, PostgreSQL, and MinIO;
- frontend lint/typecheck/Vitest/build — passed;
- repository secret scan, Docker Compose config, and `git diff --check` — passed;
- scheduler and general worker smoke checks — passed;
- Draft PR #11: https://github.com/marian-dotcom/publisher-intelligence/pull/11;
- final CI run 71: https://github.com/marian-dotcom/publisher-intelligence/actions/runs/31788207373.

## 23. Next Step

Review and merge Draft PR #11. After merge, begin GSC C3 in a separate ExecPlan, reusing the C1
connection/extract/metric lifecycle while preserving Search and Discover as distinct surfaces.
