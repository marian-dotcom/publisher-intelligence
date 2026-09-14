# EP-031 — Site Overview (Polished Operator UI, v1)

**Status:** READY — M0 (governance record) and M1 (backend projection) authorized; M2–M6 awaiting
subsequent authorization. No site registration, site enablement, publisher contact, deployment,
scheduler restart, Gate P, or Limited Pilot included.
**Owner:** Codex / Engineering
**Created / Updated:** 2026-09-14 (M0 + M1 authorized; planning + initial implementation begin)
**Target milestone:** Product / Operations track — EP-031 "polished operator UI / Site Overview"
(previously reserved by EP-028/EP-029/EP-030 as context-only; this file makes it an active plan).
**Base commit:** `6b43df655cbbda53c4a5cc5c9af00b088abb296c` (main; EP-030 doc closure, deployed a66bada)

## Progress

- [x] M0-PLAN — repo inspection + canonical doc + prior EP reconciliation (this document)
- [ ] M0 — governance record: refresh PLANS.md §76.1 forward sequence (EP-027–030 COMPLETE; register EP-031 → EP-032)
- [ ] M1 — backend: `GET /product/sites/{site_id}/overview` projection + `CheckpointStatus` literal fix + backend tests
- [ ] M2 — frontend: `/sites/[site_id]` route + page shell + identity header + monitoring card reuse + Home entry point
- [ ] M3 — frontend: diagnostic / latest-scheduled / recent-runs panels (kind + status semantics)
- [ ] M4 — frontend: source health + open incidents + recent activity panels + deep links
- [ ] M5 — loading / error / empty / stale states + a11y + tenant/security review pass
- [ ] M6 — final validation ladder + README boundary refresh + plan closure (staging deploy only under separate authorization)

---

## 1. Purpose and User Outcome

After this plan ships, an authenticated operator opens a dedicated per-site page
(`/sites/<site_id>`) and answers, at a glance, without leaving the page:

- What site am I looking at?
- Is scheduled monitoring ON or OFF? When is the next scheduled check?
- What was the latest diagnostic result?
- What was the latest scheduled monitoring result (SCHEDULED run, distinct from diagnostic)?
- Are any sources unhealthy or unavailable?
- Are there open incidents for this site?
- Were any runs SKIPPED / blocked / failed recently?
- What changed recently?
- Where do I click for evidence, diagnostic results, timeline, or incidents?

The page is a **read-only operational drill-down of Home** (ADR-002: Home / Timeline /
Investigate only; no fourth primary product area). It is **not** an analytics dashboard, an SEO
dashboard, a monitoring-control redesign, or a new monitoring cadence surface.

It must never imply publisher failure from observation failure:
preserve
`observation failure != publisher failure` and `evidence != causal claim`.

## 2. Scope

### In

- One new read-only backend projection endpoint:
  `GET /product/sites/{site_id}/overview` (tenant-scoped, non-disclosing 404).
- One new frontend route: `/sites/[site_id]` inside the authenticated `(protected)` shell.
- Reuse of existing projections where they exist (see §5/§6); a small set of new read
  queries for data that has no endpoint today (SCHEDULED run history, site-scoped incidents).
- Monitoring ON/OFF + cadence + `next_scheduled_for` + in-flight status (exact EP-030
  `monitoring` projection and `MonitoringCard` semantics, including ADMIN-only enable/pause).
- Diagnostic result summary (exact EP-028/EP-029 `_initial_diagnostic_projection` contract:
  `DIAGNOSTIC`/`OPERATOR_UI` only) + link to the existing diagnostic-results page.
- Latest SCHEDULED observation result, **excluding `SKIPPED`** (EP-030 "latest actual
  observation" semantics) — distinct from the diagnostic projection (ADR-130 cohort purity).
- Recent checkpoint-run history panel (all kinds, statuses incl. `SKIPPED`, with limitation text).
- Source-health summary (existing 5-source vocab, `HEALTHY/STALE/DEGRADED/…/UNKNOWN`),
  rendered separately from publisher/site health.
- Site-scoped open-incidents summary (status `OPEN`/`INVESTIGATING`) + links.
- Recent-activity panel reusing the exact `GET /timeline` entry serializer (site-scoped).
- Loading / error / empty / stale-missing states using existing patterns.
- Small code fix: add `"SKIPPED"` to the `CheckpointStatus` Literal in
  `backend/app/browser/contracts.py` (typing drift vs `FINAL_CHECKPOINT_STATUSES`, see §9).
- Governance: refresh `PLANS.md` §76.1 forward sequence (record EP-027–030 COMPLETE and
  register EP-031 → EP-032), and refresh the `README.md` "Repository boundaries" summary at
  closure (AGENTS.md §31).

### Out

- No charts (no Recharts; no visualization dependency) unless a later milestone justifies a
  chart from existing data — v1 has no strong justification.
- No new monitoring cadence controls, no "Run diagnostic now", no connector configuration,
  no CrUX/PSI, no AI summary generation, no Gate P / Limited Pilot behavior.
- No site enablement, no scheduler/worker/worker-runtime changes, no migration, no deployment
  (staging deploy of this feature requires a separate authorization).
- No new primary navigation area; no global site-context provider refactor.
- No delete/edit/archive of sites; no generic site CRUD; no new site-list endpoint
  (Home `/product/home/status` already returns the site list for selection).
- No incident reasoning changes (summary only); no event-logic changes.
- No new connector "next scheduled check" projection (browser `next_scheduled_for` is the only
  scheduled check this page must expose; connector cadence is out of v1 scope — see Open Decisions).

## 3. Canonical References

Read:

```text
AGENTS.md
PLANS.md
DECISIONS.md   (ADR-001, ADR-002, ADR-010, ADR-016, ADR-017, ADR-018, ADR-088, ADR-089,
                ADR-094/095, ADR-110, ADR-124, ADR-130, ADR-131)
PRODUCT.md     (§21 Home, §25 no dashboard wall, §80 site-vs-source health, §99–106 UX)
MVP.md         (§6, §7 no fourth core screen, §74 frontend, §84, §118–121)
ARCHITECTURE.md
DATA_MODEL.md
SECURITY.md    (§10–25 tenant/auth, §19 roles, §21/§201 cookies, §22 CSRF, §187–197 reviews,
                §75 artifact delivery)
EVENTS.md      (browser-source reliability: monitor-source never publisher failure)
DOMAIN.md      (§74–76 control vs data plane)
BROWSER.md
plans/EP-028-operator-site-registration.md
plans/EP-029-publisher-compatibility.md
plans/EP-030-per-site-monitoring-controls.md
```

Relevant invariants (verbatim/per plan contracts):

- ADR-002: "Primary UX: Home / Timeline / Investigate. **No fourth primary product area in MVP.**
  … can appear: inside Timeline event details; inside incident evidence; inside technical
  drill-down panels." → Site Overview is a Home drill-down page, NOT a new nav area.
- ADR-018: "`publisher 503 → SITE_ERROR`; `Chromium crash → BROWSER_ERROR`; … Monitoring failure
  must not become publisher evidence."
- ADR-130: observation kinds `SCHEDULED | VALIDATION | DIAGNOSTIC | INCIDENT_DIAGNOSTIC`;
  "Non-routine observations … MUST NOT silently contaminate: … Last Known Good eligibility." →
  diagnostic and scheduled results are distinct projections with explicit kind labels.
- EP-030 §5.2: `SKIPPED` is terminal, zero contact, "not a publisher failure, browser failure,
  access challenge, incident, or degradation evidence"; excluded from latest-actual-observation
  selection; a window of only-SKIPPED runs is `COMPLETE` (orchestration, not observation).
- PRODUCT.md §80 / PLANS.md §76.1 EP-025: source health rendered separately from publisher
  health; "browser observation degradation must never be presented as publisher/site failure".
- SECURITY.md: authenticated principal → tenant membership → object ownership; cross-tenant or
  nonexistent → non-disclosing 404; GET reads need no CSRF; ADMIN vs OPERATOR roles.
- ADR-088/089/090: tenant-confidential data, tenant isolation first, shared DB + app-level scope.

## 4. Current State

Verified against repo at base `6b43df6` (`main`, clean tree). Only **7 routers / 17
endpoints** are registered (`backend/app/main.py:23-29`). Everything the overview needs exists as
data; nothing exposes a per-site overview today.

Existing read surfaces to reuse (no change):

- `GET /product/home/status?site_id=…` (`backend/app/api/product.py:264`) returns
  `sites[{site_id,name}]`, `selected_site_id`, `publisher_site_condition` (`Site.status`),
  `source_health` (5 keys), `initial_diagnostic`, `monitoring` (EP-030),
  `open_incident_count` (**tenant-wide**, not site-scoped), `monetization_capability`.
  - `_source_health_rows(session, tenant_id, site_id)` → `{BROWSER_MONITORING, GA4, GSC, GAM,
    PUBLIC_CONFIG}` states (`product.py:132`).
  - `_initial_diagnostic_projection(...)` → latest `DIAGNOSTIC`/`OPERATOR_UI` run
    `{run_id, status, completed_at, browser_access_classification}` (`product.py:227-261`).
  - `monitoring_control_result(...)` → `{site_id, enabled, monitoring_state_updated_at,
    next_scheduled_for, in_flight_scheduled_run_status}` (`browser/monitoring_control.py:200`);
    cadence constant `MONITORING_CADENCE = six-hour` (`api/site_monitoring.py:25-28`).
- `GET /product/source-health?site_id=…` (`product.py:359`) — `{site_id, sources,
  browser_monitoring_detail?}` machine-readable degradation detail.
- `GET /product/sites/{site_id}/diagnostic-results` + `…/diagnostic-artifacts/{id}`
  (`product.py:483,559`) — diagnostic detail + authenticated artifact proxy (EP-029 M2a).
- `GET /timeline?site_id=…` (`api/memory.py:36`) — tenant-scoped Event + ManualNote with
  `time_precision` / occurrence-window semantics; the canonical "recent activity" serializer.
- `GET /incidents` (`api/memory.py:109`) — tenant-wide list; **no `site_id` filter today**
  (rows carry `site_id`). `Incident` model has `site_id` and `status ∈ OPEN/INVESTIGATING/…`.
- Auth: `get_current_actor` (reads) vs `get_current_actor_with_csrf` (writes); tenant always
  from actor; CSRF = double-submit `pi_csrf` + server-verifiable hash; secure-cookie fail-closed
  per SECURITY.md §201 / ADR-131 (`auth/routes.py:52-58`). Roles ADMIN and OPERATOR.

Data model (relevant, all exist — **no schema change needed**):

- `Site` (`browser/models.py:55-86`): `name`, `canonical_domain`, `canonical_scheme`,
  `timezone`, `status (ACTIVE)`, `monitoring_state (ON/OFF)`, `monitoring_state_updated_at`,
  `created_at`; **no `url` column** (URL = `canonical_scheme://canonical_domain`);
  `Publisher` has `name` (`models.py:46`).
- `CheckpointRun` (`browser/models.py:268`): `observation_kind`, `trigger_source`,
  `status` (check incl. `SKIPPED`, migration 0029), `limitations`, `browser_access_classification`,
  immutable provenance guard; `CheckpointWindow` at `:247`.
- `SiteMonitoringStateChange` (`browser/models.py:95`) append-only audit (EP-030 M1).
- `Incident` (`incidents/models.py`), `Event`/`ManualNote` (`events/models.py`,
  `evidence/models.py`), `DataConnection`/`SourceExtract` (`connectors/models.py`),
  `PublicConfigSnapshot` (`public_config/models.py`).
- Migrations head: `0029_site_monitoring_controls`.

Known gaps this plan fills (verified):

1. No per-site page/route; Home selection is transient (`frontend/app/(protected)/page.tsx`).
2. No checkpoint-run history endpoint (today only the latest-diagnostic projection exists);
   SCHEDULED runs are browsable nowhere.
3. Incidents endpoint has no `site_id` filter (overview needs site-scoped open incidents).
4. Typing drift: `CheckpointStatus` Literal (`backend/app/browser/contracts.py:12-19`) omits
   `"SKIPPED"` while `FINAL_CHECKPOINT_STATUSES` (`browser/models.py:27-35`) and the DB check
   include it (migration 0029). EP-031 must type against DB reality.
5. `home_status.open_incident_count` is tenant-wide, not per-site — overview must query
   site-scoped.
6. Frontend has no route/nav entry, no skeleton/error-boundary infrastructure (existing
   LoadingState/ErrorState/EmptyState patterns are the convention to follow).

Staging runtime context (2026-09-13, EP-030): scheduler/worker/3× browser-worker on a66bada,
fail-closed gates live, **`sites` = 0 rows (ON = 0)**, zero publisher-contact jobs. There is
currently **no registered site in the deployed staging DB**, so staging visual verification of
this page requires a site row — which today can only be created via POST /product/sites, and
registration necessarily triggers an immediate `DIAGNOSTIC` publisher contact (EP-028) — a
separate authorization matter (see Open Decisions).

## 5. Target Behavior

Concrete example (POST GiF assets already present):

```text
Operator is authenticated as ADMIN, tenant tid-1, clicks "Overview" for site
"Climatologie Déploiement" (https://climatologie.ro) from Home.

GET /product/sites/6d7f…/overview  (reads only, no CSRF)

Page (at /sites/6d7f…) renders, at a glance:
  Header:            Climatologie Déploiement · https://climatologie.ro · ACTIVE
                     · publisher: <publisher_name> · registered 2026-xx-xx
  Monitoring card:   "Monitoring active" · every 6 hours · next check at 18:00 UTC
                     (or "Paused — monitoring is OFF", next check: —) · ADMIN enable/pause
  Latest diagnostic: COMPLETE · access ok · completed <ts> · [View diagnostic results →]
  Latest scheduled:  COMPLETE · completed <ts> (SCHEDULED run; SKIPPED never shown here)
  Source health:     Browser Monitoring: HEALTHY · GA4: UNKNOWN · GSC: UNAVAILABLE · …
                     (publisher condition rendered separately, never conflated)
  Open incidents:    none → "No open incidents for this site." [View all incidents →]
  Recent runs:       Scheduled COMPLETE <ts> · Scheduled SKIPPED (monitoring paused) <ts> · …
                     Diagnostic COMPLETE <ts>   ← kind badge + status chip incl SKIPPED/BLOCKED
  Recent activity:   latest 5 timeline entries for this site (event/note, same serializer)
  Links:             diagnostic results / timeline (filtered) / incidents (filtered)
                     / evidence packs when referenced
```

Failure-path example:

```text
Operator opens /sites/<foreign-or-nonexistent-site-id> → the overview endpoint returns the
non-disclosing 404 "resource not found" (same message as every other 404), never revealing
whether the site exists in another tenant.
```

## 6. Architecture / Data Flow

```text
Frontend /sites/[site_id]  (protected shell)
   │  GET /product/sites/{site_id}/overview   (same-origin, Accept: application/json,
   │      cookies: pi_session; NO CSRF — read only)   via middleware proxy → FastAPI
   ▼
API GET overview   actor.tenant_id ── tenant chain: site ∈ tenant else 404 ──┐
   │                                                                        │
   ├─ reuse  _source_health_rows(session, tenant_id, site_id)                │ single
   ├─ reuse  _initial_diagnostic_projection(...)  (DIAGNOSTIC/OPERATOR_UI)   │ read-only
   ├─ reuse  monitoring_control_result(...)  (+ MONITORING_CADENCE)   ┌──────┘ projection
   ├─ new    latest SCHEDULED run EXCLUDING SKIPPED  (mirror the          leaving
   │         SCHEDULED-only + SKIPPED-exclusion filters already used      DB unchanged
   │         in events/persistence.py and EP-030 "latest actual
   │         observation" selection)
   ├─ new    recent checkpoint runs (limit 5, tenant+site, any kind/status, incl SKIPPED+limitations)
   ├─ new    site-scoped open incidents (status OPEN/INVESTIGATING, Incident.site_id)
   ├─ new    recent activity (limit 5, site-scoped, EXACT memory.py timeline serializer)
   └─ new    site block {site_id,name,url( scheme://domain ),publisher_name,status,timezone,created_at}
   → 404 on unknown/foreign site (non-disclosing)
PostgreSQL (read)
```

Rules:

- **No writes.** The overview endpoint is GET, `get_current_actor` only, no CSRF. Any
  enable/pause on the page reuses the existing ADMIN+CSRF `PUT …/monitoring` flow unchanged.
- **Tenant purity:** every query in the projection is filtered by `actor.tenant_id`; the site
  lookup is the single gate — unknown/foreign → 404.
- **ADR-130 cohort purity:** diagnostic = latest `DIAGNOSTIC`/`OPERATOR_UI`; scheduled =
  latest `SCHEDULED` (excluding SKIPPED for "latest result"); the recent-runs panel is
  informational and explicitly kind-labeled.
- **No new derived causal claims:** panels surface statuses and timestamps; no severity
  synthesis, no "publisher is breaking" copy, no speculative causation.

## 7. Files and Modules Affected

Existing (backend):

- `backend/app/api/product.py` — add `GET /sites/{site_id}/overview`; reuse
  `_source_health_rows`, `_initial_diagnostic_projection`; raise `HTTPException(404,
  "resource not found")` on the tenant gate (mirror `site_monitoring.py`).
- `backend/app/api/memory.py` — reuse timeline scalar/serializer via a small internal helper
  (extract or import the existing entry builder) for `recent_activity`.
- `backend/app/browser/contracts.py` — add `"SKIPPED"` to the `CheckpointStatus` Literal
  (typing-only fix; DB/model already include it).
- `backend/app/browser/monitoring_control.py` — reuse as-is.

To create (backend):

- `backend/tests/integration/test_product_site_overview.py` (new).

Existing (frontend):

- `frontend/app/(protected)/page.tsx` — add "Overview" entry point for the selected site.
- `frontend/components/protected-shell.tsx` — no change to the 3 primary nav links (ADR-002).
- `frontend/components/monitoring-controls.tsx` — reuse `MonitoringCard`.
- `frontend/components/domain.tsx` — reuse `SourceHealthBadge`, `DiagnosticStateBadge`,
  `StatusChip`, `SeverityBadge`, `TemporalUncertainty`, `ObservedAt`, `ProvenanceBadge`.
- `frontend/lib/api-types.ts` — add overview response types.
- `frontend/app/styles.css` — reuse existing card/status/state styles; add only if required.

To create (frontend):

- `frontend/app/(protected)/sites/[site_id]/page.tsx` (page + data load).
- `frontend/components/site-overview.tsx` (panels; import existing primitives/domain bits).
- `frontend/tests/site-overview.test.tsx` (new).

Docs:

- `plans/EP-031-site-overview.md` (living plan), `PLANS.md` (§76.1 forward sequence refresh,
  M0), `README.md` ("Repository boundaries" refresh, M6 closure).

No changes to: compose.yaml, migrations, scheduler, worker, browser-worker, auth internals,
data model, event/incident rules.

## 8. Milestones

### M0 — Governance record (planning → plan becomes the active candidate)

Goal: record the authorized planning outcome and make PLANS.md reflect reality.
Implementation:
- Update `PLANS.md` §76.1 approved forward sequence: mark EP-027/028/029/030 COMPLETE;
  register the product track `EP-031 (polished operator UI / Site Overview) → EP-032 (minimal
  CrUX History)` after EP-030, before Gate P / Limited Pilot.
Acceptance:
- [ ] PLANS.md §76.1 names EP-031 as the next candidate and no longer describes EP-028/029/030 as unlisted/unplanned.
Validation: `git diff --check`; review diff.

### M1 — Backend single read-only overview projection

Goal: `GET /product/sites/{site_id}/overview` returns the full, tenant-scoped, non-disclosing
payload constructed from reused + small new read queries; typing drift fixed.
Implementation:
- Contracts literal: add `"SKIPPED"` to `CheckpointStatus` (contracts.py).
- Router: add overview endpoint in `api/product.py` using `get_current_actor` (no CSRF).
- Site gate: fetch `Site` by id + tenant; else 404 `"resource not found"`.
- Blocks per §7; `latest_scheduled_run` queries `SCHEDULED` statuses excluding `SKIPPED`
  (use the same exclusion disciplines as `events/persistence.py` and EP-030); `recent_runs`
  (limit 5) includes all statuses incl. `SKIPPED` with `limitations`; `recent_activity`
  (limit 5) reuses the exact timeline serializer; incidents site-scoped OPEN/INVESTIGATING.
Acceptance:
- [ ] Payload contract (§10) returned; shapes for reused blocks byte-compatible with existing
      endpoints; null/empty semantics exact (absence ≠ healthy).
- [ ] Foreign/nonexistent site → 404 `"resource not found"` (non-disclosing); OPERATOR can read;
      no CSRF required for GET.
Validation (backend ladder): ruff format/check, mypy, `pytest tests/unit`,
`RUN_INTEGRATION=1 pytest tests/integration/test_product_site_overview.py`.

### M2 — Frontend route + shell + identity + monitoring + Home entry

Goal: `/sites/[site_id]` renders the authenticated page with identity header and the reused
monitoring card; Home exposes "Overview".
Implementation:
- `frontend/app/(protected)/sites/[site_id]/page.tsx` loads the overview projection.
- Page header card: name, url (`scheme://domain`), publisher, status chip, timezone, created_at.
- Reuse `MonitoringCard` for ON/OFF + cadence + `next_scheduled_for` + `in_flight` + ADMIN gating.
- Home: an "Overview" affordance next to the existing "View diagnostic results" action for the
  selected site (no new primary nav item).
Acceptance:
- [ ] Route renders under auth; 404/401/403 handled with existing ErrorState semantics.
- [ ] Header and monitoring card render from fixture data; ADMIN gating unchanged.
Validation: `pnpm --dir frontend lint`, `typecheck`, `test tests/site-overview.test.tsx`.

### M3 — Diagnostic / latest-scheduled / recent-runs panels

Goal: three data panels with correct kind and status semantics.
Implementation:
- Diagnostic panel: reuse `DiagnosticStateBadge`, render `status`,
  `browser_access_classification`, `completed_at`, "View diagnostic results →" link
  (with site context).
- Latest-scheduled panel: show only SCHEDULED non-SKIPPED latest result; if none, "No scheduled
  results yet." (absence, not failure). Diagnostic and scheduled are never merged.
- Recent-runs panel: latest 5 runs, kind badge (Scheduled / Diagnostic), status chip (incl.
  `SKIPPED` rendered as "Skipped (monitoring paused)" with limitation, never as failure),
  timestamps; `BLOCKED`/`SITE_ERROR`/`BROWSER_ERROR`/`TIMEOUT`/`PARTIAL` shown with their label.
Acceptance:
- [ ] Fixtures prove diagnostic ≠ scheduled panels never cross-populate; SKIPPED appears only in
      runs panel; missing data renders empty-states, not failure copy.
Validation: vitest `tests/site-overview.test.tsx` + `pnpm --dir frontend test`.

### M4 — Source health + open incidents + recent activity + deep links

Goal: complete the "at a glance" picture + navigation.
Implementation:
- Source-health section: reuse `SourceHealthBadge` grid (5 sources) with the existing vocabulary;
  browser-monitoring detail line when available; publisher condition rendered as a separate line.
- Incidents panel: site-scoped open incidents (severity/status) + "View incidents →".
- Recent activity: latest 5 timeline entries for the site (exact timeline entry shape with
  temporal-uncertainty rendering) + "View timeline →".
- Links block: diagnostic results, timeline (site-filtered), incidents (site-filtered), and
  evidence packs where referenced.
Acceptance:
- [ ] Each panel renders from fixture; deep links carry site context; stale/unavailable source
      states shown as data-quality states, never publisher failure.
Validation: vitest; manual route smoke via isolated local stack test data.

### M5 — Loading / error / empty / stale states + a11y + security pass

Goal: production-shaped UX and defense.
Implementation:
- Full-load/partial/empty/failure states per existing LoadingState/ErrorState/EmptyState
  convention; misleading accusatory copy forbidden.
- a11y: text-not-color health, `role="status"`/`role="alert"` usage, labels for all panels.
- Security pass: confirm cross-tenant/nonexistent site → 404 in integration; no CSRF on GET;
  OPERATOR role read access; no artifact rendering added beyond existing proxy.
Acceptance:
- [ ] New a11y + error-mapping tests; cross-tenant regression test green.
Validation: `pnpm --dir frontend test`; backend integration suite section.

### M6 — Final validation + docs + closure

Goal: full ladder green, docs current, closure record.
Implementation:
- Full validation ladder (below), migration rehearsal no-op (no schema change), secret scan,
  compose config, diff review.
- Refresh README "Repository boundaries" to name EP-031 as latest merged/deployed boundary
  (AGENTS.md §31); complete plan Decision/Discoveries/Retrospective sections.
- Staging deployment of the page happens ONLY under a separate authorization; no runtime restart;
  no scheduler change. (See Open Decisions for the staging site-row question.)
Acceptance:
- [ ] All checks green; only intended files changed; docs describe shipped behavior.
Validation: full §12 block below.

## 9. Final Acceptance Criteria

- [ ] `GET /product/sites/{site_id}/overview` exists, is read-only (GET, no CSRF), tenant-scoped,
      and returns 404 `"resource not found"` for cross-tenant/nonexistent sites (non-disclosing).
- [ ] Response reuses exact existing shapes for: monitoring (EP-030), initial diagnostic
      (EP-028/029), source health (5-key vocab), recent activity (timeline serializer).
- [ ] `latest_scheduled_run` never contains DIAGNOSTIC/INCIDENT_DIAGNOSTIC runs and never
      contains `SKIPPED`; `initial_diagnostic` never contains SCHEDULED runs.
- [ ] Recent-runs panel surface includes `SKIPPED` (with limitation text) and every terminal
      status, labeled by kind; `SKIPPED` is never rendered as a failure.
- [ ] Monitoring ON shows `next_scheduled_for`; OFF shows no next check; `Paused — current check
      finishing` shows when `in_flight_scheduled_run_status` is present; enable/pause is
      ADMIN-only with backend enforcement (no behavior change to the PUT flow).
- [ ] `/sites/[site_id]` renders all panels, links carry site context, and empty/stale states
      use absence semantics ("No X yet.") without suggesting publisher failure.
- [ ] No schema/migration change; DB read-only; no code path writes during a GET.
- [ ] `CheckpointStatus` literal includes `"SKIPPED"`.
- [ ] Frontend lint/typecheck/tests/build green; backend ruff/mypy/unit/integration green;
      `alembic upgrade head` idempotent (no-op); `check_secrets` + `docker compose config` +
      `git diff --check` green.

## 10. Data Contract — `GET /product/sites/{site_id}/overview`

```json
{
  "site": {
    "site_id": "<uuid>",
    "name": "Climatologie Déploiement",
    "canonical_domain": "climatologie.ro",
    "canonical_scheme": "https",
    "url": "https://climatologie.ro",
    "publisher_name": "<publishers.name>",
    "status": "ACTIVE",
    "timezone": "Europe/Bucharest",
    "created_at": "<iso>"
  },
  "monitoring": {
    "site_id": "<uuid>",
    "enabled": true,
    "monitoring_state_updated_at": "<iso>",
    "cadence": {"identifier": "six-hour", "hours": 6},
    "next_scheduled_for": "<iso> | null",
    "in_flight_scheduled_run_status": "PENDING | RUNNING | null"
  },
  "initial_diagnostic": {
    "run_id": "<uuid>",
    "status": "PENDING | RUNNING | COMPLETE | PARTIAL | SITE_ERROR | BROWSER_ERROR | TIMEOUT | BLOCKED",
    "completed_at": "<iso> | null",
    "browser_access_classification": "ok | degraded | challenge_suspected | null"
  },
  "latest_scheduled_run": {
    "run_id": "<uuid>",
    "status": "COMPLETE | PARTIAL | SITE_ERROR | BROWSER_ERROR | TIMEOUT | BLOCKED",
    "started_at": "<iso> | null",
    "completed_at": "<iso> | null",
    "attempt_count": 1,
    "browser_access_classification": "ok | degraded | challenge_suspected | null"
  },
  "source_health": {
    "BROWSER_MONITORING": "HEALTHY | STALE | DEGRADED | ACTION_REQUIRED | BLOCKED | UNAVAILABLE | UNKNOWN",
    "GA4": "…", "GSC": "…", "GAM": "…", "PUBLIC_CONFIG": "…"
  },
  "browser_monitoring_detail": {"state": "…", "reason": "…", "codes": ["…"]} | null,
  "open_incidents": [
    {"incident_id": "<uuid>", "title": "…", "symptom_family": "…", "status": "OPEN | INVESTIGATING",
     "severity": "…", "reported_start_at": "<iso> | null", "opened_at": "<iso>"}
  ],
  "recent_runs": [
    {"run_id": "<uuid>", "observation_kind": "SCHEDULED | DIAGNOSTIC | INCIDENT_DIAGNOSTIC",
     "status": "<any terminal or in-progress state incl SKIPPED>",
     "started_at": "<iso> | null", "completed_at": "<iso> | null",
     "limitations": ["monitoring-disabled-before-execution"]}
  ],
  "recent_activity": [ "<exact GET /timeline entry shape, site-scoped: kind event|manual_note, …>" ]
}
```

Notes:
- `initial_diagnostic` reuses `_initial_diagnostic_projection` byte-for-byte shape.
- `monitoring` reuses the EP-030 home projection shape byte-for-byte.
- `source_health` reuses `_source_health_rows` keys/states; `browser_monitoring_detail` reuses
  the existing source-health endpoint detail when available, else `null`.
- `latest_scheduled_run`: SCHEDULED only, `SKIPPED` excluded (EP-030 selection discipline); null
  when none observed.
- `open_incidents`: site-scoped, status `OPEN`/`INVESTIGATING`, shape identical to
  `GET /incidents` items (adds site scoping, which that endpoint lacks today).
- `recent_activity`: reuse the exact timeline serializer (do not fork shapes → no drift risk).
- All tenant-owned filters keyed on `actor.tenant_id`; absent data renders as null/empty.

## 11. Final Validation (commands)

```text
Backend:
  uv --directory backend run ruff format --check .
  uv --directory backend run ruff check .
  uv --directory backend run mypy app tests scripts migrations/env.py
  uv --directory backend run pytest tests/unit
  RUN_INTEGRATION=1 uv --directory backend run pytest tests/integration
  uv --directory backend run alembic upgrade head            (idempotent no-op; no new migration)
  uv --directory backend run python -m app.scheduler --once   (smoke unchanged)

Frontend:
  pnpm --dir frontend lint
  pnpm --dir frontend typecheck
  pnpm --dir frontend test
  pnpm --dir frontend build

Repo safety:
  python3 scripts/check_secrets.py
  docker compose config
  git diff --check
```

## 12. Test Cases

Backend integration (`tests/integration/test_product_site_overview.py`):

- Happy path: site with diagnostic + scheduled runs + open incident + events + monitoring ON →
  full payload, correct reuse shapes, `next_scheduled_for` present.
- Kind purity: `latest_scheduled_run` excludes DIAGNOSTIC and SKIPPED; `initial_diagnostic`
  excludes SCHEDULED.
- Tenant boundary: tenant-B actor requests tenant-A site → 404 `"resource not found"`
  (non-disclosing); nonexistent site → same 404.
- Monitoring OFF → `enabled:false`, `next_scheduled_for:null`; no CSRF needed for GET; OPERATOR
  role can read.
- Empty site: no diagnostic/no runs/no incidents/no events → null/empty fields, no 5xx.
- Recent-runs ordering and limit (5) with a SKIPPED run present and limitation surfaced.

Frontend (`tests/site-overview.test.tsx`):

- Full render from fixture (all panels present; section roles/labels).
- Error mapping: 404 → "not found" message; 401/403/network/server → existing ErrorState wording.
- Empty states: no incidents / no runs / no activity / monitoring unavailable → absence copy.
- Kind distinction: diagnostic vs scheduled panels; SKIPPED run shows "Skipped — monitoring
  paused", never failure tone.
- Monitoring card ADMIN gating reuse; enable/pause unchanged.
- A11y: health communicated by text not color; live-region roles for loading/error.

## 13. Data / Migration Impact

- **No schema change, no migration, no backfill.** All data already exists
  (`sites`, `site_monitoring_state_changes`, `checkpoint_runs`, `checkpoint_windows`,
  `incidents`, `events`, `manual_notes`, `public_config_snapshots`, `data_connections`).
- Read-only endpoint; PostgreSQL reads only. Evidence/immutability invariant untouched
  (ADR-016/017, PLANS.md §29/§74).
- Only code-level typing fix: `CheckpointStatus` literal gains `"SKIPPED"` (matches DB/model).
- Migration rehearsal at M6 confirms head stays `0029_site_monitoring_controls`.

## 14. Security / Privacy Impact

- **Tenant isolation:** every query tenant-scoped; foreign/nonexistent site → non-disclosing 404
  (SECURITY.md §13, ADR-089). New cross-tenant regression test required (AGENTS.md §13).
- **Credentials/secrets:** none touched; no new cookies; page rides the existing
  `pi_session`/`pi_csrf` posture (ADR-131 unchanged).
- **Artifacts:** none rendered by the overview; existing authenticated proxy (EP-029) unchanged.
- **Read vs write:** GET requires no CSRF; the only write affordance (enable/pause) reuses the
  existing ADMIN+CSRF PUT unchanged.
- **Roles:** read overview accessible to ADMIN and OPERATOR; monitoring control remains ADMIN-only
  (backend authoritative; client hides for non-ADMIN, as today).
- **Observation vs publisher:** page vocabulary follows ADR-018/PRODUCT §80/EVENTS.md — source
  staleness/unavailability and `SKIPPED` are data-quality/monitor states, never publisher failure.
- Conclusion: No new stored data; no permission widening; no new external surface. Addressed by
  tests in §12. (SECURITY.md §187/§188: read-only page over existing data → no forced full review
  list, but new-tenant-surface regression tests are mandatory.)

## 15. Observability / Failure Handling

- The overview is a projection; failures follow existing endpoint conventions (401 auth,
  per-role errors, 404 non-disclosing, 500 → frontend "Could not load … Try again"). No new
  structured-log requirements beyond the existing FastAPI request logging; no silent partial
  success — each panel is bounded by the single endpoint response (any backend error surfaces as
  a page-level ErrorState).
- If a panel's source data is missing (no runs, no incidents), it renders EmptyState, never a
  fabrication. If the whole site is absent → 404 page state.
- Platform health (operations) is NOT surfaced on this page; it belongs to the existing
  operations surface (PLANS §36: do not confuse platform and publisher health).

## 16. Rollback Strategy

- Backend: revert the overview endpoint + literal fix commit (additive, read-only, no migration);
  existing Home/Timeline/Incidents surfaces unaffected.
- Frontend: revert route/component commit; Home/other routes unaffected.
- No data writes to roll back; no migration; no feature flag needed (low rollout risk, no data
  category change).
- Rollback never deletes/rewrites existing evidence.

## 17. Known Risks

1. **Staging visual verification blocked by zero site rows.** Deployed staging DB has 0 sites;
   rendering the page against live data requires a site row, and registering one via
   `POST /product/sites` triggers an immediate DIAGNOSTIC publisher contact (EP-028) — a
   separate authorization. Mitigation: verify via isolated local stack + integration fixtures;
   defer staging visual check to a separately authorized registration.
2. **Contract drift (SKIPPED literal)** — must fix in M1 or typers/models disagree; already
   captured.
3. **Incidents endpoint lacks site filter** — overview stays self-contained (site-scoped query
   inside the projection) rather than changing `GET /incidents` semantics; timeline serializer is
   reused not forked to avoid drift.
4. **Scope creep toward dashboard/analytics** — guarded by ADR-001/002, PRODUCT §21/§25/§95/§99,
   no charts in v1, no new primary nav area, no cadence/revenue/causal claims.
5. **"At a glance" overload** — 9 questions can tempt a wall of cards; page must stay compact
   (progressive disclosure, links to detail pages), review at M5.
6. **PLANS.md §76.1 staleness** — resolved at M0; must not be presented as the current sequence
   meanwhile.

## 18. Open Decisions

- **OD-1 — Staging verification target.** Recommend: no staging data mutation; verify on the
  isolated local stack + integration/frontend fixtures; a staging visual check requires a
  separately authorized site registration (which itself is publisher contact). Alternatives:
  authorize a disposable test-site registration (site OFF, one DIAGNOSTIC) — approved only by a
  new human authorization. DECISION: defer to the implement+authorize step.
- **OD-2 — Connector "next scheduled check".** Only browser monitoring exposes a next-run today.
  Recommend v1 shows browser cadence only; connector slot projections are not part of EP-031
  (KISS; no endpoint exists; would need new public-connector scheduling projections). DECISION:
  EXCLUDE in v1; record as future if a concrete need appears.
- **OD-3 — Site list/selector.** Reuse `/product/home/status.sites` for any selector need; do not
  add a `GET /sites` endpoint in v1. DECISION: NO new list endpoint.
- **OD-4 — Charts.** No charts in v1; Recharts noted by EP-029 as the eventual tooling direction;
  only add when a panel's question genuinely needs a time-series that text cannot answer (none
  identified in v1 questions). DECISION: EXCLUDE; revisit at EP-031 v2 or EP-032.
- **OD-5 — New nav area?** No (ADR-002). Page reached from Home as a drill-down; Timeline and
  Incidents may later deep-link into it with site context. DECISION: Home-only entry in v1.

## 19. Decision Log

```text
Date: 2026-09-14
Decision: Single read-only overview projection endpoint GET /product/sites/{site_id}/overview
  reusing existing projection helpers, instead of composing 5-6 client round-trips.
Reason: one tenant gate + one error path + byte-compatible reuse of EP-028/029/030 contracts;
  smallest backend surface; fewer round trips; single cross-tenant regression surface.
Alternatives: (a) client-side composition of home/status+source-health+timeline+incidents+diag —
  rejected: incidents has no site filter and no run-history endpoint exists, so backend work is
  unavoidable and a single projection is smaller; (b) per-block endpoints — more surface, more tests.
Impact: one new endpoint; existing endpoints untouched.

Date: 2026-09-14
Decision: latest_scheduled_run excludes SKIPPED; recent_runs includes SKIPPED.
Reason: EP-030 §5.2 codifies SKIPPED exclusion from latest-actual-observation selection; the runs
  panel is informational transparency. No cohort contamination (ADR-130).
Alternatives: including SKIPPED as "latest result" — would misreport a paused check as the latest
  observation. Impact: honest monitoring-vs-health separation.

Date: 2026-09-14
Decision: No schema change; fix only the CheckpointStatus Literal drift.
Reason: all needed data exists; equals KISS and zero migration risk.
Impact: migration head unchanged at 0029.

Date: 2026-09-14
Decision: /sites/[site_id] deep page (path param) instead of query-param on Home.
Reason: shareable, bookmarks the site, matches existing [id] detail pages; Home remains the
  transient selector + entry point.
Impact: new route under (protected).

Date: 2026-09-14 (M1)
Decision: browser_monitoring_detail reuses the exact existing source-health endpoint shape
  (source/state/reason/detected_at/source_event_id/source_event_code/evidence_checkpoint_run_id/
  boundary), not the illustrative {"state","reason","codes"} sketch in §10.
Reason: §10 note "reuse the existing source-health endpoint detail when available, else null"
  and the no-drift rule override the sketch; extracted into a shared builder.
Impact: byte-identical detail across /product/source-health and /product/sites/{id}/overview.

Date: 2026-09-14 (M1)
Decision: recent_activity are exact /timeline entries (no added "kind" field) merged from the
  site's newest events and manual notes, sorted by observed_at descending, trimmed to 5.
Reason: serializer is extracted and reused so overview shapes cannot drift from /timeline; the
  distinction is inferred (event_id present vs note_id present) exactly as /timeline does.
Impact: single serializer used by both surfaces.
```

## 20. Discoveries / Surprises

- `CheckpointStatus` Literal (`contracts.py`) omits `"SKIPPED"` although the DB check (0029) and
  `FINAL_CHECKPOINT_STATUSES` include it — typing drift to fix.
- `GET /incidents` has no `site_id` filter and `home_status.open_incident_count` is tenant-wide —
  the overview must compute site-scoped incidents itself.
- No checkpoint-run history endpoint exists anywhere — recent-runs panel is genuinely new read
  surface (data already present).
- `sites` has no `url` column; display URL is `canonical_scheme://canonical_domain` (verified).
- PLANS.md §76.1 "approved forward sequence" is stale (last amended 2026-08-22; ends at EP-026;
  no EP-027/028/029/030); the effective sequence lives in README/EP notes. M0 will reconcile.
- Deployed staging DB has zero site rows — overview page cannot be visually verified in staging
  without a (separately authorized) registration/diagnostic.
- §10's `browser_monitoring_detail` sketch ({"state","reason","codes"}) is illustrative; the note
  and the no-drift rule decide on the existing byte-exact source-health detail shape (M1).
- `manual_notes.note_type` is DB-checked to a fixed `NOTE_TYPES` set (test fixtures must use a
  valid member, e.g. OPERATOR_INTERVENTION).

## 21. Progress Log

```text
2026-09-14  Planning only. Repo verified clean at 6b43df6; AGENTS.md + PLANS.md read; DECISIONS/
            PRODUCT/MVP/ARCHITECTURE/DATA_MODEL/SECURITY/EVENTS/INCIDENT/CONNECTORS/BROWSER/README
            distilled; EP-028/029/030 plan contracts extracted; backend + frontend implementation
            inventoried (17 endpoints, 7 routers, route map, components, tests, migrations 0026-29).
            Plan drafted as DRAFT. Nothing implemented, committed, or pushed.

2026-09-14  M0 (governance). Plan promoted DRAFT->READY. PLANS.md §76.1 "Post-2026-08-22 practical
            execution record" added: EP-027/028/029/030 COMPLETE, EP-031 ACTIVE/READY (M0-M1
            authorized), EP-032 next (proposed only), Gate P / Limited Pilot separately authorized.
            Working tree carries M PLANS.md + ?? plans/EP-031-site-overview.md. Branch
            agent/ep-031-site-overview created off 6b43df6.

2026-09-14  M1 (backend projection). Implemented GET /product/sites/{site_id}/overview in
            product.py reusing _source_health_rows / _initial_diagnostic_projection /
            monitoring_control_result / _classification_state; extracted shared
            _monitoring_projection and _browser_monitoring_detail builders; memory.py serializer
            extracted into _event_entry/_manual_note_entry + recent_activity_entries helper;
            contracts.py CheckpointStatus Literal gained "SKIPPED". New integration test file.
            See Validation Results.
```

## Validation Results

```text
2026-09-14  M1 ladder (all green):
  ruff format --check .            -> 314 files already formatted
  ruff check .                     -> all checks passed
  mypy app tests scripts ...       -> Success, 278 files
  pytest tests/unit                -> 436 passed
  RUN_INTEGRATION=1 pytest tests/integration -> 296 passed (incl. 9 new overview tests;
            existing memory/product/home tests unaffected by serializer/projection extraction)
  alembic current                  -> 0029_site_monitoring_controls (head), unchanged
  alembic upgrade head             -> no-op, no new migration
  python -m app.scheduler --once   -> unchanged (site_count 0, scheduling passes complete)
  python3 scripts/check_secrets.py -> no known credential patterns
  docker compose config --quiet    -> OK
  git diff --check                 -> clean
```

## 22. Final Outcome / Retrospective

Planned as a section to be filled at completion (What shipped / Changes from plan / Validation /
Limitations / Follow-ups / Lessons). No content yet — plan is READY; M0+M1 implemented and
validated; M2-M6 await separate authorization.

---

## MVP scope impact

**NO** — a read-only operational drill-down of the existing Home surface for internal operators,
consistent with ADR-002 (three primary surfaces + drill-down panels) and MVP §7; no new primary
area, no dashboard wall, no new data category. (If any subsequent EP-031 increment added a new
primary navigation area or publisher-facing analytics, MVP scope impact becomes YES and requires
an ADR.)

## New infrastructure / dependencies

**NO** — no new databases, queues, caches, SaaS, browser fleet, or observability vendor; no new
runtime process; no new dependencies (no chart library in v1). Smallest architecture satisfying
the milestone (PLANS.md §5, §49).