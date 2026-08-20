# EP-017 — Public Configuration E3

**Status:** IN_PROGRESS
**Owner:** Codex / Engineering
**Created:** 2026-08-21
**Updated:** 2026-08-21
**Target milestone:** E3 — Public configuration
**MVP scope impact:** NO
**New infrastructure category:** NO

## Progress

- [x] M0 — Verify the merged E2 baseline and fix the E3 semantic boundary
- [ ] M1 — Add immutable public-configuration snapshots and ads.txt records
- [ ] M2 — Implement bounded, SSRF-safe public fetches and semantic parsers
- [ ] M3 — Schedule routine observations and immediate high-risk validation
- [ ] M4 — Derive deterministic robots.txt and ads.txt events
- [ ] M5 — Prove security, lifecycle, migration, regression, and release readiness

## 1. Purpose and User Outcome

After this plan is complete, Publisher Intelligence can observe each active site's public
`/robots.txt` and `/ads.txt` independently of Chromium, preserve immutable semantic snapshots,
and explain meaningful changes without treating formatting noise as an event.

Routine valid changes appear as low-noise Timeline facts suitable for a future Weekly Brief.
Potentially dangerous states, such as a newly added site-wide robots block or a previously valid
ads.txt becoming missing, empty, or materially invalid, require a second independent fetch before
the system records a high-risk event. The resulting event states only what the public evidence
supports. It does not claim that search indexing, advertising authorization, or revenue actually
changed.

## 2. Scope and Non-Goals

### In

- fetch only canonical, configured site URLs at `/robots.txt` and `/ads.txt` using a lightweight
  HTTP client in the general worker;
- apply SSRF protections before the initial request and every redirect, with strict tenant/site
  ownership checks and bounded time, redirects, and response bytes;
- persist one immutable site-level snapshot per fetch, including status, content hash, parse state,
  normalizer version, semantic summary, and scheduled-versus-validation provenance;
- persist normalized immutable ads.txt seller records belonging to their snapshot;
- parse robots.txt according to RFC 9309, retaining parseable rules and bounded diagnostics;
- parse ads.txt 1.1 seller records and supported variables, including `OWNERDOMAIN` and
  `MANAGERDOMAIN`, with bounded invalid-row diagnostics;
- compare normalized semantic state so changes in order, whitespace, comments, line endings, or
  duplicate equivalent rules do not create routine events;
- add the E3 registry rules for `ROBOTS_TXT_CHANGED`, `ROBOTS_BROAD_BLOCK_ADDED`,
  `ROBOTS_BROAD_BLOCK_REMOVED`, `ADS_TXT_CHANGED`, `ADS_TXT_MISSING`, `ADS_TXT_EMPTY_200`, and
  `ADS_TXT_INVALID`;
- introduce canonical `IMMEDIATE_SECOND_CHECK` confirmation and an out-of-band validation job for
  high-risk candidates without replacing the regular six-hour observation;
- create, support, and resolve ads.txt condition events using the existing E2 lifecycle and
  concurrency guarantees;
- attach typed `PUBLIC_CONFIG_SNAPSHOT` evidence to each E3 event;
- add unit and PostgreSQL integration coverage for parsers, semantic diffs, scheduling,
  validation, lifecycle, security, migrations, tenancy, retries, and idempotency.

### Out / Non-Goals

- sitemap discovery or monitoring; E3's canonical minimum in `EVENTS.md` is robots.txt and ads.txt;
- sellers.json crawling, recursive `SUBDOMAIN`/`INVENTORYPARTNERDOMAIN` traversal, or arbitrary
  URLs discovered in public files;
- `ADS_TXT_CRITICAL_SELLER_REMOVED` until the product has explicit tenant-owned evidence that a
  seller/account/path is active or critical; a deleted line alone is insufficient;
- automatic recommendations to remove reseller lines or conclusions that a record is commercially
  unnecessary;
- alerts, email, Slack, push delivery, Weekly Brief rendering, Home/Timeline UI, incidents, or
  notification routing; these remain E6 and later work;
- claims that robots.txt controls authorization or indexing, or that ads.txt changes caused
  revenue, fill-rate, or demand changes;
- browser checkpoints, Playwright reruns, authenticated provider access, credentials, cookies, or
  a new worker process;
- database-editable rules, user-supplied URLs, user-supplied thresholds, LLM classification, a
  workflow engine, streaming infrastructure, or a new storage service;
- raw public-file artifact storage in E3. The canonical `artifact_id` remains nullable; the bounded
  normalized snapshot summary and ads.txt records are the durable source evidence.

## 3. Canonical References

- `AGENTS.md` sections 7, 10, 15–18, and 28;
- `PLANS.md` sections 1, 4–11, 20–48, 55, 62–66, and 71–76;
- `MVP.md` public-state, ads.txt, event-memory, and non-causal interpretation sections;
- `EVENTS.md` event invariants, confirmation modes, robots/supply catalogs, evidence rules,
  high-severity rollout guidance, EV-015/EV-016, and milestone E3;
- `DOMAIN.md` robots.txt semantics, ads.txt normalized state, failure modes F-SUP-001 through
  F-SUP-006, and prohibited shortcuts;
- `DATA_MODEL.md` `public_config_snapshots`, `ads_txt_records`, event evidence, and DM-018;
- `BROWSER.md` rule that robots.txt and sitemap collection may remain outside Chromium;
- `ARCHITECTURE.md` scheduler, PostgreSQL job queue, worker, and evidence/event boundaries;
- `SECURITY.md` configured-target authorization, SSRF controls, DNS rebinding, redirects, logging,
  tenant isolation, and bounded evidence retention;
- accepted ADR-023, ADR-025, ADR-040 through ADR-043, ADR-089, ADR-090, ADR-093, ADR-096, and
  ADR-112 in `DECISIONS.md`;
- completed `plans/EP-015-semantic-browser-events-e1.md` and
  `plans/EP-016-event-persistence-lifecycle-e2.md`;
- [RFC 9309 — Robots Exclusion Protocol](https://www.rfc-editor.org/rfc/rfc9309.html), including
  parseable-rule handling, access results, caching, and the minimum 500 KiB parsing limit;
- [IAB Tech Lab ads.txt 1.1](https://iabtechlab.com/wp-content/uploads/2022/04/Ads.txt-1.1.pdf),
  including the three required seller fields, optional certification-authority field, redirects,
  empty-file guidance, and v1.1 variables.

Relevant invariants:

- state is not an event, an event is not a cause, and semantic change is not raw-text change;
- high-risk public configuration is not confirmed from one fetch;
- source evidence remains immutable and separate from derived events;
- every job, snapshot, record, and event path validates tenant and site ownership;
- public content is still untrusted input and tenant-specific historical interpretation is
  confidential;
- the configured site determines the destination; a job payload or parsed file never grants crawl
  authority.

## 4. Current State

EP-016 is merged into `main` at `6f95667`, and post-merge CI run #107 passed. E1/E2 provide a fixed
event registry, deterministic point identity, condition lifecycle, active-condition uniqueness,
typed evidence-reference rows, occurrence uncertainty, retry-safe worker integration, and source
evidence ownership validation for browser-derived events.

The repository has no public-configuration package, snapshot tables, ads.txt record table, fetch
jobs, or E3 registry entries. `ConfirmationMode` has three E1/E2 modes but not
`IMMEDIATE_SECOND_CHECK`. `EvidencePointer` is still constructed around `checkpoint_run_id`, even
though the persistence schema already stores generic `evidence_kind` and `source_id` values.
Event persistence currently creates only `BROWSER_CHECKPOINT` source events. The registry bundle
is `e2-v1`, and migration head is `0014_event_lifecycle_e2`.

`Site` already supplies tenant, publisher, canonical domain, canonical scheme, status, and
timezone. The scheduler already runs every minute and inserts idempotent PostgreSQL jobs. The
general worker already handles connector, cross-source, and browser-event jobs. `httpx` is already
a locked backend dependency.

`app.browser.security` implements useful URL, DNS, address, and configured-domain semantics, but
it is coupled to Playwright request routing. E3 should factor the transport-independent primitives
into a common public-network guard or implement a small equivalent module without importing
Playwright into the public-config path. Application checks cannot eliminate DNS rebinding by
themselves; production egress controls remain required by `SECURITY.md`.

The existing `artifacts` table requires a `checkpoint_run_id` and one artifact type per browser
run, so it is not a safe fit for standalone public-config evidence. E3 will use the canonical
nullable `artifact_id` and will not generalize artifact ownership unless implementation uncovers a
specific evidence requirement that the normalized snapshot cannot satisfy. Such a change must be
recorded here before code proceeds.

## 5. Target Behavior

1. Every active site gets one idempotent `FETCH_PUBLIC_CONFIG` job for each of `ROBOTS_TXT` and
   `ADS_TXT` in every canonical six-hour window. URLs are derived from `Site`; they are not stored
   in or accepted from a job payload.
2. A fetch validates the canonical destination, resolves DNS with a bounded timeout, rejects
   private/reserved/metadata destinations, revalidates every redirect, and stops on an unexpected
   cross-site redirect, oversize body, timeout, or redirect limit.
3. Every completed attempt persists an immutable snapshot, including bounded failure evidence.
   HTTP 200 with no meaningful ads.txt declaration is `EMPTY`, never healthy. Network failure,
   missing resource, invalid content, and syntactic warnings remain distinct states.
4. The first snapshot establishes baseline state without emitting a changed event. Later comparable
   scheduled snapshots are compared only when normalizer versions are compatible.
5. Comments, ordering, whitespace, line-ending, and duplicate-equivalent changes do not emit
   routine events. Seller/account/relationship/certification or supported-variable changes do.
6. A newly effective universal `User-agent: *` plus `Disallow: /` is the only initial automatic
   broad-block predicate. Important-section and crawler-specific policies remain deferred until
   configured evidence exists.
7. Routine semantic changes create low-noise point events from the scheduled snapshot. A broad
   robots block, missing/empty ads.txt, or materially invalid ads.txt enqueues exactly one
   `VALIDATE_PUBLIC_CONFIG` job linked to the primary snapshot and creates no high-risk event yet.
8. A validation fetch is a second immutable observation. If it independently confirms the same
   high-risk semantic state, the service records the point event or upserts the condition event
   with both snapshots as evidence. If it refutes the candidate, no event is created and both
   observations remain queryable.
9. Repeated scheduled evidence for an active ads.txt condition adds idempotent support. Recovery
   requires a later valid scheduled state plus an immediate validation that corroborates it;
   transient one-fetch recovery does not resolve the event.
10. The validation fetch never advances or replaces the next scheduled observation. No E3 code
    sends a notification, even for CRITICAL severity.

## 6. Event and Parsing Decisions

| Event code | Kind | Confirmation | Initial severity | E3 behavior |
|---|---|---|---|---|
| `ROBOTS_TXT_CHANGED` | POINT | `SINGLE_STRONG_OBSERVATION` | LOW/MEDIUM | Record only a semantic rules/directives change; no alert delivery. |
| `ROBOTS_BROAD_BLOCK_ADDED` | POINT | `IMMEDIATE_SECOND_CHECK` | CRITICAL | Confirm only a newly effective universal root block; include exact rule and scope. |
| `ROBOTS_BROAD_BLOCK_REMOVED` | POINT | `SINGLE_STRONG_OBSERVATION` | MEDIUM | Record recovery context without claiming indexing recovered. |
| `ADS_TXT_CHANGED` | POINT | `SINGLE_STRONG_OBSERVATION` | LOW | Record valid semantic seller/directive changes; formatting-only changes are silent. |
| `ADS_TXT_MISSING` | CONDITION | `IMMEDIATE_SECOND_CHECK` | HIGH | Active only when a previously valid file becomes missing and validation agrees. |
| `ADS_TXT_EMPTY_200` | CONDITION | `IMMEDIATE_SECOND_CHECK` | HIGH | HTTP 200 without a valid declaration is a distinct active condition. |
| `ADS_TXT_INVALID` | CONDITION | `IMMEDIATE_SECOND_CHECK` | MEDIUM/HIGH | Require material parse invalidity; bounded row warnings alone do not imply total invalidity. |

`ROBOTS_TXT_CHANGED` and `ROBOTS_BROAD_BLOCK_ADDED` are mutually exclusive for the same transition:
the confirmed high-risk event supersedes the generic routine fact instead of producing duplicate
noise. A broad-block removal may coexist with a useful routine diff only if the registry explicitly
permits two distinct user-facing facts; the initial implementation should emit only the more
specific removal event.

The robots parser follows RFC 9309 group/rule semantics, case-insensitive user-agent matching,
longest-match behavior, UTF-8 handling, and partial use of parseable lines. It must process at least
500 KiB; the initial bounded limit is exactly 512,000 bytes unless a safer higher value is recorded
in the Decision Log. Unsupported fields such as `Sitemap` may be retained in bounded summary
metadata but do not affect E3 event identity.

The ads.txt parser treats the advertising-system domain case-insensitively, preserves the publisher
account ID exactly after surrounding whitespace removal, normalizes relationship to `DIRECT` or
`RESELLER`, and accepts the optional fourth certification-authority field. It parses supported
variables separately and includes `OWNERDOMAIN` and all valid `MANAGERDOMAIN` values in semantic
state. It does not follow `SUBDOMAIN` or `INVENTORYPARTNERDOMAIN` references in E3.

## 7. Architecture / Data Flow

```text
active Site + six-hour window
  → FETCH_PUBLIC_CONFIG job per config type
  → configured URL + SSRF/redirect/size/time guards
  → immutable snapshot (+ immutable ads.txt records)
  → compatible semantic predecessor comparison
  → routine event OR high-risk validation job
  → second guarded fetch linked to primary snapshot
  → confirm/refute candidate
  → deterministic point event or condition lifecycle update
  → typed PUBLIC_CONFIG_SNAPSHOT evidence refs
```

The scheduler, general worker, PostgreSQL queue, and event tables are reused. The scheduled fetch
and validation fetch use the same transport and parsers but different typed request contracts.
Evaluation remains deterministic and side-effect free; orchestration and persistence remain in the
service/repository layers.

The validation job payload contains only `site_id`, `config_type`, `primary_snapshot_id`, and the
fixed rule bundle version. The repository verifies all three IDs belong to the lease tenant and
that the primary snapshot is eligible. The target URL is always reconstructed from the current
configured site, never trusted from the payload or primary response.

## 8. Files and Modules Affected

### Existing

- `backend/app/config/settings.py`
- `backend/app/scheduler.py`
- `backend/app/worker.py`
- `backend/app/browser/security.py` and its tests, only to extract transport-independent network
  validation without weakening browser guards;
- `backend/app/events/contracts.py`
- `backend/app/events/registry.py`
- `backend/app/events/models.py`
- `backend/app/events/persistence.py`
- `backend/tests/unit/events/test_registry.py`
- `backend/tests/unit/events/test_worker.py`
- `backend/tests/integration/test_migrations.py`
- `README.md`

### To create

- `backend/app/common/network_security.py` if shared URL/DNS primitives are extracted;
- `backend/app/public_config/__init__.py`
- `backend/app/public_config/contracts.py`
- `backend/app/public_config/models.py`
- `backend/app/public_config/client.py`
- `backend/app/public_config/robots.py`
- `backend/app/public_config/ads_txt.py`
- `backend/app/public_config/evaluator.py`
- `backend/app/public_config/persistence.py`
- `backend/app/public_config/service.py`
- `backend/app/public_config/scheduling.py`
- `backend/migrations/versions/0015_public_configuration_e3.py`
- `backend/tests/unit/public_config/test_client.py`
- `backend/tests/unit/public_config/test_robots.py`
- `backend/tests/unit/public_config/test_ads_txt.py`
- `backend/tests/unit/public_config/test_evaluator.py`
- `backend/tests/unit/public_config/test_scheduling.py`
- `backend/tests/unit/public_config/test_worker.py`
- `backend/tests/integration/test_public_configuration.py`

Paths may be adjusted to preserve clear module boundaries. Any material schema, infrastructure,
scope, or semantic change must be recorded in this plan before implementation continues.

## 9. Data / Migration Impact

Migration `0015` will add `public_config_snapshots` with the canonical fields:

- UUID `id`, `tenant_id`, `site_id`, and nullable `artifact_id`;
- controlled `config_type`: `ROBOTS_TXT` or `ADS_TXT` in E3;
- `observed_at`, nullable `http_status`, nullable `content_hash`, controlled `parse_status`,
  `normalizer_version`, bounded `summary` JSONB, and `created_at`;
- controlled `fetch_kind`: `SCHEDULED` or `VALIDATION`;
- nullable `validation_of_snapshot_id`, required only for validation snapshots and constrained to
  a different immutable row;
- deterministic `observation_key` used as the retry/concurrency uniqueness boundary;
- tenant/site/config/observed and validation-link indexes required by predecessor and confirmation
  lookups.

Allowed parse statuses are initially:

- `VALID` — complete semantic state with at least one valid declaration where required;
- `VALID_WITH_WARNINGS` — usable semantic state plus bounded non-material diagnostics;
- `EMPTY` — HTTP 200 with no meaningful declaration;
- `INVALID` — fetched content has no trustworthy semantic state;
- `MISSING` — a resource-not-found response such as HTTP 404;
- `HTTP_ERROR` — other non-success response;
- `UNREACHABLE` — DNS, connection, timeout, or eligible server failure;
- `TOO_LARGE` — response exceeded the bounded byte budget;
- `BLOCKED` — URL, DNS, address, or redirect failed the security policy.

The implementation must document the exact HTTP-to-state mapping and must not collapse robots.txt
RFC `unavailable`/`unreachable` semantics into ads.txt semantics. `summary` stores only bounded,
schema-versioned normalized directives, semantic counts, response metadata needed for diagnosis,
and safe error codes. It never stores arbitrary response headers or exception strings.

Migration `0015` will also add `ads_txt_records` with canonical seller fields, `record_hash`,
`is_valid`, bounded `validation_errors`, and the snapshot/tenant/site lineage. A uniqueness
constraint on `(snapshot_id, record_hash)` deduplicates semantically identical records within one
snapshot without creating a mutable current-state table.

The existing `event_evidence_refs` schema needs no migration. `EvidencePointer` becomes generic
over `evidence_kind` and `source_id`, with a compatibility constructor/helper for existing browser
callers. Event persistence validates `PUBLIC_CONFIG_SNAPSHOT` against the lease tenant/site and
sets E3 event `source_kind='PUBLIC_CONFIG'`. Registry definition mirrors advance to schema version
3 only if the metadata schema actually changes; the fixed code registry remains authoritative.

No historical backfill is required. The first successful scheduled snapshot is a silent baseline.
The downgrade must refuse to proceed while E3 events reference public-config snapshots, unless an
operator has explicitly removed those derived rows under the repository's retention policy. It
must never silently delete source evidence.

## 10. Milestones

### M0 — Baseline and contract inspection

Goal: bind E3 to merged E2, canonical public-configuration semantics, and primary standards.

Acceptance:

- [x] branch starts clean from remote `main` merge commit `6f95667`;
- [x] post-merge CI run #107 is green;
- [x] E2 registry, evidence references, lifecycle, queue, scheduler, worker, browser security,
  existing artifact ownership, migrations, and tests are inspected;
- [x] RFC 9309 and IAB Tech Lab ads.txt 1.1 are checked as primary technical sources;
- [x] E3 excludes sitemap, sellers.json traversal, critical-seller inference, notifications, UI,
  LLMs, authenticated access, and new infrastructure.

Validation:

```bash
git status --short --branch
git rev-parse HEAD
gh run view 107 --repo marian-dotcom/publisher-intelligence
```

Expected result: `agent/implement-ep-017` is based on `origin/main`, the worktree contains only this
draft plan, and the preceding milestone is fully green.

### M1 — Immutable snapshot schema and persistence

Goal: create the minimal durable evidence model before adding network behavior.

Implementation:

- add typed public-config contracts, parse/fetch states, provenance, and version constants;
- implement migration `0015`, SQLAlchemy models, repository inserts, predecessor lookup, validation
  linkage, and ads.txt record persistence;
- validate tenant/site ownership on every repository entry point;
- use deterministic observation keys and database constraints so job retries cannot duplicate a
  snapshot or its records;
- keep `artifact_id` nullable and source evidence bounded.

Acceptance:

- [ ] scheduled and validation snapshots are immutable and distinguishable;
- [ ] every ads.txt record belongs to one snapshot and repeats tenant/site lineage;
- [ ] invalid cross-tenant/site references fail closed;
- [ ] retries and concurrent inserts converge on one observation;
- [ ] HTTP 200 empty is representable only as `EMPTY`, never `VALID`;
- [ ] upgrade/downgrade/upgrade passes and downgrade preserves evidence safety.

Validation:

```bash
uv --directory backend run pytest tests/integration/test_migrations.py
uv --directory backend run pytest tests/integration/test_public_configuration.py -k persistence
```

### M2 — Safe fetch client and semantic parsers

Goal: turn configured public files into deterministic, bounded semantic observations.

Implementation:

- extract or create transport-independent URL/DNS/IP checks shared with browser security;
- derive only `/robots.txt` and `/ads.txt` from the tenant-owned `Site` record;
- manually follow a small bounded redirect chain, revalidating every hop before connection;
- stream response bytes with explicit connect/read/total timeouts and per-config size budgets;
- implement the RFC 9309 robots parser and deterministic normalized group/rule representation;
- implement ads.txt record/variable parsing, normalized hashes, bounded warnings, and invalid-state
  classification;
- return controlled failure codes and sanitized URLs only.

Acceptance:

- [ ] IP literals, credentials, non-HTTP(S), metadata hosts, private/reserved DNS answers, invalid
  ports, cross-site redirects, redirect loops, oversized bodies, and timeouts fail closed;
- [ ] every redirect is authorized before the transport follows it;
- [ ] the robots parser processes at least 500 KiB and retains parseable rules despite bad lines;
- [ ] robots grouping, wildcard/end-marker, case, and longest-match fixtures follow RFC 9309;
- [ ] ads.txt accepts valid three/four-field rows and v1.1 directives while preserving bounded
  diagnostics for malformed rows;
- [ ] semantic hashes ignore comments, order, whitespace, line endings, and duplicates;
- [ ] no file-provided URL causes another fetch.

Validation:

```bash
uv --directory backend run pytest tests/unit/public_config/test_client.py
uv --directory backend run pytest tests/unit/public_config/test_robots.py
uv --directory backend run pytest tests/unit/public_config/test_ads_txt.py
uv --directory backend run pytest tests/unit/browser/test_security.py
```

### M3 — Scheduling and immediate validation

Goal: integrate routine collection and independent high-risk confirmation into the existing queue.

Implementation:

- add per-site/config six-hour scheduling with a deterministic window key and no catch-up storm;
- register strict `FETCH_PUBLIC_CONFIG` and `VALIDATE_PUBLIC_CONFIG` worker handlers;
- persist every bounded result before evaluation;
- enqueue at most one validation job per eligible primary snapshot/rule version;
- validate job payload shape, lease tenant, site, config type, primary provenance, and state;
- separate retryable transport/runtime failures from terminal security, payload, and state errors;
- ensure a validation fetch does not satisfy or shift the next scheduled window.

Acceptance:

- [ ] two scheduler passes create no duplicate jobs for the same site/config/window;
- [ ] a first baseline produces no change event and no unnecessary validation;
- [ ] high-risk primary state creates exactly one validation job and no premature event;
- [ ] a validation snapshot is independently fetched and linked to its primary;
- [ ] validation is never recursively validated;
- [ ] malformed/cross-tenant jobs perform no network access;
- [ ] retry exhaustion preserves prior snapshots and exposes a controlled terminal job state.

Validation:

```bash
uv --directory backend run pytest tests/unit/public_config/test_scheduling.py
uv --directory backend run pytest tests/unit/public_config/test_worker.py
uv --directory backend run pytest tests/integration/test_public_configuration.py -k validation
uv --directory backend run python -m app.scheduler --once
uv --directory backend run python -m app.worker --once
```

### M4 — Semantic events and lifecycle

Goal: derive the E3 catalog without duplicate noise or unsupported claims.

Implementation:

- add `IMMEDIATE_SECOND_CHECK` and generalize typed evidence pointers compatibly;
- add fixed `e3-v1` registry rules with event kind, confirmation, evidence, subject, scope,
  severity, resolution, dedupe, source version, domain references, and noise notes;
- compare only compatible scheduled semantic states and exclude validation snapshots from routine
  predecessor selection;
- emit the most specific applicable robots event and suppress its generic duplicate;
- confirm high-risk events only when primary and validation states semantically agree;
- use E2 active-condition identity, supporting evidence, and recovery behavior for ads.txt states;
- make recovery confirmation as strict as failure confirmation;
- attach both primary and validation snapshots with controlled relations.

Acceptance:

- [ ] formatting-only or first-baseline changes create no event;
- [ ] routine valid ads.txt/robots semantic changes create one idempotent point event;
- [ ] broad root block creates no event after one fetch and one CRITICAL point event after matching
  validation;
- [ ] validation disagreement creates no event and preserves both observations;
- [ ] missing, empty 200, and material invalidity are distinct active conditions;
- [ ] repeated affected evidence supports one active condition; confirmed valid recovery resolves it;
- [ ] a later recurrence creates a new active event;
- [ ] source evidence ownership and typed relations are enforced for public-config and unchanged for
  browser events;
- [ ] summaries mention observed rule/record scope but never assert indexing, authorization,
  revenue, or causation;
- [ ] no E3 path delivers an alert.

Validation:

```bash
uv --directory backend run pytest tests/unit/events
uv --directory backend run pytest tests/unit/public_config/test_evaluator.py
uv --directory backend run pytest tests/integration/test_public_configuration.py -k event
uv --directory backend run pytest tests/integration/test_event_lifecycle.py
```

### M5 — Full validation and release readiness

Goal: close E3 only after all repository and operational contracts are proven.

Implementation:

- update README architecture, job types, settings, and local verification commands;
- update this living plan's progress, validation results, decisions, discoveries, and retrospective;
- review the complete diff for accidental scope, secret, schema, and tenant-isolation regressions;
- run the exact CI-equivalent backend, frontend, repository-safety, scheduler, and worker checks;
- keep high-severity rule delivery disabled for later shadow/review/calibration work.

Acceptance:

- [ ] all M1–M4 criteria pass;
- [ ] every event rule has positive, no-change, noise, recovery where applicable, missing-data,
  incompatible-version, scope, dedupe, and validation-run tests;
- [ ] no regression occurs in the existing E1/E2 event suite or browser security suite;
- [ ] migration inventory and downgrade safety are explicit;
- [ ] documentation matches the implemented contracts and no unplanned infrastructure appears;
- [ ] `git diff --check`, secret scan, full backend CI, and full frontend CI pass;
- [ ] the plan is marked `COMPLETE` only after results and commit/PR state are recorded.

## 11. Final Acceptance Criteria

- [ ] active sites produce deterministic six-hour robots.txt and ads.txt snapshots without
  Chromium;
- [ ] all destinations originate from tenant-owned configured sites and pass every SSRF gate;
- [ ] snapshots and seller records are immutable, bounded, retry-safe, and tenant-isolated;
- [ ] RFC 9309 and ads.txt 1.1 semantics are covered by executable fixtures;
- [ ] semantic normalization suppresses formatting/order/comment noise;
- [ ] high-risk conditions require a linked second fetch and never treat that validation as the
  next scheduled observation;
- [ ] E3 point and condition events are deterministic, evidence-backed, correctly scoped, and
  lifecycle-safe;
- [ ] existing browser events still persist with their current evidence and lifecycle behavior;
- [ ] alerts, commercial recommendations, and causal claims remain absent;
- [ ] all targeted and full validation commands pass.

## 12. Final Validation

```bash
uv --directory backend run ruff format --check .
uv --directory backend run ruff check .
uv --directory backend run mypy app tests scripts migrations/env.py
uv --directory backend run pytest tests/unit
uv --directory backend run alembic upgrade head
RUN_INTEGRATION=1 uv --directory backend run pytest tests/integration
uv --directory backend run python -m app.scheduler --once
uv --directory backend run python -m app.worker --once
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend test
pnpm --dir frontend build
python scripts/check_secrets.py
docker compose config
git diff --check
git status --short --branch
```

## 13. Test Cases

### Happy paths

- first valid robots.txt and ads.txt snapshots become silent baselines;
- valid robots semantic change produces `ROBOTS_TXT_CHANGED` once;
- universal `Disallow: /` addition plus matching validation produces
  `ROBOTS_BROAD_BLOCK_ADDED` once with both evidence rows;
- universal root block removal produces `ROBOTS_BROAD_BLOCK_REMOVED` once;
- valid seller/account/relationship/directive change produces `ADS_TXT_CHANGED` once;
- missing, empty 200, and materially invalid ads.txt states each confirm to their distinct active
  condition;
- repeated affected observations add support, and confirmed valid recovery resolves the condition;
- recurrence after resolution creates a new active event.

### Noise and counterexamples

- reordered rules/records, comments, whitespace, CRLF/LF, field-case where defined, and duplicate
  semantic records produce no event;
- a single page-specific robots rule never becomes a broad-block event;
- an unsupported robots directive does not terminate a valid group;
- one malformed ads.txt row among valid records produces bounded warnings, not necessarily an
  `ADS_TXT_INVALID` condition;
- deleted reseller record remains `ADS_TXT_CHANGED`, not `ADS_TXT_CRITICAL_SELLER_REMOVED`;
- one high-risk primary observation, mismatched validation, or failed validation creates no event;
- validation snapshots are not selected as routine predecessors and do not recursively validate;
- first observation, missing predecessor, incompatible normalizer, or unordered time fails closed;
- robots unavailable/unreachable and ads.txt HTTP states remain semantically distinct;
- no event summary says revenue fell, indexing stopped, or a partner should be removed.

### Security and tenancy

- loopback, RFC1918, link-local, metadata, IPv4/IPv6 encoded variants, credentials, IP literals,
  bad ports, non-HTTP schemes, DNS-private results, and private redirect targets are blocked;
- a host resolving to both global and forbidden addresses is blocked;
- unexpected cross-site redirects and redirect loops are blocked before following;
- oversized, slow, and streaming responses stop at explicit limits;
- a job cannot fetch another tenant's site or validate another tenant's snapshot;
- raw response bodies, arbitrary headers, DNS answers, tokens, and exception strings are absent
  from logs and job errors;
- file-declared `SUBDOMAIN`, `INVENTORYPARTNERDOMAIN`, or URL-like values cause no follow-up fetch.

### Retry, concurrency, and regression

- duplicate scheduler passes, duplicate job delivery, and concurrent validation converge on one
  snapshot/job/event identity;
- retryable network/runtime failure uses the queue's bounded attempts; terminal policy/state
  errors do not retry;
- a failed later attempt never overwrites or deletes earlier evidence;
- E1/E2 point identities, active-condition uniqueness, evidence relations, and recovery tests pass;
- browser worker isolation and general-worker unknown-job behavior remain correct;
- migration upgrade/downgrade/upgrade and exact table inventory pass.

## 14. Security / Privacy Impact

Public files are untrusted input. E3 performs no authenticated request and sends no tenant secret,
cookie, browser storage, or provider token. Derived history, event scope, and operational analysis
remain tenant-confidential even when the original URL is public.

The application permits only HTTP(S), rejects userinfo and IP literals by default, canonicalizes
IDNA hostnames, checks the configured site/www equivalence, resolves DNS under a timeout, and
rejects every non-global address. Each redirect is parsed, authorized, resolved, and checked before
the next request. The E3 redirect policy is deliberately stricter than RFC 9309 and ads.txt's
maximum interoperability behavior: security policy allows only the configured canonical host and
its approved www alias. Supporting external delegation would require explicit configured aliases
and a later security decision.

The HTTP client streams bounded bodies, applies explicit timeouts, does not automatically follow
redirects, and never uses an environment proxy implicitly. Response bodies are parsed as untrusted
bytes with bounded diagnostics. Production must additionally restrict network egress because DNS
preflight cannot by itself eliminate DNS rebinding between resolution and connection.

## 15. Observability / Failure Handling

Structured logs include only safe identifiers and controlled fields: job ID, tenant ID, site ID,
config type, fetch kind, snapshot ID, sanitized configured URL, HTTP status, parse status,
normalizer/rule version, byte count, redirect count, validation outcome, event count, duration,
attempt, and controlled error class. They exclude file bodies, arbitrary response headers, DNS
answers, full exception text, and ads.txt account values.

Controlled fetch error classes include at least `PUBLIC_CONFIG_SECURITY_ERROR`,
`PUBLIC_CONFIG_DNS_ERROR`, `PUBLIC_CONFIG_TIMEOUT`, `PUBLIC_CONFIG_HTTP_ERROR`,
`PUBLIC_CONFIG_TOO_LARGE`, `PUBLIC_CONFIG_PARSE_ERROR`, `PUBLIC_CONFIG_STATE_ERROR`, and
`PUBLIC_CONFIG_RUNTIME_ERROR`. Snapshot parse status records the observed source outcome; job
failure records execution failure. A real publisher-facing missing/invalid state is evidence, not a
retryable worker exception.

Network timeouts and unexpected transient runtime/storage failures use the queue's existing bounded
attempt count and backoff. Invalid payload, tenant/state mismatch, policy block, malformed target,
and deterministic parser outcome do not retry. Each successful bounded fetch is persisted before
event evaluation so a later derivation failure cannot erase the observation.

## 16. Rollback Strategy

Before external alerting exists, operational rollback is to stop scheduling E3 job types or remove
their handlers in a revert while retaining all snapshots, records, and derived event history. The
fixed rule bundle can revert from `e3-v1` only for new derivations; existing events keep their
recorded source version.

Code rollback must not delete source evidence or mutate prior events. Migration downgrade is only
safe when no E3 event references the new snapshots and should fail explicitly otherwise. If pilot
noise is too high, disable the affected fixed rule or validation promotion in a new rule version;
do not relabel historical evidence.

## 17. Known Risks and Open Decisions

### Known risks

- DNS rebinding cannot be fully solved in application code; deployment egress controls are part of
  the production security boundary.
- Real publishers sometimes serve invalid content types or mixed encodings. Strictness must be
  deterministic and visible without silently calling unusable content healthy.
- robots.txt partial parsing can preserve useful rules while diagnostics exist; confusing warnings
  with total invalidity would create noise.
- ads.txt files can be large and contain many duplicates or malformed records; parsing and summary
  construction must be bounded in bytes, rows, diagnostics, and JSON size.
- a validation fetch made immediately after a transient CDN inconsistency may agree by accident;
  later scheduled evidence must remain independent and conditions must preserve uncertainty.
- overly broad redirect compatibility would weaken the repository's SSRF policy; E3 intentionally
  favors configured-target safety.

### Open decisions

None block implementation. The following initial values must be verified against repository
settings and fixtures during M2 and recorded in the Decision Log if changed:

- robots.txt byte limit: 512,000 bytes, satisfying RFC 9309's minimum 500 KiB;
- ads.txt byte/record/diagnostic limits: choose the smallest values that safely cover pilot files,
  with tests proving bounded behavior;
- redirect count and connect/read/total timeouts: explicit small settings, not library defaults;
- whether shared URL/DNS primitives can be extracted without altering browser behavior; otherwise
  use a public-config guard with parity tests.

## 18. Decision Log

### 2026-08-21 — Keep E3 separate from Chromium

**Decision:** Fetch robots.txt and ads.txt in the general worker through a bounded HTTP client.

**Reason:** Both are site-level public configuration. Browser rendering adds cost and unrelated
failure modes and is not required by `BROWSER.md`.

**Alternatives:** Reuse Playwright checkpoint jobs; add a new worker process.

**Impact:** Reuses the current queue/worker while keeping public-config evidence independent.

### 2026-08-21 — Require independent confirmation for high-risk states

**Decision:** Use a linked `VALIDATE_PUBLIC_CONFIG` fetch for broad robots blocks and ads.txt
missing/empty/material-invalid states, including recovery confirmation for conditions.

**Reason:** `EVENTS.md` requires `IMMEDIATE_SECOND_CHECK`; a single transient CDN or origin result
must not become a high-risk event.

**Alternatives:** Promote immediately; wait for the next six-hour scheduled observation.

**Impact:** Adds one bounded job only on risky transitions and preserves both observations.

### 2026-08-21 — Defer critical-seller removal

**Decision:** Do not implement `ADS_TXT_CRITICAL_SELLER_REMOVED` in E3.

**Reason:** The repository does not yet have explicit evidence that a seller/account/path is active
or critical. Line deletion alone cannot establish business impact.

**Alternatives:** Treat DIRECT removals or known domains as automatically critical.

**Impact:** Prevents unsupported commercial inference; routine semantic deletion remains visible.

### 2026-08-21 — Keep raw artifact storage out of E3

**Decision:** Persist bounded normalized snapshot evidence and seller rows, leaving `artifact_id`
null.

**Reason:** The existing artifact model is browser-checkpoint-owned; generalizing it is unnecessary
for the canonical E3 outcome and would expand migration/retention scope.

**Alternatives:** Add a polymorphic artifact owner or store raw content in PostgreSQL.

**Impact:** Smaller schema and no new storage path; summaries must retain enough bounded semantic
evidence for explanation and reproducibility.

### 2026-08-21 — Enforce stricter redirects than protocol interoperability allows

**Decision:** Permit only the configured host and approved www alias, revalidated at every hop.

**Reason:** The repository's target-authorization and SSRF invariants take precedence over optional
cross-authority robots redirects or third-party ads.txt delegation.

**Alternatives:** Follow RFC/IAB cross-authority redirects automatically.

**Impact:** Some delegated files may be recorded as blocked until the product supports explicit,
tenant-configured aliases.

## 19. Discoveries / Surprises

- `event_evidence_refs` is already generic at the database layer, but the Python `EvidencePointer`
  still assumes a checkpoint run. E3 needs a compatible contract generalization, not a schema
  rewrite.
- The current browser network guard contains reusable validation semantics but imports Playwright;
  direct reuse would couple a lightweight collector to the browser dependency.
- RFC 9309 requires a parser limit of at least 500 KiB and asks crawlers to use parseable lines even
  when other lines fail. A smaller generic text-response budget or all-or-nothing parser would be
  non-compliant.
- ads.txt 1.1 deprecates a literally empty file as the declaration of no authorized sellers and
  defines a placeholder record. This reinforces the canonical `ADS_TXT_EMPTY_200` event.
- The existing artifact table cannot represent public-config evidence without a browser checkpoint,
  while the canonical public-config `artifact_id` is optional. E3 can remain evidence-complete with
  immutable semantic snapshots and records.

## 20. Progress Log

### 2026-08-21

Verified EP-016 merge commit `6f95667` and successful post-merge CI run #107. Created local branch
`agent/implement-ep-017` from `origin/main`. Read the canonical E3 contracts, current scheduler,
worker, queue, security, event, migration, and artifact implementation. Checked RFC 9309 and IAB
Tech Lab ads.txt 1.1 primary sources. Drafted EP-017 without staging, committing, pushing, opening a
PR, or starting implementation.

### 2026-08-21 — M1 started

The user approved EP-017 and authorized M1 implementation. The plan passed through `READY` and is
now `IN_PROGRESS`. Work is limited to snapshot/record contracts, migration, persistence, and M1
tests; fetch, scheduling, validation orchestration, and event derivation remain later milestones.

Next step: implement and validate M1 without staging or publishing repository changes.

### 2026-08-21 — M1 implementation complete; PostgreSQL validation pending

Added typed public-configuration contracts, bounded summary/record invariants, deterministic
observation and record keys, SQLAlchemy snapshot/record models, migration `0015`, idempotent
tenant-scoped persistence, validation lineage, compatible predecessor lookup, unit tests, and
PostgreSQL integration tests. Static SQL generation confirms a single Alembic head and valid E3
DDL.

The current runtime has no PostgreSQL listener at `localhost:5432` and exposes neither Docker nor
local PostgreSQL binaries. Integration execution therefore stopped at connection setup rather than
an application assertion. M1 remains unchecked until those tests run in CI or another PostgreSQL
environment.

Next step: obtain explicit authorization to stage and commit the M1 checkpoint, then use GitHub CI
to run the pending PostgreSQL validation before M1 is marked complete.

## 21. Validation Results

### Planning validation — 2026-08-21

- Post-merge GitHub Actions run #107: PASS.
- Branch baseline: `agent/implement-ep-017` at `6f95667`, tracking `origin/main`.
- Canonical scope review: PASS; E3 is robots.txt, ads.txt, and high-risk validation.
- Primary-standard review: PASS; RFC 9309 and ads.txt 1.1 constraints are represented above.
- Implementation tests: M1 IN PROGRESS.

### M1 local validation — 2026-08-21

- `ruff format --check .`: PASS, 175 files formatted.
- `ruff check .`: PASS.
- `mypy app tests scripts migrations/env.py`: PASS, 160 source files.
- `pytest tests/unit`: PASS, 198 tests; one existing Starlette deprecation warning.
- Python compileall: PASS.
- `alembic heads`: PASS, one head at `0015_public_configuration_e3`.
- `alembic upgrade head --sql`: PASS, complete PostgreSQL DDL generated offline.
- whitespace checks for tracked and new files: PASS.
- PostgreSQL migration/integration tests: BLOCKED BY ENVIRONMENT; connection refused at
  `localhost:5432`, with no Docker/PostgreSQL runtime available. No test reached an application
  assertion.

## 22. Final Outcome / Retrospective

Not yet implemented. Complete this section only after all milestones and final validation pass.
