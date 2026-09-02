# EP-030 — Per-Site Monitoring Controls

**Status:** READY — M0 COMPLETE (planning/feasibility only); **M1 COMPLETE** (data model + authenticated control API); M2–M4 NOT STARTED; Gate P HUMAN GATE / UNAUTHORIZED; Limited Pilot NOT GRANTED
**Owner:** Codex / Engineering
**Created / Updated:** 2026-09-02 (M1 validated this date)
**Base commit:** `a92da909c53c0618b4671bd569b4a1937a935c27` (origin/main; EP-029 M4 merged)
**MVP scope impact:** NO
**External publisher onboarding:** OUT OF SCOPE
**Scheduler restart / deployment / live validation:** NOT AUTHORIZED (see §6.3)
**Run diagnostic now:** DEFERRED / UNNUMBERED (see §4.2)

## 1. Purpose, Scope, Non-Goals

### 1.1 Purpose

Authenticated `ADMIN` operators can enable/disable the fixed six-hour `SCHEDULED` browser
monitoring per tenant-owned site from the existing Home surface, fail-closed, with truthful
disable semantics and no backfill. Core invariants: explicit per-site `ON`/`OFF`; existing and
new sites default `OFF`; `ON` starts at the next strictly-future six-hour boundary; no disabled-
period backfill; evidence immutable; operator-facing semantics truthful.

### 1.2 Scope In

- `sites` monitoring state (`OFF` default) + append-only state-transition audit;
- one idempotent `PUT` enable/disable command (ADMIN + CSRF + actor tenant);
- scheduler gate (GATE-1) + transactional materialization re-check with site-row lock (GATE-2)
  + worker pre-flight (GATE-3) with terminal `SKIPPED` for `SCHEDULED` runs;
- minimal Home UI: monitoring status and Enable/Disable with confirmation, "Every 6 hours",
  next boundary, monitoring-vs-health separation;
- additive migration (two `sites` columns + one audit table + `SKIPPED` status value);
- backfill of all existing sites to `OFF` (`evz.ro`, `climatologie.ro` included);
- acceptance tests (§8) — isolated fixtures only, no real publisher contact.

### 1.3 Scope Out / Non-Goals

Any connector change; window/run/evidence rewrite or deletion; a generic cancellation framework
or job-state-machine rework; holding a DB lock across browser/network I/O; client tenant
selection; new surfaces/design system/dependencies; LLM in the control path; `CrUX`/`PSI`;
per-URL scheduling or cadence changes; a persisted `PAUSING` state or UI presentation state;
window-status-model redesign; "Run diagnostic now"; Gate P / Limited Pilot / staging deploy /
scheduler restart / real-site validation; creating EP-031/EP-032 plans. This is an internal
operator control, not publisher self-service.

## 2. Verified Current Behavior

Authoritative base `a92da909…`. Staging scheduler **STOPPED** (2026-08-30T13:37:08Z);
scheduled monitoring **NOT AUTHORIZED**; Gate P **HUMAN GATE**; Limited Pilot **NOT GRANTED**;
deployed app commit `b61494bb…`. `evz.ro` must stay disabled from scheduled monitoring;
`climatologie.ro` registered with no further diagnostic/contact authorized; manual incident
`ed528705-…` OPEN and untouched; `77a64afd-…` non-persisted. Migration head:
`0028_operator_ui_trigger_source`.

| Area | Fact | Reference |
|---|---|---|
| Site | plain `status` String (no CHECK); `timezone`; `UNIQUE(tenant_id, canonical_domain)`; no monitoring/schedule column | `models.py:53-71` (`:55`, `:67`) |
| Scheduler | `SIX_HOUR_BOUNDARIES=(0,6,12,18)`; local floor via `checkpoint_window_for`; `schedule_due` selects `status=="ACTIVE"`; window/run uniqueness | `scheduling.py:28`, `:62-74`, `:93`, `:104`, `:269`, `:319` |
| Worker | `begin_attempt` locks run `FOR UPDATE`, raises if finalized, sets RUNNING, creates attempt; finalize enqueues DERIVE | `persistence.py:288` (`:297`, `:305`, `:315`), `:515`, `:532` |
| Attempts | `checkpoint_attempts.status` plain String (no CHECK) | `models.py:305-324` (`:319`) |
| Runs | `ck_checkpoint_runs_status` CHECK `('PENDING','RUNNING','COMPLETE','PARTIAL','SITE_ERROR','BROWSER_ERROR','TIMEOUT','BLOCKED')`; provenance immutable post-creation | `models.py:208-212`, `:293-302` |
| FINAL set | `FINAL_CHECKPOINT_STATUSES` | `models.py:26-33` |
| Jobs | `ck_jobs_status` `('PENDING','RUNNING','RETRY','COMPLETE','FAILED')` | `db/models.py:44` |
| Health | `_BROWSER_BAD_STATUSES={SITE_ERROR,BROWSER_ERROR,TIMEOUT,BLOCKED}`; latest SCHEDULED run by `started_at desc` | `product.py:80`, `:84`, `:127-144` |
| Events | DERIVE input filters `observation_kind=="SCHEDULED"` | `events/persistence.py:145`, `:162` |
| Auth | `ActorContext`; `require_tenant`; `get_current_actor_with_csrf`; ADMIN/CSRF/404 pattern | `auth/dependencies.py:81`; `site_registration.py:31`, `:35` |
| Diagnostics | `register_and_enqueue` registration-coupled; `enqueue_incident_diagnostic` incident-bound | `service.py:82`, `:176` |
| Actor attribution | `incidents.created_by` = nullable plain uuid, no FK | `incidents/models.py:64` |
| Audit precedent | documented-but-unimplemented `operational_changes`; no composite-FK precedent; no `sites(tenant_id,id)` unique | migrations + §4.1 |
| Frontend | auth client-side only; Home `:36`; no ADMIN role gating; no confirmation pattern | `middleware.ts`; `frontend/app/(protected)/page.tsx:36` |

Accepting, out of scope: pre-existing `trigger_source` ORM drift (`models.py:218` vs migration
`0028`) — EP-029 §20 follow-up, untouched here.

## 3. Canonical References

`AGENTS.md` (§2.1/§7/§10/§16/§32) · `PLANS.md` §11/§62/§76.1 · `MVP.md` · `PRODUCT.md`
ADR-002 · `DECISIONS.md` ADR-010 (`:398-427`), ADR-011/012/101/102/130 · `SECURITY.md`
§160 (`:3025-3038`), §48 (`:1099-1113`), §49 (`:1115-1128`), §161 (`:3041-3053`) · `BROWSER.md`
· `DATA_MODEL.md` (`:407-417`, `:439-453`, `:542-557`, `:291-305`) · `plans/EP-028`
(supersedes auto-schedule-on-ACTIVE), `EP-029`, `EP-018`, `EP-002`, `EP-025a`, `EP-025b`,
`EP-026`, `EP-027`.

No new architecture ADR required: `ON`/`OFF` is an additive per-site authorization attribute
over the accepted ADR-010 cadence, not a change to observation semantics.

## 4. Canonical Decisions

### 4.1 Decision — State and data model

Per-site binary authorization `ON`/`OFF` governing only the six-hour `SCHEDULED` cadence,
orthogonal to lifecycle `status`. Deterministic next boundary computed, never stored.

**Final schema (single authoritative definition; = §6.1):**

```text
sites.monitoring_state             text NOT NULL server default 'OFF'
                                   CHECK (monitoring_state IN ('ON','OFF'))
sites.monitoring_state_updated_at  timestamptz NOT NULL server default now()
                                   changes only on a real OFF<->ON transition;
                                   serves as the enable watermark
sites UNIQUE (tenant_id, id)                        -- additive; composite-FK target

site_monitoring_state_changes (append-only)
    id          uuid PK default uuid4
    tenant_id   uuid NOT NULL FK tenants.id ON DELETE RESTRICT
    site_id     uuid NOT NULL  (no separate FK; paired via composite FK below)
    from_state  text NOT NULL CHECK IN ('ON','OFF')
    to_state    text NOT NULL CHECK IN ('ON','OFF')
    CHECK (from_state <> to_state)
    actor_id    uuid NOT NULL          -- canonical operator identity, no FK
    changed_at  timestamptz NOT NULL server default now()
    INDEX (tenant_id, site_id, changed_at)
    FOREIGN KEY (tenant_id, site_id) REFERENCES sites(tenant_id, id) ON DELETE RESTRICT
```

Explicitly not added: redundant actor column on `sites`; correlation/request identifier; custom
interval/cron; pause reason; speculative future states.

**Decisions — PK / FK / tenant–site integrity / actor identity (exact):**

- **Primary key:** single surrogate `id uuid` PK (`default uuid4`) — every repository table uses
  this; no composite PK anywhere. Exactly one PK; no contradictory composite-PK wording.
- **FKs:** `tenant_id` → `tenants.id` (RESTRICT). The `site_id` pairing is enforced by a single
  **composite FK `(tenant_id, site_id)` → `sites(tenant_id, id)`** (RESTRICT). Precedent check:
  no composite-FK precedent exists and `sites` has no `(tenant_id, id)` unique key, so this is
  the **smallest DB-enforced option (B)**: an additive `UNIQUE (tenant_id, id)` on `sites`
  (required as the FK target; redundant with PK(id) but harmless) plus the composite FK. A row
  combining tenant A with a site of tenant B cannot be inserted because no `sites` row has that
  `(tenant_id, id)` pair. This is the single new-table integrity guard; existing tables keep
  the canonical independent-FK + tenant-scoped-application-write convention, which is
  **not** changed.
- **Actor identity:** `actor_id uuid NOT NULL`, **no FK by design** — canonical identity is the
  authenticated operator id (uuid) written server-side only, mirroring the operator/incident
  provenance model (`incidents.created_by`, plain uuid, no FK). Operator lifecycle is separate;
  subject identifiers are not stored.
- **No audit rows** for migration-initialized `OFF` (no transition) or new-site registration
  (no transition); audit exists only for real `OFF↔ON` transitions.

`ensure_b2_configuration_for_active_sites()` may keep inspecting/configuring `ACTIVE` sites
regardless of monitoring state: configuration-only DB work, no publisher contact. Do not gate
it unless implementation inspection proves contact possible. `ACTIVE` = participates in the
product lifecycle; monitoring `OFF` = no new scheduled observation/contact authorization.

### 4.2 Decision — Enable / disable and the OFF contract

**Enable:** `ADMIN` + CSRF + actor tenant, one transaction (§4.3/§6). No immediate run, no
backfill. Eligible `SCHEDULED` window: local start `W`, enable instant local `E` =
`monitoring_state_updated_at.astimezone(tz)`, eligible iff `W > E` (strictly-future). Both sides
normalized through the site timezone via the single existing helper (`scheduling.py:62-74`); no
second boundary implementation and no API time string. Examples: enable 14:10 → first boundary
18:00; enable exactly at a boundary → deferred; 16:00 restart → no 12:00-window backfill;
disable 17:00 / re-enable 19:00 → schedules 00:00 next day, never 18:00; repeated enable never
moves the watermark. A disabled interval is never backfilled.

**Canonical OFF contract (single authoritative statement):**

> After the disable transaction completes: (1) OFF prevents new `SCHEDULED`
> window/run/job materialization; (2) OFF prevents queued/unclaimed `SCHEDULED` work that has
> not passed its final worker pre-flight from **initiating** publisher contact; (3) a run
> already claimed and past its final pre-flight, or already navigating, **may initiate or
> continue contact** after disable completes; (4) such a run **finalizes normally**;
> (5) its **evidence is retained**; (6) **no historical run, window, job, artifact, event, or
> incident is deleted, cancelled, rewritten, or misclassified**; (7) the **UI exposes that a
> current check is finishing**.

No immediate absolute cancellation is claimed; no DB lock spans browser/network I/O; no
cancellation framework; no persisted `PAUSING`.

**Idempotency / audit (one transaction, single authoritative rule):**

```text
Enable : UPDATE sites SET monitoring_state='ON', monitoring_state_updated_at=now()
         WHERE tenant_id=:t AND id=:site AND monitoring_state='OFF'
Disable: UPDATE sites SET monitoring_state='OFF', monitoring_state_updated_at=now()
         WHERE tenant_id=:t AND id=:site AND monitoring_state='ON'
rowcount == 1  -> append exactly one audit row (from_state,to_state,actor_id), commit together
rowcount == 0  -> tenant-owned-but-already-desired => return existing state idempotently
                  (no watermark move, no audit row); nonexistent/foreign => non-disclosing 404
```

The conditional `UPDATE` takes the site row lock; a concurrent second transition blocks then
matches nothing (rowcount 0). Winner only appends audit; exactly one real transition per race.
Repeated enable/disable are true no-ops.

**Run diagnostic now** — DEFERRED / UNNUMBERED. No clean reuse path exists
(`service.py:82` registration-coupled; `:176` incident-bound); extracting one is a bounded new
command best owned later. EP-031 remains reserved *only* as context for polished operator UI /
Site Overview; the diagnostic action is never named EP-031 and is revisited only after EP-030
closure under the one-active-ExecPlan rule.

### 4.3 Decision — API contract (canonical)

```text
PUT /product/sites/{site_id}/monitoring     body {"enabled": true|false}

ADMIN (actor.role, mirroring site_registration.py:35); CSRF required; tenant from actor only.
Unknown or cross-tenant site -> non-disclosing 404.  Non-boolean enabled -> 422.
GET (and Home projection) read-only; no action on GET; no generic site CRUD.

Response 200 (only what UI needs):
  { site_id, enabled, monitoring_state_updated_at,
    cadence: {"identifier":"six-hour","hours":6},
    next_scheduled_for: <ts>|null,
    in_flight_scheduled_run_status: "PENDING"|"RUNNING"|null }
```

No audit internals, actor IDs, credentials, or scheduling configuration in responses. `PUT`
because it sets one idempotent resource state.

### 4.4 Decision — UI contract (canonical)

Only `ON`/`OFF` persisted; all rendered states derived. Monitoring presentation (authorization):

- `Monitoring active` — `ON`;
- `Paused` — `OFF`, no in-flight/queued `SCHEDULED` run;
- `Paused — current check finishing` — `OFF` while `PENDING`/claimed/`RUNNING` `SCHEDULED` work
  may still complete (races R4/R5);
- `Monitoring state unavailable` — status read fail-closed; controls disabled until refreshed.

Source/browser health is a separate rendered status (healthy/degraded/unavailable/unknown),
never conflated: `ON` + health `UNAVAILABLE` shows `Monitoring active` **and** `Browser
Monitoring: UNAVAILABLE`. Show "Every 6 hours"; next boundary when `ON`, `—` when `OFF`; last
real observation independently; never display "no further contact" while in-flight work can
finish. Confirmations via native `<dialog>`; `ADMIN`-only client affordance (backend
authoritative); no new libraries/surfaces/redesign.

## 5. Scheduler / Worker Safety

### 5.1 Gates (single authoritative description)

```text
Scheduler tick -> GATE-1 due-site query: status='ACTIVE' AND monitoring_state='ON'
                  (window candidates via scheduling.py:62-74)
               -> GATE-2 materialization txn: lock tenant-owned sites row SELECT ... FOR UPDATE,
                  then require monitoring_state='ON' AND window_start_local > enable_instant_local
                  else materialize nothing; window/run/job created via existing uniqueness
               (window :269, run :319; queue idempotency_key dedup)

Worker claim  -> GATE-3 inside begin_attempt txn (persistence.py:288), only
                  observation_kind='SCHEDULED' (DIAGNOSTIC/OPERATOR_UI, INCIDENT_DIAGNOSTIC
                  unaffected):
                  lock tenant-owned sites row FOR UPDATE, re-read monitoring_state
                    ON        -> continue begin_attempt (run RUNNING, attempt RUNNING)
                    OFF/invalid-> atomically set run+attempt status='SKIPPED' (terminal),
                                 record limitation 'monitoring-disabled-before-execution',
                                 return explicit internal skip outcome
                  worker completes claimed job (COMPLETE); no navigation; no
                  finalize_terminal_failure; no retry; no DERIVE enqueue
```

Row locks are taken only in short commit-immediately transactions; never across
browser/network I/O. Unavoidable residual (accepted): after GATE-3 commits `ON`, disable may
commit before navigation starts; that run is in-flight (R4) — see OFF contract.

### 5.2 SKIPPED contract (single authoritative)

Terminal; zero navigation/network contact; not a publisher failure, browser failure, access
challenge, incident, or degradation evidence; completes the job with no retry; enqueues no
DERIVE; emits no event/anomaly/incident; excluded from `_BROWSER_BAD_STATUSES`
(`product.py:80`) and from latest-actual-observation selection (`product.py:127-144`), so the
previous real source-health observation is preserved; auditable as an administrative skip
(limitation id on the run + transition history in `site_monitoring_state_changes`). `BLOCKED`
stays reserved for genuine browser/access blocking; `COMPLETE`/`PARTIAL`/`SITE_ERROR`/
`BROWSER_ERROR`/`TIMEOUT` never encode an administrative skip.

Smallest bounded footprint: add `'SKIPPED'` to `ck_checkpoint_runs_status` (`models.py:208-212`)
and to `FINAL_CHECKPOINT_STATUSES` (`models.py:26-33`). `checkpoint_attempts.status` is plain
text (no CHECK) — no change. `jobs.status` CHECK unchanged. Provenance immutable guard
(`models.py:293-302`) untouched.

Accepted aggregator behavior (not redesigned): a window whose runs are all terminal non-
`BROWSER_ERROR` is `COMPLETE` (`_refresh_window_status`, `persistence.py:1031-1070`); a window
of only `SKIPPED` runs is therefore `COMPLETE` — `COMPLETE` = orchestration completed, not
observation succeeded. Events cannot be derived from it (`events/persistence.py:145,162`).

### 5.3 Race matrix (single authoritative R1–R7)

| # | Race | Guard | Contact | Run/job/window state | Evidence | UI |
|---|---|---|---|---|---|---|
| R1 | Scheduler selects ON → disable commits → materialize | GATE-2 site `FOR UPDATE` in materialize txn | Impossible | No window/run/job; audit ON→OFF | None created | Paused |
| R2 | SCHEDULED queued/unclaimed → disable → worker claims | GATE-3 in `begin_attempt` | Impossible | Run+attempt SKIPPED; job COMPLETE; no DERIVE | None created | Paused |
| R3 | Claim → disable → pre-flight | GATE-3 site `FOR UPDATE` serializes with disable UPDATE | Impossible if OFF wins (SKIPPED); else R4 | SKIPPED or normal run | None or normal | Paused / finishing |
| R4 | GATE-3 ON → disable → contact starts | None — accepted (no lock across I/O) | Possible | Normal terminal; job COMPLETE | Retained normally | Paused — current check finishing |
| R5 | Navigating → disable | None — accepted | Continues | Normal terminal | Retained, immutable | Paused — current check finishing |
| R6 | Enable vs Disable race | Conditional UPDATE + site row serialization; audit only on rowcount==1 | Impossible (state-setting) | One real transition; loser rowcount 0 | None affected | Final persisted state |
| R7 | Two scheduler processes | Window/run uniqueness (`:269/:319`) + queue idempotency + per-site lock | Single scheduled execution | One window/run/job per boundary | Single set | Monitoring active |

## 6. Migration / Downgrade / Deployment

### 6.1 Upgrade (additive)

1. `sites`: add the two monitoring columns + CHECK; add `UNIQUE (tenant_id, id)`.
2. Create `site_monitoring_state_changes` per §4.1 (single `id` PK; `tenant_id` FK; composite FK
   to `sites(tenant_id, id)` RESTRICT; from/to checks; `actor_id NOT NULL`; index).
3. `checkpoint_runs`: drop/re-add `ck_checkpoint_runs_status` to include `'SKIPPED'`.
4. Backfill: `monitoring_state` default `'OFF'` applies to all rows (`evz.ro`,
   `climatologie.ro` included); **no audit rows** written for migration defaults; no
   checkpoint/window/run/evidence mutation.

### 6.2 Guarded downgrade (canonical)

The ONLY accepted paths are guarded refusal, or a separately authorized non-destructive
archival/forward-fix decision.

Refuse while **any** of the following exist, because the downgrade removes the audit/state
schema and recreates the predecessor status constraint:

1. any rows in `site_monitoring_state_changes`;
2. any `sites.monitoring_state = 'ON'`;
3. **any `checkpoint_runs.status = 'SKIPPED'`** (the predecessor constraint cannot be recreated
   while SKIPPED rows exist).

Never rewrite `SKIPPED` to another status, delete run or audit history, silently flip `ON`→`OFF`,
or mutate evidence. Otherwise: drop the audit table, the two `sites` columns (with their
checks/unique), and restore the prior `ck_checkpoint_runs_status` without `'SKIPPED'`.
Rationale: without the guard, downgrade would restore EP-028 auto-schedule-on-`ACTIVE` and
re-risk unauthorized contact; the guard normally passes (scheduler STOPPED, all sites OFF,
no SKIPPED).

### 6.3 Deployment / authorization boundary (canonical, single statement)

- Implementation completion ≠ deployment; deployment ≠ scheduler restart; scheduler restart ≠
  enabling monitoring; enabling ≠ Gate P / Limited Pilot.
- Scheduled monitoring is NOT AUTHORIZED; Gate P = HUMAN GATE; Limited Pilot NOT GRANTED;
  consistent with EP-029 M4 status.
- Any future authorized restart requires all sites verified `OFF` first; real-site validation
  only under a separately authorized Gate activity; EP-030 performs none; staging deploy/restart
  are separately human-authorized.
- Migration may run before code deploy while the scheduler is STOPPED (no mixed-version
  scheduler exposure).

## 7. Milestones

- **M0 — Planning/feasibility (this document).** COMPLETE (planning only): accepted behavior +
  adversarial-review remediation + final consolidation reconciled; canonical planning complete;
  adversarial KISS/concurrency review complete; final human plan review accepted; no
  implementation performed or authorized.
- **M1 — Data model + control API.** Migration (§6.1), single `PUT` command (§4.3),
  audit/CSRF/tenant/role enforcement, idempotency tests.
- **M2 — Scheduler/worker safety.** GATE-1/2/3 (§5.1), `SKIPPED` (§5.2), source-health exclusion,
  R1–R7 and restart-safety tests.
- **M3 — Minimal operator controls.** Home status projection + Enable/Disable with confirmation
  (§4.4); projection-only staging smoke (no restart/contact).
- **M4 — Release-readiness.** Full §8 matrix green; migration up/down rehearsal; deployment
  boundary statement; docs/README reconciliation.

Milestones may split into smaller safe slices; must not merge into one mega-step. M1–M4 remain
**NOT STARTED**.

## 8. Acceptance Criteria and Test Matrix

All tests use isolated fixtures / disposable DB; no real publisher contact.

### OFF contract / races
- [ ] R1: disable before materialization → nothing created (GATE-2 with site `FOR UPDATE`).
- [ ] queued-before-disable → `SKIPPED`, no contact, job COMPLETE, no retry (R2).
- [ ] claimed-before-disable/pre-flight → `SKIPPED`, no contact (R3).
- [ ] pre-flight passed → disable commits → run may finish; UI `Paused — current check finishing` (R4).
- [ ] already navigating → disable → finishes normally, evidence retained (R5).
- [ ] in-flight run finalizes normally; no run/window/job/artifact/event/incident changed.

### State / watermark
- [ ] existing site `OFF` after upgrade; new registration `OFF` + one `DIAGNOSTIC`/`OPERATOR_UI`
  run; `Add site` keeps one-shot while `OFF`.
- [ ] enable → no immediate window/run; audit row appended (from/to).
- [ ] enable 14:10 → first boundary 18:00 (local, UTC-correct).
- [ ] enable exactly at boundary instant → boundary not claimed.
- [ ] 16:00 restart → no 12:00-window backfill.
- [ ] disable 17:00 / re-enable 19:00 → 00:00 next day, never 18:00.
- [ ] repeated enable: watermark unchanged, no audit duplicate; repeated disable: true no-op;
  audit row only on a real transition.
- [ ] missing/invalid state on read → `OFF` (fail closed), never `ON`.

### Scheduler / concurrency
- [ ] GATE-1 never selects `OFF` sites; GATE-2 never materializes pre-watermark windows
  (incl. current visible window).
- [ ] concurrent enable vs tick → no current-boundary creation; concurrent disable vs tick → no
  post-disable materialization, no duplicate windows/runs/jobs.
- [ ] disable-after-enqueue → `SKIPPED`; no DERIVE; no event/anomaly/incident; browser source
  health unchanged; latest-actual-observation ignores `SKIPPED`.
- [ ] two scheduler passes (simulated) → single window/run/job set (R7).
- [ ] `DIAGNOSTIC`/`OPERATOR_UI`, `INCIDENT_DIAGNOSTIC` unaffected.
- [ ] all-sites-OFF snapshot → scheduler creates nothing, exits cleanly.

### Auth / security
- [ ] non-ADMIN `403`; missing/invalid CSRF `403`; cross-tenant and unknown site non-disclosing
  `404`; non-boolean `enabled` `422`.
- [ ] no client tenant accepted; actor written server-side; audit append-only, tenant-owned, no
  secrets; cross-tenant audit combination is DB-impossible via composite FK (integrity test).

### Regression / evidence
- [ ] six-hour math + timezone/DST tests keep passing; provenance for `ON` sites unchanged;
  immutable-guard untouched by `SKIPPED`.
- [ ] enable/disable change no checkpoint evidence/windows/derived outputs; controls emit no
  event/anomaly/incident.
- [ ] migration up/down rehearsal passes; guarded downgrade refuses on audit rows, ON sites, and
  SKIPPED rows.

### Frontend
- [ ] only `Monitoring active`/`Paused`/`Paused — current check finishing`/`Monitoring state
  unavailable` render; monitoring vs health separate (`ON` + `Browser Monitoring: UNAVAILABLE`).
- [ ] "Every 6 hours"; boundary when `ON`, `—` when `OFF`; last observation independent; never
  claims "no further contact" while in-flight work may finish.
- [ ] confirmation required; cancel no-op; non-ADMIN hides controls; generic failure on
  cross-tenant/unauthorized; no new deps/surfaces.

## 9. Implementation File Map

- `models.py` — Site monitoring columns + `UNIQUE(tenant_id,id)`; `SiteMonitoringStateChange`;
  add `'SKIPPED'` to run status CHECK and `FINAL_CHECKPOINT_STATUSES`.
- `migrations/` — new additive migration (§6.1/§6.2).
- `browser/monitoring_control.py` (new, small) — `set_site_monitoring(enabled)`,
  `site_monitoring_status`.
- `browser/scheduling.py` — GATE-1 predicate (add `monitoring_state=='ON'` to site select at
  `:104`); GATE-2 site `FOR UPDATE` + watermark (§5.1/§4.2).
- `browser/persistence.py` (`begin_attempt` `:288`) + `browser/service.py` — GATE-3 pre-flight;
  skip outcome plumbing.
- `browser/browser_worker.py` — handle skip outcome: job COMPLETE, no retry/finalize/DERIVE.
- `api/...` — PUT endpoint + status projection (existing authenticated product home; no new area).
- `api/product.py` — latest-actual-observation selection excludes `SKIPPED`.
- `frontend/app/(protected)/page.tsx` + request helpers — §4.4.

## 10. Validation Ladder

- Repo hygiene: `git diff --check`; `python3 scripts/check_secrets.py`.
- Backend: targeted pytest for scheduler gating, control API, migration up/down, R1–R7
  concurrency, `SKIPPED`, tenant/CSRF (commands + counts recorded in §11).
- Existing checkpoint/scheduler/AP regression tests green (evidence with commands).
- Frontend: existing lint/typecheck + targeted component tests for §4.4.
- Migration rehearsal on a disposable copy of the staging schema snapshot: all sites `OFF`;
  guarded downgrade rehearsed; clean revert.
- CI: exact-head run of backend/frontend tasks on the merge target before merge.

## 11. Progress / Decision Log

- 2026-09-02: **M1 COMPLETE** (data model + authenticated per-site monitoring control API; branch
  `agent/ep-030-per-site-monitoring-controls`, Draft PR #38). Migration `0029_site_monitoring_controls`
  applies cleanly base→head: `sites.monitoring_state`/`_updated_at` default OFF, `UNIQUE(tenant_id,id)`,
  `site_monitoring_state_changes` append-only audit (composite FK, `from<>to`/state CHECKs), checkpoint
  `SKIPPED` added (no SKIPPED generation in M1); guarded downgrade refuses while audit rows exist, any
  site is ON, or SKIPPED runs exist (never deletes audit / rewrites SKIPPED / flips ON→OFF). Service
  (`app/browser/monitoring_control.py`) + `PUT /product/sites/{site_id}/monitoring` (ADMIN+CSRF,
  actor-tenant, non-disclosing 404, idempotent, `FOR UPDATE`, six-hour next-boundary projection,
  in-flight SCHEDULED projection) registered in `app/main.py`. **Test-only remediation (MINOR-1..5)**
  added populated-0028→0029 upgrade backfill coverage, incidents/evidence-pack zero-mutation counts,
  concurrent opposing-transition serialization, and strict-future/exact-boundary-next resolution.
  Validation ladder (§10 + remediation ladder) run on a fresh isolated
  DB/bucket (`publisher_intelligence_ep030_full` / `publisher-intelligence-ep030-full`):
  `ruff format --check`/`ruff check` clean (311 files); mypy **Success, 275 files, 0 errors**; unit
  **434 passed** (exact CI/default unit env, no stale DB/S3/RUN_INTEGRATION overrides); full
  integration (`RUN_INTEGRATION=1`, `BROWSER_ALLOW_PRIVATE_NETWORKS=true`) **255 passed, 0 failures**
  in one process; focused migration tests (`test_migrations.py`) **5 passed**; focused monitoring
  tests (`test_product_site_monitoring.py`, 14 cases incl. the new concurrent-opposing and
  strict-future-boundary tests) **14 passed**; scheduler one-shot exit 0 (browser checkpoint pass
  `site_count=0, run_count=0, job_count=0`; retention pass job_count=1); worker one-shot exit 0
  (retention only, 0 rows deleted); `docker compose config` OK; `check_secrets.py` OK; `git diff --check`
  clean. `alembic check` reports only pre-existing unrelated drift (`retention_runs`,
  `monetization_capability`, `seo_observations`) unchanged from before; no new drift from this EP. The
  earlier "16 passed" noted a module-level total (12 monitoring + 4 migrations); the truthful
  composition is 14 monitoring tests + EP-030 coverage added within `test_migrations.py` (5 migration
  tests total, incl. two EP-030-specific). M1 is **not independently deployable**: it stores the
  monitoring authorization state and exposes the control API only; scheduler due-query gating (GATE-1/2)
  and worker GATE-3 enforcement land in M2, so no site must be enabled and the staging scheduler must
  remain STOPPED until M2 is authorized and implemented. M1 does not start M2; no
  frontend exposure; scheduler/worker enforcement deferred to M2; no deployment/scheduler-restart/site
  enforcement. Test-only remediation touched no production code. NOT committed/pushed.

- 2026-09-02: planning authored. EP-029 M4 close verified at `a92da909…` (PR #37 MERGED; CI
  green on `33561839030` / `33561888659`); branch facts, migration head, containment verified;
  research subagents read canonical docs + code (§2). Status DRAFT.
- 2026-09-02: adversarial-review remediation (accepted verdict READY WITH REQUIRED PLAN
  CHANGES): truthful OFF contract; `SKIPPED`; GATE-2 `FOR UPDATE`; single `PUT`; UI
  monitoring/health separation; single R1–R7 matrix; diagnostic deferred/unnumbered; minimal
  schema; guarded downgrade; consolidation. Validation clean (§10); nothing staged.
- 2026-09-02: final consolidation — target ≤650 lines; downgrade now also refuses on `SKIPPED`
  rows; audit integrity made DB-enforced (composite FK + `UNIQUE(tenant_id,id)`). Status
  DRAFT — READY FOR FINAL REVIEW. M1–M4 NOT STARTED; nothing staged/committed/pushed; no
  runtime/gate action.
- 2026-09-01: final M0 acceptance — final plan verdict READY; adversarial-review findings
  reconciled; truthful OFF contract; `SKIPPED` administrative terminal state; GATE-2/GATE-3
  locking; final minimal schema; guarded downgrade. M1–M4 remain NOT STARTED; no runtime/gate
  action. Plan committed and PR opened (commit SHA + PR in PR description).

## 12. Next Boundary

M0 COMPLETE and **M1 COMPLETE** (data model + authenticated control API, validated, on branch/Draft
PR #38; NOT committed/pushed). **M1 is NOT independently deployable** — its scheduling-gating
(GATE-1/2/3) enforcement is M2, so no site may be enabled and the staging scheduler must remain
STOPPED until M2 is authorized and implemented. **M2–M4, deploying, restarting the scheduler,
enabling any site, creating EP-031/EP-032, or starting Gate P / Limited Pilot each require separate
authorizations.**
