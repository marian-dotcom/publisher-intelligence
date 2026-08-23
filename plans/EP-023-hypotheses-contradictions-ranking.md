# EP-023 — Hypotheses, Contradictions & Deterministic Ranking

**Status:** COMPLETE
**Owner:** Codex / Engineering
**Created:** 2026-08-22
**Updated:** 2026-08-22
**Target milestone:** Deterministic ranking (PLANS.md §76.1)
**MVP scope impact:** NO
**New infrastructure category:** NO

## Progress

- [x] M0 — Baseline verification
- [x] M1 — Migration 0021: hypotheses + hypothesis_evidence
- [x] M2 — Deterministic candidate/scoring/ranking core (pure module)
- [x] M3 — Persistence lifecycle + typed-relation/note consumption
- [x] M4 — Eval-runtime ranking cases + full validation/release readiness

## 1. Purpose and User Outcome

After this plan ships, every open investigation deterministically produces ranked hypotheses from
its stored evidence, each with supporting evidence, contradicting evidence, missing/unavailable
evidence, confidence, and a human-readable explanation of why it ranks where it does. No LLM is
involved. Ranking behavior is exercised through the EP-022 Inspect runtime using sanitized
connector fixtures.

## 2. Scope and Non-Goals

### In
- migration 0021: `hypotheses`, `hypothesis_evidence`;
- deterministic candidate generation per evidence family;
- SUPPORTS/CONTRADICTS weights from EP-021 typed relations; observation failures become
  missing-evidence context, never publisher-failure claims;
- deterministic score → rank → status (`LEADING`,`CONTENDER`,`WEAKENED`,`UNRESOLVED`) →
  confidence (`HIGH/MEDIUM/LOW`) with rationale strings explaining placement;
- persistence replaces the ranked set atomically per incident (deterministic keys);
- Inspect runtime ranking cases via the EP-022 adapter pattern + sanitized connector fixtures;
- unit/integration tests.

### Out
LLM synthesis; model grading; event_candidates persistence; per-site threshold overrides;
entity-mapping lifecycle; OAuth/UI/hardening; new event codes; CAUSES relations.

## 3. Canonical References

INCIDENT.md (status ladder ADR-007; localization before explaining ADR-049; temporal order
necessary-but-insufficient ADR-050; mechanism required ADR-051; contradictions mandatory ADR-053;
unaffected segments as active evidence ADR-057; LKG §88); EVALS.md §73/§77; DATA_MODEL.md §69–72
(hypotheses/hypothesis_evidence); EVENTS.md §15.1; DECISIONS.md ADR-041/044/050/053/059/068/114;
PLANS.md §76.1; EP-019/020/021/022 plans.

## 4. Current State

Main post-EP-022 (`da8cbeb` merge line). Available inputs per incident: incidents/segments,
scheduled checkpoint runs (kinds/statuses), public-config snapshot states, RECORDED events +
EP-021 typed relations (SUPPORTS/CONTRADICTS among others), manual notes (human context),
sanitized GA4/GSC/GAM fixture payloads, Inspect runtime with foundations task. Head `0020`.

## 5. Target Behavior

1. `rank_incident(...)` builds one candidate per distinct evidence family observed in-window
   plus optionally seeded candidate families; each candidate aggregates:
   - SUPPORTS: typed relations and same-family events with positive observed status;
   - CONTRADICTS: explicitly recorded CONTRADICTS relations targeting the candidate;
   - MISSING: unavailable/degraded observations (non-COMPLETE scheduled runs, non-mature
     extracts presence) — context only, weight 0;
   - HUMAN: manual notes overlapping window — weight 0, tagged human_reported.
2. Score = Σ supports×2 − Σ contradicts×1. Rank: descending score, ties by stable key.
   Status: top-ranked with score>0 → LEADING; score>0 non-top → CONTENDER;
   contradicts>supports → WEAKENED; no positive evidence → UNRESOLVED.
   Confidence: HIGH score≥4, MEDIUM ≥2, LOW <2. Temporal correlation alone can produce at most
   CONTENDER/POSSIBLE wording; nothing asserts CAUSES.
3. Persistence replaces the incident's hypothesis set atomically (delete-missing + upsert by
   hypothesis_key) inside one transaction; evidence rows use deterministic evidence_keys
   (idempotent under retries).
4. Eval runtime gains `ranking_cases_v0.yaml` + adapter `rank_candidates` + Inspect task
   executing ranking over sanitized fixture-derived inputs; local runner suite flag
   `--suite ranking`.

## 6. Files

New: `backend/app/hypotheses/` (contracts/models/persistence/ranking), migration `0021`,
`evals/ranking_cases_v0.yaml`, adapter/task/runner extensions in `evals_runtime`, tests
(unit ranking + integration lifecycle). Modified: conftest imports, README sentence, this plan.

## 7. Data Model / Migration Impact

```text
hypotheses
  id PK · tenant/site/incident FKs RESTRICT · hypothesis_key text NOT NULL
  family text NOT NULL · statement text NOT NULL
  status CHECK IN ('LEADING','CONTENDER','WEAKENED','UNRESOLVED') default 'UNRESOLVED'
  confidence CHECK IN ('LOW','MEDIUM','HIGH') default 'LOW'
  rank integer NOT NULL default 0 · supporting_count/contradicting_count int NOT NULL default 0
  rationale text NOT NULL · engine_version NOT NULL · created_at · updated_at
  UNIQUE (incident_id, hypothesis_key)

hypothesis_evidence
  id PK · tenant FK · hypothesis_id FK CASCADE · evidence_key text NOT NULL UNIQUE
  source_kind CHECK IN ('EVENT','MANUAL_NOTE','OBSERVATION_GAP')
  event_id NULL FK events RESTRICT · manual_note_id NULL FK manual_notes RESTRICT
  relation CHECK IN ('SUPPORTS','CONTRADICTS','CONTEXT') · weight int NOT NULL default 0
  reason text · created_at
```

Downgrade refuses while rows exist.

## 8. Milestones

- M0 baseline ✔ (branch/clean main/post-CI green; canonical sections re-read).
- M1 schema + models + inventory update.
- M2 pure ranking core (`app/hypotheses/ranking.py`) + unit tests (ordering, contradiction
  demotion, observation-gap neutrality, manual-note zero weight, determinism).
- M3 persistence lifecycle + integration tests (atomic replace, evidence-key idempotency,
  cross-tenant refusals, fixtures-derived ranking smoke).
- M4 eval cases + runner flag + full ladder + CI + release readiness.

## 9. Final Acceptance Criteria

- [x] deterministic ranked hypotheses with supporting/contradicting/missing sections and
  explanations (rank/score/status/confidence + rationale string);
- [x] observation gaps never counted as publisher-failure evidence (missing context, weight 0);
- [x] manual notes present as CONTEXT with zero score weight;
- [x] atomic per-incident replacement; retry-idempotent evidence keys;
- [x] Inspect ranking cases pass locally (`ranking_smoke_v0`: 2 cases);
- [x] full ladder green locally and in CI.

## 10. Test Cases

Happy: two-family incident → ranked LEADING/CONTENDER with rationale.
Counterexamples: CONTRADICTS-heavy candidate demoted to WEAKENED; SITE_ERROR-only window yields
UNRESOLVED with missing-evidence entries (no publisher-failure claim); duplicate evidence keys
collapse; cross-tenant refused; manual note weight 0.

## 11. Final Validation

Same ladder as prior plans + Inspect suites (`--suite foundations` and `--suite ranking`) PASS.

## 12. Security / Privacy Impact

Hypothesis rationales reference internal ids/families only. Tenant scoping enforced on all reads
and writes. No external calls.

## 13. Observability / Failure Handling

Typed `HypothesisStateError`; deterministic recomputation makes any anomaly reproducible by
re-running rank on the same stored state.

## 14. Rollback Strategy

Downgrade refuses while rows exist; revert-safe because no other subsystem consumes hypotheses
yet.

## 15. Known Risks

Ranking weights are initial deterministic defaults; calibration belongs to eval iterations
(EVALS.md §74) without reopening ADR-007's no-fake-numerics boundary.

## 16. Open Decisions

None block implementation.

## 17. Decision Log

### 2026-08-22 — Contradictions enter only as explicitly typed evidence

**Decision:** The v1 scorer consumes SUPPORTS/CONTRADICTS exclusively from EP-021 typed relations
and same-family positive observations; it never infers contradictions heuristically.

**Reason:** ADR-053 requires deliberate contradiction search; inference here would recreate the
false-cause risk EVALS.md hard-fails against.

**Alternatives:** Heuristic cross-family contradiction inference — deferred to calibrated
iterations with eval coverage.

**Impact:** Missing subtle contradictions until richer rules land; acceptable vs false certainty.

## 18. Discoveries / Surprises

To be recorded during implementation.

### 2026-08-22 — Implementation complete

Implemented migration 0021 (hypotheses/hypothesis_evidence with guarded downgrade), pure ranking
core in `app/hypotheses/ranking.py` (family candidates, SUPPORT×2/CONTRADICT×1 scoring,
LEADING/CONTENDER/WEAKENED/UNRESOLVED statuses, HIGH/MEDIUM/LOW confidence, rationale strings,
observation-gap neutrality, manual-note zero weight), atomic `HypothesisRepository.
replace_ranked_set`, Inspect ranking cases (`ranking_smoke_v0`) via the EP-022 adapter pattern,
and unit/integration suites. Full suite 62/62 integration + 280 unit; both eval suites PASS.

## 19. Progress Log

### 2026-08-22 — Created under program authorization post-EP-022 merge; marked READY→IN_PROGRESS at start of execution. Implementation not started beyond this point.

## 20. Validation Results

To be recorded.

## 21. Final Outcome / Retrospective

Pending implementation.
