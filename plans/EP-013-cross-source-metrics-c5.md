# EP-013 — Cross-Source Normalized Metrics C5

**Status:** IN PROGRESS
**Owner:** Codex / Engineering
**Created:** 2026-08-20
**Updated:** 2026-08-20
**Target milestone:** C5 — Cross-source normalized metrics
**MVP scope impact:** NO
**New infrastructure category:** NO

## Progress

- [x] M0 — Confirm merged GAM C4 and canonical C5 boundaries
- [x] M1 — Add versioned derivation provenance and aligned input selection
- [x] M2 — Persist requests/view and impressions/view without inventing missing values
- [x] M3 — Add factual divergence helpers and background execution
- [ ] M4 — Prove migrations, counterexamples, idempotency, and final validation

## 1. Purpose and User Outcome

After this plan is complete, the platform can align GA4 consumption and GAM delivery telemetry on
the same explicit UTC intervals and persist two auditable ratios: GAM ad requests per GA4 measured
view and GAM ad-server impressions per GA4 measured view. Each result links to every selected
source point and preserves numerator, denominator, maturity, limitations, and rule version.

These metrics are diagnostic evidence. They do not represent physical pageview truth, explain a
cause, create an incident, or convert missing source data into zero.

## 2. Scope

### In

- source-namespaced `derived.requests_per_view_v1` and
  `derived.impressions_per_view_v1` hourly series;
- exact UTC interval matching and explicit compatible-freshness rules;
- deterministic selection of the best current source observation per series and interval;
- site-level aggregation across the fixed GA4 traffic and GAM inventory dimensions;
- append-only, idempotent derivation runs with point-level multi-source provenance;
- numerator/denominator storage and propagated limitations;
- pure factual helpers for aligned relative movement/divergence;
- tenant-owned background scheduling/worker execution;
- unit and PostgreSQL integration coverage.

### Out / Non-Goals

- Event Engine records, anomalies, incidents, causal labels, thresholds for business alerts,
  dashboards, arbitrary formulas, C6 drill-down queries, currency/revenue metrics, user-level data,
  or forced alignment across unequal periods/timezones;
- treating GA4 as physical pageview truth, treating unavailable/stale inputs as zero, or comparing
  different metric semantic versions as interchangeable.

## 3. Canonical References

- `AGENTS.md`, `PLANS.md`, and completed `plans/EP-012-gam-connector-c4.md`;
- `CONNECTORS.md` sections 89–92, 116–119, and milestone C5;
- `ARCHITECTURE.md` sections 38–40 and 98–100;
- `DATA_MODEL.md` sections 48–53, 58, 101–102, and 132–134;
- `MVP.md` Phase C and the third internal demo;
- accepted ADR-035, ADR-036, ADR-038, and ADR-039 in `DECISIONS.md`.

## 4. Current State

PR #13 is merged into `main` at `6e200eb`. C1–C4 provide immutable GA4, GSC, and GAM extracts,
source-namespaced series, append-only points, explicit UTC intervals, freshness, and PostgreSQL jobs.
`metric_points.source_extract_id` is implemented as mandatory even though the canonical model marks
it nullable, and there is no representation for a derived point with multiple source inputs.

## 5. Target Behavior

1. A scheduled tenant/site derivation pass reads only COMPLETE GA4 traffic and GAM inventory
   extracts inside a bounded window.
2. For every exact UTC interval and source series, it selects one current observation
   deterministically, preferring mature data and then the latest retrieval.
3. It aggregates only the fixed source metric semantics and requires compatible freshness across
   both sides.
4. A positive measured-view denominator yields the two versioned ratios with stored numerator and
   denominator. Missing, stale, unknown, misaligned, or zero-denominator inputs yield an explicit
   skip/limitation, never a fabricated point.
5. Re-running the same inputs is idempotent; changed reconciled inputs create a new immutable
   derivation with traceable source links.

## 6. Architecture / Data Flow

```text
DERIVE_CROSS_SOURCE job → best current GA4/GAM points → exact UTC bucket alignment
                                                        ↓
                              derivation run + input links + derived metric points
                                                        ↓
                                  factual movement/divergence helper (no event)
```

## 7. Files and Modules Affected

Add `backend/app/metrics/`, migration 0012, unit/integration tests, and EP-013. Modify connector
models, DB model registration, scheduler, worker, process tests, migration tests, and README where
needed. No new dependency, external service, secret, or infrastructure category is introduced.

## 8. Milestones and Acceptance

### M0 — Contract

- [x] branch begins from content equivalent to merged PR #13;
- [x] C5 remains derived metric evidence and excludes Event/Incident interpretation.

### M1 — Provenance and selection

- [x] schema represents one derivation and all of its source metric-point inputs;
- [x] derived points use exactly one derivation provenance and no fake source extract;
- [x] input selection is tenant/site scoped, COMPLETE-only, deterministic, and version constrained.

### M2 — Ratios

- [x] exact intervals and compatible freshness are mandatory;
- [x] requests/view and impressions/view preserve numerator and denominator;
- [x] missing, stale, unknown, partial, or zero-denominator data cannot become a derived zero.

### M3 — Divergence and execution

- [x] helpers report only aligned numeric movement facts, never cause or incident state;
- [x] bounded scheduler jobs and worker validation are tenant-owned and idempotent;
- [x] reprocessing identical inputs reuses the derivation while reconciled inputs remain append-only.

### M4 — Release gate

- [ ] unit/integration tests prove success, counterexamples, provenance, and isolation;
- [ ] lint, format, typing, migrations, backend/frontend, security, and CI gates pass;
- [ ] plan and README match the validated implementation.

## 9. Final Acceptance Criteria

- [ ] time alignment is explicit and uses period bounds rather than source labels;
- [ ] source metric names and semantics remain namespaced/versioned;
- [ ] every derived point is traceable to all selected source points and their extracts;
- [ ] limitations and freshness are conservative and visible;
- [ ] no connector absence or missing bucket produces a false business conclusion;
- [ ] no Event Engine or causal inference is introduced.

## 10. Validation Commands

```bash
uv --directory backend sync --all-groups --locked
uv --directory backend run ruff format --check .
uv --directory backend run ruff check .
uv --directory backend run mypy app tests scripts migrations/env.py
uv --directory backend run pytest tests/unit
RUN_INTEGRATION=1 uv --directory backend run pytest tests/integration
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend test -- --run
pnpm --dir frontend build
make secret-scan
docker compose config
git diff --check
```

## 11. Test Cases

Happy path: exact hourly alignment, mature and preliminary derivations, dimensional aggregation,
both ratios, source-link audit, deterministic idempotency, reconciliation, scheduler, and worker.

Counterexamples: missing numerator/denominator bucket, zero measured views, unequal interval,
different freshness, stale/unknown point, partial/failed extract, wrong semantic version, duplicate
extract observations, tenant/site mismatch, and invalid job payload.

Regression: Browser, GA4/GSC/GAM extraction, queues, migrations, frontend, and repository safety.

## 12. Data / Migration Impact

Migration 0012 makes `metric_points.source_extract_id` nullable, adds a nullable derivation FK and
an exactly-one-provenance constraint, and adds derivation/input tables with tenant/site ownership,
definition/rule version, interval, freshness, limitations, and deterministic keys. Existing source
points remain unchanged and continue requiring a source extract through the new XOR constraint.

## 13. Security / Privacy Impact

Derived values contain only aggregate telemetry already present in the tenant. Every read and
write is constrained by tenant and site; input linkage is validated before persistence. No token,
new personal data, provider response body, or external write is added.

## 14. Observability / Failure Handling

Record run definition/version, window, source metric semantics, alignment policy, selected input
IDs, freshness, limitations, result/skip counts, and sanitized error codes. A skipped interval is an
observability limitation, not a zero metric or connector-business anomaly.

## 15. Rollback Strategy

Stop `DERIVE_CROSS_SOURCE` jobs, revert EP-013 code, and downgrade migration 0012. The downgrade
first rejects/removes derived rows according to the migration contract, then restores mandatory
source-extract provenance; all C1–C4 source observations remain intact.

## 16. Known Risks

- Source extracts overlap during reconciliation, so current-point selection must not double count.
- GA4 and GAM dimensional rows are assumed to partition the fixed aggregate definitions; definition
  changes must produce new source semantics and fail the v1 derivation until explicitly supported.
- Exact UTC intervals avoid label errors but intentionally skip unequal daily/hourly boundaries.

## 17. Open Decisions

None blocking. C5 uses strict equal freshness classes. A later rules version may permit explicitly
documented mixed maturity, but v1 will not silently combine it.

## 18. Decision Log

- 2026-08-20: Store derived points in the canonical metric tables and represent multi-source
  provenance with a derivation run plus input links rather than a fake connector extract.
- 2026-08-20: Aggregate only fixed GA4 traffic and GAM inventory v1 definitions at exact hourly UTC
  intervals; use strict freshness equality and reject stale/unknown inputs.
- 2026-08-20: Keep divergence as a pure factual helper; event creation and thresholds remain later.

## 19. Discoveries / Surprises

- The canonical data model already marks `source_extract_id` nullable, while migration 0009 made it
  non-nullable; C5 is the first legitimate derived-provenance use case for the canonical shape.

## 20. Progress Log

- 2026-08-20: Confirmed PR #13 merge, created `agent/implement-ep-013`, inspected C5 contracts and
  fixed source definitions, and selected an auditable append-only provenance design.
- 2026-08-20: Added migration 0012, exact-provenance models, deterministic current-point selection,
  both ratios, strict missingness/freshness gates, generic aligned divergence facts, two-hour
  scheduling, worker execution, and unit/PostgreSQL integration coverage.
- 2026-08-20: Ruff, mypy, 168 unit tests, frontend lint/typecheck/test/build, secret scan, offline
  migration DDL, integration collection, and diff checks pass. PostgreSQL is unavailable locally,
  so migration round-trip and the new integration test remain for GitHub Actions.

## 21. Final Outcome / Retrospective

C5 is implemented locally with versioned, append-only cross-source ratio evidence and complete
point-level provenance. Final completion remains pending the PostgreSQL and repository CI gates.

## 22. Validation Results

- Ruff format/check — passed (138 backend files);
- mypy strict — passed (126 source/test files);
- backend unit — 168 passed, with one dependency deprecation warning;
- frontend ESLint/typecheck/Vitest/production build — passed;
- secret scan, offline migration DDL, integration collection, and `git diff --check` — passed;
- PostgreSQL migration round-trip/integration and CI process gates — pending remote CI because
  PostgreSQL and Docker are unavailable locally.
