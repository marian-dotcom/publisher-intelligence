# EP-028 — Operator Site Registration

**Status:** READY
**Owner:** Codex / Engineering
**Created:** 2026-08-27
**Updated:** 2026-08-28
**M3 closed: 2026-08-27**
**M4 closed: 2026-08-28**
**Base commit:** `c2ba668e5e7deda78e4d7f6970fd45a5c904ecb0`
**Target milestone:** Internal operator Add Site surface before Gate O
**MVP scope impact:** NO — implements the existing MVP onboarding hierarchy for internal testing
**External publisher onboarding:** OUT OF SCOPE
**GAM / GA4 / GSC connection:** OUT OF SCOPE; planned separately after this EP

## 1. Purpose and User Outcome

After this plan is complete, an authenticated internal operator can add one public publisher site from the existing product Home surface without using SSH, a CLI, test factories, or manual database edits.

The product will:

1. derive tenant ownership from the authenticated session;
2. accept only publisher name, site name, and one public URL from the operator;
3. validate the URL against the existing browser network/SSRF guard before persistence;
4. create the canonical publisher/site/browser configuration for the current tenant;
5. enqueue exactly one immediate `DIAGNOSTIC` browser checkpoint with persistent `OPERATOR_UI` provenance;
6. expose the newly registered site through the existing Home site selector;
7. expose a bounded initial-diagnostic status for that site;
8. allow the existing scheduler to begin normal six-hour `SCHEDULED` monitoring automatically for the active site.

This is an **internal operator testing surface**, not publisher self-service onboarding.

## 2. Scope

### In

- an authenticated `Add site` action on the existing Home surface;
- a tenant-bound backend command for site registration;
- server-side CSRF enforcement for the write;
- server-side tenant derivation from the authenticated actor; no client-supplied tenant identity;
- public URL validation using the existing `BrowserNetworkGuard` policy;
- reuse of the canonical Publisher → Site → Template → MonitoredUrl → BrowserScenario configuration path;
- one immediate `DIAGNOSTIC` checkpoint and one `BROWSER_CHECKPOINT` job;
- explicit `OPERATOR_UI` diagnostic trigger provenance;
- a small Alembic migration extending the existing checkpoint trigger-source CHECK constraint;
- duplicate-registration protection for the same canonical domain inside one tenant;
- an initial diagnostic projection suitable for Home, including run status and bounded browser access classification;
- frontend success/error states for queued diagnostic, duplicate site, invalid/blocked URL, auth/CSRF failure, and generic server failure;
- regression coverage for the existing CLI path, which must remain `OPERATOR_CLI`.

### Out

- Google Ad Manager connection or OAuth;
- GA4 or Search Console connection;
- OCI secret creation/writes;
- publisher self-service onboarding;
- publisher accounts, invitations, organization administration, billing, or customer roles;
- delete/archive/edit-site workflows;
- representative URL discovery or 20–40 URL curation;
- a new top-level `Sites` product area;
- a new site lifecycle taxonomy such as `PENDING_VALIDATION`;
- arbitrary browser scenarios or user-supplied browser settings;
- changing six-hour scheduler semantics;
- Limited Pilot authorization or Gate P approval;
- onboarding a real publisher as part of CI or implementation validation.

## 3. Non-Goals

EP-028 does not attempt to design the final customer onboarding experience. It does not turn site registration into generic CRUD, expose tenant IDs to the browser, or make an OAuth/connector decision.

A successful `Add site` request means that the site is configured for monitoring and that the first diagnostic was queued. It does **not** mean the site is healthy, accessible without challenge, or ready for Limited Pilot.

Gate O remains a separate live-validation activity using a real publisher/site after this implementation is merged, deployed, and validated.

## 4. Canonical References

Implementation MUST preserve the contracts in:

- `AGENTS.md` — one active ExecPlan, tenant isolation, APIs as use cases rather than raw CRUD, frontend does not own domain semantics;
- `PLANS.md` — living ExecPlan and stop-and-fix validation ladder;
- `MVP.md` — onboarding hierarchy already includes Publisher → Site → URLs/templates → scenarios → connectors;
- `PRODUCT.md` and `DECISIONS.md` ADR-002 — Home / Timeline / Investigate remain the primary MVP surfaces; do not add a fourth primary area;
- `SECURITY.md` — tenant ownership is server-enforced, cookie-auth writes require CSRF, private/internal browser targets fail closed;
- `BROWSER.md` — controlled visits, explicit diagnostic provenance, diagnostic cohort purity, no stealth/evasion, six-hour scheduled monitoring;
- `DATA_MODEL.md` — tenant-owned publisher/site/configuration hierarchy and immutable checkpoint evidence;
- `DECISIONS.md` ADR-010 / ADR-011 / ADR-020 / ADR-130 — six-hour black-box monitoring, representative URL model, no anti-bot evasion, observation-run taxonomy;
- `plans/EP-002-browser-checkpoint-b1.md` — existing operator registration + diagnostic path;
- `plans/EP-018-observation-run-semantics-trigger-provenance.md` — explicit non-scheduled provenance;
- `plans/EP-025a-authenticated-product-backend-read-apis.md` — actor-bound product API boundary;
- `plans/EP-025b-product-frontend.md` — existing authenticated product surface;
- `plans/EP-026-pilot-reliability-operational-readiness.md` — browser access classification and pilot safety;
- `plans/EP-027-authentication-hardening-pre-pilot.md` — session/CSRF/trust boundary.

No new architecture ADR is required. `OPERATOR_UI` is an additive provenance value within the already accepted ADR-130 taxonomy, not a change to observation semantics.

## 5. Current State

Authoritative base is `c2ba668e5e7deda78e4d7f6970fd45a5c904ecb0`.

### Existing site-registration foundation

`backend/app/browser_cli.py register-and-enqueue` already exposes an internal CLI that calls `CheckpointService.register_and_enqueue()`.

The service already:

- canonicalizes the URL hostname;
- validates the initial URL with `BrowserNetworkGuard` before persistence;
- creates/reuses Publisher, Site, Template, MonitoredUrl and canonical browser configuration;
- creates a non-scheduled `DIAGNOSTIC` run;
- enqueues a tenant-owned `BROWSER_CHECKPOINT` job;
- refuses a site that already belongs to a different publisher inside the same tenant.

The integration test factory `backend/tests/integration/product/factories.py::create_site` is test-only and MUST NOT be reused as a production/staging onboarding mechanism.

### Existing authenticated product boundary

The API has authenticated product reads under `/product/*` and actor context carries the authorized tenant. `get_current_actor_with_csrf` is available for cookie-authenticated writes.

Home already reads `/product/home/status`, renders the site selector, and has an empty state when no sites exist.

### Existing frontend request boundary

`frontend/lib/api.ts` already:

- sends same-origin requests;
- includes cookies;
- sets `Accept: application/json`;
- attaches the CSRF header to non-GET requests.

### Existing scheduler behavior

`CheckpointSchedulingService.schedule_due()` selects all `Site.status == "ACTIVE"` records, ensures the B2 configuration, and materializes the canonical six-hour scheduled runs for active monitored URLs and desktop/mobile scenarios. The main scheduler calls this pass continuously.

Therefore an EP-028 site created with the existing active configuration naturally enters recurring monitoring. No separate `Enable monitoring` state/action is required.

### Current provenance constraint

`CheckpointRun.trigger_source` currently permits only:

- `OPERATOR_CLI`;
- `LEGACY_CLI`;
- `INCIDENT`.

Using `OPERATOR_CLI` for a UI action would make immutable checkpoint provenance false. EP-028 therefore adds `OPERATOR_UI` to the typed contract and database CHECK constraint.

Current Alembic head is `0027_checkpoint_run_budget_kind`; EP-028 uses revision `0028_operator_ui_trigger_source` with down revision `0027_checkpoint_run_budget_kind`.

## 6. Target Behavior

### User flow

From authenticated Home:

```text
Home
  ↓
Add site
  ↓
Publisher name
Site name
Website URL
  ↓
Add site
  ↓
URL safety validation
  ↓
canonical tenant-owned site configuration
  ↓
DIAGNOSTIC / OPERATOR_UI checkpoint queued
  ↓
site appears in existing Home selector
  ↓
initial diagnostic status shown
  ↓
existing scheduler owns future 6-hour SCHEDULED monitoring
```

The UI SHOULD stay deliberately small. No multi-step onboarding wizard is introduced.

### Suggested request

```json
{
  "publisher_name": "Example Publisher",
  "site_name": "Example News",
  "url": "https://news.example/"
}
```

The request MUST NOT accept:

- `tenant_id`;
- `tenant_slug`;
- `actor_subject_id`;
- arbitrary observation kind;
- arbitrary trigger source;
- arbitrary scenario/configuration payloads.

### Suggested success response

```json
{
  "site_id": "<uuid>",
  "canonical_domain": "news.example",
  "checkpoint_run_id": "<uuid>",
  "diagnostic_status": "PENDING"
}
```

Do not return secrets, job payloads, internal database objects, or full evidence manifests.

### Initial diagnostic projection

Home may expose a bounded projection such as:

```json
{
  "run_id": "<uuid>",
  "status": "PENDING|RUNNING|COMPLETE|PARTIAL|SITE_ERROR|BROWSER_ERROR|TIMEOUT|BLOCKED",
  "completed_at": null,
  "browser_access_classification": null
}
```

When final, `browser_access_classification` is limited to the existing canonical values:

```text
ok
degraded
challenge_suspected
```

Do not expose DOM, screenshots, raw manifest data, response bodies, cookies, or arbitrary diagnostic text through this projection.

## 7. Architecture / Data Flow

```text
Authenticated operator
        ↓
Home — Add site dialog
        ↓
POST /product/sites
        ↓
Session + CSRF + actor tenant
        ↓
Operator site-registration service
        ↓
BrowserNetworkGuard.validate_initial(url)
        ↓
Publisher / Site / Template / MonitoredUrl / Scenarios
        ↓
DIAGNOSTIC CheckpointRun
trigger_source = OPERATOR_UI
        ↓
PostgreSQL JobQueue
        ↓
Browser worker
        ↓
existing evidence + access classification

Existing Scheduler
        ↓
ACTIVE site + active monitored URL/scenarios
        ↓
future SCHEDULED six-hour monitoring
```

The API request never executes Chromium synchronously.

## 8. Files and Modules Affected

Expected changes, subject to repository inspection during implementation:

```text
plans/EP-028-operator-site-registration.md
backend/app/api/product.py
backend/app/browser/contracts.py
backend/app/browser/service.py
backend/app/browser/models.py              # constraint mirror only if needed
backend/migrations/versions/0028_operator_ui_trigger_source.py
backend/tests/integration/test_product_site_registration.py   # new or equivalent
backend/tests/integration/test_migrations.py                   # migration coverage if canonical pattern requires
backend/tests/unit/browser/test_observation_semantics.py       # provenance regression if appropriate
frontend/app/(protected)/page.tsx
frontend/components/add-site-dialog.tsx                         # likely new
frontend/lib/api-types.ts
frontend/tests/*site*.test.tsx                                  # focused UI coverage
```

Prefer a small dedicated service/repository helper if putting write semantics directly into `api/product.py` would make the route own persistence details. Do not introduce a generic site CRUD framework.

## 9. Milestones

### M0 — Plan and contract closure

**Goal:** establish exact scope, security boundary, recurring-monitoring behavior and provenance semantics before code.

**Acceptance:**

- [x] authoritative base inspected;
- [x] existing CLI/site registration path inspected;
- [x] authenticated product and CSRF boundary inspected;
- [x] scheduler behavior inspected and confirmed to pick up new ACTIVE sites automatically;
- [x] `OPERATOR_UI` provenance requirement identified;
- [x] no unresolved product/security/architecture decision blocks implementation;
- [x] plan is READY before production code changes.

### M1 — Tenant-bound backend command + provenance migration

**Goal:** expose one safe authenticated use case for registering a site and queueing its initial diagnostic.

**Implementation:**

- add migration `0028_operator_ui_trigger_source`;
- add `OPERATOR_UI` to typed trigger-source contracts;
- preserve existing CLI behavior as `OPERATOR_CLI`;
- add an actor-tenant-bound registration service/entry point that does not accept tenant identity from the request;
- add `POST /product/sites` (or an equivalently narrow product command endpoint) protected by session + CSRF;
- run existing `BrowserNetworkGuard` validation before persistence;
- reject duplicate canonical domain inside the actor tenant without creating another diagnostic/job;
- keep browser execution asynchronous.

**Acceptance:**

- [x] authenticated valid-CSRF request creates exactly one tenant-owned site configuration and one `DIAGNOSTIC` run;
- [x] run provenance is `OPERATOR_UI` with a fresh persistent correlation UUID;
- [x] no client tenant identifier is accepted or trusted;
- [x] unauthenticated request is 401;
- [x] missing/invalid CSRF is 403;
- [x] forbidden/private/internal URL is rejected before site/job persistence;
- [x] duplicate same-tenant canonical domain is a deterministic conflict and creates no second run/job;
- [x] same canonical domain in a different tenant cannot leak or collide across tenants;
- [x] CLI registration regression remains `OPERATOR_CLI`;
- [x] migration upgrade/downgrade/re-upgrade passes.

**M1 COMPLETE** at implementation checkpoint `d09aadc737e01b585f9dfa58081794a98ddb87a2`.
CI evidence: GitHub Actions run `33096657603` (HEAD `d09aadc737e01b585f9dfa58081794a98ddb87a2`) — backend / frontend / repository-safety all SUCCESS, including `ruff format --check`, `ruff check`, `mypy`, `pytest tests/unit`, `alembic upgrade head`, `RUN_INTEGRATION=1 pytest tests/integration`, `python -m app.scheduler --once`, `python -m app.worker --once`, frontend lint/typecheck/test/build, secret scan + `docker compose config` + `git diff --check`. M1 code covered by `backend/tests/integration/test_product_site_registration.py` (tenant-bound atomic registration, auth/CSRF 401/403, ADMIN-only 403, no client tenant id, blocked-target rejection, deterministic same-tenant duplicate conflict, cross-tenant isolation, concurrent duplicate → one site/run/job, CLI `OPERATOR_CLI` regression) and `backend/tests/integration/test_migrations.py` (upgrade/downgrade/re-upgrade + guarded downgrade).

**M2 COMPLETE** at implementation commit `d5310bf6de8fa2d69350ff2766411e1d388fa264`.
CI evidence: GitHub Actions run `33109458048` (HEAD `d5310bf6de8fa2d69350ff2766411e1d388fa264`) — backend / frontend / repository-safety all SUCCESS, including `ruff format --check`, `ruff check`, `mypy`, `pytest tests/unit`, `alembic upgrade head`, `RUN_INTEGRATION=1 pytest tests/integration`, `python -m app.scheduler --once`, `python -m app.worker --once`, frontend lint/typecheck/test/build, secret scan + `docker compose config` + `git diff --check`. Pre-existing deprecation/GC warnings only; no failures. Local pre-commit validation checkpoint: `cb9e5aacaab8bc7e43d6886ac007b50682311056`. Gate O NOT STARTED. Gate P HUMAN GATE. Limited Pilot NOT AUTHORIZED.

### M2 — Initial diagnostic read projection

**Goal:** let Home show whether the first controlled observation is queued/running/final and whether access is normal/degraded/challenged.

**Implementation:**

- extend the tenant-scoped Home/product read model with a bounded latest-initial-diagnostic projection;
- select only `DIAGNOSTIC` runs relevant to operator registration; do not mix them into scheduled source-health or LKG cohorts;
- expose only identifiers/status/timestamps/access classification needed by the UI.

**Acceptance:**

- [x] only the actor tenant's diagnostic is visible;
- [x] DIAGNOSTIC data does not become scheduled source health;
- [x] browser access classification is canonical and bounded;
- [x] no raw evidence or arbitrary page text leaks through the projection;
- [x] absence of a diagnostic is represented as absence/unknown, not healthy.

### M3 — Home Add Site UX

**Goal:** perform the full operator registration flow from the existing product UI.

**Implementation:**

- add `Add site` affordance on Home without adding a fourth primary nav item;
- use a compact form: Publisher name, Site name, Website URL;
- call the tenant-bound product command through existing same-origin API/CSRF machinery;
- on success refresh/select the new site and show its initial-diagnostic state;
- show actionable but sanitized errors for duplicate registration, blocked/invalid URL, auth/CSRF and server failure;
- preserve keyboard/focus/accessibility behavior consistent with the existing frontend.

**Acceptance:**

- [x] operator can add a site without terminal/CLI/manual DB operations;
- [x] no tenant/security/internal fields are present in the form;
- [x] success visibly shows the site and queued/running diagnostic state;
- [x] duplicate submit cannot create duplicate site/run/job;
- [x] UI errors reveal no tenant-existence or internal-network detail;
- [x] existing Home/Timeline/Incidents/Investigate behavior remains intact.

**M3 COMPLETE** at implementation commit `74712ed183bac4039d62574742f803715433c2bc`.
CI evidence: GitHub Actions run `33115221174` (HEAD `74712ed183bac4039d62574742f803715433c2bc`) — backend / frontend / repository-safety all SUCCESS. Frontend validation recorded `pnpm --dir frontend test -- tests/add-site-dialog.test.tsx tests/home-timeline.test.tsx` at 42 passed, `pnpm --dir frontend test` at 104 passed across 12 test files, `pnpm --dir frontend lint` at 0 errors with one pre-existing warning, `pnpm --dir frontend typecheck` PASS and `pnpm --dir frontend build` PASS. Repository `git diff --check` was clean.

Adversarial review closed the stale-site polling race, missing polling coverage, duplicate-submit test weakness and stale-site guard finding. The remediated implementation uses a generation token to reject stale responses and recursive, non-overlapping polling only while the selected site's diagnostic is `PENDING` or `RUNNING`, at a four-second interval with a finite maximum of 15 attempts. Polling cancels on terminal or unknown state, request failure, site change and unmount; it does not poll source health. Deterministic tests cover polling behavior, stale-response protection and handler-level duplicate-submit suppression.

### M4 — End-to-end regression and release readiness

**Goal:** prove the new write surface preserves all existing product, auth, browser and tenant boundaries.

**Acceptance:**

- [x] backend static/type/unit checks pass;
- [x] clean-database migration to head passes;
- [x] focused and full relevant integration tests pass in the canonical single-process form;
- [x] frontend lint/typecheck/tests/build pass;
- [x] secret scan and diff hygiene pass;
- [x] no real publisher/site was contacted by automated tests;
- [x] plan records exact CI evidence before COMPLETE;
- [x] Gate O and Limited Pilot remain unauthorized by this implementation alone.

**M4 COMPLETE** at validation checkpoint `59720d4a7dec95aeb2cdbde3642add15be2a4c3a`.

The accepted canonical retry used the complete GitHub Actions backend environment with an isolated database, `publisher_intelligence_ep028_m4_retry1`. Before migration it had zero public tables, no `alembic_version` relation and zero other client sessions. `uv --directory backend run alembic upgrade head` applied the full chain from base through `0028_operator_ui_trigger_source`. The original `publisher_intelligence` database remained at `0027_checkpoint_run_budget_kind`; all persistent API/worker/scheduler/browser-worker database targets and the five observed background sessions remained confined to that original database.

Local validation evidence from one coherent retry sequence:

- `uv --directory backend sync --all-groups --locked`: PASS, 121 packages resolved / 119 checked;
- `uv --directory backend run ruff format --check .`: PASS, 306 files already formatted; check-only, no files modified;
- `uv --directory backend run ruff check .`: PASS;
- `uv --directory backend run mypy app tests scripts migrations/env.py`: PASS, 271 source files;
- `uv --directory backend run pytest tests/unit`: 434 passed, one pre-existing deprecation warning;
- `docker compose config` and `docker compose up -d postgres minio minio-init`: PASS; PostgreSQL and MinIO healthy, `minio-init` exit 0;
- focused single-process integration command `RUN_INTEGRATION=1 uv --directory backend run pytest tests/integration/test_migrations.py tests/integration/test_product_site_registration.py tests/integration/test_product_initial_diagnostic_m2.py`: 37 passed, 36 warnings;
- full single-process integration command `RUN_INTEGRATION=1 uv --directory backend run pytest tests/integration`: 214 passed, 121 pre-existing deprecation/connection-GC warnings;
- `uv --directory backend run python -m app.scheduler --once`: PASS;
- `uv --directory backend run python -m app.worker --once`: PASS;
- `pnpm --dir frontend install --frozen-lockfile`: PASS; lockfile already current;
- `pnpm --dir frontend lint`: PASS, 0 errors and one pre-existing warning;
- `pnpm --dir frontend typecheck`: PASS;
- `pnpm --dir frontend test`: 104 passed across 12 test files;
- `pnpm --dir frontend build`: PASS;
- `python3 scripts/check_secrets.py`: PASS, no known credential patterns. The local-only `python3` spelling executes the same repository script because this macOS environment lacks GitHub Actions' `python` alias; the initial `python scripts/check_secrets.py` attempt exited before script execution and was not a scan finding;
- `git diff --check`: clean before documentation closure.

The earlier full-integration attempt against `publisher_intelligence_ep028_m4` is rejected as M4 evidence because its shell omitted the canonical CI-only `BROWSER_ALLOW_PRIVATE_NETWORKS=true` fixture opt-in. The successful retry set every backend-job variable from `.github/workflows/ci.yml`; private-network access was enabled only for controlled ephemeral `127.0.0.1` fixture servers. External-looking example domains were stored fixture data or used behind test doubles. No automated test contacted a real publisher or site.

Accepted CI evidence at the same checkpoint: GitHub Actions pull-request run `33122379001` and push run `33122375461` both completed SUCCESS, with backend / frontend / repository-safety all SUCCESS. Together with the focused and full local retry, this validates the product flow, authentication/CSRF behavior, browser safety and provenance, duplicate/concurrency behavior, diagnostic cohort separation and cross-tenant boundaries required by M4.

## 10. Acceptance Criteria

EP-028 is complete only when all are true:

- [x] `Add site` exists on authenticated Home for the current internal operator surface;
- [x] backend derives tenant identity exclusively from authenticated actor context;
- [x] write requires valid CSRF;
- [x] URL is validated by the canonical public-network browser guard before persistence;
- [x] one successful registration creates/reuses the required publisher hierarchy but creates exactly one new site configuration for a new canonical domain;
- [x] exactly one immediate `DIAGNOSTIC` checkpoint is created/enqueued for a successful new site;
- [x] diagnostic provenance is truthfully stored as `OPERATOR_UI`;
- [x] duplicate site registration is idempotency-safe and does not enqueue duplicate diagnostics;
- [x] diagnostic remains excluded from scheduled comparison/event/LKG cohorts per ADR-130;
- [x] existing scheduler can subsequently generate normal six-hour `SCHEDULED` runs without a new enable action;
- [x] Home exposes a bounded initial-diagnostic state separately from normal source health;
- [x] no generic site CRUD, external onboarding, OAuth, connector, or secret-write capability is introduced;
- [x] cross-tenant negative tests pass;
- [x] full relevant CI is green.

## 11. Validation Commands

Use the repository's canonical commands and stop on first relevant failure.

```bash
uv --directory backend sync --all-groups --locked
uv --directory backend run ruff format --check .
uv --directory backend run ruff check .
uv --directory backend run mypy app tests scripts migrations/env.py
uv --directory backend run pytest tests/unit

# Docker-backed validation where available
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

Focused tests should run before the full suite, but they do not replace the canonical final suite.

## 12. Test Cases

### Happy path

- ADMIN/OPERATOR with valid session + CSRF submits a public HTTPS URL;
- server derives the tenant from `ActorContext`;
- publisher/site/configuration are persisted in that tenant;
- one `DIAGNOSTIC` run exists with `OPERATOR_UI` and one matching queue job;
- Home shows the site and initial diagnostic;
- after worker completion the bounded classification can become `ok`, `degraded`, or `challenge_suspected`;
- scheduler later produces normal `SCHEDULED` runs for the new ACTIVE site.

### Security / tenancy

- unauthenticated POST → 401;
- invalid/missing CSRF → 403;
- payload cannot select another tenant;
- cross-tenant reads do not expose the new site/diagnostic;
- same domain in tenant B is independent of tenant A;
- loopback/private/link-local/metadata/reserved target is rejected before persistence;
- redirect/subresource browser security behavior remains unchanged.

### Duplicate / concurrency

- same canonical domain submitted twice in one tenant returns deterministic conflict/no-op semantics on the second attempt;
- concurrent duplicate submissions cannot create two sites or two initial diagnostic jobs;
- same site name with a different canonical domain is not treated as the same site merely by display name;
- existing site bound to another publisher in the same tenant cannot be silently reassigned.

### Provenance / cohort purity

- UI action → `DIAGNOSTIC` + `OPERATOR_UI`;
- CLI action → `DIAGNOSTIC` + `OPERATOR_CLI`;
- scheduler action → `SCHEDULED` + no trigger provenance;
- UI diagnostic cannot become scheduled comparison lineage or LKG merely because it completed successfully.

### Frontend

- Add Site dialog fields and accessible labels render;
- valid submit sends only approved fields;
- CSRF is attached by existing API client;
- duplicate/blocked/general errors are sanitized;
- success updates Home/selected site and shows diagnostic state;
- primary navigation remains unchanged.

## 13. Data / Migration Impact

No new entity table or site-lifecycle column is required.

One additive schema change is required:

```text
checkpoint_runs.trigger_source CHECK
old: OPERATOR_CLI | LEGACY_CLI | INCIDENT
new: OPERATOR_CLI | LEGACY_CLI | OPERATOR_UI | INCIDENT
```

Migration:

```text
revision: 0028_operator_ui_trigger_source
down_revision: 0027_checkpoint_run_budget_kind
```

The migration changes no historical rows. Downgrade is permitted only where no `OPERATOR_UI` rows exist or in disposable local/CI databases; production-like environments with real `OPERATOR_UI` evidence must not destructively downgrade without explicit review.

Site/Publisher uniqueness and tenant relationships remain the existing database model.

## 14. Security / Privacy Impact

This EP adds an authenticated write surface and therefore has material security impact.

Mitigations:

- derive tenant from server-side actor context only;
- require session authentication and CSRF;
- validate public URL before persistence using the canonical browser network guard;
- never accept credentials, cookies, headers, OAuth tokens or arbitrary browser options;
- never log query strings/page text/DOM/cookies/request bodies;
- cross-tenant tests are mandatory;
- duplicate and conflict responses must not disclose other tenants;
- browser security policy remains fail-closed with `BROWSER_ALLOW_PRIVATE_NETWORKS=false` in staging/production;
- no stealth, CAPTCHA solving, fingerprint spoofing or proxy rotation;
- no new secret storage path.

The URL and publisher/site names are customer configuration data and must remain tenant-scoped.

## 15. Observability / Failure Handling

The registration path may log bounded identifiers and outcome metadata:

```text
actor_subject_id
tenant_id
site_id
checkpoint_run_id
stage
status
error_class
```

Do not log:

- password/session/CSRF values;
- full URL query/fragment;
- page content;
- DOM/screenshots;
- request/response bodies from the publisher.

Failure semantics:

- invalid/unsafe target → rejected before persistence;
- duplicate canonical domain → deterministic conflict/no second diagnostic;
- database/job enqueue error → explicit platform failure, never represented as publisher health;
- browser result uses existing `COMPLETE/PARTIAL/SITE_ERROR/BROWSER_ERROR/TIMEOUT/BLOCKED` semantics;
- access classification remains separate from site business health.

## 16. Rollback Strategy

Before any real EP-028 site is registered:

1. revert EP-028 implementation;
2. downgrade migration `0028` only in disposable environments;
3. preserve the pre-existing CLI and scheduler behavior.

After real `OPERATOR_UI` checkpoint evidence exists:

- do not delete or rewrite the evidence;
- disable/remove the UI write path through a forward fix if necessary;
- preserve site configuration and checkpoint history;
- do not downgrade the trigger-source constraint if rows depend on `OPERATOR_UI`.

## 17. Progress Log

### 2026-08-27 — M0 canonical review

Reviewed the authoritative base `c2ba668e5e7deda78e4d7f6970fd45a5c904ecb0`, `AGENTS.md`, `PLANS.md`, MVP/product/security/browser contracts, existing auth/product surfaces, existing CLI registration service, checkpoint provenance constraints, current migration head, frontend Home/API client and recurring browser scheduler.

Discoveries:

- the canonical service already implements most of the underlying site/bootstrap behavior;
- the scheduler automatically picks up ACTIVE sites with active URL/scenario configuration, so no separate enable-monitoring flow is necessary;
- a UI action cannot truthfully reuse immutable `OPERATOR_CLI` provenance, requiring the additive `OPERATOR_UI` value and migration;
- Home is the correct MVP surface; a new primary `Sites` nav would conflict with ADR-002;
- initial DIAGNOSTIC status must remain distinct from normal scheduled source-health projections.

M0 complete. Plan status: READY. No production code has been changed in this planning step.

### 2026-08-27 — M1 implementation and closure

Implemented the tenant-bound backend registration command, `OPERATOR_UI` provenance and migration. Verified HEAD `d09aadc737e01b585f9dfa58081794a98ddb87a2` on branch `agent/ep-028-operator-site-management`; working tree clean; GitHub Actions run `33096657603` (same HEAD) green across backend / frontend / repository-safety, covering ruff format/check, mypy, unit tests, `alembic upgrade head`, integration tests, `scheduler --once`, `worker --once`, frontend regression checks, secret scan, compose config and `git diff --check`.

Independently reconciled the implementation and CI evidence against every M1 acceptance criterion; all pass (see M1 acceptance above). M1 is closed.

### 2026-08-27 — M2 implementation and CI closure

Implemented the initial diagnostic read projection extending the tenant-scoped Home/product read model. Verified HEAD `cb9e5aacaab8bc7e43d6886ac007b50682311056` on branch `agent/ep-028-operator-site-management`; working tree contained two M2 files: `backend/app/api/product.py` (modified) and `backend/tests/integration/test_product_initial_diagnostic_m2.py` (untracked). Full integration suite: 214 passed, exit 0, 127.17s. Scheduler `--once`: PASS, exit 0. Worker `--once`: PASS, exit 0. Post-validation working tree unchanged. Committed as `d5310bf6de8fa2d69350ff2766411e1d388fa264`; GitHub Actions run `33109458048` (same HEAD) green across backend / frontend / repository-safety, covering ruff format/check, mypy, unit tests, `alembic upgrade head`, integration tests, `scheduler --once`, `worker --once`, frontend lint/typecheck/test/build, secret scan, compose config and `git diff --check`. Pre-existing warnings only; no failures. M2 is closed.

**M3 NOT STARTED.** Gate O NOT STARTED. Gate P HUMAN GATE. Limited Pilot NOT AUTHORIZED.

### 2026-08-27 — M3 implementation and CI closure

Implemented the Home Add Site UX at commit `74712ed183bac4039d62574742f803715433c2bc`, including the compact operator form, sanitized failure states, selection of the newly registered site and bounded initial-diagnostic status. Adversarial review found and closed the stale-site polling race, missing polling coverage, duplicate-submit test weakness and stale-site guard finding. The final polling design uses generation-token stale-response protection, recursive non-overlapping requests only for `PENDING`/`RUNNING`, a four-second interval and a finite 15-attempt maximum; it cancels on terminal/unknown state, failure, site change and unmount, and never polls source health. Deterministic polling and duplicate-submit tests cover these remediations.

Targeted M3 validation via `pnpm --dir frontend test -- tests/add-site-dialog.test.tsx tests/home-timeline.test.tsx`: 42 passed. Full frontend validation via `pnpm --dir frontend test`: 104 passed across 12 test files. `pnpm --dir frontend lint`: 0 errors and one pre-existing warning. `pnpm --dir frontend typecheck`: PASS. `pnpm --dir frontend build`: PASS. `git diff --check`: clean. GitHub Actions run `33115221174` at the same HEAD completed backend / frontend / repository-safety with SUCCESS. M3 is closed; M4 and all release gates remain unstarted and unauthorized as stated below.

### 2026-08-28 — M4 isolated canonical validation and closure

Restarted M4 from the accepted checkpoint `59720d4a7dec95aeb2cdbde3642add15be2a4c3a` using a new empty database, `publisher_intelligence_ep028_m4_retry1`, and the complete backend-job environment from `.github/workflows/ci.yml`. The retry database was proven empty and session-isolated before migration, upgraded through the complete Alembic chain to `0028_operator_ui_trigger_source`, and remained isolated from persistent application containers. The original database remained unchanged at `0027_checkpoint_run_budget_kind`.

The first isolated attempt is rejected because it omitted `BROWSER_ALLOW_PRIVATE_NETWORKS=true`, causing controlled loopback browser fixtures to fail before the suite completed. The canonical retry included the variable and passed the focused integration scope (37 tests) and full integration suite (214 tests), each in one pytest process. Backend format/lint/type/unit, scheduler/worker one-shots, frontend lint/typecheck/test/build, Compose validation, secret scan and diff hygiene all passed as detailed under M4. The secret scan used the local `python3` interpreter solely because this host lacks the CI runner's `python` alias; the same repository script passed.

Automated browser traffic was limited to controlled ephemeral loopback fixture servers; provider and example-domain behavior used fixtures/test doubles. No real publisher or site was contacted. Accepted GitHub Actions runs `33122379001` (pull request) and `33122375461` (push) are SUCCESS across backend / frontend / repository-safety at the same checkpoint. M4 is closed. Gate O NOT STARTED. Gate P HUMAN GATE. Limited Pilot NOT AUTHORIZED.

### 2026-08-28 — M4 polling-test CI inconsistency and accepted remediation

After M4 closure commit `5c4d590bad01d37d6ec26ce83bfb3997f62a2856`, pull-request run `33126432621` passed while push run `33126425169` failed frontend test A (expected 3 fetches, received 2). Test-only remediation `b50b741cdda63c792aa16b3600e7dda1119aa6a8` awaited asynchronous timer advancement in A; local repetition passed, but replacement push run `33127286168` passed while pull-request run `33127289540` exposed the same synchronization defect in test G (expected 17 fetches, received 16). The root cause was synchronous fake-timer advancement not reliably flushing asynchronous polling continuations; execution-order timing masked it in complete-suite runs. No production polling defect was found.

Bounded test-only remediation `db3512cf242947b6ddb9447b0d02f90006e34929` converted asynchronous polling drivers in tests B, E, F and G to awaited `advanceTimersByTimeAsync`, preserving all behavioral, fetch-count, cancellation, terminal, stale-site, unmount and maximum-attempt assertions; production code was unchanged. Final replacement push run `33127996831` and pull-request run `33128000172` both passed: `add-site-dialog.test.tsx` 42/42, polling tests A–G passed, full frontend 104/104 across 12 files, production build SUCCESS, and backend/repository-safety SUCCESS in both workflows. Warnings remain pre-existing: the unused-variable ESLint warning, non-failing React `act(...)` output in D/F, and GitHub Actions Node/dependency deprecations; none was introduced by the remediation. M4 remains complete. Gate O, Gate P and Limited Pilot remain unstarted and unauthorized.

### 2026-08-30 — Final pre-merge documentation consistency closure (documentation only)

Final pre-merge review completed against HEAD `e65bf5c58ac2cb8b7131da4fdfc9847ffe205c82` on branch `agent/ep-028-operator-site-management`; working tree clean. After `git fetch origin`, `origin/main` is `c2ba668` and is an ancestor of the EP-028 branch. The earlier routing-scope finding (same-origin shared-prefix files appearing in the PR #34 diff) was caused by comparing against a **stale local `main`** (`57f03e0`); current `origin/main` already contains PR #33 (`c2ba668`, which includes the routing fix `6e039a7`). Recomputing `git diff origin/main...HEAD` confirms the effective PR #34 diff is exactly the expected **18-file EP-028 scope** (+3275/−23) and **excludes** the six same-origin routing files (`frontend/lib/api.ts`, `backend-routing.ts`, `middleware.ts`, and their three tests). All §10 final acceptance criteria were reconciled to accepted implementation, test, migration and CI evidence and are now checked; no live publisher, deployment, Gate O, Gate P, or Limited Pilot activity is authorized or marked complete. This entry is documentation consistency only; no implementation, test, or runtime change was made.

## 18. Decision Log

### 2026-08-27 — Internal operator surface, not self-service onboarding

**Decision:** EP-028 is available only through the existing authenticated internal product surface. No external publisher role/account/onboarding model is introduced.

**Reason:** The immediate goal is controlled first-site testing; customer onboarding has additional identity/OAuth/product requirements and should be designed after pilot learning.

### 2026-08-27 — Home affordance, no fourth primary surface

**Decision:** `Add site` belongs on Home and the existing site selector remains the navigation mechanism.

**Reason:** Preserves the accepted Home / Timeline / Investigate primary UX while adding the minimum operator capability.

### 2026-08-27 — Site ACTIVE remains configuration state

**Decision:** Do not add `PENDING_VALIDATION` to `Site.status` in EP-028. A site may be configured/ACTIVE while its initial diagnostic is pending, degraded or challenged; those are different facts.

**Reason:** Avoid conflating configuration lifecycle with browser-source accessibility and avoid an unnecessary schema/state machine.

### 2026-08-27 — Add truthful `OPERATOR_UI` provenance

**Decision:** Add `OPERATOR_UI` instead of reusing `OPERATOR_CLI`.

**Reason:** Trigger provenance is immutable evidence. Falsifying the trigger source for implementation convenience violates ADR-130 semantics.

### 2026-08-27 — Duplicate registration is not another diagnostic action

**Decision:** `Add site` for an already registered canonical domain in the same tenant does not silently enqueue another diagnostic. A future explicit `Run diagnostic` action, if needed, is a separate use case.

**Reason:** Separates resource registration from diagnostic execution and prevents double-submit side effects.

## 19. Discoveries / Surprises

- The originally CLI-oriented `CheckpointService.register_and_enqueue()` already performs nearly all of the safe canonical configuration work required by the UI use case.
- The recurring scheduler needs no new site-enablement primitive; the current ACTIVE site configuration is sufficient.
- Existing Home source-health projections are intentionally based on scheduled evidence, so using them for the onboarding diagnostic would silently violate cohort purity.

## 20. Known Risks

1. **Registration transaction vs job enqueue:** the existing service persists configuration/run before enqueueing the job. Implementation must inspect failure recovery/idempotency carefully so an enqueue failure does not make a retry look like a duplicate site with no recoverable diagnostic.
2. **Concurrent duplicate submits:** application checks alone are insufficient; database uniqueness and transaction behavior must make the outcome deterministic.
3. **Public URL redirects:** initial target validation occurs before persistence, but browser-time redirect/subresource validation remains the authoritative runtime safety boundary.
4. **Operator role granularity:** ADMIN and OPERATOR are the only current internal roles. EP-028 must not invent external/user roles; stricter product permissions can be introduced when a real need exists.
5. **Real-site behavior:** automated tests cannot prove publisher WAF compatibility. That belongs to Gate O live validation with publisher cooperation/allowlisting if required.

## 21. Final Outcome / Retrospective

Not yet applicable. Fill only after implementation, canonical validation, CI and review are complete.

## 22. Next Step

**M4 COMPLETE.** Gate O NOT STARTED. Gate P HUMAN GATE. Limited Pilot NOT AUTHORIZED. M4 completion does not authorize any release/readiness gate, GAM or connector work, real-site onboarding, live publisher contact or pilot activity; each requires separate explicit authorization.
