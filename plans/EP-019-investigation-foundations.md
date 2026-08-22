# EP-019 — Investigation Foundations

**Status:** READY
**Owner:** Codex / Engineering
**Created:** 2026-08-22
**Updated:** 2026-08-22
**Target milestone:** Investigation foundations (PLANS.md §76.1)
**MVP scope impact:** NO
**New infrastructure category:** NO

## Progress

- [ ] M0 — Baseline verification and contract inspection
- [ ] M1 — Migration 0018: incident, LKG reference, budget ledger, and retention-hold schema
- [ ] M2 — Version-comparability contract and deterministic LKG selection
- [ ] M3 — Budget ledger, retention-hold API, and provenance immutability guarantees
- [ ] M4 — Full validation and release readiness

## 1. Purpose and User Outcome

After this plan ships, the repository has the durable, tenant-scoped data model and invariants
required before any incident behavior exists: incident core records, frozen Last Known Good
references with recorded version fingerprints, a unified evidence-version comparability contract,
a generic persistent investigation budget ledger, and retention-hold hooks that can pin
investigation-owned evidence. No user-facing workflow changes; this is the foundation the intake,
localization, evidence-pack, and ranking milestones build on.

## 2. Scope and Non-Goals

### In

- migration 0018: `incidents`, `incident_symptom_segments`, `last_known_good_refs`,
  `retention_holds`, and a generic investigation budget ledger table;
- deterministic Last Known Good eligibility/selection contract: scheduled-only (ADR-130),
  healthy status, comparable version fingerprints, site/template scope, frozen append-only rows;
- unified version-comparability fingerprint helper covering collector bundle, per-subsystem
  normalizer versions, and rule-bundle versions, used by LKG selection and exposed for future EPs;
- investigation budget scaffold: idempotent resource-consumption ledger with per-incident limits;
- retention-hold create/release API over the DATA_MODEL §104 table shape;
- tenant isolation, audit timestamps, and fail-closed downgrade guards throughout;
- unit + PostgreSQL integration + migration tests.

### Out / Non-Goals

- user-facing incident intake workflow or API (EP-020);
- localization behavior in time/scope beyond storing symptom-segment rows (EP-020);
- evidence-pack generation or typed relationship graph (EP-021);
- hypothesis lifecycle, contradictions, ranking (EP-023);
- Inspect AI / eval runtime (EP-022);
- LLM synthesis;
- UI of any kind (EP-025);
- connector OAuth/secrets (EP-024);
- retention deletion/enforcement jobs — this plan only provides hold hooks (EP-026);
- cost telemetry roll-up, circuit breakers, DST test expansion (EP-026);
- entity-mapping provenance lifecycle (deferred gap, PLANS.md §76.1).

## 3. Canonical References

Read:

- `AGENTS.md` — §2.1 implementation-authorization invariant, §7 evidence invariants,
  §15–18 ExecPlan rules, §20 data-model changes, §28 diff discipline;
- `PLANS.md` — planning contract; §76.1 amended forward sequence;
- `DATA_MODEL.md` — §66 `last_known_good_refs`, §67 `incidents`, §68
  `incident_symptom_segments`, §104 `retention_holds`, §105 audit timestamps;
- `DECISIONS.md` — ADR-005 (intake starts from symptom), ADR-006 (UNRESOLVED valid),
  ADR-007 (no fake numeric confidence), ADR-029 (time uncertainty first-class), ADR-047–049
  (baseline/localization before explaining), ADR-060/061 (LKG incident-specific, reference only,
  no auto-rollback), ADR-089/090 (tenant scoping), ADR-096/097 (bounded retention, pinned
  incident evidence), ADR-130 (scheduled-only cohort eligibility);
- `INCIDENT.md` — §88 Last Known Good selection/freeze requirements;
- `EVENTS.md` — §0.1 implementation-status legend (this plan touches foundations only);
- completed `plans/EP-018` (observation-kind column enabling scheduled-only eligibility).

Relevant invariants:

- LKG is incident-specific, reference-only, never auto-applied (ADR-060/061);
- once selected for an investigation, an LKG reference is frozen and auditable; later
  scenario/collector/normalizer/parser version changes must not retrospectively alter it;
- UNRESOLVED/CLOSED_UNRESOLVED are valid terminal states; no forced cause;
- every row is tenant-scoped and validated server-side;
- evidence semantics outrank migration convenience.

## 4. Current State

Post-EP-018 main (`690c9c1`). Repository facts verified by inspection:

- no incident/investigation tables exist; `incidents` is documented at DATA_MODEL §67 but has no
  migration;
- `last_known_good_refs` is documented (DATA_MODEL ~line 2425) with `valid_for_incident_id`,
  `selection_method`, `selection_version`, `reason` fields — unbuilt;
- comparison predecessor selection exists (`previous_comparable_selection`,
  `browser/persistence.py`) and already filters to `observation_kind = 'SCHEDULED'` (EP-018) but
  has no fingerprint comparability check beyond per-component normalizer equality at diff time;
- version vocabularies today: `collector_bundle_version` ("b8-v1"), normalizer versions per
  subsystem ("robots-rfc9309-v1", "ads-txt-1.1-v1"), event rule bundles ("e3-v1"), metric
  derivation policies — no unified fingerprint registry;
- retention: `artifacts.retention_class` metadata exists; DATA_MODEL §104 `retention_holds` is an
  optional documented table; nothing enforces holds and no deletion jobs exist (EP-026);
- budgeting: connector drill-down caps exist (`MAX_DRILLDOWNS_PER_INVESTIGATION=4`) enforced via
  job-payload counts; no generic persistent budget ledger;
- migration head is `0017_observation_run_kind`.

## 5. Target Behavior

1. Migration 0018 creates five tenant-scoped tables with audit timestamps, CHECK-constrained
   vocabularies, and fail-closed downgrade guards.
2. `incidents` rows can be created only through the repository API with controlled status
   vocabulary (`OPEN`, `INVESTIGATING`, `RESOLVED`, `CLOSED_UNRESOLVED`); symptom segments attach
   as structured rows preserving the free-text description verbatim elsewhere on the incident.
3. `evidence_fingerprints()` returns a deterministic, ordered mapping of evidence-version
   identities for a site's subsystems; two fingerprints are comparable iff equal. LKG eligibility
   requires fingerprint equality between candidate run and the requesting context.
4. LKG selection is a pure deterministic function: eligible candidates are `COMPLETE` scheduled
   runs (ADR-130) with equal fingerprints, scoped to site (+ optional template/scenario), ordered
   by recency. Selection persists one frozen append-only `last_known_good_refs` row recording
   method/version/reason/fingerprints and `valid_for_incident_id`. Rows are never updated or
   deleted through application paths.
5. The budget ledger records consumption as append-only entries keyed by
   `(investigation_ref, resource_kind)`; current usage derives from summed entries against a
   per-resource default limit registry; duplicate consumption attempts converge idempotently via
   deterministic entry keys.
6. Retention holds can be created (optionally bound to an incident/artifact/extract) and released;
   release records who/when; holds expose a query other modules can use to refuse deletion of
   held objects (enforcement consumers arrive in EP-026).
7. Nothing user-facing changes: no new endpoints, jobs, scheduler entries, or UI.

## 6. Architecture / Data Flow

```text
migration 0018
   ↓
app/incidents repository (tenant-scoped)
   ├── incidents / symptom segments        (core schema; consumed by EP-020)
   ├── last_known_good_refs                (frozen selection; consumed by EP-020+)
   │      ↑ eligibility: previous-style query + fingerprint equality + SCHEDULED (EP-018 kinds)
   ├── investigation usage ledger          (idempotent consume(); consumed by EP-020/022/023)
   └── retention_holds                     (create/release/query; enforced by EP-026)

app/common/comparability.py
   └── evidence_fingerprints(site context) → ordered version identity mapping
```

No scheduler, worker, queue, browser, connector, or public-config code paths change.

## 7. Files and Modules Affected

### Existing

- `backend/tests/integration/test_migrations.py` — table inventory additions.

### To create

- `backend/migrations/versions/0018_investigation_foundations.py`;
- `backend/app/common/comparability.py` — fingerprint construction/equality helpers;
- `backend/app/incidents/__init__.py`, `contracts.py`, `models.py`, `persistence.py`;
- `backend/tests/unit/test_comparability.py`;
- `backend/tests/unit/incidents/test_contracts.py`;
- `backend/tests/integration/test_investigation_foundations.py`.

Paths may adjust for clear module boundaries; record deviations here.

## 8. Data Model / Migration Impact

Migration `0018_investigation_foundations`:

```text
incidents
  id uuid PK · tenant_id FK RESTRICT · publisher_id FK RESTRICT · site_id FK RESTRICT
  title text · symptom_family text CHECK bounded · description text
  reported_start_at/report_end nullable · opened_at NOT NULL
  status CHECK IN ('OPEN','INVESTIGATING','RESOLVED','CLOSED_UNRESOLVED') default 'OPEN'
  severity text NULL · created_by uuid NULL (no FK; operator identity arrives with auth EP)
  resolved_at NULL · resolution_summary NULL · created_at · updated_at
  index (tenant_id, site_id, status)

incident_symptom_segments
  id PK · tenant_id · incident_id FK CASCADE · dimension/operator/value text
  source text · created_at
  index (tenant_id, incident_id)

last_known_good_refs
  id PK · tenant_id · site_id · template_id NULL · scenario_id NULL
  scope_key text NOT NULL · checkpoint_run_id FK RESTRICT
  valid_for_incident_id uuid NULL (no hard FK in v1; incidents arrive in same migration —
      use FK RESTRICT to incidents.id, nullable)
  selected_at NOT NULL · selection_method text · selection_version text · reason text
  fingerprints jsonb NOT NULL (ordered evidence_fingerprints snapshot)
  created_at
  UNIQUE (scope_key, valid_for_incident_id, checkpoint_run_id)
  index (tenant_id, site_id, scope_key)

investigation_usage
  id PK · tenant_id
  incident_id uuid NULL FK RESTRICT · investigation_key text NOT NULL
  resource_kind text NOT NULL CHECK bounded ('DRILLDOWN', reserved: 'LLM_PASS','DIAGNOSTIC_RUN')
  amount integer NOT NULL default 1
  usage_key text NOT NULL (idempotency identity)
  detail jsonb bounded · occurred_at NOT NULL · created_at
  UNIQUE (usage_key)
  index (tenant_id, incident_id, resource_kind)

retention_holds
  id PK · tenant_id · incident_id NULL FK SET NULL · artifact_id NULL FK RESTRICT
  source_extract_id NULL FK RESTRICT · reason text NOT NULL
  created_at · released_at NULL · released_by text NULL
```

Downgrade refuses while any of these tables contain rows (fail-closed evidence safety), then drops
in reverse dependency order.

Schema-only notes: `incident_symptom_segments` lands here so EP-020 intake writes into an existing
contract; no behavior reads it yet. `created_by`/`released_by` are opaque operator references
until authentication exists (OPEN-003); they are never provider credentials.

## 9. Milestones

### M0 — Baseline verification

Acceptance:

- [ ] branch from clean `origin/main`; post-merge CI green;
- [ ] DATA_MODEL §66–68/§104 re-read and reconciled against this plan;
- [ ] confirm no existing module reserves the `app/incidents` namespace.

Validation: git state checks + CI run listing.

### M1 — Migration 0018 and models

Implementation: tables/constraints/indexes above; SQLAlchemy models mirror exactly; downgrade
guards refuse while rows exist.

Acceptance:

- [ ] upgrade/downgrade/upgrade from clean database passes;
- [ ] status/vocabulary violations rejected by database;
- [ ] table inventory test extended.

Validation:

```bash
uv --directory backend run pytest tests/integration/test_migrations.py
```

### M2 — Comparability contract and LKG selection

Implementation:

- `app/common/comparability.py`: `evidence_fingerprints(...)` building a sorted, stable mapping
  from known version inputs (collector bundle, robots/ads normalizers, rule bundles as applicable)
  plus `fingerprints_comparable(a, b) -> bool` (equality of full mappings);
- LKG repository: `select_eligible(...)` deterministic query (SCHEDULED + COMPLETE +
  fingerprint-equal + site/template/scenario scope + recency order) and
  `freeze_selection(...)` appending an immutable reference row (mapper-level immutability guard
  reused from the EP-018 pattern for post-creation mutation).

Acceptance:

- [ ] identical inputs produce byte-stable fingerprints;
- [ ] differing collector/normalizer/rule versions are incomparable (each dimension alone);
- [ ] diagnostic-run candidates are ineligible (kind filter);
- [ ] frozen reference mutation raises; second identical selection converges on the same row.

Validation:

```bash
uv --directory backend run pytest tests/unit/test_comparability.py
uv --directory backend run pytest tests/integration/test_investigation_foundations.py -k lkg
```

### M3 — Budget ledger and retention holds

Implementation:

- usage ledger `consume(...)` with deterministic `usage_key` (idempotent under retries), bounded
  `resource_kind` registry, and `current_usage(...)` aggregation vs default limit registry;
- retention holds `create_hold(...)` / `release_hold(...)` / `active_holds_for(...)`;
  release stamps `released_at`/`released_by`; released rows remain queryable history.

Acceptance:

- [ ] duplicate consume with same usage key inserts once;
- [ ] current usage equals summed distinct entries;
- [ ] unknown resource kind rejected;
- [ ] hold create/release round-trips; active query excludes released holds;
- [ ] all operations tenant-checked (cross-tenant rejection tested).

Validation:

```bash
uv --directory backend run pytest tests/integration/test_investigation_foundations.py
```

### M4 — Full validation and release readiness

Acceptance:

- [ ] all M1–M3 criteria pass;
- [ ] README boundary summary sentence updated (foundations shipped; no behavior change);
- [ ] full ladder green locally and in CI;
- [ ] retrospective completed; status COMPLETE only after results recorded.

## 10. Final Acceptance Criteria

- [ ] five tables land with constraints, indexes, audit timestamps, tenant scoping, and guarded
  downgrades;
- [ ] deterministic LKG eligibility honors ADR-130 kinds, fingerprint comparability, scope, and
  freeze-on-selection;
- [ ] budget ledger is idempotent, bounded, tenant-scoped, and queryable;
- [ ] retention-hold API supports create/release/query with immutable history after release;
- [ ] no scheduler/worker/browser/connector/public-config behavior changes;
- [ ] full validation ladder passes locally and in CI.

## 11. Test Cases

Happy path: incident creation with segments; LKG freeze for eligible scheduled run; budget
consume/query; hold create/query/release.

Failure paths: invalid status/kind/source vocabulary; incomparable fingerprints (each version
dimension varied); diagnostic candidate ineligible; duplicate consume collapses; cross-tenant
access rejected everywhere; downgrade refusal with live rows.

Regression: existing suites unchanged; migration inventory updated; E1/E2/E3 and EP-018 suites
green.

## 12. Final Validation

```bash
uv --directory backend run ruff format --check .
uv --directory backend run ruff check .
uv --directory backend run mypy app tests scripts migrations/env.py
env -u DATABASE_URL uv --directory backend run pytest tests/unit
uv --directory backend run alembic upgrade head
RUN_INTEGRATION=1 uv --directory backend run pytest tests/integration
pnpm --dir frontend lint && pnpm --dir frontend typecheck && pnpm --dir frontend test
python scripts/check_secrets.py
docker compose config
git diff --check
```

## 13. Security / Privacy Impact

New tables store incident titles/descriptions/symptom segments — tenant-confidential operational
data (ADR-088). All access server-side and tenant-scoped (ADR-089/090). No credentials, tokens,
provider calls, or external input surfaces. `created_by`/`released_by` are opaque operator
references pending OPEN-003; they must never carry secrets.

## 14. Observability / Failure Handling

Repository methods raise typed state errors (`InvestigationStateError`) mapped by future callers;
no new job types or logs required. Structured logging remains the caller's concern until EP-020
wires workflows.

## 15. Rollback Strategy

Downgrade refuses while foundation rows exist (evidence-safe). Because no runtime behavior reads
these tables yet, revert-and-downgrade after clearing pilot-free data is safe; destructive
clearance itself would require explicit human authorization.

## 16. Known Risks

- Fingerprint registry must stay synchronized with real version constants; mitigated by sourcing
  values from existing modules (single import path) rather than literals.
- Budget limits chosen now are provisional defaults; changing them later is additive metadata.
- `valid_for_incident_id` FK makes incident deletion impossible while LKG refs exist — intended
  (evidence pinning), consistent with ADR-097.

## 17. Open Decisions

None block implementation. Authentication/operator identity (OPEN-003), secret-provider choice
(OPEN-005), and concrete budget limit values per resource remain open and are deliberately not
needed here; EP-020+ plans inherit the ledger without schema change.

## 18. Decision Log

### 2026-08-22 — Generic usage ledger instead of per-feature counters

**Decision:** One `investigation_usage` append-only ledger with bounded `resource_kind`
vocabulary and deterministic `usage_key`, replacing per-feature counter tables.

**Reason:** Extends the proven drill-down pattern (persistent counts via unique keys) to all
future resources (drilldowns, LLM passes, diagnostic runs) without schema churn per feature.

**Alternatives:** Counter columns on incidents — rejected: concurrent increments lose history and
auditability.

**Impact:** Aggregation is a SUM over entries; fine at MVP scale (tens/hundreds of incidents).

### 2026-08-22 — LKG references are append-only, frozen at creation

**Decision:** `last_known_good_refs` rows are insert-only; fingerprints are snapshotted into the
row at selection time; later version drift cannot alter an existing reference.

**Reason:** INCIDENT.md §88 + ADR-060/061 freeze requirement; retrospective baseline mutation
would invalidate open investigations.

**Alternatives:** Mutable current-LKG pointer — rejected: destroys per-investigation freezing.

**Impact:** Repeat selections for the same incident converge via the uniqueness constraint rather
than updating.

### 2026-08-22 — Symptom-segment schema precedes intake behavior

**Decision:** Land `incidents` + `incident_symptom_segments` schema in EP-019 even though only
EP-020 writes them.

**Reason:** DATA_MODEL is the schema contract; landing it early keeps EP-020 a pure behavior
plan and lets constraint design be reviewed independently.

**Alternatives:** Defer both tables to EP-020 — rejected: splits the reviewed schema contract
across behavior work.

**Impact:** Two unused-by-runtime tables exist temporarily; acceptable and documented.

## 19. Discoveries / Surprises

To be recorded during implementation.

## 20. Progress Log

### 2026-08-22

Created from the approved roadmap amendment splitting the former combined EP-019 into
Investigation Foundations (this plan) and Incident Intake & Localization (EP-020). Marked READY:
schema contracts trace to DATA_MODEL sections, no unresolved architecture/product decision blocks
implementation (auth/provider/budget-value decisions explicitly out of scope), validation fully
defined. Implementation not started.

## 21. Final Outcome / Retrospective

Pending implementation. Complete after M4 with validation results and commit/PR references.
