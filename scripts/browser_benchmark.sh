#!/usr/bin/env bash
# EP-026 local browser-worker benchmark harness (run on your own machine).
#
# Measurement definition (identical for N=1/N=2/N=3):
#   1. infra + api + scheduler + frontend + controlled target come up;
#   2. browser-worker replicas are forced to ZERO;
#   3. the full benchmark batch is enqueued through the REAL production CLI;
#   4. exact job ids are captured and verified non-terminal (backlog proof);
#   5. drain-start timestamp is taken, then EXACTLY N workers start;
#   6. the batch is observed via direct PostgreSQL queries until every job is
#      terminal; periodic docker-stats samples are collected DURING the run;
#   7. drain-end timestamp stops the measurement.
# Drain wall time therefore includes worker startup after the benchmark start
# and excludes image build / container pre-start / enqueue time.
#
# Queue observation uses direct PostgreSQL queries scoped to this batch's job
# ids — never anonymous API calls; explicit timeout; hard failure on unreadable
# state. Requires a CONTROLLED target only.
set -euo pipefail

N="${BROWSER_WORKERS:-1}"
K="${JOBS:-60}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-900}"
POLL_INTERVAL="${POLL_INTERVAL:-5}"
SAMPLE_INTERVAL="${SAMPLE_INTERVAL:-1}"

# EP-026 M7 support: benchmark resource profiles are EXPLICIT AND ENFORCED.
# The chosen BENCHMARK_PROFILE maps to exact Compose limit variables BEFORE any
# service is created, and the created containers are verified against them.
# Concurrency comparison contract: N=1/N=2/N=3 all use MEDIUM.
# SMALL BROWSER_WORKERS=1 is the cheap 2CPU/4GB candidate experiment.
case "${BENCHMARK_PROFILE:-MEDIUM}" in
  SMALL)
    export API_CPU_LIMIT="0.30" API_MEMORY_LIMIT="512M"
    export FRONTEND_CPU_LIMIT="0.25" FRONTEND_MEMORY_LIMIT="384M"
    export SCHEDULER_CPU_LIMIT="0.10" SCHEDULER_MEMORY_LIMIT="192M"
    export WORKER_CPU_LIMIT="0.30" WORKER_MEMORY_LIMIT="320M"
    export BROWSER_CPU_LIMIT="0.70" BROWSER_MEMORY_LIMIT="1536M"
    export POSTGRES_CPU_LIMIT="0.20" POSTGRES_MEMORY_LIMIT="512M"
    export MINIO_CPU_LIMIT="0.10" MINIO_MEMORY_LIMIT="256M"
    ;;
  MEDIUM)
    export API_CPU_LIMIT="0.50" API_MEMORY_LIMIT="512M"
    export FRONTEND_CPU_LIMIT="0.40" FRONTEND_MEMORY_LIMIT="400M"
    export SCHEDULER_CPU_LIMIT="0.20" SCHEDULER_MEMORY_LIMIT="256M"
    export WORKER_CPU_LIMIT="0.50" WORKER_MEMORY_LIMIT="512M"
    export BROWSER_CPU_LIMIT="0.50" BROWSER_MEMORY_LIMIT="1280M"
    export POSTGRES_CPU_LIMIT="0.50" POSTGRES_MEMORY_LIMIT="512M"
    export MINIO_CPU_LIMIT="0.25" MINIO_MEMORY_LIMIT="320M"
    ;;
  ORACLE_FREE)
    # Honest note: at N>=2 the browser replicas exceed this 2-CPU nominal
    # envelope; expect throttling. RAM headroom is generous.
    export API_CPU_LIMIT="0.30" API_MEMORY_LIMIT="512M"
    export FRONTEND_CPU_LIMIT="0.25" FRONTEND_MEMORY_LIMIT="384M"
    export SCHEDULER_CPU_LIMIT="0.10" SCHEDULER_MEMORY_LIMIT="192M"
    export WORKER_CPU_LIMIT="0.30" WORKER_MEMORY_LIMIT="320M"
    export BROWSER_CPU_LIMIT="0.70" BROWSER_MEMORY_LIMIT="2048M"
    export POSTGRES_CPU_LIMIT="0.20" POSTGRES_MEMORY_LIMIT="1024M"
    export MINIO_CPU_LIMIT="0.10" MINIO_MEMORY_LIMIT="256M"
    ;;
  *)
    echo "FATAL: unknown BENCHMARK_PROFILE '${BENCHMARK_PROFILE}' (expected SMALL|MEDIUM|ORACLE_FREE)" >&2
    exit 2
    ;;
esac
PROFILE="${BENCHMARK_PROFILE:-MEDIUM}"

COMPOSE_FILES=(-f "$(dirname "$0")/../compose.yaml")
if [ -n "${COMPOSE_OVERRIDE:-}" ]; then COMPOSE_FILES+=(-f "${COMPOSE_OVERRIDE}"); fi
dc() { docker compose "${COMPOSE_FILES[@]}" "$@"; }

# Benchmark-only opt-in: URL validation for the controlled target happens in
# the API, and browser egress reaches the compose-internal fixture service.
# NEVER enable this flag for real publisher monitoring.
export BROWSER_ALLOW_PRIVATE_NETWORKS=true

echo "== benchmark: N=${N} workers, K=${K} jobs, BENCHMARK_PROFILE=${PROFILE} =="

# --- phase 1: runtime without browser workers -------------------------------
dc up -d migrate api scheduler worker frontend benchmark-target postgres minio minio-init
# Force browser-worker replicas to ZERO (also stops leftovers from previous
# runs) so enqueue happens without any consumer racing the producer.
dc --profile browser up -d --scale browser-worker=0 --no-deps browser-worker
# Wait for the one-off migration runner to exit successfully (poll: compose
# 'wait' is unreliable for already-exited one-offs).
migrate_state=""
for _ in $(seq 1 60); do
  migrate_state=$(dc ps -a --format '{{.Service}} {{.State}} {{.ExitCode}}' \
    | awk '$1 == "migrate" {print $2, $3}' | head -n 1)
  if [ "${migrate_state}" = "exited 0" ]; then break; fi
  sleep 2
done
if [ "${migrate_state}" != "exited 0" ]; then
  echo "FATAL: migrations did not complete cleanly (state=${migrate_state:-missing})" >&2
  exit 1
fi
echo "== migrations applied =="

# --- phase 2: enqueue the full batch BEFORE any worker exists ---------------
JOB_IDS_FILE="$(mktemp)"
trap 'rm -f "${JOB_IDS_FILE}"; [ -n "${SAMPLE_PID:-}" ] && kill "${SAMPLE_PID}" 2>/dev/null || true' EXIT

for i in $(seq 1 "${K}"); do
  out=$(dc exec -T api python -m app.browser_cli register-and-enqueue \
    --tenant-slug "bench-${N}" --tenant-name Bench --publisher-name BenchPub \
    --site-name BenchSite --url http://benchmark-target:8099/)
  job_id=$(printf '%s' "${out}" | python3 -c 'import json,sys;print(json.load(sys.stdin)["job_id"])')
  echo "${job_id}" >> "${JOB_IDS_FILE}"
done
enqueued=$(wc -l < "${JOB_IDS_FILE}")
if [ "${enqueued}" -ne "${K}" ]; then
  echo "FATAL: enqueued ${enqueued}/${K} jobs" >&2
  exit 1
fi

ids_sql=$(paste -sd, "${JOB_IDS_FILE}" | sed 's/[^,]*/'\''&'\''/g')

# --- phase 3: prove backlog exists before timing ----------------------------
backlog=$(dc exec -T postgres psql -U publisher -d publisher_intelligence -tAc \
  "SELECT count(*) FROM jobs WHERE id IN (${ids_sql}) AND status = 'PENDING'")
if [ "${backlog}" != "${K}" ]; then
  echo "FATAL: expected ${K} PENDING benchmark jobs before timing, saw ${backlog}" >&2
  exit 1
fi
echo "== backlog verified: ${K} runnable jobs waiting; starting ${N} worker(s) =="

# --- phase 4: resource sampling DURING the timed drain ----------------------
SAMPLES_FILE="$(mktemp)"
(
  while :; do
    dc stats --no-stream --format '{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}' \
      | grep 'publisher-intelligence' \
      | while IFS=$'\t' read -r name cpu mem; do echo "$(date +%H:%M:%S)|${name}|${cpu}|${mem}"; done \
      >> "${SAMPLES_FILE}"
    sleep "${SAMPLE_INTERVAL}"
  done
) &
SAMPLE_PID=$!

drain_start_epoch=$(date +%s)

# --- phase 5: start exactly N browser-worker replicas -----------------------
dc --profile browser up -d --no-deps --scale browser-worker="${N}" browser-worker

# --- verify the created containers actually received the profile limits ------
# Resolve live containers via Compose service identity (never ordinals),
# then verify every resolved container against the profile limits using the
# shared helper (scripts/benchmark_verify.py).
python3 "$(dirname "$0")/benchmark_verify.py" "${PROFILE}" "${N}" "${COMPOSE_FILES[@]}"
verify_status=$?
if [ "${verify_status}" -ne 0 ]; then
  echo "FATAL: resource-limit verification failed" >&2
  exit 1
fi


# --- phase 6: observe this exact batch until terminal -----------------------
state_sql="SELECT count(*) FILTER (WHERE status IN ('PENDING','RETRY')),
       count(*) FILTER (WHERE status = 'RUNNING'),
       count(*) FILTER (WHERE status IN ('COMPLETE','FAILED')),
       bool_and(status IN ('COMPLETE','FAILED'))
FROM jobs WHERE id IN (${ids_sql})"

deadline=$((drain_start_epoch + TIMEOUT_SECONDS))
while true; do
  stats=$(dc exec -T postgres psql -U publisher -d publisher_intelligence -tAc "${state_sql}")
  if [ -z "${stats}" ]; then
    echo "FATAL: could not read queue state from PostgreSQL" >&2
    exit 1
  fi
  IFS='|' read -r runnable in_progress terminal all_terminal <<< "${stats}"
  echo "$(date +%H:%M:%S) runnable=${runnable} in_progress=${in_progress} terminal=${terminal}"
  if [ "${all_terminal}" = "t" ]; then
    break
  fi
  now_epoch=$(date +%s)
  if [ "${now_epoch}" -ge "${deadline}" ]; then
    dc exec -T postgres psql -U publisher -d publisher_intelligence -c \
      "SELECT id, status, attempt, locked_by FROM jobs WHERE id IN (${ids_sql});"
    echo "FATAL: timeout after ${TIMEOUT_SECONDS}s — batch not drained" >&2
    exit 1
  fi
  sleep "${POLL_INTERVAL}"
done

drain_end_epoch=$(date +%s)
kill "${SAMPLE_PID}" 2>/dev/null || true
wait "${SAMPLE_PID}" 2>/dev/null || true

drain_wall=$((drain_end_epoch - drain_start_epoch))
throughput=$(python3 -c "print(round(${terminal} / max(1, ${drain_wall}), 3))")

# --- phase 7: batch-scoped results ------------------------------------------
echo "== summary =="
echo "workers=${N}"
echo "jobs=${K}"
dc exec -T postgres psql -U publisher -d publisher_intelligence -c "
SELECT j.status,
       count(*) AS jobs,
       coalesce(sum(r.attempt_count) FILTER (WHERE r.attempt_count > 1), 0) AS retries,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY r.completed_at - r.started_at) AS checkpoint_p50,
       percentile_cont(0.95) WITHIN GROUP (ORDER BY r.completed_at - r.started_at) AS checkpoint_p95,
       max(r.completed_at - r.started_at) AS checkpoint_max,
       count(*) FILTER (WHERE j.status = 'RUNNING') AS lease_reclaimed_now_running
FROM jobs j LEFT JOIN checkpoint_runs r ON j.payload->>'checkpoint_run_id' = r.id::text
WHERE j.id IN (${ids_sql})
GROUP BY j.status ORDER BY j.status;"
echo "drain_wall_seconds=${drain_wall}"
echo "jobs_per_second=${throughput}"

python3 "$(dirname "$0")/benchmark_stats.py" "${SAMPLES_FILE}"
echo "raw_samples_file=${SAMPLES_FILE}"
echo "== done =="
