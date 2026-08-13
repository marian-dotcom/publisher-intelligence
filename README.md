# Publisher Incident Intelligence

Repository foundation for a publisher operational-memory and incident-intelligence platform.

The product contracts live in the root Markdown files. Engineering work follows `AGENTS.md`, `DECISIONS.md`, `PLANS.md`, and the active ExecPlan under `plans/`.

## Prerequisites

- Python 3.12
- `uv`
- Node.js 24 LTS
- `pnpm` 11
- Docker with Compose for PostgreSQL and MinIO integration checks

## Local setup

```bash
cp .env.example .env
docker compose up -d postgres minio minio-init
uv --directory backend sync --all-groups --locked
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

The browser-worker is deliberately a placeholder in EP-001:

```bash
uv --directory backend run python -m app.browser_worker --once
```

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

EP-001 establishes infrastructure only. Browser evidence collection begins in EP-002. No provider connector, event, incident, LLM, or production authentication behavior is implemented here.
