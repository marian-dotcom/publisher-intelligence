# EP-002 — Minimal Real-Browser Checkpoint B1

**Status:** COMPLETE
**Owner:** Codex / Engineering
**Created:** 2026-08-13
**Updated:** 2026-08-13
**Target milestone:** Browser Checkpoint B1
**MVP scope impact:** NO

## 1. Purpose and User Outcome

Prove the first real product behavior after repository bootstrap:

> Given one explicitly configured public publisher URL, a background browser worker runs a controlled real Chromium observation and persists one auditable checkpoint to PostgreSQL and private S3-compatible object storage.

The checkpoint must preserve what the page returned and what the observer saw without interpreting business impact or cause.

## 2. Scope

### In

- Playwright Python with its pinned Chromium build;
- one fixed, versioned desktop scenario for B1;
- explicit configured tenant, publisher, site, template, and monitored URL records;
- checkpoint window, run, attempt, collector-run, and artifact metadata;
- background `BROWSER_CHECKPOINT` jobs handled only by the browser-worker;
- fresh non-persistent BrowserContext per run;
- bounded navigation and stabilization;
- application-level target, redirect, and subresource SSRF controls;
- viewport and final full-page screenshots;
- raw rendered DOM/HTML;
- script inventory, network hosts/domains, request failures, page/console errors;
- final URL, top-level HTTP status, redirect chain, browser/environment provenance;
- immutable JSON manifest linking all B1 evidence;
- deterministic private object keys with SHA-256 artifact integrity;
- controlled fixture-page browser integration tests and PostgreSQL/MinIO end-to-end persistence tests;
- operator CLI for creating one pilot configuration and enqueueing one checkpoint;
- CI browser installation and validation.

### Out

- six-hour recurring scheduling and desktop/mobile matrix (B2);
- deterministic scrolling or consent interaction profiles (B2/B5);
- normalized DOM comparison or semantic diffs (B2/B3 and EP-003+);
- template discovery, rotating URLs, or expected-state inference (B3);
- GPT, CMP, Prebid, video, performance, or SEO-specific collectors (B4–B8);
- authenticated pages, paywall bypass, ad clicking, browser stealth, residential proxies;
- Playwright trace retention for successful core runs;
- public or permanent artifact URLs;
- product UI, incident logic, events, alerts, or AI.

## 3. Non-Goals

This plan does not claim production browser-fleet readiness. Deployment-level egress firewall/proxy enforcement remains required before untrusted pilot traffic; B1 implements and tests the application layer and documents the infrastructure boundary. It does not simulate user traffic or prove that all real users saw the same state.

## 4. Canonical References

- `AGENTS.md` sections 7–8, 13–21, 25, 30;
- `BROWSER.md` invariants and sections 2–24, 50–65, 75–81, 85–86;
- `ARCHITECTURE.md` sections 8–27, 79–84, 100–103, 144–147;
- `DATA_MODEL.md` sections 9–24 and artifact transaction guidance;
- `SECURITY.md` sections 40–60, 64–72, 133–137, 191–192;
- `DECISIONS.md` ADR-008–023, ADR-079, ADR-092–096, ADR-110–112, ADR-126–128;
- `MVP.md` sections 11–21;
- `PLANS.md` ExecPlan lifecycle and B1 decomposition.

Accepted decisions already authorize the significant dependency and architecture: Playwright controls Chromium, browser execution is separate from API, PostgreSQL stores structured truth, and S3-compatible storage stores large artifacts. No new ADR is required.

## 5. Current State

EP-001 is merged and green on `main`.

Available foundation:

- FastAPI, SQLAlchemy async, psycopg 3, and Alembic;
- PostgreSQL-backed fenced job queue;
- separate API, worker, browser-worker placeholder, and scheduler processes;
- S3-compatible storage adapter with hashing;
- tenant bootstrap table, structured logging/redaction, health checks;
- PostgreSQL and MinIO CI services.

Missing:

- Playwright/Chromium;
- browser domain tables;
- browser collectors and SSRF guard;
- checkpoint orchestration and evidence persistence;
- a real browser-worker handler;
- controlled browser fixtures/tests.

## 6. Target Behavior

1. An operator explicitly registers one URL whose hostname matches the configured site.
2. The application creates one checkpoint window and one checkpoint run.
3. It enqueues a tenant-owned `BROWSER_CHECKPOINT` job containing identifiers only.
4. The browser-worker validates tenant ownership and the URL destination.
5. It creates a fresh Chromium BrowserContext with downloads disabled and fixed B1 environment.
6. Listeners are attached before navigation.
7. The worker navigates with bounded waits, records response/failure/error evidence, captures viewport evidence, waits for a bounded stabilization interval, captures DOM and final full-page evidence last, and closes the context.
8. Objects are uploaded before their artifact rows become available.
9. PostgreSQL finalization atomically records attempts, collectors, artifact references, manifest, and final status.
10. HTTP 4xx/5xx top-level responses are persisted as `SITE_ERROR`; SSRF/redirect denial is `BLOCKED`; timeouts are `TIMEOUT`; Chromium/runtime failures are `BROWSER_ERROR`; collector degradation with useful evidence is `PARTIAL`; otherwise the run is `COMPLETE`.
11. Only technical browser/runtime failure is eligible for one queue retry. Publisher responses are never retried away.

## 7. Architecture / Data Flow

```text
Operator CLI
    ↓
Checkpoint service ──→ PostgreSQL config/window/run
    ↓
PostgreSQL job queue
    ↓
Browser worker ──→ URL/SSRF guard ──→ Chromium context ──→ public page
    │
    ├──→ private S3-compatible artifacts
    └──→ PostgreSQL attempt/collector/artifact/manifest metadata
```

The API remains independent. Browser job payloads contain IDs and no page evidence or secrets.

## 8. Files and Modules Affected

Likely additions/changes:

```text
backend/pyproject.toml
backend/uv.lock
backend/app/config/settings.py
backend/app/db/models.py
backend/app/browser/
  contracts.py
  security.py
  collectors.py
  persistence.py
  runner.py
  service.py
backend/app/browser_worker.py
backend/app/browser_cli.py
backend/app/storage/s3.py
backend/migrations/versions/0002_browser_checkpoint_b1.py
backend/tests/unit/browser/
backend/tests/integration/browser/
backend/tests/fixtures/browser_site.py
.github/workflows/ci.yml
Makefile
README.md
plans/EP-002-browser-checkpoint-b1.md
```

Names may be simplified after repository inspection, but browser meaning remains isolated from jobs/storage primitives.

## 9. Milestones

### M0 — Contract and dependency closure

- inspect the merged foundation and all browser-relevant canonical contracts;
- verify current official Playwright Python APIs;
- add this ExecPlan and record exact B1 boundaries.

Acceptance:

- [x] plan is self-contained and `IN_PROGRESS` before code changes;
- [x] no unresolved product/security/architecture decision blocks B1.

### M1 — Browser domain schema and repositories

- add only B1-required hierarchy/configuration and checkpoint evidence tables;
- add status/ownership/integrity constraints and tenant-safe indexes;
- implement repository operations for scheduled run creation, attempt start, artifact linking, and atomic finalization;
- preserve finalized checkpoint immutability at repository boundary.

Acceptance:

- [x] migration upgrade/downgrade/re-upgrade passes;
- [x] tenant ownership is present directly on fact/artifact tables;
- [x] retry attempts are domain records and do not alter EP-001 job semantics;
- [x] artifact rows are written only after object upload succeeds;
- [x] cross-tenant repository access is denied by scoped queries.

### M2 — Security guard and B1 collectors

- add URL canonicalization, scheme/userinfo/IP validation, allowed-host checks, DNS resolution, forbidden-range detection, redirect validation, and per-request subresource checks;
- collect scripts, network host/domain summaries, request failures, page errors, console errors, redirect chain, screenshots, and DOM;
- redact query strings/fragments and never retain headers, bodies, cookies, or storage values.

Acceptance:

- [x] private/reserved/metadata targets are blocked;
- [x] configured same-site HTTP→HTTPS/www redirect is allowed;
- [x] unexpected cross-site redirect is blocked and recorded;
- [x] hostile subresource attempts are aborted and recorded without leaking internal response data;
- [x] collectors attach before navigation and fail independently.

### M3 — Real Chromium runner and evidence persistence

- add Playwright dependency and pinned Chromium installation workflow;
- run a fixed versioned desktop environment in a fresh context;
- capture viewport before stabilization and full page last;
- construct a typed, versioned manifest and persist all artifacts with hashes;
- classify complete/partial/site/browser/timeout/blocked outcomes.

Acceptance:

- [x] fixture run produces both screenshots, raw DOM, and manifest;
- [x] manifest includes all artifacts, final status/URL/HTTP status, script/network/error evidence, actions, limitations, and observer versions;
- [x] object bytes match stored SHA-256 and are retrievable;
- [x] context closes on success and failure;
- [x] no browser launch uses `--no-sandbox`.

### M4 — Background workflow and operator smoke path

- replace browser-worker placeholder with `BROWSER_CHECKPOINT` handling;
- validate job tenant/run ownership before browser execution;
- retry once only for technical `BROWSER_ERROR`/storage infrastructure failure;
- add CLI commands to register a pilot URL and enqueue/run one checkpoint without exposing arbitrary unauthorised crawling.

Acceptance:

- [x] checkpoint execution never occurs in API request path;
- [x] job payload contains IDs only;
- [x] unknown job types fail safely without payload logging;
- [x] publisher 503 is completed as `SITE_ERROR`, not retried;
- [x] technical retry adds a second checkpoint attempt and preserves the first.

### M5 — Fixtures, tests, CI, and documentation

- add controlled local fixture pages for complete, 503, JS error, failed dependency, redirect, and hostile subresource cases;
- install Chromium in backend CI and run browser integration/e2e persistence tests;
- document setup, browser install, enqueue/smoke workflow, evidence boundary, and production egress limitation;
- update the plan with exact validation evidence.

Acceptance:

- [x] local unit/static checks pass;
- [x] CI PostgreSQL/MinIO/browser tests pass;
- [x] fixture evidence is deterministic and sanitized;
- [x] final diff contains no temporary screenshots, traces, browser profiles, or secrets;
- [x] EP-002 is marked `COMPLETE` only after the final branch CI is green.

## 10. Acceptance Criteria

- [x] one configured public URL produces one persisted real-Chromium checkpoint;
- [x] checkpoint evidence includes timestamp, viewport/full-page screenshots, raw DOM, scripts, network hosts/domains, request failures, JS/console errors, HTTP/final URL, manifest, and environment provenance;
- [x] PostgreSQL remains authoritative for metadata and object storage remains private artifact storage;
- [x] evidence is tenant-owned and cross-tenant reads are tested;
- [x] finalized source evidence is not overwritten;
- [x] `SITE_ERROR`, `BROWSER_ERROR`, `TIMEOUT`, `BLOCKED`, `PARTIAL`, and `COMPLETE` semantics are distinct;
- [x] a failed collector does not discard other useful evidence;
- [x] page content cannot reach private/internal destinations through allowed browser requests at the application layer;
- [x] no ad clicks, form filling, consent action, stealth, authentication, AI, or downstream event/incident judgment is introduced;
- [x] Playwright/Chromium and collector versions are recorded;
- [x] all waits/retries/resources are bounded;
- [x] local supported checks and final GitHub Actions pass.

## 11. Validation Commands

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

The local runtime currently lacks Docker, so PostgreSQL/MinIO browser end-to-end validation must run in GitHub Actions. This limitation must not be described as a local pass.

## 12. Test Cases

### Happy path

- configured fixture URL loads and returns 200;
- scripts and first/third-party network hosts are inventoried;
- viewport screenshot precedes final full-page screenshot;
- raw DOM and manifest are private artifacts with matching hashes;
- checkpoint is `COMPLETE` with observer provenance.

### Failure paths

- top-level 503 becomes `SITE_ERROR` with preserved DOM/screenshot/network evidence;
- navigation timeout becomes `TIMEOUT` and partial evidence is retained where available;
- Chromium/runtime failure becomes `BROWSER_ERROR` and may retry once;
- artifact upload failure does not create available artifact metadata;
- unexpected cross-site redirect becomes `BLOCKED`;
- private/loopback/metadata target is rejected before launch;
- page-initiated private subresource is aborted and recorded;
- collector error yields `PARTIAL` without discarding successful collectors.

### Tenant/regression boundaries

- tenant A cannot configure a run against tenant B site/URL/scenario;
- tenant A cannot query tenant B checkpoint or artifact metadata;
- stale/finalized run cannot be overwritten;
- duplicate logical run identity does not create a second run;
- job tenant must match checkpoint tenant;
- job logs never contain URL query data, DOM, cookies, headers, or payload.

## 13. Data / Migration Impact

The migration adds only B1 identity/configuration and evidence metadata tables:

```text
publishers
sites
templates
monitored_urls
browser_scenarios
checkpoint_windows
checkpoint_runs
checkpoint_attempts
collector_runs
artifacts
```

No GPT/CMP/Prebid/video/performance/event/incident tables are added. Downgrade is allowed only in disposable local/CI databases. Historical evidence will not use cascade deletion from archived configuration.

## 14. Security / Privacy Impact

Raw DOM and screenshots are S2 customer-confidential evidence. Object keys are private; no public/signed access endpoint is added. URL query strings and fragments are excluded from structured network evidence. The browser uses no real profiles, credentials, cookies, downloads, permissions, forms, or ad clicks.

Application-level SSRF protection is necessary but does not replace production network egress enforcement. The plan records this as a deployment prerequisite rather than claiming DNS-rebinding protection from URL parsing alone.

## 15. Observability / Failure Handling

Structured browser logs contain identifiers only:

```text
process
job_id
tenant_id
site_id
checkpoint_run_id
stage
duration_ms
status
error_class
```

They do not contain full URLs, query strings, DOM, request headers/bodies, cookie values, or screenshots. Collector failures are explicit and bounded. Partial evidence is retained.

## 16. Rollback Strategy

Before production tenant evidence exists:

1. revert EP-002 implementation commits;
2. downgrade `0002` only in disposable databases;
3. remove test-only fixture objects;
4. preserve EP-001 and this plan history.

After real evidence exists, do not destructively downgrade. Disable new browser jobs, preserve artifacts/metadata, and use a new reviewed migration plan.

## 17. Progress Log

### 2026-08-13 — Plan preparation

Merged EP-001 foundation inspected. Browser, data, security, architecture, MVP, and decision contracts reviewed. Official Playwright Python documentation verified for isolated contexts, request/response/failure/page-error events, `page.content()`, screenshots, and Chromium installation.

M0 complete. The plan progressed through DRAFT and READY to IN_PROGRESS after scope, validation, dependencies, and security boundaries were confirmed.

### 2026-08-13 — B1 implementation and local validation

Implemented the B1 schema, tenant-scoped checkpoint repository, application SSRF guard, isolated
Playwright runner, independent observation/script collectors, deterministic evidence persistence,
operator CLI, fenced browser-worker handling, technical-only retry, controlled browser fixture,
and CI Chromium integration.

Local results:

- `ruff format --check` and `ruff check`: passed;
- strict `mypy`: passed;
- backend unit suite: 22 passed;
- frontend lint/typecheck/test/build: passed (1 frontend test);
- secret scan and `git diff --check`: passed.

Local integration was not claimed: Docker is unavailable, and this runtime's Playwright CDN proxy
returned a zero-byte archive when installing Chromium. PostgreSQL/MinIO migration and real-browser
tests were therefore delegated to GitHub Actions and are recorded below.

### 2026-08-13 — GitHub Actions integration closure

Draft PR #3 exposed and closed two integration-only defects: SQLAlchemy needed an explicit flush
for `checkpoint_windows` before inserting its dependent run, and Playwright needs a mutable bound
route-handler instance to cache its wrapper. Safe error-class/source diagnostics located the latter
without logging exception messages or page data. Early navigation requests without an available
frame are treated conservatively as top-level for redirect enforcement.

GitHub Actions run `31742758932` passed all jobs:

- backend: Playwright Chromium install, Ruff, mypy, 22 unit tests, Alembic migration, MinIO setup,
  11 PostgreSQL/MinIO/real-Chromium integration tests, scheduler smoke, and worker smoke;
- frontend: locked install, lint, typecheck, one Vitest test, and production build;
- repository safety: secret scan, Compose validation, and diff hygiene.

This is the authoritative B1 real-browser validation; no Docker-backed local pass is claimed.

## 18. Decision Log

### 2026-08-13 — B1 scenario boundary

Use one explicit `core_desktop_v1` scenario with no consent action or scroll. B2 will add repeatability, mobile, and deterministic interactions. Fresh context and environment provenance are retained now because evidence without them would be invalid.

### 2026-08-13 — Network evidence minimization

Store normalized scheme/host/port/resource type and failures, never query strings, fragments, request/response bodies, cookies, or arbitrary headers. Raw top-level DOM is the only response body intentionally captured.

### 2026-08-13 — SSRF boundary

Implement application validation and request interception in B1. Require deployment network egress controls before untrusted pilot traffic; do not claim a parser can solve DNS rebinding.

## 19. Discoveries / Surprises

- BROWSER.md groups isolated contexts/scenario identity under B2, while architecture and evidence invariants require provenance and isolation for every valid checkpoint. EP-002 implements the minimum fixed/versioned form without the B2 matrix or scheduler.
- The hosted implementation runtime has no Docker; CI remains the authoritative PostgreSQL/MinIO integration environment.
- Current Playwright documentation notes that HTTP 4xx/5xx responses do not emit `requestfailed`; top-level site status must come from the navigation `Response`.

## 20. Known Risks

- browser binaries and Linux dependencies add CI time and supply-chain surface;
- screenshots/full pages can be large or unstable on hostile/infinite pages;
- application SSRF interception is defense-in-depth, not a network firewall;
- headless behavior may differ from real users and must remain labeled synthetic;
- live publisher validation may require allowlisting and is not a deterministic CI dependency.

## 21. Next Step

Review and merge Draft PR #3. After EP-002 lands on `main`, prepare the next ExecPlan for B2
repeatability: six-hour cadence, desktop/mobile profiles, deterministic interaction/scroll policy,
and comparable checkpoint sequencing.

## 22. Final Outcome / Retrospective

EP-002 shipped the first real product behavior: an explicitly configured publisher URL can produce
an auditable Chromium checkpoint in a background worker. The checkpoint preserves tenant-owned
PostgreSQL metadata and private object-storage evidence for viewport/full-page screenshots,
rendered DOM, scripts, network/error observations, final HTTP state, hashes, provenance, and a
versioned manifest.

The implementation stayed inside B1: one fixed desktop scenario, bounded observation, no consent
action, no scheduler cadence, no provider-specific interpretation, and no AI/incident judgment.
Application SSRF checks and fail-closed redirect handling are implemented, while network-level
egress enforcement remains a production deployment prerequisite.

Local supported checks and GitHub Actions run `31742758932` provide the final validation evidence.
The remaining FastAPI/Starlette `httpx2` warning is non-blocking and inherited from EP-001.
