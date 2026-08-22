# EVALS.md
## Evaluation Specification for Publisher Incident Intelligence
### v1.0 — Codex / Incident Engine Quality Contract

**Audience:** Codex, engineering, product, domain reviewers  
**Status:** MVP evaluation contract  
**Depends on:** `DOMAIN.md`, `INCIDENTS.md`, `BROWSER.md`, `DATA_MODEL.md`, `EVENTS.md`, `CONNECTORS.md`, `INCIDENT.md`  
**Machine-readable seed:** `incident_evals_v0.1.yaml`  
**Rubric:** `eval_rubric_v0.1.yaml`  
**Coverage export:** `eval_coverage_v0.1.csv`

---

# 0. Purpose

The platform must not be judged by whether it can produce a convincing explanation.

It must be judged by whether it can:

1. identify the correct symptom and scope;
2. retrieve the right evidence;
3. rank plausible mechanisms;
4. use timing correctly;
5. search for evidence against its own leading explanation;
6. reject superficially plausible wrong causes;
7. preserve observability limits;
8. recommend a discriminating low-risk next test;
9. say **UNRESOLVED** when the evidence does not justify a cause.

This file defines how we test those capabilities before trusting the Incident Engine with real publisher decisions.

---

# 1. Why evals are part of the product architecture

Incident intelligence is a reasoning product.

A normal software unit test can verify:

```text
did parser return field X?
```

but not fully verify:

```text
did the system understand that a decline predates the suspected integration and therefore should reduce its causal confidence?
```

For this reason, evals are not an afterthought.

They are the regression suite for the product's intelligence.

Every material reasoning rule added to `DOMAIN.md` or `INCIDENT.md` should eventually have an eval.

---

# 2. Current v0.1 seed

The initial machine-readable set contains:

**Total evals: 76**

By outcome:

- **CONFIRMED:** 44
- **CONTEXT_ONLY:** 1
- **PROBABLE:** 15
- **UNRESOLVED:** 16

By eval type:

- **counterexample:** 4
- **counterfactual_test_quality:** 1
- **diagnostic_ranking:** 50
- **epistemic_restraint:** 12
- **external_context:** 2
- **external_or_context_discipline:** 1
- **measurement_integrity:** 6

By difficulty:

- **hard:** 23
- **medium:** 53

The public cases come from the curated `INCIDENTS v0.5` corpus and preserve source tier/evidence score. Two additional cases are explicitly marked `internal_user_report` and are used only as counterexample/test-design evals, not public confirmed ground truth.

---

# 3. Corpus coverage is not prevalence

This rule is mandatory.

Our public incident corpus is structurally biased:

- Google publishes rich status histories;
- Prebid is open source;
- proprietary SSP/server-side problems are less visible;
- private publisher configuration failures are rarely public;
- many Search/Discover cases remain unresolved.

Therefore:

> **Number of incidents in a category cannot be used as probability that the category caused a new incident.**

Evals use the corpus as:
- mechanism examples;
- counterexamples;
- epistemic-restraint tests;
- evidence-chain cases.

Not as epidemiology.

---

# 4. Evaluation layers

## Layer A — Collector correctness

Covered primarily in `BROWSER.md` and `CONNECTORS.md`.

Questions:
- was the observation collected correctly?
- did we preserve freshness?
- did we distinguish missing from zero?

## Layer B — Event correctness

Covered primarily in `EVENTS.md`.

Questions:
- should this raw change become an event?
- is scope correct?
- should it alert?

## Layer C — Retrieval

Can the Incident Engine retrieve the relevant:
- DOMAIN failure modes;
- events;
- source metrics;
- similar incidents?

## Layer D — Reasoning

Can it rank and explain plausible causes?

## Layer E — Epistemic discipline

Can it:
- reject false causes;
- preserve uncertainty;
- say UNRESOLVED?

## Layer F — Action quality

Can it recommend the next test with high information gain and low risk?

## Layer G — Explanation/provenance

Can a human trace every material conclusion to evidence?

---

# 5. The most important eval is not “find the answer”

A weak eval suite contains only cases where:

```text
symptom + obvious error → known root cause
```

That rewards overconfidence.

Our suite must include at least four categories:

```text
POSITIVE RCA
COUNTEREXAMPLE
UNRESOLVED
CONTEXT-ONLY
```

A mature engine must perform well on all four.

---

# 6. Positive RCA evals

These test whether the system can identify a real mechanism.

Examples in the seed include:
- consent/TCF eligibility;
- Prebid timeout/race/currency/floor problems;
- VAST/render failures;
- GAM platform/reporting incidents;
- migration/robots/indexing problems;
- browser/layout failures;
- external infrastructure outages.

Expected behavior:

```text
retrieve mechanism
→ connect intermediate evidence
→ rank correctly
→ preserve source/segment/timing
```

---

# 7. Counterexample evals

These are strategically more important than ordinary positive cases.

They test whether the engine can say:

> **That explanation looks plausible, but the evidence argues against it.**

Core patterns:

### Predates candidate

```text
decline starts
→ suspected integration introduced later
```

The integration cannot explain onset.

### Persists after removal

```text
component removed
→ symptom continues
```

Primary-cause confidence must fall when recovery latency permits.

### Cross-publisher contradiction

```text
publisher A SSP ↓
publisher B same SSP ↑
```

Weakens a generic SSP-wide outage claim.

### External event wrong timing

```text
traffic decline
→ Google update starts later
```

The update cannot explain onset.

### Broad shutdown

Changing many variables simultaneously may create cost while reducing attribution quality.

---

# 8. UNRESOLVED evals

We intentionally include incomplete cases.

Success means:

```text
UNRESOLVED
```

when evidence is insufficient.

The engine should still return:
- what is known;
- what was ruled out;
- plausible remaining families;
- observability gap;
- best next test.

A system that always chooses a root cause fails this layer.

---

# 9. Context-only evals

Official platform events are useful timeline anchors.

But:

```text
Google/GAM/CDN incident exists
```

is not the same as:

```text
that incident caused this publisher's symptom
```

Context-only evals test this boundary.

---

# 10. Machine-readable case format

Each case in `incident_evals_v0.1.yaml` has:

```yaml
id:
source_incident_id:
eval_type:
family:
difficulty:

provenance:
  type:
  source_tier:
  evidence_score:
  source_name:
  source_url:

visible_case:
  ...

task:
  instruction:
  max_user_facing_hypotheses:

gold:
  expected_outcome:
  accepted_failure_modes:
  root_cause:
  resolution:
  recovery:
  lesson:

grading:
  must_do:
  must_not_do:
```

---

# 11. Gold leakage rule

The evaluation harness MUST pass only:

```text
visible_case
task
```

to the system under test.

It MUST NOT pass:
- `gold`;
- expected root cause;
- lesson;
- resolution;
- recovery;
- hidden grading instructions that reveal the answer.

This is non-negotiable.

---

# 12. Why source titles are hidden

Many incident titles explicitly reveal the diagnosis.

Therefore corpus `title`, `root_cause`, `resolution`, `recovery` and `lesson` are not automatically placed in `visible_case`.

The eval input should resemble what an investigator knew before closure, not a postmortem containing the answer.

---

# 13. Staged evals

Future versions should derive multiple stages from the same incident:

## Stage 1 — initial triage
Only symptom.

Expected:
correct first data requests and controls.

## Stage 2 — partial evidence
Metrics/browser state.

Expected:
candidate ranking.

## Stage 3 — contradiction
Rollback/control evidence appears.

Expected:
re-ranking.

## Stage 4 — closure
Known recovery/resolution.

Expected:
appropriate confidence.

v0.1 mainly contains one seed case per selected incident.

---

# 14. Retrieval eval

Input:
incident symptom + scope.

Expected:
retrieve relevant DOMAIN families/patterns.

Example:

```text
traffic stable
GAM requests down
```

Expected retrieval:
- GPT request generation;
- CMP/TCF;
- JS;
- slot/lazy/refresh.

Not:
broad demand as first hypothesis.

Metric:
Recall@K of accepted failure modes.

---

# 15. Event retrieval eval

Given incident window/scope:

Expected:
retrieve the few relevant timeline events.

Measure:
- relevant-event recall;
- irrelevant-event precision;
- temporal-window correctness;
- scope correctness.

The system should not send every event from the month into reasoning.

---

# 16. Evidence retrieval eval

Measure whether the evidence pack contains:
- symptom metric;
- control segment;
- Last Known Good;
- relevant event;
- external context;
- contradiction if available.

An otherwise capable model cannot reason well from a bad evidence pack.

---

# 17. Localization eval

Expected:
affected scope is no broader than evidence.

Hard-fail examples:

```text
one mobile URL affected
→ site-wide incident
```

or:

```text
Discover only
→ all Google traffic
```

---

# 18. Temporal reasoning eval

Tests:
- onset-before-candidate;
- uncertain 6-hour browser window;
- source reporting lag;
- recovery latency;
- external event start vs announcement.

The system must not manufacture exact timestamps.

---

# 19. Mechanism eval

Top hypothesis must include:

```text
candidate
→ mechanism
→ expected intermediate effect
→ observed symptom
```

Scoring asks:
- is the mechanism in DOMAIN/current knowledge?
- does it fit the observed stage?
- does it predict the supplied evidence?

---

# 20. Intermediate-signal eval

Example:

```text
CMP issue
→ TCF error
→ GAM request loss
→ impression loss
```

is stronger than:

```text
CMP changed
→ revenue fell
```

Eval should reward use of intermediate stages.

---

# 21. Contradiction eval

For every top hypothesis, expected output must consider at least one falsification test.

Possible contradictions:
- predates candidate;
- wrong segment;
- control also affected;
- expected signal missing;
- persists after removal;
- magnitude mismatch.

Contradiction handling receives its own rubric score.

---

# 22. Negative-control eval

Create cases where:
- harmless script change;
- normal CMP version update;
- routine ads.txt change;
- one noisy JS error;

coincides with a symptom.

Expected:
do not promote harmless coincidence to top cause without mechanism evidence.

---

# 23. Measurement-integrity eval

Cases:
- GA4 decline while independent source is stable;
- GAM reporting error while serving is unaffected;
- synthetic vs field performance mismatch.

Expected:
separate measurement symptom from business/runtime symptom.

---

# 24. External-context eval

Cases:
- Google Search update;
- GAM status incident;
- CDN outage.

Expected:
check:
- product;
- timing;
- geography/scope;
- local symptom.

Do not auto-attribute.

---

# 25. Multi-causal eval

Some incidents should contain several contributors.

Expected:
do not force one explanation.

Example:

```text
pageviews ↓
requests/view ↓
eCPM ↓
```

Potentially several contributors to programmatic revenue.

Score:
- decomposition;
- no double counting;
- primary vs secondary factors.

---

# 26. Causal-chain eval

The engine must distinguish:

```text
root cause
→ intermediate event
→ downstream metric
```

from multiple independent causes.

This protects against requests ↓, impressions ↓ and revenue ↓ being counted as three separate confirmations.

---

# 27. Observability eval

Hidden mechanism case:

Prebid Server / SSP server-side.

Expected:
- use what browser/API exposes;
- mark internal bidder detail NOT_OBSERVABLE;
- lower confidence if discrimination requires hidden data.

Hard fail:
inventing hidden bidder behavior.

---

# 28. Counterfactual-test eval

Expected test should maximize information gain while minimizing risk, blast radius, cost and irreversibility.

A good answer also states:

> If H is true, expect X. If H is false, expect Y.

---

# 29. Explanation eval

Expected structure:

```text
Observed
Mechanism
Supporting evidence
Contradicting evidence
Unknowns
Next test
```

Do not reward verbosity by itself.

---

# 30. Provenance eval

Every material claim must map to supplied evidence.

Automated checks should validate:
- referenced evidence ID exists;
- source type is correct;
- no invented metric;
- no invented timestamp;
- no invented external event.

---

# 31. Rubric

`eval_rubric_v0.1.yaml` scores 24 points:

- symptom verification — 2;
- localization — 2;
- temporal reasoning — 3;
- mechanism fit — 3;
- evidence grounding — 3;
- contradiction search — 3;
- epistemic restraint — 3;
- external-context discipline — 1;
- next-test quality — 2;
- explanation quality — 2.

Pass:
**18/24**.

Strong pass:
**21/24**.

Core dimensions also have minimum scores so fluent but ungrounded answers cannot pass.

---

# 32. Hard fails

Regardless of total score, fail if the system:

- invents a material fact;
- claims hidden internals as observed;
- attributes an external event without local evidence;
- ignores explicit onset-before-candidate evidence;
- converts missing/stale data to zero;
- exposes fake numeric causal probability;
- broadens scope unsupported;
- uses corpus frequency as prevalence;
- recommends a destructive broad test when a narrower diagnostic exists.

These are product-safety failures, not style issues.

---

# 33. Deterministic graders

Use deterministic checks wherever possible.

Examples:

```text
expected confidence/outcome label
required/forbidden failure mode in top K
evidence ID exists
no unsupported site-wide scope
no numeric causal probability
external event remains context
```

Prefer deterministic graders for objective constraints.

---

# 34. Model graders

Use model graders only for genuinely semantic questions:

- mechanism quality;
- contradiction interpretation;
- next-test information gain;
- clarity of causal chain.

A model grader has its own error rate.

It must be validated against human judgment before being trusted at scale.

---

# 35. Human evaluation

v0.1 requires human audit of:
- all hard fails;
- all grader disagreements;
- random sample of passes;
- every new failure mode;
- unresolved/field-case gold that materially affects ranking.

Do not treat model-as-judge as ground truth.

---

# 36. Baselines we should compare

At least three systems:

## RULE-ONLY
No LLM synthesis.

## LLM-ONLY
Same evidence, without our deterministic reasoning constraints.

## HYBRID
Our intended system:
deterministic evidence + DOMAIN + ranking + LLM explanation.

The hybrid should especially outperform LLM-only on:
- contradiction;
- epistemic restraint;
- provenance.

---

# 37. Holdout strategy

Do not evaluate only on cases used to design the rules.

Split by:
- source incident;
- mechanism;
- family;
- date/source.

Avoid putting near-duplicate cases from the same Prebid issue pattern on both development and holdout sides.

---

# 38. Public-case memorization risk

A public incident may already be known to the underlying model.

Therefore success cannot be based only on naming the historical root cause.

Score:
- reasoning from visible evidence;
- timing;
- contradiction;
- confidence;
- observability;
- next test.

Future best evals will come from private pilot incidents and controlled synthetic fixtures.

---

# 39. Metamorphic evals

One of the strongest reasoning tests is to change one fact while leaving the rest similar.

## Time flip
candidate before onset vs after onset.

## Segment flip
same segment vs wrong segment.

## Control flip
control healthy vs equally affected.

## Recovery flip
rollback recovers vs no effect.

## Source-quality flip
mature vs stale/incomplete.

## External-event flip
matching product/timing vs wrong product/timing.

The answer should change predictably.

---

# 40. Ablation eval

Remove critical evidence.

Example:

With GAM request data:
TCF → request-loss chain is visible.

Without GAM:
confidence should fall.

If confidence remains identical despite losing the discriminating signal, the engine is overconfident.

---

# 41. Source contradiction eval

Supply two sources that disagree.

Expected:
- recognize disagreement;
- inspect semantics/freshness;
- avoid arbitrarily choosing the preferred dashboard.

Examples:
GA4 vs GSC;
GAM reporting surfaces;
synthetic vs field CWV.

---

# 42. Timing uncertainty eval

Browser:

```text
12:00 healthy
18:00 broken
```

Expected:
change occurred between 12:00–18:00.

If metric degradation begins at 15:00:
timing is compatible.

Do not state the browser change definitely happened before 15:00.

---

# 43. Search discipline

Penalize:
- “Google penalized site” without evidence;
- Core Update attribution from overlap alone;
- treating Discover volatility as deterministic;
- ignoring impressions/CTR/position decomposition;
- ignoring local technical causes.

---

# 44. GAM discipline

Penalize:
- starting from total revenue only;
- blaming demand when requests already fell;
- ignoring direct displacement;
- confusing report failure with serving failure;
- using fill without denominator context.

---

# 45. CMP discipline

Penalize:
- version change = failure;
- assuming all geographies/users from one scenario;
- skipping Accept/Reject control;
- claiming consent caused revenue without request/delivery chain.

---

# 46. Prebid discipline

Penalize:
- timeout event = bidder failed;
- server-side bidder details invented;
- floor/currency behavior ignored;
- bids exist but GAM targeting stage not checked.

---

# 47. Video discipline

Penalize:
- VAST response = successful playback;
- bid = impression;
- player present = video healthy;
- policy risk = confirmed policy violation.

---

# 48. Performance discipline

Penalize:
- synthetic = field;
- one synthetic run = persistent regression;
- worse CWV = Search penalty;
- correlation with ad change = revenue causality.

---

# 49. Current family coverage

- **analytics_measurement:** 4
- **browser_performance:** 6
- **consent_cmp:** 10
- **external_infrastructure:** 5
- **gam_adserving:** 7
- **policy_compliance:** 5
- **prebid_header_bidding:** 12
- **programmatic_market:** 4
- **reporting_discrepancy:** 2
- **search_discover:** 11
- **traffic_programmatic_isolation:** 1
- **traffic_vendor_attribution:** 1
- **video:** 8

Counts indicate test-set representation only, not expected production frequency.

---

# 50. Coverage gap policy

After v0.1:

Do not simply add more easy public cases.

Use:

```text
DOMAIN failure mode
→ positive eval?
→ counterexample?
→ unresolved?
→ source diversity?
→ intervention evidence?
```

Prioritize weak cells.

---

# 51. Highest-priority future gaps

- proprietary SSP/server-side RCA;
- publisher-specific GAM configuration with verified recovery;
- commercial/direct-delivery context;
- CMP incidents with full browser → GAM → business chain;
- closed-source video/player failures;
- GA4/GTM verified measurement recovery;
- real publisher rollback experiments;
- strong Search technical before/after cases.

Pilot incidents become more valuable than padding Google status events.

---

# 52. Eval versioning

Every dataset version is immutable:

```text
incident_evals_v0.1.yaml
incident_evals_v0.2.yaml
```

Do not silently edit v0.1 after benchmark results exist.

Corrections go into a new version with changelog.

---

# 53. Grader versioning

Store:
- deterministic grader version;
- model-grader model/version;
- rubric version;
- prompt version;
- harness configuration.

A benchmark score without harness provenance is incomplete.

---

# 54. System-under-test provenance

Every run should record:

```text
commit_sha
DOMAIN version
INCIDENTS version
EVENTS version
INCIDENT engine version
model
reasoning setting
tools enabled
retry budget
token budget
wall-clock
```

The system/harness being tested is part of the evaluation result.

---

# 55. Retry/budget policy

Do not give one system unlimited retries and another one attempt.

Define:
- attempts;
- tool-call budget;
- maximum drill-down queries;
- timeout.

Eval should resemble intended production behavior.

---

# 56. Eval run record

Preserve:

```yaml
eval_id:
system_version:
raw_output:
structured_output:
tool_calls:
retrieved_evidence_ids:
score:
dimension_scores:
hard_fail:
grader_details:
human_review:
latency:
cost:
```

This allows regression debugging.

---

# 57. Regression policy

A new build should not ship Incident Engine changes if:

- hard-fail rate increases;
- epistemic restraint decreases materially;
- contradiction score regresses;
- critical release-gating evals fail.

Overall average can hide dangerous regressions.

---

# 58. Slice reporting

Always report by:
- family;
- eval type;
- outcome;
- source tier;
- difficulty;
- positive vs unresolved/counterexample.

A model can look excellent overall while failing the exact cases where it should refuse certainty.

---

# 59. Product eval metrics

Track:

```text
Top-1 accepted mechanism accuracy
Top-3 accepted mechanism recall
False-cause rate
UNRESOLVED precision
UNRESOLVED recall
Contradiction-use rate
Unsupported-claim rate
Evidence-reference validity
Scope-overreach rate
External-misattribution rate
Next-test quality
Hard-fail rate
```

---

# 60. False-cause rate

Definition:

> Fraction of cases where the engine asserts PROBABLE/CONFIRMED causality not supported by gold/rubric.

This is one of the most dangerous metrics.

Initially, a slightly higher UNRESOLVED rate is preferable to a high false-cause rate.

---

# 61. UNRESOLVED quality

Do not optimize by saying UNRESOLVED everywhere.

Measure:

## Precision
When it says UNRESOLVED, was evidence actually insufficient?

## Recall
When gold is unresolved, did it avoid forcing a cause?

We need both.

---

# 62. Confidence calibration

Later compare qualitative labels with empirical correctness.

Expectation:

```text
CONFIRMED > PROBABLE > POSSIBLE
```

in reliability.

Until sufficient cases exist:
do not publish percentages behind those labels.

---

# 63. Operator usefulness

Human reviewer should also answer:

> Would this output materially reduce investigation time?

Suggested score:
- 0 harmful;
- 1 not useful;
- 2 somewhat useful;
- 3 directly actionable.

This can become a pilot KPI.

---

# 64. Test-design quality

For recommended counterfactuals, score:
- isolates variable;
- uses a control;
- prediction stated;
- duration bounded;
- blast radius minimized;
- synthetic/read-only test attempted first where possible.

---

# 65. Eval promotion

A new eval is promoted only when:

1. source/evidence reviewed;
2. visible input does not leak gold;
3. gold outcome justified;
4. must-do/must-not-do defined;
5. failure mode tagged;
6. deterministic checks added where possible;
7. human review complete.

---

# 66. Synthetic fixtures

Not every eval needs a historical case.

Use controlled fixtures for:
- exact GPT lifecycle;
- missing-vs-zero;
- freshness;
- timestamp windows;
- connector failure;
- slot/lazy behavior.

Use real incidents for:
- ambiguity;
- confounders;
- causal chains;
- counterexamples.

---

# 67. Private pilot incidents

Private pilot incidents should eventually become the best eval source.

Process:

```text
incident
→ evidence frozen
→ RCA/closure reviewed
→ anonymized eval
→ gold validated
→ access policy applied
```

Do not promote private data to shared corpus automatically.

---

# 68. Flagship eval: TCF → GAM requests

Expected reasoning:

```text
traffic stable
→ TCF error/change
→ GAM requests decline
→ programmatic impressions decline
```

Consent/request eligibility should rank above broad demand because the first broken stage is already request generation.

No unsupported revenue estimate.

---

# 69. Release-gating counterexample: suspected cause after onset

Expected:

```text
decline precedes integration
→ integration cannot explain onset
```

It may remain a later contributor only with evidence.

No invented replacement cause.

---

# 70. Release-gating counterexample: external event after onset

Expected:
- preserve Google/update context;
- reject onset attribution;
- continue investigation;
- possibly conclude UNRESOLVED.

---

# 71. Release-gating epistemic case

Evidence:
- real Search decline;
- local state stable;
- no clear external match;
- measurement healthy.

Expected:

```text
UNRESOLVED / NO_STRONG_LOCAL_CAUSE
```

Do not invent an algorithm change.

---

# 72. Release-gating test-design case

Broad shutdown changed many variables and caused business loss without RCA.

Expected:
- identify confounding;
- recommend narrow test;
- define prediction/control;
- reduce blast radius.

---

# 73. Initial release gate

Before pilot incident recommendations are trusted:

- zero invented-evidence hard fails in reviewed critical slice;
- counterexample slice passes;
- UNRESOLVED slice passes;
- no critical external-misattribution failure;
- no onset-before-candidate failure;
- major families have acceptable top-mechanism recall;
- human reviewer confirms outputs are useful.

Do not ship because a demo sounds convincing.

---

# 74. Current v0.1 limitations

The 76-case seed is not yet a perfect benchmark.

Limitations:
- some public field cases are incomplete;
- some `visible_case.investigation` text may still contain stronger clues than a real initial report;
- family coverage is uneven;
- public cases may be model-familiar;
- two internal cases are based on private user-reported chronology rather than independently verified RCA.

Therefore v0.1 is best used for:
- harness construction;
- rule regression;
- grader validation;
- discovering leakage and scoring problems.

v0.2 should add staged and metamorphic variants before we treat the score as a serious product benchmark.

---

# 75. Immediate v0.2 work

Priority:

1. review all 76 inputs for gold leakage;
2. convert strongest 30–40 cases into staged evals;
3. create metamorphic pairs for timing/control/recovery;
4. add synthetic exact-evidence fixtures;
5. create deterministic graders;
6. human-review gold for unresolved/probable field cases;
7. create holdout set not used for rule tuning.

---

# 76. Codex rules

Codex MUST:

- never pass gold into SUT;
- preserve dataset version;
- record SUT/harness provenance;
- report by slice;
- keep deterministic and model graders separate;
- validate model graders with humans;
- include counterexamples and unresolved cases;
- preserve unresolved gold;
- create metamorphic variants;
- add new reasoning rules to evals;
- never use corpus count as prior probability;
- never fix an eval by leaking its answer into the prompt.

Codex MUST NOT:

- delete hard cases because score falls;
- change gold without review;
- compare different harness budgets as equivalent;
- count fluent prose as correctness without evidence grounding;
- allow model grader to excuse invented evidence;
- hide slice regressions behind one average.

---

# 77. Evaluation runtime boundary (ADR-129)

Evaluation **execution** uses replaceable runtime infrastructure. The adopted runtime is
[Inspect AI](https://github.com/UKGovernmentBEIS/inspect_ai) (`UKGovernmentBEIS/inspect_ai`),
accepted in ADR-129.

The boundary is mandatory:

> **Inspect is the eval engine. `EVALS.md` remains the contract.**

Publisher Intelligence remains canonical and repository-owned for:

- eval corpus and case IDs (`incident_evals_v0.1.yaml` and successors);
- gold answers and expected outcomes;
- deterministic assertions;
- rubric semantics (`eval_rubric_v0.1.yaml`);
- hard-fail semantics;
- mandatory eval sets and holdout policy;
- release thresholds and release eligibility.

Inspect AI provides replaceable infrastructure only for: execution, dataset/sample orchestration,
scorer plumbing, run logging and provenance capture, result inspection, usage/latency/cost
telemetry, re-scoring, and regression execution.

Rules:

- PASS, hard-fail, mandatory-set membership, holdout semantics, thresholds, and release
  eligibility MUST NOT be encoded exclusively in Inspect configuration.
- An adapter boundary separates Publisher Intelligence corpus/rubric/release types from Inspect
  concepts; Inspect APIs MUST NOT leak into Incident Engine domain code.
- Replacing Inspect later MUST NOT require redefining any of the semantics listed above; the
  machine-readable assets in `evals/` must survive unchanged.

---

# 78. Final principle

A credible Incident Engine is not one that always has an answer.

It is one whose answer changes when the evidence changes.

If candidate timing flips from before to after onset:
the candidate must fall.

If rollback changes from recovery to no effect:
confidence must fall.

If a critical evidence source disappears:
confidence must fall.

If evidence remains insufficient:
the answer must stay UNRESOLVED.

# **We do not test whether the engine can tell a plausible story. We test whether its conclusions are constrained by evidence.**
