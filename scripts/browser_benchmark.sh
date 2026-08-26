#!/usr/bin/env bash
# EP-026 local browser-worker benchmark harness (run on your own machine).
# Usage: BROWSER_WORKERS=N JOBS=K ./scripts/browser_benchmark.sh
#
# Requires: Docker, the compose stack, and a CONTROLLED target only.
# Queue drain is observed via direct PostgreSQL queries against the exact
# benchmark job ids (the authenticated /product/operations endpoint is NOT
# used anonymously, and no auth is bypassed).
set -euo pipefail

N="${BROWSER_WORKERS:-1}"
K="${JOBS:-12}"
# Optional extra compose override file (e.g. to drop host port mappings when
# another local Postgres owns 5432). Set COMPOSE_OVERRIDE=/path/to/file.yml.
COMPOSE_FILES=(-f "$(dirname "$0")/../compose.yaml")
if [ -n "${COMPOSE_OVERRIDE:-}" ]; then COMPOSE_FILES+=(-f "${COMPOSE_OVERRIDE}"); fi
dc() { docker compose "${COMPOSE_FILES[@]}" "$@"; }
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-600}"
POLL_INTERVAL="${POLL_INTERVAL:-10}"

echo "== benchmark: ${N} browser-worker(s), ${K} checkpoints =="

BROWSER_WORKER_REPLICAS="${N}" BROWSER_ALLOW_PRIVATE_NETWORKS=true \
  dc up -d --build --force-recreate browser-worker benchmark-target migrate api scheduler frontend

JOB_IDS_FILE="$(mktemp)"
trap 'rm -f "${JOB_IDS_FILE}"' EXIT

echo "== enqueueing ${K} checkpoints through the real production CLI =="
for i in $(seq 1 "${K}"); do
  out=$(dc exec -T api python -m app.browser_cli register-and-enqueue \
    --tenant-slug "bench-${N}" --tenant-name Bench --publisher-name BenchPub \
    --site-name BenchSite --url http://benchmark-target:8099/)
  job_id=$(printf '%s' "${out}" | python3 -c 'import json,sys;print(json.load(sys.stdin)["job_id"])')
  echo "${job_id}" >> "${JOB_IDS_FILE}"
done
echo "enqueued $(wc -l < "${JOB_IDS_FILE}") jobs"

ids_sql=$(paste -sd, "${JOB_IDS_FILE}" | sed 's/[^,]*/'\''&'\''/g')

state_sql="SELECT count(*) FILTER (WHERE status IN ('PENDING','RETRY')),
       count(*) FILTER (WHERE status = 'RUNNING'),
       count(*) FILTER (WHERE status IN ('COMPLETE','FAILED')),
       bool_and(status IN ('COMPLETE','FAILED'))
FROM jobs WHERE id IN (${ids_sql})"

deadline=$((SECONDS + TIMEOUT_SECONDS))
while true; do
  stats=$(dc exec -T postgres psql -U publisher -d publisher_intelligence -tAc "${state_sql}")
  if [ -z "${stats}" ]; then
    echo "FATAL: could not read queue state from PostgreSQL" >&2
    exit 1
  fi
  IFS='|' read -r runnable in_progress terminal all_terminal <<< "${stats}"
  echo "$(date +%H:%M:%S) runnable=${runnable} in_progress=${in_progress} terminal=${terminal}"
  if [ "${all_terminal}" = "t" ]; then
    echo "== batch drained: ${terminal}/${K} reached a terminal state =="
    break
  fi
  if [ "${SECONDS}" -ge "${deadline}" ]; then
    dc exec -T postgres psql -U publisher -d publisher_intelligence -c \
      "SELECT id, status, attempt FROM jobs WHERE id IN (${ids_sql});"
    echo "FATAL: timeout after ${TIMEOUT_SECONDS}s — batch not drained" >&2
    exit 1
  fi
  sleep "${POLL_INTERVAL}"
done

echo "== results (checkpoint_runs for this batch) =="
dc exec -T postgres psql -U publisher -d publisher_intelligence -c "
SELECT r.status,
       count(*) AS runs,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY r.completed_at - r.started_at) AS p50,
       percentile_cont(0.95) WITHIN GROUP (ORDER BY r.completed_at - r.started_at) AS p95,
       max(r.completed_at - r.started_at) AS max_duration,
       coalesce(sum(r.attempt_count) FILTER (WHERE r.attempt_count > 1), 0) AS retried_attempts,
       count(*) FILTER (WHERE j.status = 'RUNNING') AS lease_reclaimed_now_running
FROM checkpoint_runs r JOIN jobs j ON j.payload->>'checkpoint_run_id' = r.id::text
WHERE j.id IN (${ids_sql})
GROUP BY r.status ORDER BY r.status;
SELECT id, status, attempt, locked_by FROM jobs WHERE id IN (${ids_sql}) ORDER BY created_at;"

echo "== resource snapshot (record on your Mac) =="
docker stats --no-stream
echo "Host load/swap: uptime; sysctl vm.swapusage (macOS)."
echo "== done =="
