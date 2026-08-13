# Publisher Incident Intelligence

Repository foundation for a publisher operational-memory and incident-intelligence platform.

The product contracts live in the root Markdown files. Engineering work follows `AGENTS.md`, `DECISIONS.md`, `PLANS.md`, and the active ExecPlan under `plans/`.

## Prerequisites

- Python 3.12
- `uv`
- Node.js 24 LTS
- `pnpm` 11
- Docker with Compose for PostgreSQL and MinIO integration checks
- Playwright's pinned Chromium build for browser checkpoints

## Local setup

```bash
cp .env.example .env
docker compose up -d postgres minio minio-init
uv --directory backend sync --all-groups --locked
uv --directory backend run playwright install --with-deps chromium
pnpm --dir frontend install --frozen-lockfile
uv --directory backend run alembic upgrade head
```

Start each process in a separate terminal:

```bash
make api
make worker
make scheduler
make frontend
```

## Repeatable browser checkpoints (B2)

Register one explicit public pilot URL. The command also enqueues one immediate legacy B1
diagnostic run so an operator can verify the configuration without waiting for the next window:

```bash
uv --directory backend run python -m app.browser_cli register-and-enqueue \
  --tenant-slug pilot \
  --tenant-name "Pilot Tenant" \
  --publisher-name "Example Publisher" \
  --site-name "Example Site" \
  --url "https://www.example.com/"
```

Run the isolated browser worker in a separate terminal, or use `--once` for one polling cycle:

```bash
make browser-worker
uv --directory backend run python -m app.browser_worker --once
```

The scheduler idempotently materializes one desktop and one mobile run for every active monitored
URL in the site-local 00:00, 06:00, 12:00, and 18:00 windows. Jobs are deterministically staggered
inside the window. Repeated scheduler ticks do not create duplicate windows, runs, or jobs.

Each scheduled run uses a fresh non-persistent Chromium context and a frozen, versioned device and
interaction profile. B2 waits and scrolls deterministically to 25%, 50%, and 75% of the available
document range, records requested/actual positions, and captures the full-page screenshot last.
The versioned manifest preserves complete observer/action provenance plus the previous comparable
run ID for the same URL and exact scenario. It does not compute a semantic diff yet.

PostgreSQL stores authoritative metadata; private S3-compatible storage holds viewport/full-page
screenshots, rendered DOM, manifests, and their hashes. No public artifact URLs are created.

`BROWSER_ALLOW_PRIVATE_NETWORKS` defaults to `false` and must remain false outside controlled
tests. The application validates DNS destinations and intercepts browser requests, but production
deployment still requires network-level egress enforcement to cover DNS rebinding and browser
runtime failures. B2 does not perform consent actions, authenticate, bypass paywalls, click ads,
submit forms, run stealth, or make diff/event/incident/AI judgments.

Apply or inspect migrations independently:

```bash
make migrate
uv --directory backend run alembic current
uv --directory backend run alembic history
```

## Health endpoints

- `GET /health/live` checks process liveness only.
- `GET /health/ready` checks PostgreSQL and object-storage readiness without returning credentials or connection strings.

## Validation

```bash
make check
make test-integration
```

If Docker is unavailable, run the local unit/lint/build checks and rely on GitHub Actions for PostgreSQL and MinIO integration validation. Do not treat skipped integration tests as passing local integration tests.

## Common setup failures

- A readiness `503` means PostgreSQL or MinIO is unavailable; liveness at `/health/live` remains independent.
- Port conflicts on `5432`, `9000`, or `9001` require stopping the conflicting local service or changing the local Compose mapping and matching `.env` value.
- A locked-install failure means the manifest and lockfile differ; regenerate the relevant lockfile intentionally and include both changes in review.
- Migration errors should be investigated before retrying. Destructive downgrades are only for disposable local or CI databases.
- The values in `.env.example` and Compose are local-only placeholders, never production credentials.

## Repository boundaries

EP-003 adds repeatable six-hour-compatible desktop/mobile checkpoints and deterministic scroll
interactions. No provider connector, semantic diff, event, incident, LLM, consent action, or
production authentication behavior is implemented here.
