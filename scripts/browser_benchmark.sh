#!/usr/bin/env bash
# EP-026 local browser-worker benchmark harness (run on your own machine).
# Usage: BROWSER_WORKERS=N JOBS=K ./scripts/browser_benchmark.sh
# Requires: Docker, the compose stack, and a controlled target only.
set -euo pipefail

N="${BROWSER_WORKERS:-1}"
K="${JOBS:-12}"

echo "== benchmark: ${N} browser-worker(s), ${K} checkpoints =="
BROWSER_WORKER_REPLICAS="${N}" BROWSER_ALLOW_PRIVATE_NETWORKS=true \
  docker compose up -d --build --force-recreate browser-worker benchmark-target migrate api scheduler frontend
for i in $(seq 1 "${K}"); do
  docker compose exec -T api uv run python -m app.browser_cli register-and-enqueue \
    --tenant-slug "bench-${N}" --tenant-name Bench --publisher-name BenchPub \
    --site-name BenchSite --url http://benchmark-target:8099/ >/dev/null
done

echo "== drain watch (queue.runnable) =="
for i in $(seq 1 120); do
  runnable=$(curl -fsS http://localhost:8000/product/operations | python3 -c 'import json,sys;print(json.load(sys.stdin)["queue"]["runnable"])' || echo "?")
  echo "t=${i}0s runnable=${runnable}"
  [ "${runnable}" = "0" ] && break
  sleep 10
done

echo "== results (checkpoint_runs) =="
docker compose exec -T postgres psql -U publisher -d publisher_intelligence -c "
SELECT status,
       count(*) AS runs,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY completed_at - started_at) AS p50,
       percentile_cont(0.95) WITHIN GROUP (ORDER BY completed_at - started_at) AS p95,
       max(completed_at - started_at) AS max_duration,
       coalesce(sum(attempt_count) FILTER (WHERE attempt_count > 1), 0) AS retried_attempts
FROM checkpoint_runs WHERE monitored_url_id IN (
  SELECT id FROM monitored_urls WHERE url LIKE '%benchmark-target%'
) GROUP BY status ORDER BY status;
SELECT count(*) AS jobs_total FROM jobs WHERE job_type = 'BROWSER_CHECKPOINT';"

echo "== resource snapshot =="
docker stats --no-stream
echo "Record host load/swap manually if desired: uptime; sysctl vm.swapusage (macOS)."
echo "== done =="
