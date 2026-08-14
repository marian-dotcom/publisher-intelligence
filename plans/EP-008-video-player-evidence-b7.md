# EP-008 — Video / Player Evidence B7

**Status:** IN_PROGRESS
**Owner:** Codex / Engineering
**Created:** 2026-08-14
**Updated:** 2026-08-14
**Target milestone:** B7 — Video/player evidence
**MVP scope impact:** NO
**New infrastructure category:** NO

## Progress

- [x] M0 — Verify B6 integration and close the B7 contract
- [x] M1 — Add lightweight player observation schema and contracts
- [x] M2 — Implement passive generic video/player observation
- [x] M3 — Persist player state and bounded VAST/media network evidence
- [ ] M4 — Prove sticky, playback, opaque-network, absence, and tenancy behavior
- [ ] M5 — Complete documentation, final CI, and retrospective

## 1. Purpose and User Outcome

After this plan is complete, a controlled browser checkpoint can show whether a generic web video
player was observable, its bounded dimensions and visibility, whether it became sticky/fixed after
the configured scroll sequence, its observable autoplay/mute/native-controls state, whether
playback started, and whether sanitized VAST/media requests succeeded or failed.

B7 preserves lifecycle distinctions. A VAST request is not a played impression, a configured
autoplay attribute is not proof of playback, and a visible video-like network request without an
inspectable player is `NOT_OBSERVABLE`, not an invented player row or policy conclusion.

## 2. Scope

### In

- passive observation of publisher-owned native `HTMLVideoElement` instances, including elements
  inserted after navigation;
- bounded structural player identity derived from tag/nth-of-type ancestry and hashed before
  persistence, without DOM text, media URLs, query values, or arbitrary element attributes;
- final presence/visibility/dimensions plus observed sticky/fixed transitions during existing
  deterministic waits and scrolls;
- observable `autoplay`, muted/zero-volume state, native controls, narrowly detected accessible
  dismiss controls, and playback-start evidence;
- page-level sanitized VAST and media request counts plus HTTP/failure evidence from the existing
  network observer;
- per-player VAST/media attribution only when exactly one player is observable; ambiguous
  multi-player attribution remains explicitly unavailable;
- explicit `OK`, `NOT_PRESENT`, `NOT_OBSERVABLE`, and `ERROR` collector outcomes;
- canonical `video_player_observations` persistence, stable site-owned player entities, manifest
  v7, collector bundle `b7-v1`, and `video-b7-v1` provenance;
- deterministic sticky/player, VAST error, opaque-network-only, absent, tenancy, and migration
  coverage.

### Out / Non-Goals

- proprietary player APIs or vendor adapters, reverse engineering, iframe traversal, or injection
  into cross-origin frames;
- intentionally calling `play()`, changing volume/mute/controls, seeking, clicking player/ad
  controls, dismissing sticky players, or watching long content;
- raw VAST XML, request/response bodies, headers, cookies, query values, media bytes, tracking URLs,
  creative IDs, cache IDs, or user identifiers;
- quartile/completion/viewability/impression analytics, OM SDK integration, SSAI reconstruction,
  ad/content classification, revenue analytics, or every VAST error code;
- a Google/IAB/Coalition compliance certificate, policy violation, event, alert, incident, severity,
  causality, or automated remediation;
- B8 synthetic performance, connectors, a new service/database/dependency, or production rollout.

## 3. Canonical References

Preserve:

- `AGENTS.md` browser, evidence, security, minimization, validation, and planning invariants;
- `PLANS.md` milestone and living-document contract;
- `MVP.md` sections 14–16, 27, Phase B, and the constrained commercial-MVP boundary;
- `BROWSER.md` sections 38–40, manifest/collector provenance, fixture requirements,
  EVAL-BR-009, milestone B7, and optional-video regression acceptance;
- `DOMAIN.md` sections 58–62, 71–73, and failure family F-VID;
- `DATA_MODEL.md` section 40 canonical `video_player_observations` fields;
- `ARCHITECTURE.md` modular collectors, partial success, and staged rollout;
- `DECISIONS.md` ADR-009, ADR-010, ADR-014, and ADR-015;
- `SECURITY.md` hostile-page isolation, bounded execution, network/URL/body minimization, and no ad
  clicking/access-control bypass;
- `knowledge/DOMAIN_SOURCE_REGISTRY_v1.0.md` official video/VAST sources;
- completed `plans/EP-007-prebid-auction-evidence-b6.md`.

Current official anchors:

- the WHATWG HTML Standard defines `autoplay`, `muted`, and `controls` as media-element state and
  defines media lifecycle events; B7 observes those surfaces without changing them;
- IAB Tech Lab VAST 4.3 defines the ad-server-to-player response framework, but a network response
  alone does not prove render or playback;
- current Google video restrictions distinguish visibility, autoplay/audibility, controls, and
  sticky dismissibility; B7 records objective signals only and does not certify compliance.

Official references:

- https://html.spec.whatwg.org/multipage/media.html
- https://iabtechlab.com/standards/vast/
- https://iabtechlab.com/wp-content/uploads/2022/09/VAST_4.3.pdf
- https://support.google.com/publisherpolicies/answer/15208072
- https://support.google.com/admanager/answer/10437795

## 4. Current State

PR #8 is merged into `main` at `0732f8b`. B6 provides isolated Chromium scenarios, configured
consent, deterministic waits/scrolls, B3 normalization, GPT/CMP/Prebid collectors, sanitized
network request-start/response timing, PostgreSQL evidence, manifest v6, and independent collector
outcomes.

The concrete B7 gaps are:

- no passive media-element observer or generic player identity;
- no sticky/fixed transition or playback-start evidence;
- no bounded video/VAST network classifier;
- no canonical player observation table/read path;
- no sticky/VAST/opaque-player deterministic fixture;
- collector bundle and manifest remain B6/v6.

## 5. Target Behavior

For every checkpoint, B7 will:

1. install a passive init script before navigation without creating a player, invoking playback,
   or mutating publisher media state;
2. periodically discover bounded native video elements and attach read-only lifecycle listeners;
3. retain a structural path made only of bounded tag/nth-of-type segments and hash it in Python
   into a site-stable player key before persistence;
4. sample bounding boxes, viewport intersection, computed fixed/sticky positioning, native media
   attributes, and playback events throughout the existing deterministic interaction sequence;
5. classify only sanitized path/resource/status/failure metadata as VAST or media evidence;
6. assign page-level network counts to a player only when one observable player makes attribution
   unambiguous;
7. persist stable `VIDEO_PLAYER` entities and specialized observation rows atomically with the
   checkpoint, exposing manifest v7 evidence;
8. report `NOT_OBSERVABLE` when video/VAST network evidence exists without an inspectable player;
9. isolate observer/parser failure so B1–B6 evidence survives in a `PARTIAL` checkpoint.

## 6. Architecture / Data Flow

```text
Native video elements + existing deterministic scroll
                         ↓
Passive page-side state sampler and lifecycle listeners
                         ↓
Hashed structural identity + observable player state
                         ↓
Sanitized VAST/media network classifier
                         ↓
Player rows + collector result + manifest v7
```

B7 stays inside the existing browser modular monolith and reuses Playwright, Chromium,
PostgreSQL, object storage, jobs, workers, scenarios, network observations, collector runs, and
domain entities.

## 7. Files and Modules Affected

Expected additions:

```text
backend/app/browser/video.py
backend/migrations/versions/0008_video_player_evidence_b7.py
backend/tests/unit/browser/test_video.py
```

Expected modifications:

```text
backend/app/browser/contracts.py
backend/app/browser/models.py
backend/app/browser/persistence.py
backend/app/browser/runner.py
backend/app/browser/service.py
backend/app/browser/scheduling.py
backend/tests/integration/test_browser_checkpoint.py
backend/tests/integration/test_migrations.py
backend/tests/unit/browser/test_persistence.py
README.md
```

No dependency or infrastructure file should change.

## 8. Milestones and Acceptance

### M0 — Integration, standards, and contract

Goal: start from merged B6 and close the smallest canonical B7 behavior.

Implementation:

- verify PR #8 and exact `main` merge;
- inspect B7 product/browser/domain/data/security contracts;
- verify current WHATWG, IAB VAST, and Google video anchors;
- record observability and attribution boundaries.

Acceptance:

- [x] PR #8 is merged and branch starts at exact `main`;
- [x] no new dependency, infrastructure category, product scope, or security permission is needed;
- [x] generic native-player evidence is prioritized over proprietary adapters;
- [x] VAST/network evidence is not equated with playback or impression.

Validation:

```bash
git status --short --branch
git rev-parse origin/main
```

Expected result: clean `agent/implement-ep-008` based on `0732f8b` and a closed B7 contract.

### M1 — Contracts and schema

Goal: add the canonical lightweight player observation model.

Implementation:

- add the player evidence contract and BrowserEvidence collection;
- add `video_player_observations` with tenant/site/run/entity ownership, canonical nullable state,
  bounded counts/dimensions, provenance, metadata, indexes, and uniqueness;
- add migration 0008 with upgrade/downgrade coverage;
- bump newly created runs to collector bundle `b7-v1`.

Acceptance:

- [x] player identity is site-owned and contains no URL, query, DOM text, or raw attribute value;
- [x] unknown state remains null instead of false/zero;
- [x] counts and dimensions reject negative values;
- [ ] upgrade/downgrade/re-upgrade succeeds.

Validation:

```bash
UV_CACHE_DIR=/tmp/publisher-intelligence-uv-cache uv --directory backend run ruff check .
UV_CACHE_DIR=/tmp/publisher-intelligence-uv-cache uv --directory backend run mypy app tests scripts migrations/env.py
```

Expected result: schema and typed contracts import cleanly without changing B1–B6 semantics.

### M2 — Passive generic observer

Goal: observe native player state and sticky/playback transitions without interaction mutation.

Implementation:

- add a bounded init-script sampler for dynamic native video elements;
- attach read-only `play`/`playing`/time evidence listeners;
- sample structural identity, connectedness, visibility, size, computed position, autoplay, mute,
  native controls, and a narrow accessible dismiss-control signal;
- parse/reject arbitrary hostile-page values and hash structural paths in Python.

Acceptance:

- [x] observer never calls `play()`, seek, volume, mute, controls, dismiss, or player APIs;
- [x] dynamically inserted players remain observable in the deterministic browser fixture;
- [x] inline-to-fixed transition after scroll produces sticky evidence in the fixture contract;
- [x] configured autoplay and observed playback stay separate;
- [x] non-video pages preserve an explicit `NOT_PRESENT` outcome path.

Validation:

```bash
UV_CACHE_DIR=/tmp/publisher-intelligence-uv-cache uv --directory backend run pytest \
  tests/unit/browser/test_video.py
```

Expected result: safe deterministic snapshots produce bounded player observations.

### M3 — Network evidence, persistence, and manifest

Goal: combine player state with sanitized VAST/media lifecycle evidence.

Implementation:

- classify sanitized URLs by bounded path patterns/resource type/extension only;
- count VAST requests/errors and media requests without inspecting query values or bodies;
- attribute counts only for one-player checkpoints and preserve ambiguity otherwise;
- persist player entities/observations and tenant-scoped reads;
- add manifest v7 video output and `video-b7-v1` collector provenance;
- mark technical collector error as `PARTIAL` without discarding other evidence.

Acceptance:

- [x] HTTP/failure evidence is not described as parsed VAST error-code evidence;
- [x] VAST request, media request, and playback-start remain distinct;
- [x] multi-player network attribution is not duplicated or guessed;
- [x] network-only player evidence is `NOT_OBSERVABLE` with a limitation;
- [x] no response body, VAST XML, media bytes, query values, or tracking URLs persist.

Validation:

```bash
UV_CACHE_DIR=/tmp/publisher-intelligence-uv-cache uv --directory backend run pytest tests/unit
```

Expected result: manifest and database rows contain only the canonical bounded evidence.

### M4 — Deterministic validation

Goal: prove the B7 behavior and all relevant failure/tenancy boundaries.

Implementation:

- add one native player fixture that becomes fixed/sticky after scroll, exposes controls/dismiss,
  emits playback evidence, and generates successful/failed VAST plus media requests;
- add a network-only fixture representing an opaque/cross-origin player boundary;
- verify ordinary pages remain `COMPLETE` with a `NOT_PRESENT` video collector;
- verify tenant-scoped player reads and migration table inventory;
- run all backend/frontend/repository checks.

Acceptance:

- [ ] EVAL-BR-009 sticky player is observed after deterministic scroll;
- [ ] dimensions, visibility, autoplay, mute, controls, dismiss, and playback evidence persist;
- [ ] VAST/media counts and VAST HTTP failure count are explainable;
- [ ] opaque network-only evidence creates no player row;
- [ ] wrong-tenant reads return no player evidence;
- [ ] format, lint, typecheck, unit, integration, migration, build, and secret checks pass.

Validation:

```bash
UV_CACHE_DIR=/tmp/publisher-intelligence-uv-cache uv --directory backend run pytest tests/unit
RUN_INTEGRATION=1 UV_CACHE_DIR=/tmp/publisher-intelligence-uv-cache \
  uv --directory backend run pytest tests/integration
```

Expected result: controlled browser fixtures prove observable behavior and explicit limitations.

### M5 — Completion

Goal: leave B7 reviewable, reproducible, and safely reversible.

Implementation:

- update README and this plan with actual behavior/results;
- inspect page mutation, evidence minimization, identity, attribution, and diff scope;
- publish a Draft PR and obtain green GitHub Actions.

Acceptance:

- [ ] plan becomes `COMPLETE` only after local and remote validation pass;
- [ ] PR states behavior, limitations, safety, tests, and rollback;
- [ ] no unrelated change, accidental secret, or hidden blocker remains.

Validation:

```bash
git diff --check
python scripts/check_secrets.py
git status --short
```

Expected result: one focused, green Draft PR for B7.

## 9. Final Acceptance Criteria

- [ ] a native player is persisted with canonical observable state and `video-b7-v1` provenance;
- [ ] sticky/fixed and autoplay/playback distinctions are preserved;
- [ ] VAST/media lifecycle counts use sanitized metadata only;
- [ ] opaque/multiple-player limits are explicit and no attribution is fabricated;
- [ ] video absence or non-observability does not crash or fail an otherwise valid checkpoint;
- [ ] technical collector failure retains B1–B6 evidence as `PARTIAL`;
- [ ] tenant ownership, migration round trip, and all regressions pass;
- [ ] manifest v7 and bundle `b7-v1` are documented and tested.

## 10. Final Validation

```bash
UV_CACHE_DIR=/tmp/publisher-intelligence-uv-cache uv --directory backend run ruff format --check .
UV_CACHE_DIR=/tmp/publisher-intelligence-uv-cache uv --directory backend run ruff check .
UV_CACHE_DIR=/tmp/publisher-intelligence-uv-cache uv --directory backend run mypy app tests scripts migrations/env.py
UV_CACHE_DIR=/tmp/publisher-intelligence-uv-cache uv --directory backend run pytest tests/unit
RUN_INTEGRATION=1 UV_CACHE_DIR=/tmp/publisher-intelligence-uv-cache uv --directory backend run pytest tests/integration
COREPACK_HOME=/tmp/publisher-intelligence-corepack corepack pnpm@11.16.0 --dir frontend lint
COREPACK_HOME=/tmp/publisher-intelligence-corepack corepack pnpm@11.16.0 --dir frontend typecheck
COREPACK_HOME=/tmp/publisher-intelligence-corepack corepack pnpm@11.16.0 --dir frontend test
COREPACK_HOME=/tmp/publisher-intelligence-corepack corepack pnpm@11.16.0 --dir frontend build
python scripts/check_secrets.py
git diff --check
```

## 11. Test Cases

Happy path:

- dynamically inserted native player becomes visible/fixed after scroll;
- autoplay/muted/native controls/dismiss and playback event are independently recorded;
- one player receives sanitized successful/failed VAST and media counts.

Failures and explicit limitations:

- observer evaluation failure returns collector `ERROR` and checkpoint `PARTIAL`;
- VAST/media network evidence without an observable native player returns `NOT_OBSERVABLE`;
- multiple players retain player rows but page-level network attribution remains ambiguous;
- VAST request failure increments bounded HTTP/failure evidence without inventing a VAST code.

Regression and tenancy:

- ordinary non-video page returns `NOT_PRESENT` and remains `COMPLETE`;
- B1–B6 manifest content and collector behavior remain present;
- wrong-tenant player query returns no rows;
- migration clean upgrade/downgrade/re-upgrade includes only the B7 table addition.

## 12. Data / Migration Impact

Migration 0008 adds only `video_player_observations` from `DATA_MODEL.md` section 40, including:

- UUID primary key and tenant/site/checkpoint/player-entity foreign keys;
- one observation per checkpoint/player entity;
- nullable observable booleans and dimensions;
- non-negative VAST/media counts;
- collector version, timestamp, and bounded metadata;
- tenant/checkpoint read index.

No backfill is required. Old manifest v1–v6 checkpoints remain immutable and interpretable.
Downgrade removes only the B7 table and does not rewrite B1–B6 evidence.

## 13. Security / Privacy Impact

B7 adds a new bounded public-page evidence category but does not expand credentials, permissions,
tenancy, retention, or external services.

Mitigations:

- page is still hostile and runs in the existing disposable guarded context;
- collector is read-only and does not play/click/dismiss/seek or mutate media/player state;
- structural identity excludes DOM text and raw attributes, then is SHA-256 hashed;
- network input is already URL-sanitized; classification uses host/path/resource/status/failure;
- query values, request/response bodies, XML, media, headers, cookies, storage, and identifiers are
  excluded;
- counts and arrays are bounded and tenant-owned reads/writes remain server-scoped.

## 14. Observability / Failure Handling

Collector type: `VIDEO_PLAYER`  
Collector version: `video-b7-v1`

Outcomes:

- `OK`: one or more native players were safely observed;
- `NOT_PRESENT`: no player and no recognizable video/VAST network evidence;
- `NOT_OBSERVABLE`: network evidence exists but no inspectable native player exists;
- `ERROR`: page-side snapshot/evaluation failed.

`ERROR` contributes to checkpoint `PARTIAL`; absence and expected non-observability do not. The
collector summary records player/network counts, ambiguity, and limitations without exception
strings or sensitive page data.

## 15. Rollback Strategy

Revert B7 commits and downgrade migration 0008. The downgrade removes only B7 player observations.
B1–B6 checkpoint rows, artifacts, normalized observations, GPT/CMP/Prebid evidence, and historical
manifest versions remain intact. No existing evidence is compacted or rewritten.

## 16. Known Risks

- native video elements inside inaccessible cross-origin frames remain uninspectable;
- custom controls/dismiss buttons may not expose accessible labels, so unknown remains null;
- CSS/DOM player replacement can change structural identity across checkpoints;
- generic URL patterns cannot identify every VAST/media request and do not parse VAST error codes;
- one-player network attribution is page-scoped correlation, not proof that every request belongs
  to that element;
- synthetic autoplay behavior may differ from real users due browser policy and lack of gesture.

## 17. Open Decisions

None blocking. Vendor adapters, iframe-specific contracts, policy rulesets, and richer VAST parsing
remain future pilot-driven decisions outside B7.

## 18. Decision Log

- 2026-08-14 — Observe native HTML video generically before adding vendor adapters. This satisfies
  MVP B7 without coupling the collector to proprietary APIs.
- 2026-08-14 — Use bounded structural tag/nth-of-type ancestry and hash it before persistence.
  Raw media URLs, DOM text, IDs, classes, and query values are not player identity.
- 2026-08-14 — Never call `play()` or alter media/player state. Playback evidence comes only from
  publisher/browser events and readable state.
- 2026-08-14 — Use sanitized network metadata only; do not capture VAST bodies or media bytes.
- 2026-08-14 — Attribute page-level video network counts only when exactly one player is observable;
  preserve ambiguity for multiple/opaque players.
- 2026-08-14 — B7 records objective behavior, not Google/IAB policy compliance.

## 19. Discoveries / Surprises

- The existing `core_scroll_v1` profile already ends with the versioned
  `sticky_and_video` inspection marker, so B7 needs no new scenario or interaction behavior.
- B6 already preserves sanitized request-start/response/failure observations, so B7 requires no
  body capture or second network recorder.
- Native `controls=false` does not prove controls are absent because publishers may use custom
  controls; B7 reports native controls when true and otherwise leaves generic presence unknown.

## 20. Progress Log

- 2026-08-14 — PR #8 merge verified at `0732f8b`; branch `agent/implement-ep-008` created from
  `origin/main`.
- 2026-08-14 — Canonical browser/video/data/security contracts and current official standards
  reviewed; M0 complete and B7 implementation contract closed.
- 2026-08-14 — M1–M3 implemented: migration 0008, passive generic native-video observer,
  structural identity hashing, sanitized VAST/media classification, persistence, manifest v7, and
  tenant-scoped reads.
- 2026-08-14 — Local Ruff, mypy, all 59 backend unit tests, frontend lint/typecheck/test/build,
  secret scan, and diff check passed. PostgreSQL/MinIO integration and migration round trip remain
  for GitHub Actions because Docker is unavailable locally.

## 21. Validation Results

Local validation on 2026-08-14:

- `ruff format --check .` — passed (68 files);
- `ruff check .` — passed;
- `mypy app tests scripts migrations/env.py` — passed (60 source files);
- `pytest tests/unit` — passed (59 tests; one upstream Starlette deprecation warning);
- frontend lint, typecheck, Vitest, and production build — passed;
- repository secret scan and `git diff --check` — passed;
- PostgreSQL/MinIO browser integration and migration round trip — pending GitHub Actions because
  Docker is unavailable in this workspace.

## 22. Final Outcome / Retrospective

Pending implementation and validation.

## 23. Next Step

Review and commit the B7 implementation, publish a Draft PR, then use GitHub Actions to validate
the dynamic sticky-player and opaque-network fixtures plus the migration round trip.
