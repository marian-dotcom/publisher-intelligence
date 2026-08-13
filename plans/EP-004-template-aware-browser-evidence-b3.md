# EP-004 — Template-aware Browser Evidence B3

**Status:** COMPLETE
**Owner:** Codex / Engineering
**Created:** 2026-08-14
**Updated:** 2026-08-14
**Target milestone:** B3 — Template-aware browser evidence
**MVP scope impact:** NO
**New infrastructure category:** NO

## Progress

- [x] M0 — Verify B2 integration and close the B3 contract
- [x] M1 — Complete template configuration and normalized-evidence schema
- [x] M2 — Add deterministic DOM, script, network, and error normalization
- [x] M3 — Persist versioned normalized evidence and stable entity observations
- [x] M4 — Produce explainable URL/template comparison output
- [x] M5 — Prove migration, tenancy, recomputability, and real-browser behavior
- [x] M6 — Complete documentation, final CI, and retrospective

## 1. Purpose and User Outcome

After this plan is complete, repeated browser runs will preserve a stable structural description of
each monitored page rather than forcing operators to compare noisy raw HTML. A concrete article URL
may be retired and replaced while its template identity remains stable. For each compatible run,
the platform will record normalized DOM structure, stable script and network dependency identities,
normalized JavaScript error fingerprints, expected template references, and an explainable list of
what was added, removed, or structurally changed relative to the previous comparable checkpoint.

This is evidence preparation, not incident intelligence. B3 does not promote differences into
events, send alerts, assign severity, claim causality, or use AI.

## 2. Scope

### In

- complete the existing template record with family, fingerprint/expectation metadata, and archive
  lifecycle without rewriting historic B1/B2 evidence;
- deterministic, bounded, versioned structural DOM normalization;
- stable script identities based on normalized host/path family rather than query cache-busters;
- stable network dependency identities, safe aggregate counts, status families, and categories;
- deterministic JavaScript/page-error fingerprints without retaining volatile identifiers in keys;
- long-lived normalized DOM artifact plus compact normalized state in the checkpoint manifest;
- tenant/site-owned domain entities and append-only entity observations for scripts/dependencies;
- exact same-URL/scenario predecessor first, then same-template/exact-scenario fallback for rotated
  representative URLs;
- structured comparison kinds: presence, set, status, and structural change;
- explicit collector/normalizer versions and limitation reporting;
- migration, unit, PostgreSQL/MinIO/Chromium integration, frontend regression, and security tests.

### Out

- GPT slot lifecycle or expected slot records (B4);
- CMP actions (B5), Prebid (B6), video (B7), or synthetic performance (B8);
- automatic template discovery or silent promotion of crawled URLs;
- automatic representative-URL rotation, crawling every article, or publisher-wide link discovery;
- pixel-level screenshot diffing or visual AI;
- event promotion, alerting, severity, Last Known Good selection, incidents, hypotheses, or AI;
- production deployment or new network/storage infrastructure.

## 3. Canonical References

Preserve:

- `AGENTS.md` sections 7–8, 13–21, 25, 28–32;
- `PLANS.md` implementation loop and EP-004 sequence;
- `MVP.md` sections 8–23 and Phase B;
- `BROWSER.md` sections 4–6, 18–25, 56–62, and milestones B3/B4;
- `ARCHITECTURE.md` systems of record, object storage, and normalization/diff pipeline;
- `DATA_MODEL.md` templates, monitored URLs, collector runs, domain entities, entity observations,
  JavaScript errors, hashing, versioning, retention, and required isolation tests;
- `SECURITY.md` long-lived normalized versus shorter-lived raw evidence rules;
- `DECISIONS.md` ADR-010, ADR-011, ADR-016, and ADR-017;
- completed `plans/EP-003-repeatable-browser-runs-b2.md`.

Contract anchors:

- raw checkpoint evidence is immutable;
- normalized evidence is derived, versioned, and reproducible;
- template identity survives representative-URL rotation;
- hashes do not imply semantic equality without documented normalization rules;
- a collector/normalizer change must be distinguishable from a publisher change;
- browser differences are evidence, not events or causes.

## 4. Current State

EP-003 is merged into `main` in PR #4 at merge commit `57a8c58`. The system now schedules frozen
desktop/mobile runs every site-local six-hour window, executes deterministic scroll profiles,
persists raw DOM/screenshots/manifests, and identifies the previous exact URL/scenario run.

The concrete B3 gaps are:

- `templates` only stores code/display name/status;
- manifests carry raw script URLs and host sets but no stable normalized identities;
- request status/path/resource evidence is not retained as safe aggregates;
- raw DOM exists, but there is no normalized structural artifact;
- no domain-entity or entity-observation persistence exists;
- predecessor selection cannot cross an intentional representative-URL rotation;
- manifests expose lineage but not explainable structured differences;
- observer version changes cannot yet be separated cleanly from normalized-state changes.

## 5. Target Behavior

For a completed checkpoint, B3 will:

1. retain the raw DOM unchanged under the existing medium-term retention class;
2. derive a deterministic structural representation using a frozen normalizer version;
3. retain only meaningful element/attribute structure and replace recognized volatile values;
4. normalize scripts and requests into stable host/path/resource/category identities;
5. aggregate counts and response/error state without storing bodies, cookies, or unsafe headers;
6. persist stable entities and append-only observations scoped to tenant/site/run;
7. choose the prior same URL + exact scenario run, or fall back to the same template + exact
   scenario only when the concrete representative URL has changed;
8. compare like-version normalized states and list additions/removals/structural changes;
9. mark the comparison unavailable, rather than inventing a difference, when required normalized
   state or compatible normalizer versions are absent.

## 6. Architecture / Data Flow

```text
Chromium checkpoint
    ↓
Raw DOM + request/script/error observations
    ↓
Versioned deterministic normalizers
    ↓
Normalized DOM artifact + compact normalized state
    ↓
Domain entities + append-only observations
    ↓
Compatible predecessor (URL first, template fallback)
    ↓
Structured evidence diff in manifest v3
```

Normalization stays within the browser subsystem for B3. PostgreSQL remains the structured store,
and S3-compatible storage remains the large-artifact store. No additional queue, service, database,
or event engine is introduced.

## 7. Files and Modules Affected

Expected additions:

```text
backend/app/browser/normalization.py
backend/app/browser/comparison.py
backend/migrations/versions/0004_template_aware_browser_evidence_b3.py
backend/tests/unit/browser/test_normalization.py
backend/tests/unit/browser/test_comparison.py
```

Expected modifications:

```text
backend/app/browser/contracts.py
backend/app/browser/collectors.py
backend/app/browser/models.py
backend/app/browser/persistence.py
backend/app/browser/runner.py
backend/app/browser/service.py
backend/tests/integration/test_browser_checkpoint.py
backend/tests/integration/test_migrations.py
README.md
```

## 8. Milestones

### M0 — Verify B2 integration and close the B3 contract

Acceptance:

- [x] PR #4 merge and exact `main` commit verified;
- [x] branch `agent/implement-ep-004` starts from merged `main`;
- [x] canonical B3 boundaries and current implementation gaps documented;
- [x] no new infrastructure, dependency, or product/security decision is required.

### M1 — Template configuration and normalized-evidence schema

Implementation:

- add backwards-compatible template family, fingerprint version, expected features, and archive
  metadata;
- add tenant/site-owned `domain_entities`, append-only `entity_observations`, and dedicated
  `js_error_observations` following the canonical data model;
- add constraints/indexes that preserve stable identity and tenant-scoped query paths;
- keep historic template/run/artifact rows readable through migration downgrade/re-upgrade.

Acceptance:

- [x] template identity is unique within a site and carries explicit expectation provenance;
- [x] stable entity keys cannot collide across sites;
- [x] observations retain checkpoint, collector version, and observed time;
- [x] JavaScript fingerprint recurrence remains queryable without full-stack identity;
- [x] clean migration upgrade/downgrade/re-upgrade passes.

### M2 — Deterministic normalizers

Implementation:

- implement a standard-library structural HTML normalizer with explicit element/attribute allowlists,
  volatile-value replacement, bounded depth/node/attribute/text-free output, and canonical JSON;
- normalize script and request URLs using sanitized host/path families and remove queries/fragments;
- classify a bounded set of functional dependency categories using deterministic rules;
- normalize JavaScript messages/source paths and compute versioned fingerprints;
- hash canonical normalized representations with SHA-256.

Acceptance:

- [x] article copy, timestamps, random IDs, auction IDs, and cache-busters do not create false diffs;
- [x] hierarchy, scripts, iframes, canonical/meta state, sticky/fixed indicators, and key containers
  remain represented;
- [x] equivalent cache-busted dependency URLs share one stable identity;
- [x] sensitive query values, cookies, headers, request bodies, and raw page text are absent;
- [x] malformed/oversized input is bounded and deterministic;
- [x] every normalizer version is explicit in output.

### M3 — Persist normalized evidence and entity observations

Implementation:

- extend browser collection with safe request method/resource/status/failure observations;
- create a `NORMALIZED_DOM` long-lived artifact after interactions and before final screenshot;
- add normalized script/network/error state to `BrowserEvidence` and manifest v3;
- upsert stable entity identity within tenant/site and append one observation per entity/run;
- persist normalized JavaScript error recurrence rows independently from raw manifest samples;
- keep optional normalizer failure isolated as `PARTIAL` with raw evidence preserved.

Acceptance:

- [x] a successful fixture run persists raw and normalized DOM with distinct retention classes;
- [x] artifact hashes resolve and finalized raw evidence remains immutable;
- [x] entity observations are tenant/site/checkpoint scoped and idempotent per run;
- [x] `NOT_PRESENT`, `NOT_OBSERVABLE`, and `ERROR` remain distinct collector outcomes;
- [x] normalizer failure never destroys screenshots/raw DOM/attempt evidence.

### M4 — Explainable URL/template comparison

Implementation:

- prefer the previous same monitored URL + exact scenario checkpoint;
- fall back to the previous same template + exact scenario checkpoint for intentional URL rotation;
- require compatible DOM/script/network/error normalizer versions;
- compare hashes and stable-key sets into bounded structured change records;
- record predecessor identity, selection scope, versions, counts, and limitations in manifest v3;
- never emit events, severity, alert state, or causal language.

Acceptance:

- [x] desktop/mobile and scenario versions never cross comparison lineages;
- [x] a rotated article URL may compare within its stable template;
- [x] another template or tenant can never become a predecessor;
- [x] unchanged normalized state yields an explicit empty change set;
- [x] incompatible/missing normalized versions yield `NOT_COMPARABLE` with a reason;
- [x] every reported addition/removal references stable normalized identity only.

### M5 — Integration and security proof

Implementation:

- extend the deterministic HTTP fixture with volatile article values, scripts, redirects, request
  statuses, and a second URL representing the same template;
- execute repeated desktop/mobile checkpoints and prove stable state plus intentional changes;
- test migration, idempotency, tenant boundaries, URL rotation, normalizer versions, retention,
  SSRF preservation, and manifest/object integrity;
- keep PostgreSQL, MinIO, and real Chromium CI authoritative where local Docker is unavailable.

Acceptance:

- [x] two noisy-but-equivalent pages produce the same normalized structural hash;
- [x] a meaningful structural/dependency change produces a bounded explainable diff;
- [x] raw query secrets never enter normalized state, entity keys, logs, or comparison output;
- [x] cross-tenant entity, observation, predecessor, and artifact reads are denied;
- [x] B2 scheduling/action/status/retry behavior remains green;
- [x] frontend and repository safety checks remain green.

### M6 — Documentation, final CI, and retrospective

Acceptance:

- [x] README explains template identity, normalized evidence, URL rotation, and limitations;
- [x] docs distinguish raw evidence, normalized state, differences, and future events;
- [x] no generated browser artifacts, profiles, traces, secrets, or build output are committed;
- [x] all supported local checks and final GitHub Actions pass;
- [x] retrospective records deviations and the exact B4 boundary.

## 9. Final Acceptance Criteria

- [x] representative URLs retain explicit stable template identity;
- [x] template configuration carries versioned expectations without inventing templates;
- [x] normalized DOM is deterministic, bounded, versioned, and stored separately from raw DOM;
- [x] scripts/network dependencies/errors use safe stable fingerprints;
- [x] stable entities and append-only observations remain tenant/site/run scoped;
- [x] URL rotation preserves template comparison history without crossing scenarios;
- [x] incompatible observer/normalizer versions never produce silent false diffs;
- [x] comparison output is structured, bounded, explainable, and non-causal;
- [x] raw finalized evidence and all B1/B2 behavior remain intact;
- [x] no GPT, CMP, Prebid, video, events, incidents, alerts, AI, or broad crawling is introduced;
- [x] migration, local supported checks, and authoritative GitHub Actions pass.

## 10. Validation

```bash
uv --directory backend run ruff format --check .
uv --directory backend run ruff check .
uv --directory backend run mypy app tests scripts migrations/env.py
uv --directory backend run pytest tests/unit

docker compose config
docker compose up -d postgres minio minio-init
uv --directory backend run alembic upgrade head
RUN_INTEGRATION=1 uv --directory backend run pytest tests/integration

pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend test
pnpm --dir frontend build

python scripts/check_secrets.py
git diff --check
git status --short
```

Docker availability must be reported truthfully. GitHub Actions is authoritative for PostgreSQL,
MinIO, and real-Chromium integration when the implementation runtime cannot provide them.

## 11. Data / Migration Impact

Additive migration `0004` will enrich `templates` and add the minimum canonical normalized-evidence
tables:

```text
domain_entities
entity_observations
js_error_observations
```

Large normalized DOM remains an object artifact. Compact normalized hashes, stable-key sets,
versions, expected references, and structured comparison metadata remain in manifest v3 and
collector summaries. Historic manifests remain readable; they are not backfilled or rewritten.

## 12. Security / Privacy Impact

B3 reduces long-term sensitivity by retaining normalized structure rather than raw page content.
It must not persist page copy, request bodies, cookies, authorization headers, full query strings,
or visitor/session identifiers in normalized evidence. Stable keys use sanitized hosts/path
families only. Raw evidence keeps existing shorter retention. Normalized structural state uses
`CORE_LONG` because it is bounded operational memory.

Application SSRF interception remains unchanged and still requires production network-level egress
enforcement before untrusted pilot traffic.

## 13. Rollback Strategy

1. stop browser/scheduler workers before reverting application behavior;
2. preserve finalized B3 artifacts/entities/observations already written;
3. deploy the previous application while leaving additive schema in place after real evidence;
4. downgrade `0004` only in disposable local/CI databases;
5. continue B2 runs without normalized comparison until B3 is repaired.

Rollback never rewrites manifests or deletes checkpoint evidence.

## 14. Known Risks

- overly aggressive DOM reduction can hide meaningful structure;
- overly permissive attributes can reintroduce high-noise or sensitive values;
- path-family rules may split one dependency or merge two distinct endpoints;
- template fallback can create false comparisons unless exact scenario and site/template identity
  are enforced;
- normalizer upgrades can resemble publisher changes unless versions are explicit;
- normalized artifact/entity volume grows with every URL × device × six-hour run.

## 15. Decisions

### 2026-08-14 — Normalized evidence is derived and append-only

New code creates a versioned representation and never rewrites historic raw checkpoints.

### 2026-08-14 — URL-first, template-fallback lineage

Automatic comparison prefers the exact monitored URL. Template fallback is allowed only within the
same tenant, site, template, and exact scenario, supporting intentional representative URL rotation.

### 2026-08-14 — B3 differences are not events

The manifest may state that a stable script identity was added or removed. Promotion, persistence
thresholds, severity, alerting, and causal claims remain owned by future event/incident milestones.

## 16. Progress Log

### 2026-08-14 — M0 complete; implementation started

PR #4 was verified merged into `main` at `57a8c58`, the local checkout was synchronized, and the
EP-004 branch was created from that exact merge. Canonical B3 requirements and B2 implementation
gaps were inspected. The smallest coherent B3 slice is versioned structural normalization, stable
script/network/error identities, template-aware lineage, append-only observations, and non-causal
structured comparison output. No new dependency or infrastructure category is required.

### 2026-08-14 — M1–M4 implementation complete; integration validation pending

Added additive template metadata and canonical domain-entity, entity-observation, and JavaScript
error observation models/migration. Browser runs now derive a bounded versioned structural DOM
artifact, normalized script/network dependency state, and JavaScript error fingerprints. Manifest
v3 records compact normalized state, exact template expectations, URL-first/template-fallback
lineage, and bounded non-causal structural/presence/status changes. Stable entities and append-only
observations finalize atomically with checkpoint metadata.

Local supported validation:

- Ruff format and lint: passed;
- strict mypy across app, tests, scripts, and migrations: passed;
- backend unit suite: 47 passed;
- frontend lint, typecheck, Vitest, and production build: passed;
- secret scan and `git diff --check`: passed.

Docker is not installed in this runtime, so clean PostgreSQL migration, MinIO artifact persistence,
real Chromium normalization, URL-rotation lineage, and downgrade/re-upgrade were not claimed
locally. The following authoritative GitHub Actions run supplied that coverage before M1–M5
acceptance was closed.

### 2026-08-14 — M5–M6 complete; authoritative CI green

GitHub Actions CI run #35 completed successfully for remote commit
`65be99b456b3c875370959a9e88ca215899e0cc9`. The backend installed Chromium, applied the full
Alembic chain, started PostgreSQL and MinIO, passed all 47 unit tests and all 12 integration tests,
and completed scheduler/worker smoke commands. Frontend lint, typecheck, Vitest, and production
build passed. Repository secret scanning, Compose validation, and diff hygiene also passed.

The real-browser integration proves manifest v3, raw and normalized DOM artifact integrity, stable
entity/error observations, tenant-scoped reads, unchanged B2 interactions, and the same-template
lineage fallback after representative URL rotation. No CI-only implementation correction was
required.

## 17. Final Outcome / Retrospective

EP-004 delivers B3 template-aware browser evidence. Repeated runs now preserve a deterministic,
versioned structural representation that ignores page copy and recognized volatile identifiers,
plus stable script/network identities and JavaScript error fingerprints. Large structural output
is stored as a long-lived normalized artifact; PostgreSQL keeps stable entities and append-only
observations; manifest v3 keeps compact hashes, versions, expectations, lineage, and bounded
explainable differences.

Representative URL rotation no longer breaks operational memory: comparison prefers an exact URL
and may fall back only to the same tenant/site/template and exact browser scenario. Incompatible
normalizer versions produce `NOT_COMPARABLE` rather than a false publisher change.

The milestone remains deliberately non-causal. Differences are not promoted into events, alerts,
severity, incidents, or AI conclusions. B4 should next add GPT slot identity and lifecycle
observation on top of B3 template/normalized evidence, without changing historic B3 observer or
normalizer identities in place.
