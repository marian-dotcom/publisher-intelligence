# EP-029 — Zero-Resistance Pilot Candidate Validation (pre-pilot)

**Status:** M0–M1 COMPLETE; M2 collection PASS / original UI presentation gap CONFIRMED; M2a UI remediation IMPLEMENTED / MERGED / DEPLOYED — STAGING UI VERIFIED (2026-09-01); M3 COMPLETE; M4 NOT STARTED; Gate P HUMAN GATE / UNAUTHORIZED; Limited Pilot NOT GRANTED
**Owner:** Codex / Engineering
**Created:** 2026-08-30 (revised 2026-08-30 per final product decision)
**Base commit:** `84593fb7547a9d92d8245622fbb9b03c2b875e0b` (`origin/main` at EP-029 creation; EP-029
merged into `origin/main` at `b61494bb…` on 2026-09-01)
**Business objective:** Validate the authorized **zero-resistance pilot candidate** — a second
publisher site that does not challenge our standard monitor — to prove the existing browser /
DOM / screenshot / artifact / event pipeline yields genuinely useful results in the platform.
**Documentation / planning scope:** YES. Execution (any live contact) requires the exact candidate
domain plus explicit authorization.
**MVP scope impact:** NO — unchanged product semantics.
**Gate P / Limited Pilot:** UNAUTHORIZED by this plan alone (separate human decisions).
**Scheduler:** MUST remain STOPPED. Do not restart because evz.ro remains ACTIVE and could be
contacted again. No scheduled cycle may begin without separate authorization.

## 1. Purpose

Gate O executed faithfully and contained everything, but evz.ro returned HTTP 429 with
`challenge_suspected`/`captcha` on every attempt (no retry) — leaving **no useful first-site
measurement**. Evz.ro compatibility is recorded as an **immutable finding** (see §5). EP-029 now
validates an authorized **zero-resistance pilot candidate**: an explicitly permissioned second site
whose pages accept the platform's standard, bounded, real-browser monitor, so we can prove the
browser/DOM/screenshot/artifact/event evidence end-to-end in the existing platform.

EVZ allowlisting and any EVZ re-diagnostic are **DEFERRED** — removed from this plan's milestones.
No edge runners, UA changes, proxies, stealth, CAPTCHA solving, or other WAF-bypass work is proposed
here; the platform's existing standard monitor is used unchanged.

## 2. Scope

### In

- plan the validation of exactly one **zero-resistance pilot candidate** site (a consenting second
  site that accepts the standard monitor without a challenge);
- exactly **one** permissioned initial `DIAGNOSTIC` run for that candidate, scheduler stopped;
- verify useful browser results (DOM, screenshots, artifacts, derived events) render normally in the
  existing platform;
- document evidence and contain the activity;
- release-readiness hand-off; Gate P remains a separate HUMAN GATE;
- use only the **existing, unchanged** browser worker / scenario / evidence pipeline (or the minimal
  additive command from prior feasibility findings, if needed — documented, not a WAF-bypass).

### Out

- any EVZ allowlisting or EVZ re-diagnostic in this plan (deferred);
- any edge runner, UA change, proxy, stealth plugin, CAPTCHA solver, header/fingerprint spoofing,
  or any other WAF-bypass work;
- any scheduled cycle or scheduler restart (evz.ro remains ACTIVE);
- any crawl, retry, concurrent navigation, or second-other-than-candidate site;
- creating checkpoint records via raw SQL (must go through an application service/API/CLI);
- exposing PostgreSQL/MinIO publicly;
- Gate P approval or Limited Pilot authorization.

## 3. Non-Goals

EP-029 does not perform multi-site or scheduled-fleet monitoring, does not change browser/connector/
event/security semantics, and does not itself authorize live contact, scheduler operation, or pilot
activity. It does not re-open the immutable evz.ro finding. It no longer contains EVZ allowlisting
or EVZ re-diagnostic milestones (deferred).

## 4. Canonical References

- `AGENTS.md` — one active ExecPlan, tenant isolation, no LLM authority over evidence derivation,
  validation/stop-and-fix, publisher-boundary and security invariants;
- `PLANS.md` — ExecPlan lifecycle and living-document rule;
- `DECISIONS.md` — ADR-010 (six-hour black-box monitoring), ADR-020 (no stealth/anti-bot evasion),
  ADR-130 (observation-run taxonomy and cohort purity);
- `SECURITY.md` — §154/§155 (no bypass/stealth), §160 (monitoring domain approval), §201
  (secure-cookie pre-pilot hard gate);
- `BROWSER.md` — §81.1 browser-source reliability/access classification; controlled visits, no
  evasion, cohort purity, six-hour scheduled monitoring;
- `EVENTS.md` — deterministic browser-source events;
- `docs/runbooks/pilot-readiness.md` — Part A4 (allowlisting/monitoring identity), A5
  (compatibility self-check), Part E (gate statuses; Gate O EXECUTED / PARTIAL / CONTAINED);
- `docs/runbooks/publisher-allowlisting.md` — monitoring UA, stable egress identity (reference only;
  candidate not yet allowlisted here);
- `plans/EP-028-operator-site-registration.md` — implemented Add Site surface + Gate O evidence;
- `backend/app/browser_worker.py` — worker entrypoint + provenance semantics.

## 5. Current State

- As of 2026-09-01 (M3 closure): `origin/main` = `b61494bb…`; staging deployed at that commit; DB
  revision `0028_operator_ui_trigger_source`. (Plan base was `84593fb…` at creation; the M2a change
  merged via PR #35 at `b61494bb…`.)
- evz.ro remains `ACTIVE` (site `d6d7f097-…`), publisher `1294d0c7-…`.
- Scheduler stopped (container preserved) and MUST remain stopped.
- **Immutable evz.ro compatibility finding:** every diagnostic/scheduled attempt returned terminal
  `SITE_ERROR` HTTP 429 with `challenge_suspected`/`captcha`, `attempt_count=1`, **no retry**, fully
  contained — no run/window/job at or after 18:00 UTC. This is a **monitoring-source finding**, not a
  platform or publisher-health defect. It is preserved, not amended. Gate O: EXECUTED / PARTIAL /
  CONTAINED (platform execution PASS, containment PASS, useful first-site measurement NOT YET
  PROVEN, evz.ro compatibility CHALLENGED).
- No candidate site is assumed; the candidate domain + explicit authorization are required before
  any contact.

- **Candidate result (climatologie.ro):** the operator submitted `https://climatologie.ro` exactly
  once through the authenticated Home UI (see §7 M1). One `DIAGNOSTIC`/`OPERATOR_UI` run
  `4fd24e2e-660b-4065-b2fe-05a8ddc96419` (site `636ce2ac-86a6-4ac4-a1f4-2addf7715e8d`, tenant
  `d6cd36b7-…`) reached terminal **COMPLETE, HTTP 200, attempt_count=1, no retry**, producing a full
  set of persisted raw/normalized DOM, pre-consent + viewport + full-page screenshots, and manifest
  with successful browser/script/SEO/performance/CMP/network observation (see §7 M2 collection
  evidence). **Reconciliation is CLOSED (2026-09-01, read-only + authorized M2a staging UI
  verification):** (a) "zero events" is verified and now correctly scoped — climatologie.ro produced
  **zero persisted events**; the only tenant event is evz.ro, which the M2a site-filtered Timeline
  hides while climatologie.ro is selected and shows under 「All sites」 with evz.ro attribution; (b) the
  candidate **publisher identity/name** is verified read-only: the persisted `publishers` row is
  **climatologie.ro** (slug `climatologie-ro`, ACTIVE; site `climatologie.ro`, ACTIVE) — the earlier
  draft "publisher `staging`" value was wrong and is replaced; (c) evidence now **renders normally** in
  the deployed platform via the M2a diagnostic-results surface (operator-verified at staging). This
  remains a single useful baseline measurement, not recurring monitoring and not complete
  advertising/consent coverage.

## 6. Feasibility findings (read-only, from prior inspection; no live contact)

- The **browser-worker** (`backend/app/browser_worker.py`, `python -m app.browser_worker [--once]`)
  claims `BROWSER_CHECKPOINT` jobs from the PostgreSQL queue, runs the standard `BrowserRunner`
  (bundled Playwright Chromium, real browser), and persists via `CheckpointRepository` +
  `EvidencePersister`/`S3Storage`. Worker/API/frontend/scheduler unchanged.
- Locale/timezone/UA come from the **persisted scenario** row; the standard bounded desktop scenario
  is used as-is. No UA/channel/proxy/stealth changes are proposed.
- Canonical diagnostic creation for an **already-registered** site has no existing helper
  (`register_and_enqueue` creates a new site; `enqueue_incident_diagnostic` forces INCIDENT
  provenance). If the candidate is registered and a plain `DIAGNOSTIC` is needed, the documented
  incremental change is a **diagnostic-for-existing-site application command** (§8), which is
  additive and does not touch the browser worker or bypass anything.
- No secrets are required in this document; env names only.

## 7. Milestones

### M0 — Authorization and containment verification — COMPLETE

- Confirm the candidate site's **exact domain** and **explicit written authorization** are provided.
- Verify the scheduler is stopped (`docker compose … ps scheduler` → Exited) and the OCI
  browser-worker availability for the single diagnostic (stop only that worker for the window if
  needed; container preserved).
- Record the authorized scope (one candidate, one bounded DIAGNOSTIC, scheduler stopped).

### M1 — One permissioned initial DIAGNOSTIC — COMPLETE

- Register the candidate (or reuse its registration) and enqueue exactly **one** `DIAGNOSTIC` run
  through an application service/API/CLI (no raw SQL), scheduler stopped.
- Restricted to the candidate's exact `https://<candidate>/` monitored URL; bounded desktop
  scenario; no retry, no crawl, no second site.

### M2 — Verify useful results in the existing platform — collection PASS / UI presentation FAIL (NOT IMPLEMENTED)

- Confirm the run produced terminal classification + browser results: raw DOM, scripts, third-party
  domains, viewport + full-page screenshots, JS errors, network state, environment provenance.
  **Collection: PASS** (evidence read-only verified; see §17).
- Verify derived events/evidence appear normally in the existing platform (Home/Timeline/Evidence).
  **UI presentation: FAIL / NOT IMPLEMENTED.** The accepted M2 UI-visibility findings report
  (recorded in §17) confirms there is **no authenticated API/UI surface** for viewing the initial
  diagnostic artifacts; the only evidence-projection path (`EvidencePackBuilder`) targets
  `SCHEDULED` runs and excludes the `DIAGNOSTIC`/`OPERATOR_UI` run; and the Timeline frontend omits
  `site_id` while the API supports it.
- Confirm tenant isolation applies to the candidate's evidence.

### M2a — Baseline diagnostic-results UI (remediation) — IMPLEMENTED / MERGED / DEPLOYED — STAGING UI VERIFIED (2026-09-01)

Authorized bounded remediation to make the successful initial diagnostic genuinely useful in the
operator UI. **Implementation, local validation, merge (`b61494bb…`), staging deployment and staging UI
verification complete** (revalidated after the NOT READY adversarial review B1/M1/M2/M3/m5/m6
remediation, merged via PR #35, deployed to `publisher-intelligence-staging` at `b61494bb…`, and
operator-verified 2026-09-01 — see §16). No site contact; scheduler stays
stopped; no fabricated event/incident/alert.

Delivery is via an **authenticated API proxy** — NOT public or presigned object-storage URLs. MinIO
stays private; artifacts are proxied read-only.

- `GET /product/sites/{site_id}/diagnostic-results` — tenant-scoped summary of the latest
  `DIAGNOSTIC`/`OPERATOR_UI` run.
- `GET /product/sites/{site_id}/diagnostic-artifacts/{artifact_id}` — tenant-scoped artifact delivery.
- Home 「View diagnostic results」 action and a baseline-results page (pre-consent / viewport /
  full-page screenshots; SEO; CMP; performance; script inventory; network hosts).
- Timeline site filter: pass selected `site_id`, show site/domain on each tenant-wide event,
  「No events for this site yet」 on an empty site view, and an explicit 「All sites」 mode.
- Explicit state labels: 「Unknown」 plus the diagnostic lifecycle states (queued / running /
  complete / failed). Dead or conflating members (`Scheduled monitoring not started`, `Not connected`,
  `Not detected`, `No events yet`) were removed during review remediation; `StateLabel` is internal to
  `domain.tsx` and `SourceStateBadge` was deleted.
- No fabricated event, incident or alert.

Per-request backend enforcement (404 on foreign/nonexistent): `actor.tenant_id` → requested site
belongs to actor tenant → diagnostic run belongs to site → artifact belongs to diagnostic run →
artifact kind is allowlisted.

Artifact handling: screenshots inline; normalized DOM text/download only; raw DOM download only;
never execute or inject collected HTML into the product UI; no `dangerouslySetInnerHTML`; do not
expose MinIO keys or internal hostnames; `Cache-Control: private, no-store`; explicit MIME types;
bounded artifact-size handling.

Implementation files:
- `backend/app/api/product.py` — new endpoints `/product/sites/{site_id}/diagnostic-results` and `/product/sites/{site_id}/diagnostic-artifacts/{artifact_id}`
- `frontend/app/(protected)/diagnostic-results/page.tsx` — diagnostic results page with screenshots inline and downloadable artifacts
- `frontend/app/(protected)/page.tsx` — added "View diagnostic results" button on Home
- `frontend/app/(protected)/timeline/page.tsx` — added site filtering with visible site/domain, "All sites" mode, and "No events for this site yet" state
- `frontend/components/domain.tsx` — added `StateLabel` (internal), `DiagnosticStateBadge`;
  `SourceStateBadge` was added then removed during review remediation
- `frontend/lib/api-types.ts` — added `DiagnosticArtifactType`, `DiagnosticResults`, `DiagnosticRun`, `DiagnosticArtifact` types

Tests:
- Backend: `tests/integration/test_product_diagnostic_results_m2a.py` (23 tests covering auth, tenant isolation, artifact kind allowlist, content-disposition, cache-control, no MinIO exposure)
- Backend: `tests/integration/test_memory_p2b.py` (11 tests, incl. two new regression tests for the Timeline notes site filter and entire-timeline site filtering)
- Frontend: `tests/diagnostic-results.test.tsx` (12 tests incl. routing/pending/missing-id contract), `tests/timeline-site-filter.test.tsx` (8 tests incl. initial `?site_id` and stale-entry replacement), `tests/home-timeline.test.tsx` (8 tests incl. diagnostic action state/URL contract)

No database migration required to `head` (`0028_operator_ui_trigger_source`).

Validation evidence:
- Backend: format, lint, mypy, unit tests (434/434 passed), focused M2a integration tests (23/23 passed), complete integration suite (239/239 passed in one pytest process)
- Frontend under Node 24.6.0 (pnpm 11.16.0): frozen-lockfile install, lint (warnings only), typecheck, tests (14 files / 133 tests passed), production build
- Scheduler one-shot: passed against the isolated empty test DB
- Worker one-shot: passed against the isolated test DB
- Secret scan: passed
- Docker Compose config: valid
- git diff --check: clean

Implementation details:
- Backend endpoint `/product/sites/{site_id}/diagnostic-results` returns tenant-scoped run summary with artifacts
- Backend endpoint `/product/sites/{site_id}/diagnostic-artifacts/{artifact_id}` delivers artifacts (buffered in memory, not streaming) with server-side MIME mapping, `nosniff`, `private/no-store` headers, safe filenames
- Artifact response is capped at 20 MB before read and checked after read; oversized artifacts return 413
- Artifact kind allowlist enforced server-side; unsupported kinds return 404
- Cross-tenant/cross-site/cross-run access returns 404 (non-disclosing)
- Artifact delivery: screenshots inline; RAW_DOM/NORMALIZED_DOM/MANIFEST as attachment download only
- Security headers: `Cache-Control: private, no-store`, `X-Content-Type-Options: nosniff`, safe `Content-Disposition` filenames
- 20 MB is aligned with SECURITY.md §75; climatologie.ro full-page screenshot observed at ~4.6 MB; cap at 20 MB to allow headroom
- Frontend: Home "View diagnostic results" button enabled for all terminal states (COMPLETE, PARTIAL, SITE_ERROR, etc.)
- Diagnostic results page uses `DiagnosticStateBadge` for explicit state labels
- Timeline site filter with server-side filtering, visible site/domain attribution, explicit "All sites" mode
- No database migration required

### M3 — Document evidence and contain activity — COMPLETE (2026-09-01)

- Persist the evidence summary; record run id, classification, artifact references.
- Verify scheduler still stopped and no run/window/job materialized after the diagnostic.
- **Blocked until §17 UI/evidence reconciliation is closed** (the MEDIUM / RECORDED projection with
  non-persisted ID `77a64afd-…` versus the verified collection evidence and the authoritative
  publisher association). Do not close M3 while unverified "zero events" / "normal presentation" /
  publisher-name claims remain.

**Closed 2026-09-01 (documentation + read-only reconciliation; no code/test/DB/site change):** the
plan-level evidence summary, run id (`4fd24e2e-…`), terminal classification
(DIAGNOSTIC/OPERATOR_UI/COMPLETE/HTTP 200/attempt_count=1/Access normal) and the six persisted artifact
references are recorded below in §16/§19. Read-only checks confirmed the scheduler **stopped**
(`Exited(0)`) and **no run/window/job materialized** after the diagnostic (all collection/evidence
counts identical to the deployment baseline; zero new messages in scheduler/worker/browser-worker; no
new publisher contact). One **separate manual authenticated operator incident** (`ed528705-…`) was
created after deployment/UI verification — an operator write, not a system/derived climatologie.ro
finding; preserved unchanged and does **not** invalidate the M2a results UI or Timeline site-filter
verification (see §16). The three reconciliation
claims are closed: "zero events" is verified and correctly scoped to climatologie.ro (the sole tenant
event is evz.ro, shown only under 「All sites」 with evz.ro attribution); "normal presentation" is
verified in the deployed M2a UI (screenshots/DOM/manifest render or download with sizes + hashes
matching the stored manifest; normalized DOM = 675 nodes, not truncated); the authoritative publisher
row is **climatologie.ro** (slug `climatologie-ro`, ACTIVE). The non-persisted identifier
`77a64afd-b29e-5cb3-a6d8-f7aa1e564293` was re-checked read-only and remains absent from every
id-bearing table — recorded honestly as non-persisted / observed only in the operator's captured
Timeline / currently unreproduced; non-blocking, no fabricated event. Remaining lower-value follow-ups
are non-blocking (see §20).

### M4 — Release-readiness hand-off — NOT STARTED

- Hand the candidate evidence + Gate O evidence to the human Gate P evaluation.
- Gate P stays a separate HUMAN GATE; Limited Pilot remains NOT GRANTED by this plan.
- No scheduled cycle may begin without a separate authorization.

**EVZ allowlisting and EVZ re-diagnostic are DEFERRED** — not milestones here.

## 8. Success criteria

- exactly one `DIAGNOSTIC`/`OPERATOR_UI` run for the candidate reaches a terminal state,
  `attempt_count=1`, no retry;
- normal page access (no challenge markers) → useful browser/DOM/screenshot/artifact/event evidence
  persisted and rendered in the existing platform;
- tenant isolation preserved; no connector/secret path; no cross-tenant leakage;
- no scheduled run/window/job during/after the diagnostic; scheduler remains stopped; candidate
  remains the only contacted site.

## 9. Acceptance Criteria (plan-level)

- [x] valid candidate site's exact domain + explicit authorization on record before contact;
- [x] one run, no raw SQL, no retry, no crawl, no second site, restricted to the candidate URL;
- [x] useful DOM/screenshot/artifact/event results verified in the existing platform;
- [x] contained afterward (worker/tunnels stopped, scheduler stopped, no spillover);
- [ ] evidence documented and handed to human Gate P (M4, NOT STARTED);
- [x] EVZ allowlisting / EVZ re-diagnostic recorded as DEFERRED (not milestones);
- [x] no scheduled-cycle restart; no UA/egress/WAF change without a separate ADR + SECURITY review.

## 10. Validation / Evidence Boundary

Use the cheapest relevant ladder and stop on first relevant failure (AGENTS.md §17). No live contact
until exact domain + explicit authorization. Terminal classifications and run/artifact/event evidence
come from authoritative DB + object-storage rows, read-only, under the same no-retry/no-crawl/tenant/
containment boundary as Gate O. Cite run ids, classifications, and refs; a bare status is not
evidence.

## 11. Smallest change (documented pending candidate authorization)

If the candidate must be enqueued as a plain `DIAGNOSTIC` for an already-registered site, the 
documented additive change is a **diagnostic-for-existing-site** application command
(`CheckpointService.enqueue_operator_diagnostic` + a `run-diagnostic` CLI subcommand), analogous to
`enqueue_incident_diagnostic` but producing `DIAGNOSTIC`/`OPERATOR_UI` provenance, with unit +
integration tests (happy path, foreign tenant → 403/404, inactive site, no duplicate run, cohort
purity, cross-tenant isolation). No migration. This does **not** modify the browser worker, and is
**not** WAF-bypass work. It is implemented only if and when the candidate's authorization makes it
necessary (or the standard Add Site → immediate diagnostic path suffices, in which case no code
change is needed).

## 12. Data / Migration Impact

None unless the §11 additive command is used (still no schema/migration change). Uses existing
tenant-owned config and `DIAGNOSTIC`/`OPERATOR_UI` path (migration `0028`). Candidate evidence may be
pinned/retained per `SECURITY.md`.

## 13. Security / Privacy Impact

Same invariants as Gate O: tenant derived server-side; session+CSRF for UI writes; public URL
validated by `BrowserNetworkGuard` before persistence; never store/log credentials, cookies,
headers, OAuth tokens, or arbitrary browser options; `BROWSER_ALLOW_PRIVATE_NETWORKS=false`; no
stealth/CAPTCHA/fingerprint/proxy (ADR-020); any monitoring-identity change requires a separate ADR +
SECURITY review. No public exposure of PostgreSQL/MinIO. page = hostile; evidence = confidential;
model = untrusted; tenant isolation non-negotiable.

## 14. Observability / Failure Handling

Log only bounded identifiers and outcomes (tenant_id, site_id, checkpoint_run_id, stage, status,
error_class). Never log page content, DOM, screenshots, request/response bodies, or secrets. If the
candidate challenges, treat as a monitoring-source finding, never a site-health claim; do not retry;
record and report. If a terminal challenge occurs (such as has not been observed for a
zero-resistance candidate), escalate through the human gate rather than attempting evasion.

## 15. Containment / Rollback

- Do not delete or rewrite any evidence; keep candidate (and evz.ro) ACTIVE.
- Keep the scheduler stopped; never restart while evz.ro remains ACTIVE and could be contacted again.
- If an unauthorized scheduled cycle must be halted, stop the scheduler immediately (container
  preserved); verify no run/job/window materialized; preserve any spillover as evidence without
  deleting/cancelling/retrying.
- Stop any local transient worker/tunnels after the single diagnostic; restore the OCI browser-worker
  only upon explicit instruction.
- Never downgrade migration `0028` where `OPERATOR_UI`/`DIAGNOSTIC` rows exist.

## 16. Progress Log

### 2026-08-30 — Revised per final product decision

Superseded the earlier operator-edge/allowlisting direction. EVZ allowlisting and EVZ re-diagnostic
**DEFERRED**. EP-029 now validates the authorized **zero-resistance pilot candidate** with M0–M4.
Immutably preserved evz.ro Gate O evidence and classified it as a monitoring-source finding. No edge
runner, UA change, proxy, stealth, CAPTCHA solving, or other WAF-bypass work is proposed. No staging
change; no commit; scheduler stays stopped.

### 2026-08-31 — M3 closure halted; UI/evidence reconciliation

Operator-visible evidence superseded the draft M3 closure: while climatologie.ro is selected, the UI
shows Home **Open incidents = 0** and a Timeline/Incidents **Machine observed / MEDIUM / RECORDED /
Occurrence time not established / Observed 30/08/2026 16:58:52 / ID `77a64afd-b29e-5cb3-a6d8-f7aa1e564293`**.
M2 is recorded **collection PASS / UI presentation FAIL (NOT IMPLEMENTED)**; M2a **PLANNED / NOT
STARTED**; M3 **NOT STARTED (BLOCKED ON RECONCILIATION)**; M4 **NOT STARTED**. Unverified claims (zero
events; normal Timeline/Evidence presentation; candidate publisher identity/name; complete useful UI
projection) were removed/qualified in §5. Reconciliation findings are recorded in §17. Documentation-only;
no code/data/container/site change; scheduler remains stopped.

### 2026-09-01 — Adversarial review: NOT READY → authorized remediation applied and revalidated

An adversarial review of the implemented M2a UI returned **NOT READY**: **B1 (BLOCKER)** — broken
`/diagnostic-results` routing (the page read `useParams().site_id` which never exists on the static
route, so result/error/loading states were unreachable); **M1 (MAJOR)** — Timeline notes were not
site-filtered server-side while events were; **M2 (MAJOR)** — no Home tests for the diagnostic action
(routing contract unprotected); **M3 (MAJOR)** — `StateLabel`/`SourceStateBadge` carried dead or
conflating union members. Also MS minor findings (m5 timeline initial-query test, m6 URL-encoding
consistency).

The remediation was **explicitly authorized** (all changes left **unstaged/uncommitted**; base HEAD
`2de22ca` unchanged): fixed the routing (**Suspense + `useSearchParams().get("site_id")` + encoded
site ids + missing-id unavailable state**), added the notes site filter in the Timeline endpoint,
added Home diagnostic-action tests, trimmed the dead state members and deleted `SourceStateBadge`,
added the initial-`?site_id` and stale-entry replacement tests, and normalized URL encoding in the
timeline API call. Recorded as a deliberately out-of-scope follow-up: ORM constraint drift in
`backend/app/browser/models.py` (source checkpoints); unrelated MINOR/NOTE findings from the review
were not remediated under this authorization.

No migration was created (schema unchanged). Scheduler stays stopped; no real site contact; PR #35
unchanged and NOT applied to staging. Gate P remains a human gate and Limited Pilot remains NOT
GRANTED by this plan.

### 2026-09-01 — Bounded mypy typing remediation and final canonical validation (GREEN)

Canonical mypy (`uv --directory backend run mypy app tests scripts migrations/env.py`) exposed **nine
typing errors, all in `backend/tests/integration/test_product_diagnostic_results_m2a.py`** (M2a
integration test file). A bounded **test-file-only** typing remediation was authorized and applied:
parameterized `_login_operator` to `-> dict[str, str]`; added explicit `assert … is not None`
narrowing for the seeded `MonitoredUrl`/`Template`/`BrowserScenario` before `.id`; replaced the
direct `app.api.product.get_session_factory` read/write with the canonical
`monkeypatch.setattr(product_module, "get_session_factory", …)` typed pattern (typed
`AsyncIterator[AsyncSession]` context manager; patched where production resolves it; no `product.py`
export, no `Any`, no `type: ignore`). No production code changed; only type annotations/narrowing
changed in that test file; no tenant/security/endpoint semantics changed.

**Final canonical ladder (all steps green, zero failures):**
1. `uv --directory backend sync --all-groups --locked` — passed.
2. Playwright Chromium installed/verified (CI `--with-deps` is ubuntu-only; chromium already present).
3. `ruff format --check .` — passed (307 files).
4. `ruff check .` — passed.
5. `mypy app tests scripts migrations/env.py` — **Success, 272 source files, 0 errors**.
6. Unit suite only, exact CI/default env (`ENVIRONMENT=test`, default `DATABASE_URL`/`S3_BUCKET`, no
   `RUN_INTEGRATION`) — **434 passed**.
7. Clean migration on fresh isolated DB `publisher_intelligence_m2afinal_green` — **head
   `0028_operator_ui_trigger_source`**.
8. New isolated MinIO bucket `publisher-intelligence-m2afinal-green` — created.
9. Focused Timeline/manual-note regression (`tests/integration/test_memory_p2b.py`) — **11 passed**.
10. Focused M2a suite (`tests/integration/test_product_diagnostic_results_m2a.py`) — **23 passed**.
11. Complete integration in one pytest process (`RUN_INTEGRATION=1 uv --directory backend run pytest
    tests/integration`, isolated DB/bucket) — **239 passed, 0 failures**.
12. Scheduler one-shot (`python -m app.scheduler --once`) — exit 0, no site jobs (isolated DB).
13. Worker one-shot (`python -m app.worker --once`) — exit 0 (internal retention job, 0 rows).

Repository checks: secret scan passed; `docker compose config` valid; `git diff --check` clean;
`git status` unchanged (11 modified + 4 untracked); nothing staged.

**Rejected as acceptance evidence (not green):** all earlier combined/order-sensitive runs
(`pytest tests/unit tests/integration/test_memory_p2b.py`; `pytest -q` = 669 passed / 4 failed; any
run without the isolated DB/bucket or without `RUN_INTEGRATION=1`; the `app`-only mypy run; the unit
invocation that injected the unique integration `DATABASE_URL`, which conflicted with
`tests/unit/test_config.py`'s local-default expectation). Only the final zero-failure canonical
ladder above is acceptance evidence.

### 2026-09-01 — M2 UI-visibility findings accepted; M2a milestone authorized (documentation only)

The M2 UI-visibility findings report (authorized earlier) was accepted: **collection PASS**, **UI
presentation FAIL / NOT IMPLEMENTED**, root cause = collected evidence is not projected through an
authenticated tenant-scoped operator surface. A bounded **M2a remediation** milestone was added under
§7 (PLANNED / NOT STARTED): authenticated API-proxy retrieval of diagnostic artifacts (NOT public or
presigned object-storage URLs; MinIO stays private), Home 「View diagnostic results」 action,
baseline-results page, Timeline site filter with visible site/domain and 「All sites」 mode, explicit
state labels, and no fabricated event/incident/alert. Full accepted findings and the proposed M2a
architecture/security/tests/estimate are recorded in §17 and §19. Code/test implementation of M2a is
**not authorized in this plan** and remains a separate step. No code/data/container/site change;
scheduler remains stopped.

### 2026-09-01 — M2a implementation committed; exact-head CI executes green

Implementation committed on `agent/ep-029-publisher-compatibility` at
`cf833544ed6e9d406bc78994d8faf5d179385026` (15 files: M2a endpoints, M1 Timeline notes site-filter,
frontend M2a UI, frontend/backend M2a tests, typing remediation, documentation) and pushed. GitHub CI
at exact HEAD:

- Push run `33539907395` — **SUCCESS**: backend ✓, frontend ✓, repository-safety ✓.
- Pull-request run `33539912074` — **SUCCESS**: backend ✓, frontend ✓, repository-safety ✓.

Final accepted totals remain unchanged per the authoritative record in §20: 434 unit; 11 focused
Timeline/manual-note; 23 focused M2a; 239 complete integration in one process; 133 frontend; mypy 272
files / zero issues; production build; scheduler/worker isolated one-shots; security/repository
checks. The CI evidence above appends to that record and is not a competing evidence block.

No deployment and no staging/live UI verification was performed. The staging scheduler remains
stopped; Gate P remains **UNAUTHORIZED** by this plan and Limited Pilot remains **NOT GRANTED**. PR #35
unchanged (OPEN, DRAFT, MERGEABLE, head `cf833544…`); body refresh and Ready-for-review remain pending.

### 2026-09-01 — M2a merged, deployed to staging, and staging UI verified (M3 closure)

PR #35 (M2a) was refreshed, marked Ready, and **merged** to `origin/main` at commit
`b61494bb445836d18a7b5e0e469348bd789aa551` (normal merge; `84593fb` + PR commits ancestry verified;
all six CI checks green at `f3388e9`). The M2a build was **deployed** to the
`publisher-intelligence-staging` Oracle Cloud ARM64 host at that exact commit, bounded to the api and
frontend compose services (pre-deployment PostgreSQL dump + MinIO baseline recorded and backed up).
Post-deploy read-only reconciliation (2026-09-01) confirmed:

- Deployed checkout = `b61494bb…`, clean; DB revision `0028_operator_ui_trigger_source`; scheduler
  `Exited(0)` (zero restarts); health live + ready both 200 (db + object true).
- **No new automatic diagnostic/scheduler/worker/browser activity; no new site / run / job / event /
  artifact / collector run / scheduled window** materialized, and **no new publisher contact** occurred:
  all collection/evidence counts identical to the pre-deploy baseline (publishers 2, sites 2,
  monitored_urls 2, checkpoint_runs 4, jobs 15 all COMPLETE, events 1, artifacts 21,
  checkpoint_windows 3, collector_runs 44, operators 3; runs_active 0; queue non-terminal 0).
- **Zero new messages** in scheduler / worker / browser-worker / migrate / minio-init since deployment —
  no scheduled cycle, no live site contact.
- Authenticated operator verification reads in the api log: `diagnostic-results` 200; all **six**
  climatologie.ro artifacts delivered 200 — `MANIFEST` `9d251598-…`, `NORMALIZED_DOM` `ab6fbebd-…`,
  `RAW_DOM` `e1232708-…`, `SCREENSHOT_FULL_PAGE` `8d46d50f-…`, `SCREENSHOT_VIEWPORT` `221e3686-…`,
  `SCREENSHOT_VIEWPORT_PRECONSENT` `31d7b252-…` (matched to stored artifact rows read-only);
  `/timeline` 200 and `/timeline?site_id=…` 200. The only two 401s were the deployment prober's
  deliberately unauthenticated requests. No cookies or credentials appeared in logs.

**Operator-created manual incident (preserved unchanged, read-only):** one **separate** manual
`incidents` row `ed528705-d063-4804-990f-cba0d7eccc64` exists — site climatologie.ro
(`636ce2ac-…`), title "not sure", symptom_family OTHER, status OPEN, severity null, created at
2026-09-01T18:48:08.430026Z (`created_at` == `updated_at` — never modified since creation),
created_by actor_subject `bab3a2a2-…` = the **staging ADMIN operator** (`e2fa3bea-…`). Provenance:
manually created through an authenticated ADMIN operator action — the api log retains
`POST /investigations` 200 followed by `GET /incidents/ed528705-…` 200 (no cookies/credentials in
logs). Not created by scheduler, worker, browser-worker, diagnostic pipeline, event derivation, or
deployment; no associated new site contact; no new run/job/event/artifact/collector run/window;
scheduler stayed stopped; queue stayed drained. A read-only scan of every UUID column in the schema
found **no persisted link** from this row to any event, checkpoint run, artifact, evidence reference,
manual note, hypothesis, symptom segment, or other causal record — it is an isolated, manually inserted
row. Its presence does **not** invalidate the M2a results UI or the Timeline site-filter verification,
and it is **not** a derived climatologie.ro finding. This task preserves it unchanged (no delete /
edit / close / resolve / relabel) and makes no inference about why the operator created it.
Reconciliation is an explicit M4 follow-up (see §20). **Current authoritative count: incidents = 1,
OPEN = 1, manually created by the staging ADMIN operator.**

**Operator-confirmed staging UI evidence:** Home → 「View diagnostic results」 renders; terminal summary
DIAGNOSTIC / OPERATOR_UI / COMPLETE / HTTP 200 / attempt_count=1 / Access normal (stored access
classification `ok`, "no access anomalies in bounded signal set"); viewport, pre-consent and full-page
screenshots render inline; RAW_DOM / NORMALIZED_DOM / MANIFEST downloaded through the authenticated
private proxy with sizes + hashes matching the stored manifest; normalized DOM shows 675 nodes (not
truncated); Timeline with climatologie.ro
selected hides the evz.ro event and shows the site-empty state; 「All sites」 restores the event with
evz.ro attribution; no system-fabricated event/incident; no new diagnostic or site contact. (The
separate operator-created manual incident above is a manual ADMIN write — not a system/pipeline output
and not a derived climatologie.ro finding.)

**Useful first baseline (stored manifest `4fd24e2e-…`, read-only):** normal HTTP/browser access; 34
requests across 8 hosts; AdSense, GTM, Google Analytics, OneSignal and Google Funding Choices observed;
CMP/TCF detected (cmp id 300, tcf api + gdpr applies); consent action status NOT_REQUESTED (no action
taken); SEO canonical `https://climatologie.ro/` + `index,follow`; synthetic LCP 788 ms / TTFB ~294 ms
/ CLS ~0.00019; normalized DOM (`normalized_state.dom`): node_count 675, truncated false (normalizer
`dom-b3-v1`); resource-timing: entry_count 33, truncated false. Limitations
preserved: synthetic observation ≠ real-user truth; no consent action taken; first baseline only, not
recurring monitoring; not complete advertising/consent truth. Prebid / GPT / video: present false.

**M3 blocking items reconciled (read-only):** (1) the identifier
`77a64afd-b29e-5cb3-a6d8-f7aa1e564293` still appears in **no id-bearing table** (rechecked 2026-09-01)
— retained honestly as non-persisted / observed only in the operator's captured Timeline / currently
unreproduced; non-blocking; no fabricated event. (2) The authoritative `publishers` row for the
candidate is **climatologie.ro** (slug `climatologie-ro`, ACTIVE; site `climatologie.ro`, ACTIVE) — the
draft "publisher `staging`" value was wrong and is replaced. The M2a site filter resolves the UX/scope
concern (tenant-wide Timeline ignoring the Home site selection) by hiding the evz.ro event under the
climatologie.ro filter and showing it under 「All sites」.

Non-blocking follow-ups retained (not implemented): simplify the redundant publisher/site/domain
heading in the diagnostic-results UI; surface manifest conclusions as UI cards; ORM `trigger_source`
declaration drift vs migration `0028` (existing §20 follow-up). Staging rollback note: the pre-M2a
api/frontend images were garbage-collected after deployment; rollback to `84593fb` would be a compose
rebuild (documented, low risk, not exercised).

M2a: IMPLEMENTED / MERGED / DEPLOYED — STAGING UI VERIFIED. M3: COMPLETE (documentation + read-only;
no code/test/DB/site change; scheduler remains stopped; one operator-created manual incident preserved
unchanged — not modified by this task). M4: NOT STARTED. Gate P: HUMAN GATE / UNAUTHORIZED by this
plan. Limited Pilot: NOT GRANTED.

## 17. Decision Log

### 2026-08-30 — Validate zero-resistance pilot candidate instead of bypassing evz.ro

**Decision:** validate the authorized zero-resistance second-site candidate through the existing
pipeline under M0–M4.
**Reason:** prove useful end-to-end evidence in the platform; do not attempt to work around the
immutable evz.ro challenge (no WAF-bypass).

### 2026-08-30 — EVZ allowlisting / re-diagnostic DEFERRED

**Decision:** remove EVZ allowlisting and EVZ re-diagnostic from this plan's milestones.
**Reason:** not the current authorized step; defer rather than gate progress on it.

### 2026-08-30 — Scheduler stays stopped; evz.ro preserved ACTIVE

**Decision:** no scheduler restart; no scheduled cycle without separate authorization.
**Reason:** evz.ro remains ACTIVE and could be contacted again on restart.

### 2026-08-31 — UI/evidence reconciliation (read-only; M3 blocked)

**Trigger:** while climatologie.ro is selected the UI shows Home **Open incidents = 0** and a
Timeline/Incidents **Machine observed / MEDIUM / RECORDED / Occurrence time not established / Observed
30/08/2026 16:58:52 / ID `77a64afd-b29e-5cb3-a6d8-f7aa1e564293`**. This conflicts with the draft "zero
events" claim, so M3 is not closed.

**Findings (code + recorded authoritative DB rows, read-only):**

1. **Event provenance of the visible item.** `frontend/app/(protected)/timeline/page.tsx` calls
   `/timeline` with **no `site_id`**; `backend/app/api/memory.py` `timeline()` returns the **top 100
   tenant events across all sites** (only filters by site when `site_id` is supplied). The Home page
   (`frontend/app/(protected)/page.tsx`) scopes source-health/diagnostic to the selected site, but the
   Timeline and Incidents pages are **tenant-wide** and ignore that selection. The only event recorded in
   the tenant (`d6cd36b7-…`) is **evz.ro** `ce0f7560-41c5-5dfc-a8ff-abc0ed68427c`
   (`BROWSER_ACCESS_CHALLENGE_SUSPECTED`, family `BROWSER_MONITORING`, **MEDIUM/RECORDED**, detected
   2026-08-30 13:58:52Z). Its displayed attributes match the operator-observed item exactly: MEDIUM
   (rule `default_severity="MEDIUM"`), RECORDED (po2 `confirmation="SINGLE_STRONG_OBSERVATION"`,
   `resolution_rule="NONE_POINT_EVENT"`), "Occurrence time not established" (POINT/source-level event,
   `time_precision` != EXACT; `memory.py` never substitutes observed_at for occurred_at), Surface
   displayed "Observed … 16:58:52" = `detected_at` 13:58:52Z rendered in the local/in-browser timezone
   (UTC+3 → EEST, consistent with the Romanian `.ro` targets; `toLocaleString()`). **Conclusion: the
   visible MEDIUM/RECORDED item is the evz.ro challenge event shown on the tenant-wide Timeline, not a
   climatologie.ro event.**

2. **climatologie.ro produced NO events.** The single climatologie.ro run (`4fd24e2e-…`) is terminal
   COMPLETE/HTTP 200; its recorded observation produced **zero persisted events**. The evz.ro event is
   the sole event in the tenant. Draft "zero events" referred to climatologie.ro itself and is correct
   for that site; it is reworded to avoid implying a quiet/empty Timeline (which is false because the
   tenant-wide Timeline shows the evz.ro event).

3. **Home "Open incidents = 0" is consistent.** `product.py` `home_status()` computes
   `open_incident_count` as the count of persisted `Incident` rows with status OPEN/INVESTIGATING; the
   `incidents` table is **empty**, so 0 is correct. A MEDIUM/RECORDED **event** is not an incident
   (`event != incident`), so it is correctly not counted. No stored incident exists for either site.

4. **The displayed ID `77a64afd-b29e-5cb3-a6d8-f7aa1e564293` is NOT produced by any current code and
   is NOT in any table.** No Timeline/Incidents component renders an event or incident id as visible
   text (`event_id`/`incident_id` are used only as React keys). `/timeline` returns the raw stored event
   id `ce0f7560…`; `/incidents` returns stored incident ids from the (empty) table. The literal
   `77a64afd` appears nowhere in the repository. As a UUIDv5 it is not in
   events/domain_entities/checkpoint_runs/artifacts/event_evidence_refs/incidents. **It cannot be
   reproduced or tied to any stored entity from the repository or persisted data** — a data-linkage/
   projection inconsistency in the operator's captured observation, not a rendered value this code
   produces. It is unrelated to the climatologie.ro run id (`4fd24e2e-…`) and to the evz event id
   (`ce0f7560…`).

5. **Site filtering.** Home scopes by selected site; Timeline and Incidents do not. The perceived
   "climatologie.ro shows MEDIUM/RECORDED" is the tenant-wide Timeline surfacing the evz.ro event while
   the Home selector shows climatologie.ro — a **UX/scope** concern (the Timeline does not surface the
   currently selected site), not a climatologie.ro defect.

6. **Publisher identity/name unverified.** The Add Site dialog sends free-text `publisher_name`
   (`add-site-dialog.tsx` → `POST /product/sites` → `operator_registration` → `Publisher.name`). The
   operator submitted Publisher = **Climatologie**. The draft's "publisher `staging`" is therefore
   **unverified and likely wrong**; the persisted `publishers` row must be confirmed read-only before
   M3.

**Classification:** expected behavior — Home "Open incidents = 0" (no incidents recorded) is correct,
and a MEDIUM/RECORDED machine observation in the tenant-wide Timeline for the pre-existing evz.ro event
is correct system behavior, not a climatologie.ro failure. The **data-linkage discrepancy** is the
non-persisted ID `77a64afd-…` (no code/table yields it) and the **UX/scope** point that Timeline /
Incidents ignore the Home site selection. M3 stays blocked until these are closed, the authoritative
publisher row is verified, and the "publisher `staging`" claim is replaced with the verified name.

### 2026-09-01 — M2 UI-visibility findings accepted; M2a remediation scoped (docs only)

**Decision:** accept the M2 UI-visibility findings report and add a bounded **M2a** remediation milestone
(PLANNED / NOT STARTED, §7). Collection of the climatologie.ro initial diagnostic is **PASS**; useful UI
presentation is **FAIL / NOT IMPLEMENTED** because no authenticated tenant-scoped surface projects the
initial-diagnostic evidence. M2a delivers it via an **authenticated API proxy**
(`GET /product/sites/{site_id}/diagnostic-results`,
`GET /product/sites/{site_id}/diagnostic-artifacts/{artifact_id}`) — **not public or presigned
object-storage URLs**; MinIO stays private, with per-request tenant→site→run→artifact→kind-allowlist
verification (foreign/nonexistent → 404). Artifacts: screenshots inline; normalized DOM text/download
only; raw DOM download only; never execute/inject collected HTML or `dangerouslySetInnerHTML`; no MinIO
keys/internal hostnames; `Cache-Control: private, no-store`; explicit MIME; bounded size. Timeline gains
site filtering (selected `site_id`, visible site/domain, 「No events for this site yet」, explicit 「All
sites」). Home gains 「View diagnostic results」 and a baseline-results page (pre-consent/viewport/full-page
screenshots; SEO; CMP; performance; script inventory; network hosts). Explicit state labels:
「Scheduled monitoring not started」/「Not connected」/「Not detected」/「Unknown」. **No fabricated event,
incident or alert.**

**Acceptance journey (operator-visible):** select climatologie.ro → open diagnostic results → see the
three screenshots and all bounded summaries; climatologie.ro Timeline shows **no EVZ event**; 「All sites」
Timeline shows the EVZ event labeled **evz.ro**; Home uses the explicit state labels.

**Tests required:** authenticated happy path; foreign tenant/site/run/artifact → 404; non-OPERATOR_UI run
excluded; artifact ownership + kind allowlist; MIME/disposition/cache headers; raw DOM never rendered as
HTML; results page and screenshots; site-filtered and All-sites Timeline; no-event baseline state; no
fabricated event/incident; existing Home/Timeline/Incident regressions.

**No database migration expected.**

**Reason:** the browser collection pipeline works and persists useful evidence, but the product does not
project that evidence through an authenticated, tenant-scoped operator UI (delivery gap, not a collection
gap). Preserve as **unresolved, not defects**: the exact live `publishers` row for climatologie.ro
(name/slug/tenant_id) and the origin of the displayed identifier `77a64afd-b29e-5cb3-a6d8-f7aa1e564293`
(unexplained; not found in inspected tables or repository code). M2a code/test implementation is not
authorized by this plan and remains a separate authorization step.

### 2026-09-01 — M2a merged / deployed / staging-verified; M3 closed (documentation + read-only)

**Decision:** accept M2a as merged and deployed, record the operator-verified staging UI as M3 closure
evidence, and terminate the M3 blocking conditions established 2026-08-31.
**Reason:** PR #35 merged at `b61494bb…`; the operator confirmed the full diagnostic-results journey at
staging (screenshots inline, RAW_DOM/NORMALIZED_DOM/MANIFEST downloads with sizes/hashes matching the
stored manifest, 675-node normalized DOM not truncated, site-filtered Timeline, 「All sites」 with evz.ro
attribution, no fabricated event/incident); read-only reconciliation confirmed the scheduler stopped, no
site/run/job/event/artifact/window automatically materialized after deployment, and **one separate
manual authenticated operator incident** (`ed528705-…`) created after UI verification, preserved
unchanged (see §16). The non-persisted ID
`77a64afd-b29e-5cb3-a6d8-f7aa1e564293` remains absent from every id-bearing table — preserved honestly
as non-persisted/observed-in-operator-capture/unreproduced/non-blocking. The authoritative `publishers`
row is **climatologie.ro** (slug `climatologie-ro`, ACTIVE), replacing the draft "publisher `staging`"
value. "Zero events" is correctly scoped to climatologie.ro itself; the evz.ro event now appears only
under 「All sites」.

## 18. Known Risks

1. Candidate also challenges → terminal finding, escalate through human gate; no evasion.
2. Delayed explicit candidate authorization → M0 blocks; no premature contact.
3. New immutable evidence from the candidate → by design; stays out of scheduled cohorts (ADR-130).
4. Connectivity/network variance on the candidate → terminal SITE_ERROR/BROWSER_ERROR, documented;
   no retry.
5. Scope creep toward scheduled fleets/pilot → out of scope here.

## 19. Final Outcome / Retrospective

**M0 — Authorization and containment verification: COMPLETE**
**M1 — One permissioned initial DIAGNOSTIC: COMPLETE**
**M2 — Verify useful results in the existing platform: collection PASS / UI presentation FAIL (NOT IMPLEMENTED)**
**M2a — Baseline diagnostic-results UI (remediation): IMPLEMENTED / MERGED / DEPLOYED — STAGING UI VERIFIED (2026-09-01)**
**M3 — Document evidence and contain activity: COMPLETE (2026-09-01)**
**M4 — Release-readiness hand-off: NOT STARTED**
**Gate P: HUMAN GATE / UNAUTHORIZED by this plan**
**Limited Pilot: NOT GRANTED**

The climatologie.ro `DIAGNOSTIC`/`OPERATOR_UI` run (`4fd24e2e-…`) produced terminal COMPLETE/HTTP 200
with full browser evidence (raw/normalized DOM, pre-consent/viewport/full-page screenshots, manifest,
script/SEO/CMP/performance/network observation) — **collection PASS**. The existing platform had **no
authenticated tenant-scoped operator surface** to project initial-diagnostic artifacts (Timeline was
tenant-wide and showed the pre-existing evz.ro `BROWSER_ACCESS_CHALLENGE_SUSPECTED` event while the
Home selector showed climatologie.ro; Home "Open incidents = 0" was correct as no incidents existed at
the time of that finding) — **UI
presentation FAIL / NOT IMPLEMENTED**.

**M2a IMPLEMENTED / MERGED / DEPLOYED — STAGING UI VERIFIED**: The bounded M2a remediation (authenticated API
proxy for diagnostic artifacts, Home "View diagnostic results", baseline-results page with screenshots
inline and downloadable artifacts, Timeline site filter with visible site/domain and explicit "All
sites" mode, explicit state labels, no fabricated event/incident) has been **implemented, merged via PR
#35 (`b61494bb…`), deployed to staging, and verified by the operator in the staging UI (2026-09-01)**.
An adversarial
review returned **NOT READY** and identified one blocker and three majors; the authorized remediation
below was applied and the **final canonical ladder re-executed from scratch to zero failures**
(434 unit + 239 integration + 133 frontend tests green; mypy 272 source files, 0 errors — see §16
Progress Log, 2026-09-01 "Bounded mypy typing remediation and final canonical validation (GREEN)").
The M2a integration test file additionally carries the mypy typing remediation (test-file only).

**M3 COMPLETE (2026-09-01)**: The evidence summary (run `4fd24e2e-…`, DIAGNOSTIC/OPERATOR_UI/COMPLETE/
HTTP 200/attempt_count=1/Access normal, six persisted artifacts) is recorded in §16/§19/§20; read-only
reconciliation confirmed the scheduler still stopped (`Exited(0)`) with no run/window/job materialized
(after the deploy baseline, all collection/evidence counts identical and zero new
scheduler/worker/browser-worker messages; no new publisher contact). **Current authoritative incident
count: incidents = 1 / OPEN = 1**, manually created by the staging ADMIN operator after
deployment/UI verification — a separate operator write, not a system/derived climatologie.ro finding,
preserved unchanged (see §16).
The three blocked claims are closed and qualified: climatologie.ro produced **zero** events (the sole
tenant event is evz.ro, shown only under 「All sites」 with evz.ro attribution); evidence **renders
normally** in the deployed M2a UI (operator-verified screenshots/DOM/manifest, sizes + hashes matching
the stored manifest, 675-node normalized DOM not truncated); the authoritative publisher row is
**climatologie.ro** (slug `climatologie-ro`, ACTIVE). The non-persisted identifier
`77a64afd-b29e-5cb3-a6d8-f7aa1e564293` was rechecked read-only and remains absent from every id-bearing
table — recorded honestly as non-persisted/observed-only-in-operator-capture/unreproduced/non-blocking.
The baseline remains a single synthetic first measurement: not recurring monitoring, not a consent-aware
ad measurement, not complete advertising truth.

Implementation files, tests, validation evidence and implementation details are recorded in §7.
The single authoritative final zero-failure validation record is maintained in §20.

## 20. Next Step

The M2a UI remediation is **implemented, merged (`b61494bb…`), deployed to staging, and staging-UI
verified (2026-09-01)** via the final canonical ladder (673 backend tests: 434 unit + 239 integration,
0 failures; 133 frontend tests; full static/type/lint/build checks) and green GitHub CI on push and
pull-request (see §16 Progress Log, 2026-09-01 "M2a implementation committed; exact-head CI executes
green" and "M2a merged, deployed to staging, and staging UI verified (M3 closure)"). **M3 is COMPLETE;
M4 — Release-readiness hand-off — is the next authorized step and is NOT STARTED.** Acceptance evidence
is limited to the zero-failure canonical ladder recorded below and in §16; all earlier rejected runs are
recorded there but are not evidence.

**Accepted canonical validation record (2026-09-01 FINAL — zero failures):**

Only the final zero-failure canonical ladder is acceptance evidence. Full step-by-step record in §16
(2026-09-01 "Bounded mypy typing remediation and final canonical validation (GREEN)").

- Static: `ruff format --check .` clean (307 files); `ruff check .` clean;
  `mypy app tests scripts migrations/env.py` **Success, 272 source files, 0 errors**.
- Unit suite only (exact CI/default env; no `RUN_INTEGRATION`; default `DATABASE_URL`/`S3_BUCKET`):
  **434 passed**.
- Clean migration on fresh isolated DB `publisher_intelligence_m2afinal_green`:
  **head `0028_operator_ui_trigger_source`**; new isolated MinIO bucket
  `publisher-intelligence-m2afinal-green` created.
- Focused Timeline/manual-note regression: **11 passed**. Focused M2a suite: **23 passed**.
- Complete integration in one pytest process (`RUN_INTEGRATION=1`, isolated DB/bucket):
  **239 passed, 0 failures**.
- Scheduler one-shot: exit 0, no site jobs; Worker one-shot: exit 0 (internal retention job, 0 rows).
- Repository checks: secret scan passed; `docker compose config` valid; `git diff --check` clean;
  nothing staged; base HEAD `2de22ca` unchanged; staging scheduler stopped; PR #35 unchanged.
- Frontend (reused, untouched): Node 24.6.0 / pnpm 11.16.0; lint 0 errors / 1 pre-existing warning;
  typecheck pass; full suite 14 files / 133 tests; production build pass (`/diagnostic-results` static).

**Rejected (not acceptance evidence):** every earlier combined/order-sensitive or otherwise
noncanonical run — `pytest tests/unit tests/integration/test_memory_p2b.py`; `pytest -q` (669 passed /
4 failed); any invocation without the isolated migrated DB/bucket or without `RUN_INTEGRATION=1`;
the `app`-only mypy invocation; and the unit invocation that injected the unique integration
`DATABASE_URL` (conflicting with `tests/unit/test_config.py`'s local-default expectation). None of
these is green or acceptance evidence.

**Follow-up recorded (not remediated under this authorization):** ORM constraint drift in
`backend/app/browser/models.py` source-checkpoint constraints vs migration; unrelated MINOR/NOTE
findings from the adversarial review.

**Earlier validation attempts (historical, subsumed):** An earlier canonical current-diff run passed
237/237 integration tests in one process, and earlier pre-remediation frontend runs passed 14 files /
119 tests under Node 24.6.0 before the remediation tests were added; 669 passed / 4 failed runs and
the other rejected invocations are recorded in §16. None of these competes with the final accepted
record above. Artifact delivery details recorded then remain valid: response capped at 20 MB before
read and checked after read; not streaming; 20 MB aligned with SECURITY.md §75; climatologie.ro
full-page screenshot ~4.6 MB. Gate P and Limited Pilot remain unstarted/unauthorized; deployment and
staging UI verification are complete (M2a, 2026-09-01).

**Lifecycle state:**

Completed:
- **Final diff review** of the M2a implementation, typing remediation, and documentation updates
  (M-1 stale §19 validation record removed; §19 now references §7/§20).
- **Implementation commit and push** — commit `cf833544ed6e9d406bc78994d8faf5d179385026` pushed to
  `agent/ep-029-publisher-compatibility`.
- **Exact-head CI** — push run `33539907395` SUCCESS and pull-request run `33539912074` SUCCESS
  (backend/frontend/repository-safety passed in both); recorded in §16.
- **PR #35 body refresh + Ready + review and merge** — refreshed body, marked Ready, reviewed and
  merged via normal merge into `origin/main` at `b61494bb445836d18a7b5e0e469348bd789aa551`;
  exact-head CI at `f3388e9`: push `33541155946` SUCCESS, pull-request `33541161039` SUCCESS.
- **Deploy M2a to staging** — bounded api + frontend deploy at `b61494bb…`; pre-deployment PostgreSQL
  backup + MinIO baseline recorded; post-deploy health green.
- **Staging UI verification** of the operator-facing diagnostic-results projection — operator-confirmed
  2026-09-01 (See §16 "M2a merged, deployed to staging, and staging UI verified (M3 closure)").
- **M3 — Document evidence and contain activity** — COMPLETE (2026-09-01, documentation + read-only
  reconciliation; see §16/§17/§19).

Next:
- **M4 — Release-readiness hand-off:** Hand the candidate evidence + Gate O evidence to the human Gate P
  evaluation (NOT STARTED).
- **M4 — Reconcile the manual test incident (`ed528705-…`) before Gate P:** use a supported, auditable
  status transition if closure is authorized; never delete or rewrite it; the transition is NOT
  performed by this task.

**Operational constraints remain:**

- **The scheduler remains STOPPED.** No scheduled cycle may begin without separate authorization.
- **The manual operator-created test incident (`ed528705-…`) is preserved unchanged** — not deleted,
  edited, closed, resolved, or relabeled by this task; reconciliation is deferred to the M4/Gate P
  follow-up.
- **No further site contact** (climatologie.ro, evz.ro, or any other) is authorized by this plan.
- **No Gate P or Limited Pilot activity** is authorized by this plan; both remain separate human
  decisions.
