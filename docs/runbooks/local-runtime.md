# EP-026 Local Production-Like Runtime

Docker Compose topology that runs the real application processes from this
repository: `api`, `frontend`, `scheduler`, `worker`, and scalable
`browser-worker` replicas, on top of the canonical PostgreSQL + MinIO
infrastructure. One shared backend image runs every backend process type
(ADR-078 / ADR-083). No Kubernetes (ADR-084); simple deployment (ADR-087).

This runtime is for local/technical-preview use. It is NOT production, NOT a
Limited Pilot, and does not satisfy the M7 live HTTPS smoke.

## Quick start

```bash
docker compose up -d --build           # builds + starts the full stack
docker compose up migrate              # alembic upgrade head (idempotent; auto-runs via dependency)
open http://localhost:3000             # frontend (same-origin API routing)
curl http://localhost:8000/health/live # API liveness
```

Scale browser workers:

```bash
BROWSER_WORKER_REPLICAS=3 docker compose up -d --scale browser-worker=3 browser-worker
```

## Same-origin routing

The frontend intentionally calls the API with relative same-origin paths.
`frontend/lib/backend-rewrites.ts` forwards ONLY backend-owned prefixes
(`/auth`, `/health`, `/investigations`, `/product`, `/timeline`, `/incidents`,
`/evidence`) to `BACKEND_INTERNAL_URL` (default `http://api:8000`). The browser
sees one origin; cookies/CSRF semantics are unchanged; no CORS is added. The
prefix list is unit-tested (`frontend/tests/backend-rewrites.test.ts`) against
the actual FastAPI routers.

## Resource profiles

Limits are per-service Compose `deploy.resources.limits` values driven by
environment variables (see `.env.example`). Browser-worker resources are
explicit and independently tunable because Chromium dominates memory.

| Profile | Total envelope | Suggested env |
|---|---|---|
| SMALL (≈2 CPU / 4 GB) | api .5c/512M · worker .5c/384M · scheduler .25c/256M · browser 1c/1.5G · frontend .5c/512M · infra ~1G | `BROWSER_CPU_LIMIT=1.0 BROWSER_MEMORY_LIMIT=1536M WORKER_CPU_LIMIT=.5 …` |
| MEDIUM (≈4 CPU / 8 GB) | double per-service limits | `BROWSER_CPU_LIMIT=1.5 BROWSER_MEMORY_LIMIT=2048M` |
| ORACLE-FREE TARGET (≈2 CPU / 12 GB) | SMALL limits with larger RAM headroom | `BROWSER_MEMORY_LIMIT=2048M` |

Copy `.env.example` → `.env` and adjust before `docker compose up`.

## Browser-worker concurrency (N = 1/2/3)

One browser-worker process claims at most one BROWSER_CHECKPOINT job at a
time. Replicas share the PostgreSQL JobQueue; `FOR UPDATE SKIP LOCKED`
prevents duplicate claims; lease heartbeat + fencing tokens make retries and
crash recovery safe; all lease math uses DB server time. Scaling is therefore
purely `--scale browser-worker=N`. No Redis/Celery/RQ — by design.

## Benchmark harness (run on your Mac)

Target must be a controlled page (never arbitrary external sites).

```bash
# 0. stack up with N workers
BROWSER_WORKER_REPLICAS=N BROWSER_ALLOW_PRIVATE_NETWORKS=true \
  docker compose up -d --build browser-worker benchmark-target migrate api scheduler frontend

# 1. start the controlled target (serves deterministic pages on :8099)
docker compose up -d benchmark-target

# 2. enqueue K diagnostic checkpoints through the REAL production CLI path
for i in $(seq 1 12); do
  docker compose exec api uv run python -m app.browser_cli register-and-enqueue \
    --tenant-slug bench --tenant-name Bench --publisher-name BenchPub \
    --site-name BenchSite --url http://benchmark-target:8099/
done

# 3. watch drain (operations endpoint)
curl -s localhost:8000/product/operations | jq '.queue'

# 4. resource sampling in another terminal
docker stats --no-stream
docker compose ps
```

Results live in PostgreSQL; export them after drain:

```bash
docker compose exec postgres psql -U publisher -d publisher_intelligence -c "
SELECT status, count(*),
       percentile_cont(0.5) WITHIN GROUP (ORDER BY completed_at-started_at) AS p50,
       percentile_cont(0.95) WITHIN GROUP (ORDER BY completed_at-started_at) AS p95,
       max(completed_at-started_at) AS max_duration,
       sum(attempt_count) FILTER (WHERE attempt_count > 1) AS retried_attempts
FROM checkpoint_runs GROUP BY status;"
```

Repeat Run A/B/C with `BROWSER_WORKER_REPLICAS=1|2|3` (full down/up between
runs keeps results comparable). Record numbers yourself — none are precomputed
here.

## Local Technical Preview (NOT Limited Pilot)

Clearly non-production procedure:

- **2h smoke**: stack stays up; every 15 min check `/product/operations`
  (scheduler CURRENT, workers non-stale, queue draining), one manual
  diagnostic checkpoint completes COMPLETE.
- **24h**: add scheduled checkpoints each 6h window (desktop+mobile);
  verify retention ENFORCE_RETENTION job created once/day and processed;
  confirm no stale leases accumulate; MinIO objects persist across restarts.
- **72h** (optional): continue 24h pattern; restart one browser-worker mid-run
  to exercise lease reclaim; confirm source-health states stay truthful.

Boundary — allowed during preview:
public unauthenticated publisher pages with consent; controlled checkpoints;
real evidence generation; functional investigations; connector credential
tests only through approved secret mechanisms.

NOT proven locally (and explicitly out of scope):
public production HTTPS; stable outbound egress identity; publisher IP
allowlisting; 24/7 reliability; production secrets posture; disaster recovery;
Limited Pilot readiness. This preview never substitutes for the M7 live HTTPS
secure-cookie smoke.

## Portability guardrails

No Oracle/OVH/Railway/Fly-specific application code; no provider queues or DB
APIs; storage stays behind the existing S3 abstraction; no host-path
dependencies outside named volumes. Moving to any Linux VM is
deployment/configuration work only.

## Verified locally (2026-08-25)

The following was executed end-to-end on the development Mac:

- All images built (`api`, `frontend`, `scheduler`, `worker`, `migrate`,
  `browser-worker`, plus `benchmark-target`).
- Full stack started with `BROWSER_WORKER_REPLICAS=2`; every service healthy.
- `/health/ready` = database:true, object_storage:true.
- Same-origin routing proven: `GET /login` 200 via frontend;
  `GET /auth/session` through :3000 reaches FastAPI (401 when anonymous).
- Staging fail-closed re-proven on the real path: `ENVIRONMENT=staging`
  without `COOKIE_SECURE=true` ⇒ settings refuse to boot AND login emits zero
  cookies (500); with `COOKIE_SECURE=true` ⇒ login emits
  `pi_session` (`Secure; HttpOnly; SameSite=lax; Path=/`) and
  `pi_csrf` (`Secure; SameSite=lax; Path=/`, JS-readable); authenticated
  `/product/home/status` = 200; `/product/operations` reports scheduler
  CURRENT / workers CURRENT / retention HEALTHY.
- Real browser checkpoints completed through browser-worker replicas against
  the controlled `benchmark-target` service (5 COMPLETE, 0 retries,
  queue drained to 0 pending).
- Chromium launches sandbox-enabled as non-root `appuser`
  (`PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright`).
- `--scale browser-worker=3` verified (three replica containers).

Operational notes baked into the files above:

- Runtime commands use `/app/.venv/bin` binaries directly (never `uv run` at
  container runtime — the venv is root-owned read-only for `appuser`).
- Benchmark runs require `BROWSER_ALLOW_PRIVATE_NETWORKS=true` for the whole
  backend (URL validation happens in the API), controlled targets only.
- The local runtime Postgres volume is `postgres-local-runtime` — a fresh
  volume kept separate from the quarantined legacy
  `publisher-intelligence_postgres-data`.
- When your machine's port 5432 is taken by another Postgres, use a small
  compose override file to drop that host port mapping for the smoke.
