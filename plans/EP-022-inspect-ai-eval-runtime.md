# EP-022 — Inspect AI Eval Runtime Integration

**Status:** COMPLETE
**Owner:** Codex / Engineering
**Created:** 2026-08-22
**Updated:** 2026-08-22
**Target milestone:** Inspect AI eval runtime (PLANS.md §76.1, ADR-129)
**MVP scope impact:** NO — ADR-129 accepted
**New infrastructure category:** NO (replaceable eval runtime per ADR-129)

## Progress

- [x] M0 — Baseline verification and dependency pinning
- [x] M1 — Adapter boundary and foundations system-under-evaluation
- [x] M2 — Inspect task, deterministic scorers, foundations case set
- [x] M3 — Local runner, CI smoke integration
- [x] M4 — Full validation and release readiness

## 1. Purpose and User Outcome

After this plan ships, evaluation execution runs on Inspect AI behind a replaceable adapter:
deterministic scorers exercise the EP-019–EP-021 investigation foundations (localization anchoring,
LKG eligibility/freeze semantics, budget enforcement, fingerprint comparability) as a real system
under evaluation. Per ADR-129: **"Inspect is the eval engine. EVALS.md remains the contract."**
Corpus, gold, rubric, hard-fail, mandatory-set, holdout, threshold and release authority remain in
Publisher Intelligence; no release-gate semantics are encoded in Inspect configuration.

## 2. Scope and Non-Goals

### In

- pinned `inspect-ai` dependency (exact version locked by uv);
- `backend/evals_runtime/` package OUTSIDE `app/`: adapter + Inspect task + deterministic scorers;
  Incident Engine / app code MUST NOT import inspect (boundary enforced by test);
- foundations SUT: pure deterministic decision functions extracted over plain dicts (localization
  anchor pick, LKG eligibility, budget within-limit, fingerprint comparability) so evaluation needs
  no database or network;
- `evals/foundations_cases_v0.yaml`: small explicitly-non-release smoke case set for the
  foundations SUT (clearly marked: NOT part of the 76-case corpus or release gate);
- local runner (`python -m evals_runtime`) executing the Inspect task and reporting pass/fail;
- unit tests: adapter determinism, boundary (no inspect import under app/), scorer behavior.

### Out / Non-Goals

- hypothesis lifecycle/ranking evaluation (EP-023 will extend cases);
- LLM/model-graded scoring or any model API usage;
- release gate wiring to EVALS.md §73 thresholds (the full RCA engine does not exist yet; gate
  stays defined by EVALS.md and activates with EP-023+);
- modifying EVALS.md canonical semantics, the 76-case corpus, gold answers or rubric;
- CI workflow file changes beyond adding the smoke command to an existing job if trivially safe —
  otherwise documented as follow-up;
- UI, dashboards, OAuth, retention, WAF handling.

## 3. Canonical References

- `DECISIONS.md` ADR-129 (Inspect replaceable runtime; adapter boundary);
- `EVALS.md` §0.1 legend context, §73 release gate, §77 runtime boundary;
- `AGENTS.md` §2.1 implementation authorization, §21 dependency rule;
- `INCIDENT.md` §88 (LKG), ADR-060/061; EP-018/EP-019/EP-020/EP-021 plans.

## 4. Current State

Main after EP-021 merge (`135e950`). Foundations SUT logic exists inside repository/service modules
but is entangled with persistence. No inspect dependency. No eval runtime. Fixture inventory +
sanitized connector payloads available via `app/evidence/fixtures.py` (kept app-side because they
are also used by integration suites; the eval adapter may import them — direction is
eval_runtime→app, never app→inspect).

## 5. Target Behavior

```text
python -m evals_runtime --cases evals/foundations_cases_v0.yaml
  → loads YAML cases (repository-owned gold)
  → adapter maps each case to FoundationsEngine calls (pure dicts)
  → Inspect executes samples with a custom solver (no model) and our scorer
  → report printed; exit code 0 iff all foundation assertions pass
```

Boundary guarantees:

- `grep -r "inspect_ai" backend/app/` returns nothing (tested);
- replacing Inspect requires rewriting only `backend/evals_runtime/tasks.py` and its runner entry.

## 6. Files

To create: `backend/evals_runtime/__init__.py`, `adapter.py`, `solver.py`, `task.py`,
`scorers.py`, `__main__.py`; `evals/foundations_cases_v0.yaml`;
`backend/tests/unit/test_evals_adapter.py`, `backend/tests/unit/test_evals_boundary.py`.
Modified: `backend/pyproject.toml` (+inspect-ai pin), `uv.lock`, README sentence,
plans/EP-022 (this file).

## 7. Milestones

- M0 ✔ branch/pin verified.
- M1 adapter: pure functions `pick_localization_anchor(runs, onset)`,
  `lkg_eligible(run_dict, fingerprints)`, `within_budget(used, kind)` delegating to existing app
  logic where practical (budget/comparability imported from app; localization pick reimplemented
  as extracted pure function moved INTO app so app and adapter share one implementation).
- M2 task/scorer/case-set.
- M3 runner + smoke proof locally.
- M4 full ladder + CI green; plan COMPLETE.

## 8. Acceptance Criteria

- [x] `inspect-ai` pinned (`>=0.3.260`, locked 0.3.260);
- [x] adapter contains zero inspect imports; app/ contains zero inspect imports (boundary test
      greps app/ tree);
- [x] smoke run over foundations cases passes locally and reports structured results;
- [x] scorer proven non-vacuous: wrong-gold scratch check failed as required;
- [x] no changes outside evals_runtime/, pyproject/lockfile, evals/ new file, README, this plan.

## 9. Test Cases

Adapter determinism; boundary grep test; scorer exact-match + failure detection; runner exit codes
(pass/fail paths exercised during development).

## 10. Final Validation

Full ladder (ruff format/check incl. new package, mypy, unit suite, integration suite, migration
cycle, smoke, frontend, secret scan, compose config, whitespace) + GitHub Actions CI green.

## 11. Security / Privacy Impact

No network/model access; fixtures are sanitized. inspect-ai is a build/test-time-only import path
(never imported by app runtime). No secrets handled.

## 12. Rollback Strategy

Remove dependency + package; nothing else depends on it.

## 13. Known Risks

inspect-ai API churn → mitigated by adapter + pinned version; smoke subset is small by design.

## 14. Open Decisions

None block implementation. Release-gate thresholds remain governed by EVALS.md (human domain).

## 15. Decision Log

### 2026-08-22 — Runtime lives outside app/

**Decision:** Place adapter/task/runner in top-level `backend/evals_runtime/` package, not
`app/`.

**Reason:** Makes the boundary mechanically enforceable: app code cannot accidentally import
runtime internals, and runtime can be deleted/replaced without touching app packaging.

**Alternatives:** `app/evals/` — rejected: weakens the replaceability guarantee.

**Impact:** One extra package path; documented in README.

## 16. Discoveries / Surprises

To be recorded during implementation.

## 17. Progress Log

### 2026-08-22 — M0 complete

Branch created from main post-EP-021 merge (green CI). `inspect-ai` added and locked via uv;
version recorded in Validation Results after first successful smoke run. Plan IN_PROGRESS.

## 18. Final Outcome / Retrospective

Pending implementation.
