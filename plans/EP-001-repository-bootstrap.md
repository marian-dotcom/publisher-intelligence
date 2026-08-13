# EP-001 — Repository Bootstrap and Local Development Environment

**Status:** IN_PROGRESS
**Owner:** Codex / Engineering  
**Created:** 2026-08-13  
**Updated:** 2026-08-13  
**Target milestone:** Repository foundation before Browser Checkpoint B1  
**MVP scope impact:** NO  
**New infrastructure category:** NO — this plan selects concrete tools inside the already approved PostgreSQL + S3-compatible object storage architecture.

## Progress

- [x] M0 — Inspect the documentation-only repository and close bootstrap decisions
- [x] M1 — Create repository, backend, and frontend skeletons
- [ ] M2 — Add local PostgreSQL and S3-compatible object storage (implemented; CI validation pending)
- [ ] M3 — Add persistence and migration foundation (implemented; CI validation pending)
- [ ] M4 — Add PostgreSQL job queue, worker, and scheduler skeletons (implemented; CI validation pending)
- [ ] M5 — Add configuration, object-storage adapter, and health checks (implemented; CI validation pending)
- [ ] M6 — Add CI, documentation, and final validation (in progress)

## 1. Purpose and User Outcome

After this plan is complete, a developer can clone the repository, install locked backend and frontend dependencies, start PostgreSQL and an S3-compatible local object store, apply migrations, run the API, worker, browser-worker placeholder, scheduler, and frontend, and execute the complete validation suite.

This foundation enables EP-002 to implement the first product proof:

> One public publisher URL produces one reproducible Chromium checkpoint persisted to PostgreSQL and object storage.

EP-001 does not implement that checkpoint. It makes the repository safe, repeatable, testable, and ready for it.

## 2. Scope

### In

- canonical documents and machine-readable knowledge/eval assets at repository root;
- `backend/` FastAPI application managed with `uv`;
- `frontend/` Next.js/React/TypeScript application managed with `pnpm`;
- PostgreSQL for structured data;
- S3-compatible local object storage, using MinIO for local development;
- SQLAlchemy 2.x, psycopg 3, and Alembic;
- a minimal `tenants` table required for tenant-safe infrastructure tests;
- a PostgreSQL-backed `jobs` table and queue repository;
- API, general worker, browser-worker placeholder, and scheduler entry points;
- deterministic claiming, fencing, heartbeat, retry, and expired-lease reclaim behavior;
- environment configuration and `.env.example` placeholders;
- backend and frontend test/lint/typecheck/build foundations;
- GitHub Actions CI;
- concise developer setup and validation documentation.

### Out

- Playwright installation and real browser checkpoint collection;
- browser collectors, screenshots, DOM, network, GPT, CMP, Prebid, video, or SEO evidence;
- GA4, GSC, or GAM connectors;
- event detection, Timeline, Home, Incident Engine, LLM calls, or eval execution logic;
- production authentication provider selection;
- production cloud, object-storage, LLM, email, or monitoring vendor selection;
- production deployment;
- billing, enterprise RBAC, Slack, RUM, session replay, or autonomous remediation;
- a generic workflow engine, Redis, Kafka, Kubernetes, or another database.

## 3. Canonical References

Read completely before implementation:

- `AGENTS.md`
- `PLANS.md`
- `ARCHITECTURE.md`
- `DATA_MODEL.md`
- `SECURITY.md`
- `DECISIONS.md`

Relevant contracts:

- modular monolith with separate API, worker, browser-worker, and scheduler runtime processes;
- PostgreSQL is the only structured database in MVP;
- large evidence belongs in private S3-compatible object storage;
- background work is asynchronous, bounded, retryable, and distinct from domain truth;
- all tenant-owned data and jobs carry and validate tenant ownership;
- secrets never enter job payloads or logs;
- migrations are mandatory for schema changes;
- CI uses locked dependencies and no production secrets;
- ADR-126 defines the repository toolchain;
- ADR-127 defines the persistence and migration stack;
- ADR-128 defines the bootstrap queue contract.

Where older architectural examples conflict with ADR-128, the accepted ADR controls. In particular, EP-001 does not implement a `CANCELLED` job state and does not conflate expired-lease reclaim with normal job claiming.

## 4. Current State

At plan approval:

- the repository contains canonical Markdown specifications and versioned `knowledge/` and `evals/` assets;
- the canonical files are being normalized to repository root;
- there is no backend or frontend implementation;
- there is no package metadata, lockfile, migration, database schema, object-storage adapter, worker, scheduler, CI workflow, or executable test suite;
- no application dependencies or infrastructure services have been installed by this documentation change;
- Docker, PostgreSQL client availability, and browser tooling must be probed by the implementation environment rather than assumed.

## 5. Target Behavior

From a clean checkout, a developer should be able to follow documented commands equivalent to:

```bash
cp .env.example .env
docker compose up -d postgres minio
uv --directory backend sync --all-groups
pnpm --dir frontend install --frozen-lockfile
uv --directory backend run alembic upgrade head
```

Then the following process types start independently:

```text
API
general worker
browser-worker placeholder
scheduler
Next.js frontend
```

Observable outcomes:

- API liveness responds without requiring external provider credentials;
- readiness reports PostgreSQL and object-storage dependency state without leaking secrets;
- migrations apply from a clean database;
- scheduler can enqueue a safe bootstrap/no-op job without duplicating the same idempotency key;
- a worker can claim, heartbeat, complete, retry, and fail a job;
- an expired lease is reclaimed by a separate reclaim operation;
- a stale worker with an old `lock_token` cannot heartbeat or finalize a reclaimed job;
- backend and frontend checks pass in CI;
- no product-domain feature is presented as implemented.

## 6. Architecture / Data Flow

```text
Next.js frontend
        |
        v
FastAPI API --------> PostgreSQL
                         ^
                         |
Scheduler ---> jobs ---> Worker
                         |
                         +----> S3-compatible object storage adapter

Browser-worker placeholder uses the same application packages,
but EP-001 does not launch Chromium or collect publisher evidence.
```

All process types share one codebase and release version. They are separate runtimes, not microservices.

## 7. Files and Modules Affected

Existing and retained at root:

```text
AGENTS.md
ARCHITECTURE.md
BROWSER.md
CONNECTORS.md
DATA_MODEL.md
DECISIONS.md
DOMAIN.md
EVALS.md
EVENTS.md
INCIDENT.md
INCIDENTS.md
MVP.md
PLANS.md
PRODUCT.md
SECURITY.md
START_HERE.md
evals/
knowledge/
plans/
```

Likely files to create:

```text
.env.example
.gitignore
.github/workflows/ci.yml
README.md
compose.yaml
Makefile

backend/
  pyproject.toml
  uv.lock
  alembic.ini
  migrations/
  app/
    api/
    common/
    config/
    db/
    jobs/
    storage/
    worker.py
    browser_worker.py
    scheduler.py
  tests/

frontend/
  package.json
  pnpm-lock.yaml
  tsconfig.json
  next.config.*
  app/
  tests/
```

Exact internal names may change if repository inspection reveals a simpler coherent layout. Module boundaries and accepted ADRs must not change silently.

## 8. Milestones

### M0 — Repository inspection and decision closure

**Goal:** Establish a trustworthy repository root and remove bootstrap ambiguity.

**Implementation:**

- place canonical documents, `knowledge/`, and `evals/` at root;
- add this READY ExecPlan under `plans/`;
- add ADR-126, ADR-127, and ADR-128;
- leave unrelated vendor/product decisions open.

**Acceptance criteria:**

- [x] `AGENTS.md` is at repository root;
- [x] the wrapper upload directory is absent on the plan branch;
- [x] the plan is self-contained and READY;
- [x] durable bootstrap decisions are recorded in `DECISIONS.md`.

**Validation:**

```bash
git ls-tree -r --name-only HEAD
git diff --check main...HEAD
```

**Expected observable result:** A fresh Codex session discovers repository instructions and the approved bootstrap plan without chat context.

### M1 — Repository, backend, and frontend skeletons

**Goal:** Create executable applications with locked, minimal toolchains.

**Implementation:**

- create root hygiene and developer command files;
- create a FastAPI application with liveness endpoint and process entry points;
- configure Python 3.12, `uv`, Ruff, mypy, and pytest;
- create a minimal Next.js/React/TypeScript application;
- configure pinned `pnpm`, ESLint, TypeScript, and a focused test runner;
- avoid product UI, design-system work, browser behavior, or external provider calls.

**Acceptance criteria:**

- [ ] backend dependencies install from lockfile;
- [ ] frontend dependencies install from lockfile;
- [ ] API imports and liveness test pass;
- [ ] worker, browser-worker placeholder, and scheduler entry points import and exit cleanly in test mode;
- [ ] frontend renders a neutral foundation page and builds;
- [ ] no second Python or Node package manager is introduced.

**Validation:**

```bash
uv --directory backend sync --all-groups --locked
uv --directory backend run ruff check .
uv --directory backend run ruff format --check .
uv --directory backend run mypy app
uv --directory backend run pytest tests/unit
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend test
pnpm --dir frontend build
```

**Expected observable result:** Both applications are reproducible from lockfiles and all process entry points are explicit.

### M2 — Local PostgreSQL and object storage

**Goal:** Provide a small, repeatable local infrastructure environment.

**Implementation:**

- add Compose services for PostgreSQL and MinIO;
- pin container image versions or immutable major/minor tags;
- add health checks, named development volumes, and non-secret local defaults;
- create the local bucket through an idempotent initialization step;
- keep services bound for local development and document exposure;
- do not add Redis, Kafka, Elasticsearch, or Kubernetes.

**Acceptance criteria:**

- [ ] `docker compose config` succeeds;
- [ ] PostgreSQL becomes healthy;
- [ ] MinIO becomes healthy and the local bucket exists;
- [ ] restart preserves local development data;
- [ ] `.env.example` contains placeholders only;
- [ ] no real credential or production endpoint is committed.

**Validation:**

```bash
docker compose config
docker compose up -d postgres minio
docker compose ps
```

**Expected observable result:** A developer can start both required stateful dependencies with one documented command.

### M3 — Persistence and migration foundation

**Goal:** Establish tenant-aware relational persistence and a reversible first migration.

**Implementation:**

- configure SQLAlchemy 2.x typed models, psycopg 3, and Alembic;
- use one documented async session/transaction convention;
- add a minimal `tenants` table and the infrastructure `jobs` table;
- use application text enums with database CHECK constraints for stable job statuses;
- add foreign keys, timestamps, queue indexes, and ADR-128 partial unique idempotency indexes;
- keep queue-specific claiming SQL explicit and tested;
- do not generate future browser, connector, event, or incident tables.

**Acceptance criteria:**

- [ ] clean database upgrades to head;
- [ ] downgrade and re-upgrade work in the disposable test database;
- [ ] schema contains only milestone-required tables;
- [ ] `jobs.tenant_id` is nullable only for explicitly global jobs;
- [ ] job status vocabulary is `PENDING`, `RUNNING`, `RETRY`, `COMPLETE`, `FAILED`;
- [ ] no `CANCELLED` state or `job_attempts` table exists;
- [ ] tenant and global partial idempotency indexes match ADR-128;
- [ ] application runtime and migration configuration are separable.

**Validation:**

```bash
uv --directory backend run alembic upgrade head
uv --directory backend run alembic downgrade base
uv --directory backend run alembic upgrade head
uv --directory backend run pytest tests/integration/test_migrations.py
```

**Expected observable result:** Schema creation is reproducible from version-controlled migrations and preserves tenant-safe queue identities.

### M4 — Job queue, worker, and scheduler skeletons

**Goal:** Prove safe PostgreSQL-backed background execution without implementing product jobs.

**Implementation:**

- implement enqueue with tenant/global idempotency;
- claim eligible work transactionally with `FOR UPDATE SKIP LOCKED`;
- assign a new opaque `lock_token` on every claim;
- require matching `lock_token` for heartbeat, completion, retry, and failure transitions;
- implement expired-lease reclaim as a separate operation;
- preserve attempt count and last stable error metadata on `jobs`;
- provide bounded polling and graceful shutdown;
- provide one safe bootstrap/no-op handler solely for integration validation;
- ensure job payloads contain references, never secrets.

**Acceptance criteria:**

- [ ] concurrent workers cannot claim the same job simultaneously;
- [ ] duplicate tenant idempotency key returns/conflicts with the existing logical job instead of inserting a duplicate;
- [ ] global and tenant idempotency namespaces remain distinct;
- [ ] expired RUNNING work is not silently stolen by normal claim;
- [ ] reclaim moves expired work to RETRY and clears ownership before it can be claimed again;
- [ ] stale `lock_token` cannot mutate a reclaimed job;
- [ ] retry increments attempt and respects `max_attempts`;
- [ ] exhausted work becomes FAILED with stable error code and bounded message;
- [ ] scheduler inserts work and does not execute domain logic;
- [ ] worker logs contain identifiers but no payload secrets.

**Validation:**

```bash
uv --directory backend run pytest tests/unit/jobs
uv --directory backend run pytest tests/integration/jobs
uv --directory backend run python -m app.scheduler --once
uv --directory backend run python -m app.worker --once
```

**Expected observable result:** The same PostgreSQL queue contract works across scheduler and worker processes, including race and crash-recovery cases.

### M5 — Configuration, storage adapter, and health checks

**Goal:** Create safe dependency boundaries needed by EP-002.

**Implementation:**

- add validated environment-based application settings;
- separate liveness from readiness;
- add an S3-compatible storage adapter with put/head/get/delete primitives required by later evidence work;
- add a deterministic test key/payload and content-hash verification;
- use dependency injection/test doubles for unit tests;
- redact secrets and credentials from settings representations, errors, and logs;
- keep production bucket policy and vendor selection out of scope.

**Acceptance criteria:**

- [ ] missing required configuration fails clearly without printing secrets;
- [ ] liveness does not depend on PostgreSQL or object storage;
- [ ] readiness reports dependency failure safely;
- [ ] storage integration round trip succeeds against MinIO;
- [ ] object content hash is verified;
- [ ] tests prove secret values are absent from logs and error strings;
- [ ] browser-worker placeholder remains isolated from API execution.

**Validation:**

```bash
uv --directory backend run pytest tests/unit/config tests/unit/storage
uv --directory backend run pytest tests/integration/storage
uv --directory backend run pytest tests/integration/health
```

**Expected observable result:** EP-002 can depend on stable database and artifact-storage interfaces without knowing local vendor details.

### M6 — CI, documentation, and final validation

**Goal:** Make repository health reproducible and reviewable.

**Implementation:**

- add GitHub Actions jobs for backend and frontend checks;
- run PostgreSQL and object-storage integration services in CI without production secrets;
- add dependency and secret scanning where available without blocking on a vendor choice;
- document setup, process commands, migrations, tests, and common failure states;
- update this ExecPlan progress, validation, discoveries, and retrospective;
- review the complete diff for scope creep and accidental secrets.

**Acceptance criteria:**

- [ ] backend format, lint, typecheck, unit, migration, and integration checks pass;
- [ ] frontend lint, typecheck, test, and build pass;
- [ ] clean migration validation passes in CI;
- [ ] queue concurrency/fencing/reclaim tests pass;
- [ ] object-storage round-trip test passes;
- [ ] README reproduces a clean setup;
- [ ] CI does not receive production secrets;
- [ ] secret scan reports no committed secret;
- [ ] plan status and logs match actual implementation.

**Validation:**

```bash
make check
make test-integration
git diff --check
git status --short
```

**Expected observable result:** A clean pull request proves the repository foundation is reproducible and ready for EP-002.

## 9. Final Acceptance Criteria

- [ ] canonical documents and assets are at root;
- [ ] backend and frontend use one locked package manager each;
- [ ] FastAPI and Next.js skeletons run;
- [ ] PostgreSQL and MinIO local services are documented and healthy;
- [ ] first migration applies from a clean database and is reversible in test;
- [ ] job queue semantics conform to ADR-128;
- [ ] API, worker, browser-worker placeholder, and scheduler are distinct processes in one codebase;
- [ ] configuration is validated and secrets are redacted;
- [ ] object-storage adapter passes a local integration round trip;
- [ ] backend and frontend validation suites pass;
- [ ] GitHub Actions passes without production credentials;
- [ ] no deep product feature or MVP expansion was introduced;
- [ ] implementation diff contains no accidental secret or unrelated refactor;
- [ ] this plan is updated to COMPLETE only after evidence for every criterion is recorded.

## 10. Final Validation

Implementation must define stable wrapper commands, then run the complete equivalent ladder:

```bash
docker compose config
docker compose up -d postgres minio

uv --directory backend sync --all-groups --locked
uv --directory backend run ruff check .
uv --directory backend run ruff format --check .
uv --directory backend run mypy app
uv --directory backend run pytest
uv --directory backend run alembic upgrade head

pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend test
pnpm --dir frontend build

git diff --check
git status --short
```

If the implementation environment lacks Docker or a PostgreSQL client, record the limitation and use the GitHub Actions service environment for the missing integration checks. Do not claim those checks passed locally.

## 11. Test Cases

### Happy path

- clean dependency installation from both lockfiles;
- clean migration to head;
- API liveness/readiness;
- storage put/head/get/delete round trip;
- scheduler enqueue followed by worker completion;
- frontend lint/typecheck/test/build.

### Failure paths

- PostgreSQL unavailable makes readiness fail without breaking liveness;
- object storage unavailable makes readiness fail safely;
- invalid configuration fails without exposing credentials;
- worker crash leaves a lease that can be reclaimed after expiry;
- stale worker token cannot finalize reclaimed work;
- retryable failure becomes RETRY; exhausted failure becomes FAILED;
- malformed/unknown job type fails safely;
- job logs do not expose payload secrets.

### Edge and regression cases

- two workers race for one job;
- duplicate tenant idempotency key;
- same idempotency key in different tenants;
- global key collides only inside global namespace;
- global and tenant namespaces do not collide;
- normal claim ignores expired RUNNING work until reclaim runs;
- migration downgrade/re-upgrade in disposable database;
- tenant-scoped queue read cannot return another tenant's job;
- status CHECK rejects `CANCELLED` during EP-001;
- repository contains no `job_attempts` table.

## 12. Data / Migration Impact

EP-001 introduces only the smallest schema needed to validate foundation behavior:

- `tenants` — minimal tenant identity for isolation and foreign-key tests;
- `jobs` — infrastructure queue state defined by ADR-128.

It does not pre-create browser, connector, event, incident, or report tables.

All schema changes use Alembic. The first migration must be safe for a clean database. Because no production data exists, downgrade can remove the two bootstrap tables in disposable local/CI environments. Production destructive rollback is not authorized by this plan.

## 13. Security / Privacy Impact

No customer evidence or external credentials are collected by EP-001.

Security obligations:

- `.env.example` contains placeholders only; `.env` is ignored;
- jobs contain `tenant_id` and never raw tokens, API keys, passwords, or signing keys;
- worker validates tenant ownership before future tenant-owned handlers execute;
- PostgreSQL and object storage use isolated local credentials;
- production evidence storage remains private by contract;
- configuration and logs redact secret values;
- CI receives no production secrets;
- dependency lockfiles and basic dependency/secret scanning are enabled;
- readiness exposes state, not connection strings or credentials.

Relevant references: `SECURITY.md` sections 11, 15, 33–38, 70–73, 80–83, 134–146, 187, and 195–198.

## 14. Observability / Failure Handling

Use structured logs with, when available:

```text
process
request_id
job_id
tenant_id
job_type
attempt
error_class
```

Do not log full job payloads by default.

Foundation error classes should include at least:

```text
DATABASE_ERROR
STORAGE_ERROR
TIMEOUT
VALIDATION_ERROR
```

API exposes separate liveness and readiness. Worker and scheduler log startup, graceful shutdown, claim/reclaim counts, and stable error codes. Queue polling and retries are bounded.

## 15. Rollback Strategy

Before EP-001 reaches production, rollback is:

1. revert the implementation commit(s);
2. run Alembic downgrade only in disposable local/CI environments when needed;
3. preserve repository documents and this ExecPlan history;
4. do not delete external evidence because EP-001 creates none.

After any real tenant or job data exists, destructive schema rollback requires a new reviewed migration plan.

## 16. Known Risks

- implementation runtime may not expose Docker; CI must then prove integration behavior;
- package-manager or framework versions may drift unless lockfiles and version files are committed;
- lease/reclaim races can permit stale writes without `lock_token` fencing;
- idempotency indexes can be incorrect if tenant/global namespaces are merged;
- local MinIO behavior is compatible with S3 APIs but does not prove every production provider policy;
- overbuilding auth, deployment, product UI, or browser behavior would delay the first evidence proof.

## 17. Open Decisions

Not required for EP-001 and intentionally remain open:

- production authentication provider;
- cloud provider;
- production object-storage provider;
- LLM provider/model;
- email provider;
- application monitoring vendor;
- PostgreSQL RLS activation;
- contractual production retention commitments.

If implementation reveals a choice with material business or security impact, stop and request a decision. Ordinary library patch versions are locked by implementation and do not require founder approval.

## 18. Decision Log

### 2026-08-13 — Repository toolchain

**Decision:** Adopt ADR-126: Python 3.12 + `uv` for backend and pinned `pnpm` + Node LTS for frontend, with one lockfile per ecosystem.  
**Reason:** Reproducible installs, low ceremony, and direct fit with FastAPI/Next.js.  
**Alternatives:** Poetry, pip-tools, npm, yarn.  
**Impact:** Bootstrap commands, CI, lockfiles, and contribution workflow are standardized.

### 2026-08-13 — Persistence stack

**Decision:** Adopt ADR-127: SQLAlchemy 2.x + psycopg 3 + Alembic.  
**Reason:** Mature PostgreSQL integration, explicit relational modeling, standard migrations, and freedom to use clear SQL for queue primitives.  
**Alternatives:** SQLModel, raw SQL for all persistence, another ORM.  
**Impact:** Schema and session conventions become uniform without hiding database semantics.

### 2026-08-13 — Queue semantics

**Decision:** Adopt ADR-128: separate reclaim operation, per-claim `lock_token` fencing, tenant/global partial idempotency indexes, no `job_attempts` table, and no `CANCELLED` state in EP-001.  
**Reason:** Prevent stale-worker writes and ambiguous ownership while keeping the first queue minimal.  
**Alternatives:** combined claim/reclaim, lock owner only, one nullable-tenant unique index, separate attempt history, expanded status vocabulary.  
**Impact:** Queue schema, migration, repository API, and concurrency tests are explicit.

## 19. Discoveries / Surprises

### 2026-08-13

- The initial GitHub upload created one wrapper directory instead of placing the repository contents at root.
- The uploaded starter package contained ADR-001 through ADR-125 but not the separately approved EP-001 and ADR-126–128 changes from the previous GitHub account.
- The old textual PR was not accessible from the newly connected account, so the plan and ADRs were reconstructed from the canonical contracts and the preserved approved decision summary.
- The current repository has no code or infrastructure; no implementation validation can honestly be reported yet.
- The implementation runtime provides Python 3.12, `uv`, Node.js 24, and `pnpm`, but not Docker or `psql`.
- `pnpm` 11 requires dependency build permissions in `pnpm-workspace.yaml`; only `esbuild` and `unrs-resolver` are allowed.
- Python and pnpm cache roots are read-only in this hosted runtime, so local validation used temporary cache directories without changing repository commands.
- GitHub Dependency Review is unavailable until the repository Dependency Graph is enabled; the optional job was removed after its explicit unsupported-repository error, while locked installs and the repository secret scan remain enforced.

## 20. Progress Log

### 2026-08-13 — Plan preparation

M0 complete. Repository state inspected, root normalization defined, bootstrap decisions recorded, and implementation milestones made verifiable. No application code, dependencies, migrations, or infrastructure were created. Next: begin M1 in a new implementation branch and change plan status to `IN_PROGRESS`.

### 2026-08-13 — Foundation implementation

M1 is locally validated. M2–M5 are implemented with locked dependencies, Compose services, the first migration, ADR-128 queue primitives, separate runtime entry points, configuration redaction, storage boundaries, and health checks. M6 includes CI, README guidance, and a repository secret scan. PostgreSQL/MinIO integration evidence remains pending because Docker is unavailable locally; GitHub Actions is the designated validation environment.

## 21. Validation Results

Local implementation validation on 2026-08-13:

- `uv sync --all-groups --locked` — passed with 51 locked packages;
- Ruff format and lint — passed across 32 files;
- mypy — passed across application and test sources;
- backend unit tests — 6 passed;
- `pnpm install --frozen-lockfile` — passed;
- frontend lint, typecheck, Vitest, and production build — passed;
- frontend test suite — 1 passed;
- browser-worker placeholder smoke command — passed;
- Compose and GitHub Actions YAML syntax parse — passed;
- repository secret scan — passed;
- `git diff --check` — passed;
- Docker, migrations, PostgreSQL queue integration, MinIO round trip, and real readiness — not run locally because Docker is unavailable; CI workflow added to execute them.
- GitHub Actions run 31733563563 — backend, PostgreSQL migrations/queue integration, MinIO storage/readiness, frontend, and repository safety passed; only the optional Dependency Review job failed because the repository Dependency Graph is disabled.

## 22. Next Step

Publish the implementation branch as a draft pull request, let GitHub Actions prove the PostgreSQL/MinIO path, correct any CI-only failure, then mark M2–M6 and the plan complete only after all checks pass.

## 23. Final Outcome / Retrospective

Pending implementation.

When complete, record:

- what shipped;
- deviations from the original plan;
- exact validation commands and results;
- known limitations;
- follow-up ExecPlan for Browser Checkpoint B1.
