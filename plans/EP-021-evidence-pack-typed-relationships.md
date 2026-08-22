# EP-021 — Evidence Pack & Typed Relationships

**Status:** COMPLETE
**Owner:** Codex / Engineering
**Created:** 2026-08-22
**Updated:** 2026-08-22
**Target milestone:** Evidence pack & typed relationships (PLANS.md §76.1)
**MVP scope impact:** NO
**New infrastructure category:** NO

## Progress

- [x] M0 — Baseline verification
- [x] M1 — Migration 0020: event_relations, manual_notes, evidence_packs
- [x] M2 — Typed relationships and manual-notes repositories
- [x] M3 — Deterministic evidence-pack builder + sanitized fixture inventory
- [x] M4 — Full validation and release readiness

## 1. Purpose and User Outcome

After this plan ships, investigations can cite a deterministic, reproducible evidence pack —
assembled from real stored evidence within a bounded window — and every relationship between
events is a typed, auditable database row instead of prose. Operators can record manual
operational changes as clearly-human evidence that never automatically becomes deterministic
truth. Sanitized connector fixtures are inventoried and composed so hypothesis ranking (EP-023)
can be tested without live OAuth.

## 2. Scope and Non-Goals

### In

- migration 0020: `event_relations` (DATA_MODEL §64 shape), `manual_notes` (DATA_MODEL manual
  notes section), `evidence_packs` (append-only generation records);
- typed relation vocabulary exactly per DATA_MODEL: PRECEDES, COINCIDES_WITH, SAME_SEGMENT_AS,
  MECHANISTICALLY_CAN_AFFECT, METRIC_PARENT_OF, METRIC_DESCENDANT_OF, SUPPORTS, CONTRADICTS,
  INTRODUCED_BY, RESOLVED_AFTER, PERSISTED_AFTER_REMOVAL, EXTERNAL_CONTEXT_FOR,
  UNKNOWN_RELATION; CAUSES stays reserved;
- append-only repositories for relations and manual notes (no update paths; mapper guards);
- deterministic evidence-pack builder over stored evidence: scheduled checkpoint runs,
  public-config snapshot states, events with relation counts, incident window/scope, manual notes
  clearly tagged human_reported — recorded inputs, engine version, stable content ordering;
- sanitized connector fixture inventory documented and composed into reusable Python fixtures for
  EP-023;
- unit + PostgreSQL integration tests.

### Out / Non-Goals

- intake/localization behavior changes (EP-020 shipped);
- Inspect AI (EP-022); hypothesis lifecycle/ranking (EP-023);
- OAuth/onboarding (EP-024); UI (EP-025); retention enforcement/telemetry/WAF handling (EP-026);
- entity-mapping provenance lifecycle (deferred gap);
- graph databases (ADR-026: relational edges only); CAUSES relations;
- automatic promotion of manual notes into events or deterministic facts;
- new collectors or event-catalog breadth.

## 3. Canonical References

- AGENTS.md §2.1, §7, §15–18, §20, §28;
- DATA_MODEL.md §63–65 (events/event_relations/relational graph + relation vocabulary),
  manual_notes section, §104 retention holds;
- DECISIONS.md ADR-026 (relational edges), ADR-033 (predefined extracts), ADR-045 (manual changes
  are first-class evidence), ADR-064 (corpus precedent not truth), ADR-089/090, ADR-130;
- INCIDENT.md — evidence supports AND contradicts hypotheses;
- EVENTS.md §0.1 legend (derivation boundary unchanged);
- CONNECTORS.md — sanitized fixtures discipline;
- completed EP-019 (foundations) and EP-020 (incident workflow).

## 4. Current State

Main after EP-020 merge (`72067a8`). Evidence sources available to a pack: `checkpoint_runs`
(+ collector observations), `public_config_snapshots`, `events` + `event_evidence_refs`,
`source_extracts`, `metric_points`/`metric_series`. No relations table, no manual-note table, no
pack assembly. Sanitized connector fixtures exist under
`backend/tests/fixtures/connectors/{ga4,gsc,gam}/` (GA4 metadata/traffic/behavior/thresholded;
GSC sites/search-daily/discover-empty/url-inspection; GAM networks/report pages/today report) and
are exercised by connector suites. Migration head `0019`.

## 5. Target Behavior

1. Relations between events are rows: (from_event, to_event, relation_type) with optional
   confidence/reason, derived_at, engine_version; inserts are append-only; any ORM update raises;
   duplicates collapse on UNIQUE (tenant, from, to, relation_type, engine_version).
2. Manual notes are appended with bounded type vocabulary (DEPLOY, ROLLBACK, CONFIG_CHANGE,
   OPERATOR_INTERVENTION, EXTERNAL_COMMUNICATION, OTHER), optional occurred-at, author reference;
   queryable per site/incident; structurally unread by event derivation.
3. build_evidence_pack(tenant, incident_id, window, fingerprints) deterministically collects:
   incident + segments, scheduled runs in window (bounded fields), public-config snapshot states,
   events in window with relation counts, manual notes overlapping the window tagged
   human_reported — producing an ordered JSON-serializable structure whose stable hash is
   recorded. Identical repository state produces byte-identical packs. Packs persist append-only
   with engine version and input bounds; oversize fails closed.
4. Fixture composition helper exposes sanitized GA4/GSC/GAM payload dicts (loading the existing
   JSON fixtures) so EP-023 can test ranking against connector evidence without network access.

## 6. Architecture / Data Flow

```text
app/evidence/persistence.py   relations · manual notes · pack persistence (tenant-scoped)
app/evidence/builder.py       deterministic assembly over existing tables
app/evidence/contracts.py     vocabularies, pack shapes, validation
tests/fixtures/connectors/*   existing sanitized provider payloads (documented inventory)
tests/unit/test_pack_builder.py        determinism/provenance
tests/integration/test_evidence_relations.py
```

No scheduler/worker/browser/connector/public-config runtime paths change.

## 7. Data Model / Migration Impact

Migration `0020_evidence_relationships`:

```text
event_relations
  id PK · tenant FK RESTRICT · site FK RESTRICT
  from_event_id/to_event_id FK events RESTRICT
  relation_type CHECK IN (vocabulary above)
  confidence text NULL CHECK IN (LOW/MEDIUM/HIGH)
  reason text NULL · derived_at NOT NULL · engine_version NOT NULL · created_at
  UNIQUE (tenant_id, from_event_id, to_event_id, relation_type, engine_version)

manual_notes
  id PK · tenant/site FKs RESTRICT · incident_id NULL FK RESTRICT
  note_type CHECK IN ('DEPLOY','ROLLBACK','CONFIG_CHANGE',
                      'OPERATOR_INTERVENTION','EXTERNAL_COMMUNICATION','OTHER')
  note_text text NOT NULL · occurred_at NULL · created_by uuid NULL
  source text NOT NULL default 'operator' · created_at
  index (tenant_id, site_id, created_at)

evidence_packs
  id PK · tenant/site FKs RESTRICT · incident_id NULL FK RESTRICT
  window_start/window_end NOT NULL · fingerprints jsonb NOT NULL
  content jsonb NOT NULL (bounded) · content_hash text NOT NULL
  engine_version NOT NULL · created_at
  UNIQUE (incident_id, window_start, window_end, content_hash)
```

Downgrade refuses while any table contains rows.

## 8. Milestones

### M0 — Baseline verification
- [ ] branch/clean main/post-merge CI green; DATA_MODEL §63–65 re-read; fixture inventory listed.

### M1 — Migration 0020 and models
- [ ] upgrade/downgrade/up from clean DB; vocabulary violations rejected at database level;
      table inventory updated; downgrade refuses while rows exist.

### M2 — Relations & manual-notes repositories
- [ ] duplicate relation collapses on unique key; update raises (frozen);
- [ ] unknown relation type / note type rejected;
- [ ] cross-tenant reads/writes impossible;
- [ ] import-boundary test asserts event derivation never imports manual-notes module.

### M3 — Deterministic evidence pack + fixtures
- [ ] identical state ⇒ identical content and hash;
- [ ] pack includes only in-window, tenant-owned evidence with source tags (machine_observed vs
      human_reported);
- [ ] oversize pack fails closed with controlled error;
- [ ] sanitized GA4/GSC/GAM fixture composition helper available for EP-023.

### M4 — Full validation and release readiness
- [ ] full ladder local + CI green; README sentence; plan COMPLETE.

## 9. Final Acceptance Criteria

- [x] typed relations are append-only, vocabulary-bound, tenant-scoped, uniquely deduplicated;
- [x] manual notes are auditable human evidence isolated from deterministic derivation;
- [x] evidence packs are deterministic, bounded, provenance-complete, persistable;
- [x] sanitized GA4/GSC/GAM fixture inventory documented and consumable by EP-023;
- [x] no runtime behavior outside the new module changes;
- [x] full ladder green locally and in CI.

## 10. Test Cases

Happy: relation insert/dedupe; note append/query; pack build/persist/rebuild equality; fixture
composition loads all three providers.
Counterexamples: CAUSES rejected; unknown types rejected; cross-tenant refused; oversize pack
fails closed; update attempts raise; derivation module does not import manual notes.
Regression: full suites; migration inventory.

## 11. Final Validation

Same ladder as prior plans (ruff format/check, mypy, unit suite, clean-DB upgrade/downgrade-up,
full PostgreSQL integration incl. Chromium + E1/E2/E3 regressions, scheduler/worker smoke,
frontend suite/build, secret scan, compose config, whitespace checks, GitHub CI).

## 12. Security / Privacy Impact

Packs bundle confidential operational evidence — tenant-scoped, never public, no external
transmission. Manual-note author references stay opaque pending OPEN-003. Relation/note text is
length-bounded.

## 13. Observability / Failure Handling

Typed `EvidenceStateError`; oversize packs fail closed with `EVIDENCE_PACK_TOO_LARGE`; no silent
truncation.

## 14. Rollback Strategy

Downgrade refuses while tables contain rows. No runtime consumers yet, so revert is safe after
explicit data clearance.

## 15. Known Risks

Pack content schema will evolve; mitigated by engine_version + fingerprint snapshots. Fixture
realism ceiling: synthetic payloads cannot cover every provider quirk; EP-023 may extend them
incrementally.

## 16. Open Decisions

None block implementation. Relation inference rules (which relations are auto-created versus
human-recorded) are deferred to EP-023 where they have a consumer.

## 17. Decision Log

### 2026-08-22 — Pack determinism over incrementality

**Decision:** Packs rebuild from stored evidence each generation and persist by content hash;
no incremental pack mutation.

**Reason:** Reproducibility is the product claim; identical state must yield identical packs.

**Alternatives:** Incremental pack updates — rejected: ordering/versioning complexity without a
consumer.

**Impact:** Rebuilding large windows costs queries only; bounded by window limits.

### 2026-08-22 — Autopilot execution; M0–M4 complete

Implemented migration 0020, the `app/evidence` module (models/contracts/persistence/builder with
append-only guards on relations and a deterministic pack builder), unit + integration suites, and
a consolidated guarded-downgrade descent test in `test_migrations.py` replacing three
order-fragile scattered tests. Sanitized GA4/GSC/GAM fixtures inventoried and exposed via
`app/evidence/fixtures.py`. No human gates encountered.

## 18. Discoveries / Surprises

- The `(window, url, scenario)` uniqueness constraint structurally forbids mixing observation
  kinds per window; cohort purity rests on that constraint plus write-path discipline plus
  derivation filters.
- Cross-module FK metadata requires importing every model module in test processes; conftest now
  mirrors migrations/env.py imports.
- Consolidating three order-fragile guarded-downgrade tests into one ordered descent test removed
  shared-database interference permanently.
- Purge helpers must call the session factory twice (`session_factory()()`) — the factory is not
  itself an async context manager.

## 20.1 Validation Results

### Local validation — 2026-08-22

- ruff format/check, mypy: PASS (222 files / 202 sources).
- Unit suite: PASS, 271 tests (+4 evidence contracts).
- Clean-DB upgrade → head 0020; full downgrade base / re-upgrade: PASS.
- Full PostgreSQL integration suite after consolidation: PASS, **60/60**.
- Frontend lint/typecheck/test/build, scheduler/worker smoke, secret scan, compose config,
  whitespace checks: PASS.

## 19. Progress Log

### 2026-08-22

Created under the multi-ExecPlan program immediately after EP-020's merge and green post-merge CI.
Marked READY: schema traces to DATA_MODEL sections; no human-gated decision required; validation
fully defined. Implementation not started.

### GitHub CI — 2026-08-22

All required checks green for pushed heads of this branch (backend incl. PostgreSQL integration,
frontend, repository-safety).

## 20. Final Outcome / Retrospective

### What shipped

Typed, append-only event relationships bound to the DATA_MODEL vocabulary with CAUSES reserved;
auditable manual operational notes structurally isolated from derivation; deterministic,
content-hashed, bounded evidence packs assembled from scheduled checkpoints, public-config
states, events, relations, and clearly-tagged human notes; sanitized connector fixture inventory
composed for EP-023 ranking tests.

### What changed from the plan during implementation

Consolidated the three prior guarded-downgrade tests into one ordered descent test to eliminate
shared-database interference discovered during full-suite runs (test-only change touching EP-018/
EP-019 test files, recorded here).

### Known limitations

Pack content schema will evolve with engine versions; relation inference rules arrive with EP-023.

### Follow-ups

PR review/merge requires human authorization; then EP-022 Inspect AI Eval Runtime per roadmap.
