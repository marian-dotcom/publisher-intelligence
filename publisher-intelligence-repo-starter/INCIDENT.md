# INCIDENT.md
## Incident Investigation Engine Specification
### Publisher Incident Intelligence Platform — v1.0

**Audience:** Codex, backend engineering, product, technical reviewers  
**Status:** MVP implementation contract  
**Depends on:** `DOMAIN.md`, `BROWSER.md`, `DATA_MODEL.md`, `EVENTS.md`, `CONNECTORS.md`, `INCIDENTS.md`, `MVP.md`  
**Feeds:** `EVALS.md`, Investigate UI, Incident Reports, Publisher Memory, Weekly learning

---

# 0. Purpose

The Incident Engine is the reasoning layer that turns operational memory into a structured investigation.

Its job is to answer:

> **What most plausibly explains the publisher's symptom, what evidence supports each explanation, what evidence argues against it, what remains unobservable, and what is the safest next test?**

It does not need to identify a root cause every time.

A successful investigation may conclude:

```text
CONFIRMED
PROBABLE
POSSIBLE CONTRIBUTOR
UNRESOLVED
```

The ability to say **UNRESOLVED** is a core product capability.

The Incident Engine should behave like a disciplined senior investigator:
- establish the symptom;
- localize it;
- verify measurement;
- construct the right baseline;
- reconstruct relevant changes;
- generate plausible hypotheses;
- test those hypotheses against evidence;
- actively search for contradictions;
- use interventions carefully;
- distinguish local causes from external context;
- stop when the evidence does not justify stronger claims.

---

# 1. Core mental model

The Incident Engine does not start with:

> "What caused this?"

It starts with:

> **"What exactly changed, where, and when?"**

Only then does it ask why.

Canonical flow:

```text
USER-REPORTED SYMPTOM
        ↓
SYMPTOM NORMALIZATION
        ↓
MEASUREMENT-INTEGRITY CHECK
        ↓
LOCALIZATION
        ↓
BASELINE + TIME WINDOWS
        ↓
RELEVANT EVENT / CHANGE RETRIEVAL
        ↓
FAILURE-MODE CANDIDATES
        ↓
EVIDENCE CHAINS
        ↓
CONTRADICTION SEARCH
        ↓
HYPOTHESIS RANKING
        ↓
OPTIONAL COUNTERFACTUAL TEST
        ↓
REPORT
        ↓
RECOVERY / RESOLUTION LEARNING
```

---

# 2. Non-negotiable invariants

## INC-INV-001 — Correlation is not causation

Temporal proximity creates a candidate, not a conclusion.

```text
deployment before decline
```

does NOT automatically mean:

```text
deployment caused decline
```

## INC-INV-002 — Baseline first

No incident investigation may reason only from the incident period.

The engine MUST construct a meaningful pre-incident baseline.

## INC-INV-003 — Localize before explaining

The engine must determine the affected scope before ranking causes.

Examples:
- site-wide vs one template;
- mobile vs desktop;
- Search vs Discover;
- one ad unit vs all inventory;
- one bidder vs all demand.

## INC-INV-004 — Measurement integrity first

Before concluding business reality changed, verify that the measurement system itself is plausible.

Examples:
- GA4 tracking can fail;
- GSC recent data can be incomplete;
- GAM reporting can be delayed;
- browser collector can fail.

## INC-INV-005 — Mechanism required

A top hypothesis must have a plausible physical/logical mechanism linking candidate to symptom.

Coincidence alone is insufficient.

## INC-INV-006 — Search for evidence against the hypothesis

For every top hypothesis, the engine MUST ask:

> **What evidence would make this explanation weaker or wrong?**

Contradicting evidence is first-class.

## INC-INV-007 — Preserve temporal uncertainty

If a change is only known to have occurred between two checkpoints, treat it as an interval.

Do not invent an exact onset.

## INC-INV-008 — Preserve observability limits

Hidden systems remain hidden.

The engine MUST lower confidence or mark unknown when:
- SSP internals are unavailable;
- Prebid Server hides bidder detail;
- Google ranking logic is not exposed;
- advertiser intent is unknown.

## INC-INV-009 — External event is context, not local cause

A Google update or vendor outage is not publisher-specific root cause until local evidence matches.

## INC-INV-010 — Incident corpus is precedent, not truth

Similar historical cases help generate/rank hypotheses.

They MUST NOT be treated as:
- prevalence statistics;
- proof;
- automatic diagnosis.

## INC-INV-011 — No forced single cause

Incidents may be:
- multi-causal;
- cascading;
- partly explained;
- unresolved.

## INC-INV-012 — Do not double-count descendant metrics

Requests ↓, impressions ↓ and revenue ↓ may be one chain, not three independent pieces of evidence.

## INC-INV-013 — Intervention evidence matters

Rollback/recovery and controlled tests receive high evidentiary weight when timing/mechanism are plausible.

## INC-INV-014 — Failed rollback matters

If a suspected component is removed and the symptom continues after a plausible recovery period, confidence in that component as the primary cause MUST fall.

## INC-INV-015 — AI explains evidence; it does not invent it

The LLM may synthesize, compare and explain.

It MUST NOT fabricate:
- events;
- metric movements;
- source data;
- timestamps;
- causal confidence;
- rollback outcomes;
- external incidents.

## INC-INV-016 — Read-only diagnosis in MVP

The Incident Engine does not make production changes automatically.

It may recommend a test or rollback.

Execution remains human-controlled unless a later explicit product decision changes this.

---

# 3. Incident versus event

An **event** is something meaningful that happened.

Example:

```text
GPT_EXPECTED_SLOT_MISSING
```

An **incident** is a user/business problem being investigated.

Example:

```text
"Mobile programmatic monetization has been weaker since yesterday."
```

One incident can have:
- zero relevant events;
- one event;
- many related events.

One event can be relevant to:
- no incident;
- multiple incidents.

Do not create one incident automatically for every event.

---

# 4. Incident creation modes

MVP supports two primary modes.

## USER-INITIATED

User clicks **Investigate** and reports a symptom.

This is the primary product workflow.

## ALERT-INITIATED

A critical event may offer:

> Investigate this issue

If user opens it, create an incident seeded from the alert/event.

Do not automatically create a full incident for every alert in MVP unless explicitly configured later.

---

# 5. Minimum intake

Required:

```text
symptom description
approximate start time/date
```

The UI may also ask for a broad symptom family.

Optional:
- device;
- section/category;
- affected page;
- screenshot/message;
- known deploy;
- vendor notice;
- Google notice;
- commercial context.

The user should not need to know:
- which API;
- which failure mode;
- which technical layer.

---

# 6. Approximate start time

Users often say:

```text
"de ieri"
"around August 4"
"since last weekend"
"cam de două săptămâni"
```

Preserve original input and convert to an investigation interval.

Example:

```yaml
user_reported:
  text: "around 4 August"
normalized:
  earliest: 2026-08-03T00:00:00+03:00
  latest: 2026-08-05T23:59:59+03:00
  precision: APPROXIMATE
```

Do not silently convert "around Aug 4" to exactly midnight Aug 4.

---

# 7. Symptom families

Initial user-facing families:

```text
TRAFFIC
SEARCH
DISCOVER
MONETIZATION
ADS_NOT_SERVING
PERFORMANCE
VIDEO
POLICY_OR_COMPLIANCE
SITE_AVAILABILITY
MEASUREMENT
OTHER
```

The description remains primary.

Family helps choose the first diagnostic plan.

---

# 8. Symptom normalization

The engine transforms user language into structured symptom claims.

Example:

User:

> "Monetizarea pe mobile e mult mai proastă de ieri."

Normalized:

```yaml
family: MONETIZATION
reported_scope:
  device: mobile
reported_direction: decrease
reported_start: approximate
reported_metric: unknown
```

Important:

Do not automatically translate "monetization" into:
`GAM revenue`.

The user may mean:
- revenue;
- fill;
- eCPM;
- impressions;
- general commercial performance.

The engine must determine which observable metrics moved.

---

# 9. Symptom truth levels

A user statement is evidence with human provenance.

It may be:
- accurate;
- approximate;
- mislocalized;
- based on a misleading dashboard.

Therefore classify:

```text
REPORTED
OBSERVED
CORROBORATED
NOT_REPRODUCED
```

Example:

```text
Reported: traffic is down 20%
Observed: GA4 sessions down 18%
Corroborated: GSC clicks down 17%
```

This distinction should appear in the internal investigation state.

---

# 10. Incident triage output

Before generating causes, the engine should produce a short internal triage:

```yaml
symptom:
  family:
  onset_window:
  affected_scope:
  observed_metrics:
  data_quality:
  severity:
  observability:
```

If the reported symptom cannot be reproduced from available sources:
do not continue as if it were confirmed.

Investigate:
- source mismatch;
- measurement issue;
- unavailable data;
- user-reported commercial metric outside platform.

---

# 11. Data readiness gate

Before investigation:

Check:

```text
Browser evidence available?
GA4 healthy?
GSC healthy?
GAM healthy?
Public config available?
External timeline available?
```

For each:

```text
AVAILABLE_MATURE
AVAILABLE_PRELIMINARY
STALE
UNAVAILABLE
NOT_CONNECTED
NOT_APPLICABLE
```

The engine may continue with partial data.

But the report must list missing evidence.

---

# 12. Data freshness gate

Never build strong causal conclusions on:
- stale connector data;
- failed extracts;
- incomplete source periods;

without stating the limitation.

Mixed maturity is allowed.

Example:

```text
GA4 = mature
GAM = preliminary
GSC hourly = preliminary
browser = direct checkpoint evidence
```

Confidence must account for this.

---

# 13. Incident window architecture

Every incident can have multiple windows.

Required concepts:

```text
BASELINE
PRE_INCIDENT
INCIDENT
RECOVERY
COMPARISON
```

Do not use one universal ±24-hour window.

---

# 14. Baseline principles

A good baseline should represent:

> **what normal looked like before the symptom**

Possible techniques:
- same hour-of-week;
- previous comparable weekdays;
- previous 2–4 weeks;
- rolling median;
- pre-change stable interval;
- matched control segment.

Avoid:
- unusual holiday;
- known prior incident;
- major breaking-news spike;
- already-degrading period.

Baseline selection is versioned and explainable.

---

# 15. Baseline contamination

The engine MUST test whether the baseline already contains the decline.

This is critical for gradual incidents.

Example:

User:
> "Traffic started Aug 10."

But change-point evidence:
decline began Jul 28.

Then:

```text
Aug 1–9
```

cannot be treated as healthy baseline.

The engine should move the investigation onset earlier.

This is also powerful contradicting evidence against changes introduced after Jul 28.

---

# 16. Change-point assistance

For gradual trends, the system MAY use simple change-point methods.

Initial:
- robust rolling median;
- deviation persistence;
- piecewise trend check.

Do not start with opaque ML.

Output:

```text
reported onset: Aug 10
estimated measurable onset: Jul 29–31
```

Preserve both.

---

# 17. Default window guidance by symptom

These are starting heuristics, not fixed constants.

## SITE_AVAILABILITY

Baseline:
hours to days.

Lookback:
hours/days.

## ADS_NOT_SERVING / MONETIZATION sudden

Baseline:
same hour/day patterns over recent days/weeks.

Lookback:
hours to several days.

## CMP / JS / browser runtime

Lookback:
browser checkpoints around onset plus several prior checkpoints.

## PERFORMANCE

Lookback:
several comparable checkpoints + recent field data if available.

## TRAFFIC

Lookback:
days/weeks depending trend.

## SEARCH

Lookback:
at least days/weeks because crawl/index/ranking effects can lag.

## DISCOVER

Use longer context because volatility can be high.

## POLICY

Lookback:
policy notice + relevant site-change window.

The final windows must be stored in `incident_windows`.

---

# 18. Recovery window

If the suspected change is:
- rolled back;
- fixed;
- removed;
- vendor incident ends;

create a recovery window.

Recovery expectations depend on symptom.

Examples:

Browser request path:
may recover quickly.

GAM delivery:
may reflect quickly subject to reporting delay.

GA4 tracking:
may recover quickly but historical missing data may remain missing.

Search indexing/ranking:
may recover with significant lag.

Do not use one universal recovery timeout.

---

# 19. Symptom localization hierarchy

Localization reduces the search space.

Recommended dimensions:

```text
SOURCE / PRODUCT
DEVICE
TEMPLATE
CATEGORY
PAGE
GEOGRAPHY
AD UNIT
FORMAT
DEMAND CHANNEL
BIDDER
CONSENT STATE
BROWSER SCENARIO
```

Start broad, then narrow only when data supports it.

---

# 20. Localization matrix

The engine should create an affected/unaffected matrix.

Example:

| Segment | Affected? |
|---|---|
| Mobile article | Yes |
| Desktop article | No |
| Mobile homepage | No |
| Direct traffic | No |
| Organic Search | Yes |

The unaffected segments are as valuable as the affected ones.

They act as control groups.

---

# 21. Unaffected controls

Examples:

- desktop unaffected while mobile affected;
- homepage unaffected while article affected;
- Direct stable while Organic Search falls;
- bidder B stable while bidder A falls;
- Reject path works while Accept path fails.

Control evidence should increase/decrease hypothesis relevance.

A cause that should affect both control and target equally is weakened when only target changes.

---

# 22. Measurement integrity checkpoint

Before domain diagnosis, ask:

> **Could the observed symptom be a measurement/reporting artifact?**

This is mandatory for:
- traffic;
- Search;
- monetization.

---

# 23. GA4 measurement integrity

Check:

- connector health;
- extract completeness;
- property/report semantics;
- `dataLossFromOtherRow`;
- thresholding;
- tracking/consent changes;
- pageview behavior;
- cross-check with GSC/browser where possible.

Pattern:

```text
GA4 down
GSC stable
browser/site healthy
analytics/CMP change present
```

raises measurement hypothesis.

Do not say GA4 is broken until supported.

---

# 24. GSC measurement integrity

Check:

- final vs preliminary data;
- first incomplete date/hour;
- query/page row limitations;
- search type;
- source timezone;
- connector health.

Do not treat missing long-tail rows as zero.

---

# 25. GAM measurement integrity

Check:

- report completion;
- partial extraction;
- report semantics version;
- network timezone/currency;
- direct/programmatic mix;
- platform/reporting incidents.

Pattern:

```text
dashboard/API discrepancy
browser ad serving normal
other source delivery normal
```

raises reporting anomaly.

Do not equate reporting failure with serving failure.

---

# 26. Investigation plan

Once symptom is localized, build a deterministic plan.

Plan contains:

```yaml
symptom:
windows:
required_evidence:
candidate_failure_families:
external_checks:
drilldown_queries:
browser_comparisons:
control_segments:
```

The plan may be expanded as evidence arrives.

The LLM may help explain the plan.

It does not get to invent unavailable queries.

---

# 27. Candidate generation sources

Candidate hypotheses come from six sources:

1. `DOMAIN.md` failure modes;
2. relevant EVENTS around onset;
3. manual/operational changes;
4. external official events;
5. similar INCIDENTS patterns;
6. source-specific diagnostic decomposition.

No single source gets authority.

---

# 28. Candidate generation from events

Retrieve events using:
- incident window;
- temporal lookback;
- scope overlap;
- domain family;
- criticality.

Do not retrieve every event from the last month.

Ranking candidates begins before full hypothesis scoring.

---

# 29. Candidate generation from DOMAIN

Map symptom to failure-mode families.

Example:

```text
MONETIZATION
+ requests down
+ traffic stable
```

candidate families include:

```text
F-GAM-001 slot removed
F-GAM-002 request/config mismatch
F-GPT-002 defined not requested
F-CMP-* consent
F-BR-002 JS failure
lazy loading / refresh changes
```

Broad demand weakness receives lower initial relevance because request generation is upstream of demand.

---

# 30. Candidate generation from INCIDENTS

The corpus can retrieve analogous patterns.

Use:
- symptom family;
- failure mode;
- evidence chain;
- affected layer;
- record quality;
- root-cause status.

Prefer:
- Tier A/B;
- confirmed/probable;
- similar mechanism.

Unresolved cases remain useful for:
- alternative hypotheses;
- known ambiguity;
- false leads.

Do not rank because:
"this pattern appears 122 times."

Corpus frequency is heavily biased by public-source availability.

---

# 31. Incident corpus evidence tiers

Use corpus tier as precedent reliability:

```text
A = primary/official/reproducible
B = strong field case
C = incomplete/limited
D = anecdotal discovery
```

A Tier A analogue may increase mechanism plausibility.

It does not turn local hypothesis into PROBABLE without publisher-specific evidence.

---

# 32. Candidate generation from external events

Retrieve official events matching:
- time;
- product;
- scope;
- geography if relevant.

Examples:
- Search ranking update;
- indexing incident;
- GAM outage;
- CDN incident;
- CMP vendor outage.

External event becomes a hypothesis candidate only if it can plausibly affect the observed symptom.

---

# 33. Candidate generation from operational changes

Retrieve:
- deployment;
- player change;
- CMP change;
- Prebid change;
- GAM config;
- direct campaign;
- rollback;
- vendor integration.

A change near onset is a candidate.

But:

```text
change present
```

is weak evidence without:
- segment match;
- mechanism;
- intermediate signals.

---

# 34. Hypothesis object

Each hypothesis needs:

```yaml
failure_mode:
title:
mechanism:
expected_effects:
expected_scope:
expected_latency:
supporting_evidence:
contradicting_evidence:
missing_evidence:
observability_limit:
confidence:
next_discriminating_test:
```

A hypothesis without a mechanism is not a valid top hypothesis.

---

# 35. Mechanism statement

Mechanism must be concrete.

Weak:

> CMP problem affected monetization.

Strong:

> The consent signal was unavailable on the mobile Accept path, preventing expected Google ad requests from being generated; lower GAM request volume then reduced served programmatic impressions.

The mechanism creates testable intermediate expectations.

---

# 36. Expected intermediate signals

For every hypothesis, ask:

> **If this were true, what else should we expect to observe?**

Examples:

## Slot removed

Expect:
- browser expected-slot missing;
- requests/view lower;
- affected template/device;
- potentially impressions/view lower.

## Demand weakness

Expect:
- ad requests stable;
- lower responses/fill/eCPM;
- multiple demand sources potentially affected;
- no slot/request-generation change.

## GA4 tracking failure

Expect:
- GA4 decline;
- independent source(s) more stable;
- measurement/consent/tag change;
- browser analytics request change.

Hypotheses that predict observed intermediate signals deserve more weight.

---

# 37. Expected non-effects

Also ask:

> **What should remain unchanged if this hypothesis is true?**

Example:
mobile-only template defect.

Expected:
desktop unaffected.

If desktop also declines identically:
mobile-only hypothesis weakens.

This is control logic.

---

# 38. Temporal relevance

For each candidate:

1. Did it occur before symptom onset?
2. Is timing known exactly or only as a window?
3. Is the expected causal latency plausible?
4. Did symptom begin before candidate?

If symptom predates candidate:
major contradiction.

A later candidate may still:
- worsen;
- contribute;
- affect recovery;

but should not explain onset.

---

# 39. Overlap with uncertain windows

Example:

Change:
between 12:00–18:00.

Metric decline:
begins around 15:00.

The windows overlap.

This supports temporal compatibility.

Do NOT claim:
change definitely occurred before 15:00.

Temporal score should reflect uncertainty.

---

# 40. Segment match

Assess overlap:

```text
device
template
source/channel
geo
ad unit
format
demand partner
consent state
```

Possible classes:

```text
EXACT
STRONG
PARTIAL
WEAK
NONE
UNKNOWN
```

A candidate with `NONE` segment overlap should normally fall sharply unless mechanism is truly global.

---

# 41. Mechanism plausibility

Sources:
- canonical DOMAIN;
- current official docs;
- incident-backed pattern.

Possible:

```text
ESTABLISHED
STRONG
PLAUSIBLE
WEAK
UNKNOWN
```

Do not let LLM invent a mechanism absent from DOMAIN/current source knowledge.

If new mechanism is discovered:
human/research validation should update DOMAIN.

---

# 42. Intermediate evidence

Possible levels:

```text
DIRECT
MULTIPLE
SINGLE
ABSENT
CONTRADICTORY
NOT_OBSERVABLE
```

Example:

```text
CMP change
→ TCF errors
→ GAM requests ↓
→ impressions ↓
```

provides multiple intermediate stages.

That is much stronger than:

```text
CMP change
→ revenue ↓
```

---

# 43. Magnitude compatibility

Ask:

> Could the candidate plausibly explain the observed size?

Examples:

One ad slot disappears from a page with five slots:
might explain some request/view reduction.

It is less plausible as sole explanation for:
90% site-wide traffic loss.

Do not require exact mathematical prediction.

Use magnitude as a sanity constraint.

---

# 44. Persistence match

If candidate persists:
does symptom persist?

If candidate resolves:
does symptom recover after expected lag?

Mismatch is useful evidence.

Example:

CMP error existed for 30 minutes.
Revenue/request decline persists for 5 days.

CMP error may have been incidental or only a contributor.

---

# 45. Causal evidence ladder

Use DOMAIN ladder:

1. coincidence;
2. temporal precedence;
3. plausible mechanism;
4. segment match;
5. intermediate metric chain;
6. repeated reproduction;
7. unaffected control group;
8. targeted intervention;
9. rollback + recovery;
10. direct technical proof.

The engine should prefer a mundane hypothesis at level 7–9 over a dramatic hypothesis at level 2.

---

# 46. Positive evidence

Supporting evidence can include:

- matching timing;
- matching scope;
- expected intermediate metric;
- known failure mechanism;
- repeated browser reproduction;
- vendor/platform confirmation;
- rollback recovery;
- control group difference;
- exact technical error.

Evidence must reference source IDs.

---

# 47. Contradicting evidence

Contradiction types include:

```text
PREDATES_CANDIDATE
PERSISTS_AFTER_REMOVAL
CONTROL_ALSO_AFFECTED
EXPECTED_SIGNAL_MISSING
WRONG_SEGMENT
MAGNITUDE_MISMATCH
EXTERNAL_EVENT_WRONG_PRODUCT
SOURCE_DATA_STALE
ALTERNATIVE_BETTER_EXPLAINS
```

Contradiction is not an afterthought.

It is part of every hypothesis.

---

# 48. Contradiction search procedure

For each top hypothesis, explicitly run:

1. onset-before-candidate test;
2. unaffected-control test;
3. expected-intermediate-signal test;
4. removal/recovery test if available;
5. segment mismatch test;
6. source-quality test;
7. alternative explanation test.

A hypothesis report without contradiction search is incomplete.

---

# 49. Onset-before-candidate rule

This is one of the strongest negative rules.

If:

```text
symptom measurable onset = July 20
suspected integration introduced = August 1
```

then the integration cannot explain onset.

Possible labels:
- unrelated;
- later contributor;
- worsened existing decline.

But it should not remain top root-cause hypothesis for initial decline.

---

# 50. Persists-after-removal rule

If:

```text
suspected component removed
```

and after a plausible recovery window:

```text
symptom trajectory continues
```

then:
reduce primary-cause confidence.

Do NOT make this rule universal without latency awareness.

Example:
Search recovery can lag.

But for a client-side ad-request failure, expected recovery may be rapid.

---

# 51. Recovery-after-rollback rule

Strong chain:

```text
change introduced
→ symptom begins
→ rollback
→ intermediate signal recovers
→ symptom recovers
```

This is high-quality evidence.

Even here:
check confounders such as:
- demand shift;
- external outage ending simultaneously;
- unrelated deploy.

---

# 52. Control-group evidence

Good controls:
- unaffected device;
- unaffected template;
- unaffected geography;
- unaffected bidder;
- unaffected traffic source;
- old version cohort;
- Accept vs Reject;
- staging/production.

Controls help distinguish:
local mechanism
from
global coincidence.

---

# 53. Confounder checklist

Every investigation should consider relevant confounders.

## Temporal
- hour;
- weekday;
- season;
- holiday;
- breaking-news cycle.

## Traffic
- device mix;
- country mix;
- source mix;
- content mix.

## Monetization
- direct campaign;
- demand seasonality;
- floor;
- deal;
- ad-unit mix;
- viewability.

## Technical
- A/B experiment;
- browser update;
- CDN;
- vendor outage;
- collector change.

## Measurement
- data freshness;
- tracking change;
- attribution change;
- report definition.

## Search
- search demand;
- query mix;
- external Google event.

A candidate can look causal when a confounder moved at the same time.

---

# 54. Alternative hypothesis competition

Do not score hypotheses independently and ignore competition.

Example:

Observed:
- traffic stable;
- GAM requests stable;
- fill down;
- multiple demand channels down;
- no local changes;
- market-wide external signals.

Demand weakness may explain the full chain better than:
new harmless script.

The engine should reward explanatory completeness.

---

# 55. Occam with caution

Prefer the simplest hypothesis that explains the evidence.

But do not force simplicity when:
- two independent changes clearly occurred;
- cascading failure exists;
- one cause explains onset and another explains magnitude.

Allow:
`primary cause + contributor`.

---

# 56. Multi-causal incidents

Example:

```text
Traffic -15%
+
slot count -20%
+
eCPM -10%
```

Revenue could be affected by:
- lower traffic;
- lower inventory/view;
- lower price.

Do not force one cause.

Output may contain:

```text
Primary contributor
Secondary contributor
Background factor
```

Confidence applies to each.

---

# 57. Cascading incidents

Causal chain:

```text
CMP failure
→ request eligibility loss
→ GAM requests down
→ impressions down
→ revenue down
```

Do not call:
- impressions down;
- revenue down;

independent root causes.

They are downstream symptoms.

Use event graph / metric hierarchy.

---

# 58. Root cause versus trigger versus contributor

Useful distinctions:

## ROOT CAUSE
Underlying mechanism necessary for incident.

## TRIGGER
Event that activated a latent failure.

## CONTRIBUTOR
Factor that increased impact but is not sufficient alone.

Example:
latent script bug + traffic spike.

Traffic spike may be trigger.
Bug may be root cause.

MVP user-facing report does not need philosophical perfection, but internal representation should permit these distinctions.

---

# 59. Hypothesis scoring

Use an internal deterministic ranking score.

Do not present it as probability.

Components may include:

```text
temporal_relevance
segment_match
mechanism_strength
intermediate_evidence
magnitude_compatibility
persistence_match
control_evidence
intervention_evidence
external_corroboration
source_quality
contradiction_penalty
observability_penalty
```

Store component values/version.

---

# 60. Suggested scoring scale

Internal components can use a bounded scale such as:

```text
-2 strongly contradicts
-1 weakly contradicts
 0 unknown/neutral
+1 supports
+2 strongly supports
```

Some components:
- mechanism;
- source quality;

may use 0–2.

The exact formula is versioned and calibrated with evals.

Do not pretend the numeric result is scientifically calibrated probability.

---

# 61. Hard penalties

Some contradictions deserve stronger penalties.

Examples:

```text
symptom clearly predates candidate
candidate affects wrong segment
source evidence invalid/stale
expected component never present on affected pages
```

These should often outweigh many weak correlations.

---

# 62. Hard gates

A hypothesis should not become PROBABLE unless:

1. plausible mechanism exists;
2. timing is compatible;
3. affected scope is compatible;
4. at least one meaningful publisher-specific supporting signal exists;
5. no major unexplained contradiction remains.

CONFIRMED requires stronger evidence.

---

# 63. Confidence labels

## CONFIRMED

Use when:
- direct technical proof;
- controlled reproduction;
- strong intervention/rollback + recovery;
- official/vendor confirmation plus matching local evidence.

Not simply:
many weak signals.

## PROBABLE

Use when:
- several independent evidence lines;
- good mechanism;
- timing/scope match;
- few material contradictions.

## POSSIBLE CONTRIBUTOR

Use when:
- relevant evidence exists;
- mechanism plausible;
- material uncertainty remains.

## UNRESOLVED

Use when:
- evidence is insufficient;
- candidates tie without discrimination;
- observability is too weak;
- key data unavailable;
- no hypothesis crosses confidence threshold.

---

# 64. UNRESOLVED is not failure

The report should explain:

```text
What was ruled out
What remains plausible
What is missing
What test would be most informative
```

Example:

> No strong local technical cause was identified. Search decline is real in GSC and GA4, but the available evidence cannot distinguish editorial/search-demand effects from an external ranking-system effect.

That is better than inventing certainty.

---

# 65. No Strong Local Cause

A useful special conclusion:

```text
NO_STRONG_LOCAL_CAUSE
```

This can sit under overall:
`UNRESOLVED`

when:
- local browser/config evidence is stable;
- measurement is healthy;
- local deployment candidates are contradicted;
- external/content factors remain.

This is a meaningful product outcome.

---

# 66. Search/Discover external uncertainty

For Search/Discover, the engine should be especially conservative.

Google itself documents that Search traffic drops can arise from:
- algorithmic updates;
- technical issues;
- security/spam/manual actions;
- seasonality;
- changing interest;
- site moves.

The engine cannot infer hidden ranking logic.

Use:
- GSC decomposition;
- local technical evidence;
- official external events;
- content/search-demand context.

---

# 67. Search incident diagnostic tree

Input:
Search traffic down.

## Step S1 — Measurement

Compare:
- GA4 Organic Search;
- GSC web clicks.

If only GA4:
measurement/attribution rises.

## Step S2 — Visibility decomposition

Inspect:
- GSC impressions;
- clicks;
- CTR;
- position.

## Step S3 — Scope

Break down:
- device;
- page/template;
- country;
- search appearance;
- top pages/queries on demand.

## Step S4 — Technical

Check:
- robots;
- noindex;
- canonical;
- status/redirect;
- rendered mobile content;
- JS failures;
- site availability;
- migration.

## Step S5 — Timeline

Retrieve:
- deploys;
- template changes;
- SEO changes;
- CDN incidents;
- Google official events.

## Step S6 — External/search demand

Check:
- Google update/incident timing;
- content/seasonality/query-demand evidence if available.

## Step S7 — Contradictions

Especially:
- did decline predate suspected change/update?
- are unaffected templates using same tech?
- is position stable while CTR changes?

Then rank.

---

# 68. Search pattern interpretation

## Impressions down

Raises:
- visibility;
- indexing;
- ranking;
- search demand.

## Impressions stable + clicks down + CTR down

Raises:
- SERP presentation;
- query mix;
- title/snippet;
- competition.

## Position worse + impressions/clicks down

Ranking/system/content hypotheses rise.

## Position stable + clicks down

Do not default to ranking loss.

## One template down

Local technical/content hypotheses rise.

## Site-wide web + Discover down

Global/content/external hypotheses rise, but still verify measurement/technical.

---

# 69. Core Update handling

Google's current guidance recommends comparing appropriate before/after periods around core updates rather than reacting to a single point, and Search Central explicitly notes that traffic drops may have many causes.

Engine rule:

```text
official update overlap
→ external context candidate
```

Not:

```text
update caused decline
```

Required for stronger attribution:
- timing compatible;
- affected Google product;
- local Search metrics compatible;
- local technical causes weak/contradicted;
- possibly broader cohort evidence.

---

# 70. Discover incident diagnostic tree

Input:
Discover dropped.

1. verify GSC Discover data maturity;
2. compare Discover-only vs Search/direct/social;
3. identify pages/templates/devices affected;
4. inspect technical changes;
5. inspect policy/manual action context if available;
6. inspect official Discover/Search events;
7. consider inherent volatility;
8. avoid hidden-algorithm certainty.

If Discover falls while Search/direct/social stable and no local technical change:
external/Discover-specific distribution becomes more plausible.

Still may remain UNRESOLVED.

---

# 71. Traffic incident diagnostic tree

Input:
general traffic down.

## Step T1
Verify GA4 measurement.

## Step T2
Break by channel.

## Step T3
Break by device.

## Step T4
Break by template/category/page.

## Step T5
Check site availability/browser.

## Step T6
If Google-specific:
handoff into Search/Discover tree.

## Step T7
If all channels:
site/global measurement/editorial demand hypotheses rise.

## Step T8
Check behavioral ratios:
users vs views/user.

---

# 72. Analytics measurement diagnostic tree

Pattern:
reported traffic decline.

Evidence:
GA4 down.

Check:
- GSC;
- browser analytics network;
- consent;
- tag/script;
- pageview/navigation logic;
- property/report metadata.

Strong measurement pattern:

```text
GA4 views ↓
GSC clicks stable
browser page loads stable
tracking request behavior changed
```

Hypothesis:
analytics measurement issue.

Do not call it actual audience loss.

---

# 73. Monetization investigation principle

Do not begin with total revenue.

Use the chain:

```text
traffic
→ pageviews
→ eligible ad slots
→ GAM ad requests
→ eligibility/demand
→ impressions
→ price/eCPM
→ programmatic revenue
```

Find the first meaningful break.

That is the strongest localization clue.

---

# 74. Monetization diagnostic tree

Input:
programmatic monetization down.

## M1 — Traffic

Are pageviews/users down in affected scope?

If yes:
traffic contribution exists.

## M2 — Inventory opportunities

Did:
- expected slot count;
- lazy loading;
- refresh;
- article/template structure;

change?

## M3 — GAM requests

Requests/view stable or down?

If down:
prioritize upstream request generation.

## M4 — Delivery

Requests stable but impressions/fill down?

Prioritize:
- demand eligibility;
- targeting;
- pricing;
- direct displacement;
- consent;
- platform/demand.

## M5 — Price

Impressions stable but eCPM/value down?

Prioritize:
- demand mix;
- floors;
- geo/device mix;
- seasonality;
- buyer mix.

## M6 — Composition

Did direct/reserved delivery rise?

Programmatic decline may be intentional displacement.

## M7 — Runtime

Check GPT/Prebid/CMP/browser.

## M8 — External

Check GAM/vendor/platform/market context.

---

# 75. Monetization decomposition

Approximate conceptual decomposition:

```text
Programmatic revenue
≈ pageviews
× ad opportunities/view
× request realization
× fill
× eCPM / 1000
```

This is diagnostic, not accounting identity.

It helps allocate contribution.

Example:

```text
pageviews -10%
requests/view -15%
fill stable
eCPM -5%
```

Revenue decline is likely multi-factor.

Do not claim one variable explains everything.

---

# 76. Requests down, traffic stable

Prioritize:

- slot disappeared;
- lazy-loading behavior;
- refresh behavior;
- GPT request missing;
- JS runtime failure;
- CMP/TCF gating;
- template change.

Broad demand weakness should rank lower because it is downstream of request generation.

---

# 77. Requests stable, impressions/fill down

Prioritize:

- demand;
- targeting;
- pricing/floors;
- direct/reserved competition;
- consent eligibility;
- serving restrictions;
- GAM/vendor platform issue.

Browser slot-removal hypothesis weakens if requests remain stable.

---

# 78. Impressions stable, eCPM down

Prioritize:

- buyer/demand mix;
- pricing;
- geo/device mix;
- seasonality;
- viewability/inventory quality;
- deals.

Do not call it implementation failure automatically.

---

# 79. Direct displacement

If:

```text
programmatic impressions ↓
direct/reserved impressions ↑
total opportunities broadly stable
```

hypothesis:

```text
intentional inventory displacement
```

This may be normal/positive business behavior.

Do not report "monetization incident" solely from programmatic share decline.

---

# 80. Raw GAM revenue trap

If raw GAM revenue falls:

check:
- direct campaign booked rates;
- direct/programmatic composition;
- commercial context;
- eCPM;
- impressions.

Publisher business revenue is not inferable from GAM total alone.

This hypothesis may remain outside what platform can know.

---

# 81. Ads not serving diagnostic tree

Input:
"ads aren't showing."

Use GPT lifecycle:

```text
expected slot
→ defined
→ request
→ response
→ creative injected
→ onload
→ viewable
```

Find first missing stage.

## Slot absent
Template/DOM/config.

## Defined but no request
Lazy load / consent / JS / GPT init.

## Request but no response/delivery
GAM eligibility/demand/pricing/policy.

## Creative injected but not loaded
Network/creative/iframe/browser.

## Loaded but not viewable
Layout/viewport/scroll.

Do not jump directly to SSP.

---

# 82. Prebid diagnostic tree

Input:
header-bidding performance issue.

Check:

1. Prebid present/version;
2. auction starts;
3. bidder requests;
4. bid responses;
5. timeouts/no-bids;
6. auction duration;
7. targeting keys;
8. GAM request timing;
9. control bidder;
10. server-side observability limits.

Patterns:

```text
requests sent, responses late
→ timeout/latency

responses exist, targeting missing
→ propagation/config

all bidders stable, GAM falls
→ downstream/upstream non-HB cause
```

---

# 83. Consent diagnostic tree

Check:

- CMP present;
- API present/ready;
- Accept works;
- Reject works;
- TC signal;
- error codes;
- pre/post-consent network;
- Prebid;
- GAM request path;
- analytics.

High-value pattern:

```text
traffic stable
CMP/TCF errors begin
GAM requests ↓
programmatic impressions ↓
```

Consent/request eligibility rises.

Still verify:
- affected geo;
- device;
- timing;
- control path.

---

# 84. Video diagnostic tree

Flow:

```text
player
→ ad request
→ VAST
→ wrapper/cache
→ media/renderer
→ playback
→ tracking
```

Find first missing stage.

Possible:
- player runtime;
- VAST error;
- cache/key mismatch;
- media/render;
- playback;
- policy restriction;
- reporting discrepancy.

A bid/VAST response is not a played impression.

---

# 85. Performance diagnostic tree

Input:
site slower / CWV worse.

First distinguish:

```text
synthetic
field
user-reported
```

Then:
- template/device;
- Last Known Good;
- scripts;
- dependency latency;
- long tasks;
- LCP/CLS/INP components;
- ads/player/CMP;
- browser version/collector change;
- business engagement correlation.

Do not say:
worse CWV = Google penalty.

---

# 86. Site availability diagnostic tree

Check:
- browser request;
- HTTP;
- DNS/network;
- multiple URLs;
- dependency;
- CDN/external incident.

Immediate verification is appropriate.

If site fails then succeeds:
preserve intermittent failure.

Do not erase outage because retry was healthy.

---

# 87. Policy/UX investigation

Input:
policy notice or suspected risky implementation.

Use:
- exact official policy/ruleset version;
- screenshot;
- geometry/behavior;
- GAM serving restriction if available;
- player behavior;
- ad format.

Output:
- observed behavior;
- policy/ruleset intersection;
- confidence/limitations.

Do not claim legal compliance certification.

---

# 88. Last Known Good

Last Known Good is selected per incident/scope.

It is not one global checkpoint.

For:
mobile video incident

use:
latest healthy mobile/video comparable run.

For:
Search incident

use:
latest stable SEO/browser + traffic context before measurable onset.

Selection must record:
- method;
- reason;
- scope;
- checkpoint ID.

---

# 89. Last Known Good comparison pack

For browser-relevant incidents, compare:

```text
screenshots
DOM structure
scripts
dependencies
JS errors
GPT slots/lifecycle
Prebid
CMP
video
SEO state
synthetic performance
```

Only compare supported collectors/scenarios.

Do not call missing collector data "unchanged."

---

# 90. Incident evidence pack

The engine should build a bounded evidence pack.

Sections:

```text
SYMPTOM
WINDOWS
AFFECTED / UNAFFECTED SEGMENTS
METRIC MOVEMENTS
LAST KNOWN GOOD DIFF
RELEVANT EVENTS
OPERATIONAL CHANGES
EXTERNAL EVENTS
SIMILAR INCIDENT PATTERNS
SOURCE LIMITATIONS
```

This is what reasoning consumes.

Do not hand an LLM an unbounded month of raw logs.

---

# 91. Evidence selection

Evidence selection should favor:

- direct relevance;
- temporal proximity;
- scope overlap;
- high source quality;
- known mechanism;
- discriminating value.

Avoid context-window pollution with:
- unrelated routine changes;
- every JS warning;
- all Search queries;
- all GAM line items;
- every external incident.

---

# 92. Evidence item semantics

Every evidence item needs:

```yaml
fact:
source:
time/period:
scope:
maturity:
strength:
supports_or_contradicts:
source_reference:
```

The `supports_or_contradicts` direction belongs to hypothesis relation, not evidence itself.

Same evidence can support one hypothesis and contradict another.

---

# 93. Independent evidence

Evidence is stronger when it comes from independent sources.

Example:

```text
Browser: noindex detected
GSC: impressions decline later
```

stronger than:
two charts derived from same GSC report.

Do not double-count correlated views from same source.

---

# 94. Evidence family deduplication

Group evidence by provenance family:

```text
BROWSER
GA4
GSC
GAM
EXTERNAL
MANUAL
INCIDENT_CORPUS
```

Multiple metrics from one extract should not count as fully independent evidence.

Scoring should account for source dependence.

---

# 95. Source quality

Suggested hierarchy for facts:

```text
DIRECT OBSERVATION
AUTHORITATIVE PLATFORM DATA
OFFICIAL EXTERNAL EVENT
PUBLISHER MANUAL RECORD
DERIVED EVENT
INCIDENT PRECEDENT
HEURISTIC
```

This is not absolute.

A direct synthetic observation may still not represent all users.

Source quality and observability are separate.

---

# 96. Observability matrix

For every hypothesis, mark key mechanism stages:

```text
OBSERVED
PARTIALLY_OBSERVED
NOT_OBSERVABLE
NOT_CONNECTED
NOT_APPLICABLE
```

Example:
Prebid Server bidder internals:
`NOT_OBSERVABLE`.

Report should say this explicitly.

---

# 97. Missing evidence

Missing evidence types:

```text
SOURCE_NOT_CONNECTED
SOURCE_STALE
NO_HISTORICAL_CHECKPOINT
INSUFFICIENT_BASELINE
SERVER_SIDE_HIDDEN
NO_CONTROL_GROUP
NO_ROLLBACK
LOW_VOLUME
```

Missing evidence is not contradiction.

Do not penalize absence of data the same as evidence against.

---

# 98. Hypothesis generation limits

Do not output 25 hypotheses.

Internal candidate pool can be larger.

User-facing:
typically top 3–5.

Additional:
"other lower-ranked possibilities" only when useful.

If all candidates weak:
say UNRESOLVED.

---

# 99. Hypothesis diversity

Avoid returning five versions of the same hypothesis.

Example bad:

1. CMP broken
2. TCF missing
3. consent problem
4. vendor mapping problem

If evidence does not distinguish:
use one family:

> Consent/TCF request eligibility issue

and explain possible submechanisms.

Drill down later.

---

# 100. Candidate pruning

Prune when:

- impossible timing;
- no mechanism;
- wrong scope;
- directly contradicted;
- source data invalid;
- candidate requires component that does not exist;
- candidate is a downstream symptom, not cause.

Record pruning reason for debugging/evals.

---

# 101. Candidate resurrection

A pruned candidate can re-enter if new evidence appears.

Example:
vendor outage announced later with start time matching incident.

Investigations are revisable.

Do not permanently blacklist a hypothesis.

---

# 102. External event timing

External events can be announced after they begin.

Store:
- started_at;
- announced_at;
- ended_at.

Incident reasoning uses event start, not ingestion/announcement time.

But availability of knowledge at report generation should be auditable.

---

# 103. Market/cohort intelligence

Future cross-publisher evidence can be useful:

```text
multiple similar publishers
same product/source decline
same time window
no common local change
```

This may increase:

```text
POSSIBLE GOOGLE ECOSYSTEM EVENT
```

Do not claim a secret update.

MVP may not yet have enough tenants for this.

---

# 104. Counterfactual testing

When evidence cannot discriminate, propose a test.

The test should maximize:

```text
expected information gain
```

while minimizing:

```text
business risk
blast radius
irreversibility
cost
```

---

# 105. Test ranking

Internal factors:

```text
discrimination_power
risk
reversibility
scope
time_to_signal
observability
business_cost
```

Prefer:
high discrimination + low risk.

---

# 106. Good tests

Examples:

- mobile vs desktop;
- affected vs unaffected template;
- Accept vs Reject;
- one ad unit;
- one bidder;
- small traffic cohort;
- staging vs production;
- targeted rollback.

---

# 107. Bad tests

Avoid:

- disable all programmatic vendors;
- change CMP + player + Prebid simultaneously;
- remove all ads;
- wait weeks without a specific prediction;
- production-wide destructive experiment;
- test that changes several variables.

These reduce attribution quality.

---

# 108. Test prediction

Before recommending a test, state:

```text
If hypothesis H is true, we expect X.
If H is false, we expect Y.
```

Example:

> If the Accept-path consent signal is causing missing GAM requests, a controlled synthetic Accept run with corrected signal should restore the GPT/GAM request stage while the rest of the page remains unchanged.

This makes the test falsifiable.

---

# 109. Human approval

MVP Incident Engine may:
- recommend;
- create an investigation task;
- request an additional synthetic run.

It may not:
- alter GAM;
- deploy code;
- change CMP;
- disable vendors;
- rollback production.

Human executes production changes.

---

# 110. Automatic diagnostic browser runs

Safe read-only synthetic runs MAY be launched automatically by Incident Engine.

Examples:
- fresh mobile validation;
- Accept vs Reject;
- second article URL;
- extra screenshot;
- repeated run.

Rules:
- bounded;
- no ad clicking;
- no load testing;
- no write action;
- all runs stored as evidence.

---

# 111. Automatic connector drill-down

Incident Engine MAY run validated Tier C connector extracts.

It asks semantically.

Application selects from allowlisted query definitions.

LLM never constructs arbitrary API queries.

---

# 112. Stop conditions

Investigation should stop/escalate when:

1. one hypothesis is CONFIRMED;
2. one hypothesis is PROBABLE and next action is clear;
3. evidence ceiling reached and result is UNRESOLVED;
4. required source unavailable;
5. further tests require risky production change/human decision;
6. symptom already recovered but cause remains uncertain;
7. data volume/quality cannot discriminate.

Do not continue querying forever seeking certainty.

---

# 113. Investigation budget

Every investigation has a bounded budget.

Possible limits:
- max connector drill-down queries;
- max extra browser runs;
- max hypotheses;
- max evidence items;
- max LLM reasoning passes.

Budget may be higher for severe incidents.

This protects:
- API quota;
- cost;
- latency;
- cognitive quality.

---

# 114. Fast path versus deep path

## FAST PATH

Used when evidence is strong.

Example:
broad noindex appears + Search begins degrading.

Return early high-confidence hypothesis.

## DEEP PATH

Used when:
- symptom ambiguous;
- multiple layers;
- conflicting evidence;
- no obvious local change.

Do not run the deep path for every incident.

---

# 115. Investigation phases

Recommended internal phase state:

```text
TRIAGE
LOCALIZING
COLLECTING
HYPOTHESIS_GENERATION
HYPOTHESIS_TESTING
WAITING_FOR_DATA
WAITING_FOR_HUMAN
CONCLUDED
RESOLVED
CLOSED_UNRESOLVED
```

This can remain application state; do not create overcomplex workflow engine.

---

# 116. Incident severity

Incident severity is distinct from hypothesis confidence.

Severity describes business/operational impact.

Possible:

```text
LOW
MEDIUM
HIGH
CRITICAL
```

Inputs:
- magnitude;
- scope;
- duration;
- critical area;
- user/commercial impact.

Do not infer exact money loss unless valid data exists.

---

# 117. Impact estimation

Impact can use observable metrics.

Examples:
- Search clicks lost versus baseline;
- ad requests/impressions difference;
- synthetic outage duration.

Financial estimate:
only if publisher data supports it.

State assumptions.

Do not invent euro impact from eCPM without valid volume/value context.

---

# 118. Incident report contract

Every report MUST contain:

## 1. Incident summary

What user reported.

## 2. What we observed

Validated symptom + scope + onset.

## 3. Data quality / limitations

Unavailable/preliminary sources.

## 4. Timeline

Relevant events before/after.

## 5. Last Known Good

Relevant comparison state.

## 6. Top hypotheses

Ranked.

For each:
- confidence;
- mechanism;
- evidence supporting;
- evidence contradicting;
- observability gaps.

## 7. External context

Clearly separated.

## 8. What we ruled out / deprioritized

Important negatives.

## 9. Recommended next test/action

High-information, low-risk.

## 10. Conclusion

May be UNRESOLVED.

---

# 119. Report language

Good:

> GAM requests on mobile article inventory fell 22% while GA4 views remained within baseline. The decline began in the same observation window in which TCF errors appeared. This makes a consent/request-eligibility issue the leading hypothesis.

Bad:

> CMP definitely caused a 22% revenue loss.

The second statement:
- changes metric;
- overstates certainty;
- ignores downstream value;
- asserts cause.

---

# 120. Report confidence language

Use:

```text
CONFIRMED
PROBABLE
POSSIBLE CONTRIBUTOR
UNRESOLVED
```

Optionally:

```text
LOW RELEVANCE
DEPRIORITIZED
REJECTED
```

for alternatives.

Do not expose internal score as:
`87.4%`.

---

# 121. Report evidence table

Useful internal/user-facing representation:

| Evidence | Direction | Source | Strength |
|---|---|---|---|
| TCF error starts in same window | Supports | Browser | Strong |
| GAM requests -22% mobile article | Supports | GAM | Strong |
| Desktop unaffected | Supports | Control | Medium |
| CMP update actually occurred 3 days later | Contradicts | Operational | Strong |

This is more trustworthy than narrative-only reasoning.

---

# 122. Timeline selection

Incident timeline should not include every event.

Select:
- candidate changes;
- symptom onset;
- important intermediate events;
- interventions;
- recoveries;
- external context.

Show enough to reconstruct reasoning.

Do not show irrelevant weekly churn.

---

# 123. Last Known Good visual comparison

For browser incidents:
the report should link/show:

```text
Last Known Good screenshot
vs
Incident screenshot
```

when visual difference matters.

This is one of the product's strongest explanations for non-technical users.

---

# 124. No visual hallucination

If automated image analysis is later used:
it can propose visual differences.

But event evidence should still reference:
- actual screenshots;
- geometry/state where available.

Do not let vision-only prose become technical truth without evidence.

---

# 125. Incident report revision

Reports are versioned.

New evidence can produce:
- new hypothesis rank;
- new confidence;
- new conclusion.

Never overwrite the old report.

Store:
- engine version;
- DOMAIN version;
- INCIDENTS version;
- connector evidence versions.

---

# 126. New evidence handling

When new data arrives:

Examples:
- GSC becomes final;
- GAM backfill completes;
- vendor outage published;
- rollback performed;
- next browser checkpoint arrives.

Re-evaluate if:
- active incident;
- important hypothesis may change;
- confidence may change materially.

Do not rerun all closed incidents continuously.

---

# 127. Incident resolution

Resolution means:
the operational symptom has ended or is accepted/closed.

Root cause can still be unresolved.

Valid:

```text
status = RESOLVED
conclusion = UNRESOLVED
```

Example:
site recovered after vendor service returned, but exact root cause never confirmed.

---

# 128. Closed unresolved

Use when:
- symptom ended;
- no more useful evidence;
- no safe test;
- business chooses to stop.

Preserve:
- candidates;
- ruled-out causes;
- unknowns;
- lessons.

Unresolved historical incidents are valuable future evidence.

---

# 129. Recovery verification

Do not resolve solely because someone says:

> "looks better."

Verify with relevant source.

Examples:

Ad request incident:
GPT/GAM request stage recovered.

Traffic incident:
GA4/GSC recover toward baseline.

Availability:
multiple successful checks.

Performance:
synthetic/field signal recover.

---

# 130. Recovery lag

Different mechanisms have different lag.

Store expected lag from DOMAIN/rule.

Examples:

```text
client-side script fix
→ minutes/hours

GAM report
→ source reporting delay

Search indexability
→ days/weeks possible
```

Do not reject a Search hypothesis because traffic failed to recover five minutes after fix.

---

# 131. Post-incident learning

When incident closes, record:

- confirmed/probable mechanism;
- rejected hypotheses;
- intervention outcome;
- actual recovery behavior;
- data that was missing;
- detection opportunities;
- false alerts;
- useful controls.

This updates **Publisher Memory**.

---

# 132. Publisher-specific learning

Future investigations can use prior private incidents.

Example:

> On this publisher, mobile article GPT initialization has failed twice after changes to script X.

This may increase prior relevance.

But:
publisher-specific precedent is still not proof.

---

# 133. Promotion into shared corpus

Do NOT automatically add a private publisher incident to shared INCIDENTS corpus.

Future process requires:
- permission;
- anonymization;
- evidence review;
- provenance;
- quality tier.

Private client data remains private by default.

---

# 134. Historical internal lesson — pre-existing decline

High-value pattern:

```text
decline begins
→ suspected vendor/integration introduced later
→ vendor blamed
→ vendor removed
→ decline continues
```

Incident rule:

A component introduced after measurable onset cannot explain initial onset.

If removal does not change the trajectory after plausible latency, reduce confidence further.

This pattern should exist in EVALS.

---

# 135. Historical internal lesson — broad shutdown destroys attribution

High-value pattern:

Publisher experiences traffic issue.

Many external monetization components are disabled simultaneously for an extended period.

Result:
- revenue is lost;
- root cause remains unresolved;
- causal attribution becomes worse because multiple variables changed together.

Incident rule:

Prefer narrow tests over broad shutdowns.

This pattern should exist in EVALS.

---

# 136. Incident corpus anti-bias rule

Corpus currently over-represents:
- Google platform events;
- Prebid client-side issues;

because those sources publish more.

Under-represents:
- proprietary SSP internals;
- publisher-specific config;
- closed-source players;
- commercial/operational incidents.

Therefore do not use:

```text
frequency in corpus
```

as a direct prior probability of real-world cause.

---

# 137. LLM architecture

The Incident Engine should have a deterministic evidence/reasoning core and an LLM synthesis layer.

Deterministic:
- source retrieval;
- data freshness;
- segmentation;
- window selection primitives;
- event retrieval;
- failure-mode mappings;
- score components;
- contradictions;
- evidence references;
- query allowlist;
- test safety.

LLM:
- compare narratives;
- explain mechanism;
- summarize;
- propose from allowed next-test patterns;
- produce human-readable report.

---

# 138. Incident context packet for LLM

Pass a bounded structured packet.

Example:

```yaml
incident:
  reported_symptom:
  observed_symptom:
  windows:
  scope:

data_quality:
  browser:
  ga4:
  gsc:
  gam:

metrics:
  - ...

timeline:
  - ...

candidate_hypotheses:
  - failure_mode:
    mechanism:
    score_components:
    expected_signals:
    evidence:
    contradictions:
    unknowns:

external_context:
  - ...

similar_incidents:
  - ...

allowed_next_tests:
  - ...
```

Do not send raw secrets or unbounded logs.

---

# 139. LLM output schema

Require structured output.

Conceptual:

```yaml
summary:
hypotheses:
  - id:
    rank:
    confidence:
    explanation:
    supporting_evidence_ids:
    contradicting_evidence_ids:
    observability_gaps:
recommended_next_test:
unknowns:
conclusion:
```

Application validates:
- evidence IDs exist;
- confidence allowed;
- no invented hypothesis IDs;
- no unsupported source claim.

---

# 140. Citation-to-evidence requirement

Every factual statement in generated incident report should be traceable internally to:
- evidence ID;
- event ID;
- metric point/series;
- artifact;
- source extract;
- external event.

User UI may render clickable evidence.

This is product-level provenance.

---

# 141. LLM disagreement with deterministic rank

If LLM narrative ranks a lower deterministic candidate first:

do not silently accept.

Options:
- reject output;
- ask model to re-evaluate against score/evidence;
- flag for human review.

Deterministic constraints win over prose preference unless the system explicitly records a reason to update the ranking.

---

# 142. LLM must not fill missing data

Examples prohibited:

- assuming bidder timeout because no bidder data;
- assuming Google update because traffic fell;
- assuming CMP version;
- assuming revenue loss amount;
- assuming rollback timing.

Use:
`unknown`.

---

# 143. Source-aware phrasing

Examples:

Browser:
> Our synthetic mobile checkpoint observed...

GA4:
> GA4 reported...

GSC:
> Search Console reported...

GAM:
> GAM reporting showed...

Manual:
> The publisher recorded...

External:
> Google's official status/update source reported...

This prevents source provenance from disappearing in prose.

---

# 144. Investigation latency

Product goal:
fast useful investigation.

Not:
instant fake certainty.

Target:
- triage within minutes;
- initial hypotheses after existing evidence retrieval;
- deeper report after bounded drill-down.

Do not block first answer waiting for every slow source if a partial answer with limitations is useful.

---

# 145. Progressive report

Incident UI may evolve:

## Initial
"Investigating — symptom confirmed."

## Early findings
"Request generation appears affected; checking consent/GPT."

## Full report
ranked hypotheses.

## Updated
after mature data/rollback.

But MVP may ship only:
- loading/progress;
- final versioned report.

Do not overbuild live-agent theatrics.

---

# 146. Search-specific time caution

Current Google Search guidance indicates analysis around core updates should compare suitable before/after periods and wait for the update rollout to complete before making some assessments.

Therefore:
- early incident report can flag overlap;
- later mature report may update after final data/rollout;
- do not declare core-update attribution during a few noisy hours.

---

# 147. Root-cause analysis is iterative

Mature troubleshooting practice is iterative:

```text
observe
→ hypothesize
→ test
→ update
```

Do not encode Incident Engine as:
one LLM call → final cause.

The system must support evidence revisions and hypothesis updates.

---

# 148. Mitigation versus diagnosis

Sometimes mitigation should happen before exact RCA.

Example:
site unavailable due obviously failing dependency.

Operator may restore service first.

Incident Engine should preserve:
- mitigation;
- symptom recovery;
- later root-cause analysis.

Do not require full root cause before recommending an obvious low-risk mitigation.

In MVP, recommendation remains human-executed.

---

# 149. Trigger vs root cause example

Example:

```text
latent player memory leak
+
traffic spike
→ player crash
```

Possible interpretation:

```text
root cause: player defect
trigger: traffic spike
```

This distinction can matter for prevention.

Do not blame ordinary traffic if the system should have handled it.

---

# 150. External outage example

Publisher:
ads not serving.

Evidence:
- browser GPT requests present;
- GAM official outage active;
- multiple ad-serving symptoms;
- local config unchanged;
- delivery recovers when outage resolves.

Potential:
PROBABLE/CONFIRMED external platform cause depending evidence.

Still store local symptom independently.

---

# 151. Consent example

Reported:
mobile monetization down.

Observed:
- GA4 mobile views stable;
- GPT expected slots stable;
- GAM requests/mobile article -22%;
- TCF errors begin same window;
- desktop unaffected;
- Accept path fails to produce expected request behavior.

Hypothesis:
Consent/TCF request eligibility issue.

Support:
multiple independent stages.

Contradiction:
none material.

Confidence:
PROBABLE; could become CONFIRMED after correction restores requests.

---

# 152. Search counterexample

Reported:
Search down after new player.

Observed:
- GSC decline begins 6 days before player deployment;
- pages without player affected similarly;
- player removed later;
- decline continues.

Player:
REJECTED / LOW RELEVANCE for onset.

This is precisely the behavior the engine must learn.

---

# 153. GAM direct counterexample

Reported:
programmatic revenue down.

Observed:
- direct/reserved delivery sharply up;
- total ad opportunities stable;
- programmatic share down;
- publisher direct campaign intentionally started.

Conclusion:
No strong evidence of ad-serving failure.

Programmatic displacement likely intentional.

Do not alert "monetization broken."

---

# 154. Measurement counterexample

Reported:
traffic down.

Observed:
- GA4 views down;
- GSC Search clicks stable;
- direct server/business evidence stable where available;
- analytics tag behavior changed after deploy.

Hypothesis:
Measurement issue.

Do not count GA4 decline itself as independent proof of traffic loss.

---

# 155. Performance counterexample

Observed:
synthetic CLS worse once.

Field:
stable.

Browser:
different creative/layout random variation.

Conclusion:
insufficient persistence.

Do not create ranking/UX root-cause claim.

---

# 156. Hypothesis status

Possible internal status:

```text
CANDIDATE
ACTIVE
DEPRIORITIZED
REJECTED
CONFIRMED
SUPERSEDED
```

Confidence is separate.

Example:
a hypothesis can be ACTIVE + POSSIBLE.

---

# 157. Rejection criteria

A candidate may be REJECTED when:

- impossible timing;
- direct technical proof against;
- repeated controlled test falsifies;
- expected component absent;
- unaffected controls contradict mechanism;
- removal/recovery evidence strongly disproves.

Use REJECTED carefully.

"Not enough evidence" = deprioritized/unknown, not rejected.

---

# 158. Deprioritized

Use when:
- weaker than alternatives;
- insufficient evidence;
- partial segment mismatch;
- mechanism plausible but unsupported.

Deprioritized candidates can return later.

---

# 159. Incident evidence graph

Logical graph:

```text
EVENTS / METRICS / CHANGES / EXTERNAL
        ↓
EVIDENCE ITEMS
        ↓
SUPPORTS / CONTRADICTS
        ↓
HYPOTHESES
        ↓
INCIDENT REPORT
```

Use Postgres relational tables.

No graph DB.

---

# 160. Evidence chains

A chain is a sequence of mechanism-consistent evidence.

Example:

```text
CMP readiness changed
→ TCF error appeared
→ expected GAM request missing
→ GAM requests/view fell
→ programmatic impressions fell
```

The engine should explicitly show the chain.

Chains make complex reasoning understandable to non-technical users.

---

# 161. Evidence chain gaps

If chain is:

```text
CMP changed
→ ?
→ revenue down
```

call out missing stage.

Maybe:
GAM requests are unavailable.

This lowers confidence.

Do not fill the gap with assumption.

---

# 162. Evidence chain forks

A symptom can have multiple upstream branches.

Example:

```text
revenue down
├── traffic down
├── requests/view down
└── eCPM down
```

Each branch can contribute.

Incident report should show contribution conceptually.

Do not force one linear chain.

---

# 163. Incident ranking output

Internal:

```yaml
hypothesis_rank:
  1:
    failure_mode: F-CMP-003
    confidence: PROBABLE
    score:
    evidence_count:
    contradictions:
  2:
    failure_mode: F-HB-002
    confidence: POSSIBLE_CONTRIBUTOR
  3:
    failure_mode: F-GAM-006
    confidence: LOW_RELEVANCE
```

UI can display top 3.

---

# 164. Confidence downgrade conditions

Downgrade when:
- source preliminary;
- onset uncertain;
- candidate time uncertain;
- hidden server-side mechanism;
- no control;
- no intermediate evidence;
- corpus only;
- conflicting sources;
- low volume.

A beautiful mechanism with poor local evidence stays POSSIBLE.

---

# 165. Confidence upgrade conditions

Upgrade when:
- exact error matches mechanism;
- multiple independent sources;
- same-segment match;
- repeated reproduction;
- control difference;
- targeted rollback;
- expected recovery;
- vendor/platform confirmation plus local match.

---

# 166. Evidence maturity

If report produced while data preliminary:
label hypothesis:

```text
PROVISIONAL
```

internally if useful.

User-facing:
> Based on preliminary GAM/GSC data.

When mature data arrives:
recompute if material.

Do not silently change report.

---

# 167. Incident SLA semantics

MVP should not promise universal root-cause SLA.

Possible product measures:
- time to symptom localization;
- time to first useful hypothesis;
- time to confident conclusion;
- time to resolution.

The strongest initial KPI:
**Mean Time To Investigate**.

---

# 168. Incident observability score

Optional internal summary:

```text
HIGH
MEDIUM
LOW
```

based on required sources available.

Example:
Search incident with GA4+GSC+browser:
HIGH/MEDIUM.

Monetization incident without GAM:
LOW/MEDIUM.

This explains why confidence may be limited.

Do not confuse with incident severity.

---

# 169. Unknown commercial context

The platform may not know:
- booked direct price;
- invoice adjustments;
- sponsorship;
- sales commitments.

When relevant:
ask user for context or state limitation.

Do not invent business economics.

---

# 170. Human clarification

Avoid unnecessary questions.

The engine should first use available data.

Ask only when a missing human fact materially changes investigation.

Examples:
- "Was a direct campaign launched?"
- "Was the reported decline in invoiced revenue or GAM revenue?"
- "Was this player change intentional?"

Do not ask the user to repeat data already observable.

---

# 171. Incident comments/notes

Operators may add:
- vendor answer;
- test result;
- commercial context;
- deployment note.

These become manual evidence.

They should be timestamped and attributed.

Manual note is not automatically confirmed fact.

---

# 172. Incident attachments

User may attach:
- screenshot;
- vendor email;
- Google notice.

Store as incident artifact/manual evidence.

Do not parse unsupported conclusions from an image/document without preserving source.

Future extraction can produce derived evidence linked to original artifact.

---

# 173. Postmortem

After significant incidents, platform may generate a lightweight postmortem.

Sections:
- impact;
- timeline;
- trigger;
- root cause/contributors;
- mitigation;
- resolution;
- what went well;
- what made diagnosis hard;
- prevention/detection actions;
- unresolved items.

Postmortem is future/secondary MVP functionality.

Incident investigation data model already supports it.

---

# 174. Blameless language

Reports should focus on:
- system state;
- change;
- process;
- evidence.

Avoid:
> Developer X broke revenue.

Prefer:
> The article-template deployment introduced a configuration in which two expected GPT slots were no longer defined.

Actor attribution can exist separately.

---

# 175. Prevention learning

If root cause confirmed:
generate follow-up candidate:

```text
Could we detect this earlier next time?
```

Examples:
- stronger critical event;
- new canary scenario;
- missing connector;
- new event rule;
- new eval;
- better expected-state model.

This creates compounding product value.

---

# 176. New failure mode discovery

If an incident reveals a mechanism absent from DOMAIN:

1. mark as new/unknown mechanism;
2. preserve incident;
3. human/research review;
4. update DOMAIN;
5. add event logic if observable;
6. add EVAL;
7. version knowledge.

Do not silently allow LLM-learned folklore into canonical rules.

---

# 177. Incident-to-eval pipeline

Every high-quality resolved incident should produce one or more evals.

Types:

```text
positive diagnosis
counterexample
unresolved
rollback/recovery
measurement divergence
external-event attribution
```

This is how the Incident Engine improves safely.

---

# 178. Required positive evals

At minimum:

1. accidental noindex;
2. broad robots block;
3. expected slot removed;
4. JS blocks GPT initialization;
5. TCF issue reduces GAM requests;
6. bidder timeout spike;
7. Prebid targeting missing;
8. floor-driven fill change;
9. direct campaign displacement;
10. GA4 measurement break;
11. VAST/render failure;
12. site/CDN outage.

---

# 179. Required counterexample evals

1. Google update starts after decline;
2. CMP version changes but behavior stable;
3. eCPM down while monetization/value stable or up;
4. direct campaign displaces programmatic;
5. ads.txt changes but seller unused;
6. one JS error on unaffected widget;
7. synthetic CWV worse but field stable;
8. vendor suspected but unaffected publisher/control evidence contradicts universal outage;
9. suspected component introduced after decline began;
10. suspected component removed but decline persists.

---

# 180. Required unresolved evals

Include cases where:
- two hypotheses fit equally;
- source unavailable;
- server-side mechanism hidden;
- Search decline has no strong local cause;
- event correlation exists without mechanism proof.

Engine fails if it always picks a cause.

---

# 181. Incident Engine implementation milestones

## I1 — Intake + windows + localization

Implement:
- incident creation;
- reported onset;
- data readiness;
- baseline/pre/incident windows;
- affected segments.

No LLM root-cause yet.

## I2 — Evidence pack

Implement:
- relevant events;
- metrics;
- Last Known Good;
- source limitations;
- external events.

## I3 — Deterministic candidate generation

Map:
- symptom;
- first broken stage;
- DOMAIN failure modes;
- incident patterns.

## I4 — Evidence scoring + contradiction engine

Implement:
- temporal;
- segment;
- mechanism;
- intermediate evidence;
- controls;
- contradiction penalties.

## I5 — Report synthesis

Use LLM on structured packet.

Validate evidence references.

## I6 — Counterfactual tests

Read-only synthetic/browser and validated connector drill-down.

Human production actions only.

## I7 — Revisions/recovery

New evidence;
rollback outcomes;
report revisions;
resolution.

Do not start with autonomous agents.

---

# 182. Acceptance criteria

INCIDENT v1 is acceptable when:

1. user can submit a vague symptom without diagnosing it;
2. reported symptom and observed symptom remain distinct;
3. approximate onset remains approximate;
4. engine constructs an appropriate baseline;
5. baseline contamination can be detected;
6. incident windows vary by symptom type;
7. source health/freshness gates reasoning;
8. missing data is not zero;
9. symptom is localized before cause ranking;
10. unaffected segments are used as controls;
11. measurement problems are considered explicitly;
12. Last Known Good is incident/scope-specific;
13. candidate hypotheses come from DOMAIN/events/changes/external/corpus;
14. corpus frequency is never treated as prevalence;
15. every top hypothesis has a mechanism;
16. every top hypothesis lists expected intermediate signals;
17. timing uncertainty is preserved;
18. onset-before-candidate strongly penalizes causality;
19. persisted-after-removal reduces primary-cause confidence when recovery lag permits;
20. rollback/recovery can materially increase confidence;
21. evidence can support or contradict hypotheses;
22. missing evidence differs from contradicting evidence;
23. independent evidence is not double-counted;
24. downstream metric effects are not counted as independent causes;
25. multi-causal incidents are supported;
26. external events remain context until local match;
27. server-side/hidden observability lowers confidence;
28. LLM cannot invent source evidence;
29. LLM cannot execute arbitrary connector queries;
30. counterfactual tests are bounded/read-only by default;
31. recommendations state predicted outcomes;
32. no production write action is automatic;
33. user-facing confidence is qualitative;
34. internal score is auditable/versioned;
35. UNRESOLVED is a valid outcome;
36. No Strong Local Cause is representable;
37. reports list supporting and contradicting evidence;
38. reports list unavailable sources/unknowns;
39. report revisions do not overwrite history;
40. incident can resolve without confirmed root cause;
41. resolved incidents feed publisher memory;
42. high-quality incidents can become evals;
43. private incidents are not shared automatically;
44. root cause, trigger and contributor can be distinguished;
45. source-aware language is used;
46. all material report claims trace to evidence IDs;
47. Search reasoning avoids hidden-algorithm claims;
48. raw GAM revenue is not business truth;
49. synthetic browser evidence is not universal user truth;
50. the engine can demonstrably reject a superficially plausible wrong cause.

---

# 183. Codex rules for incident work

Codex MUST:

- read canonical `DOMAIN.md`;
- read `EVENTS.md`;
- read `CONNECTORS.md`;
- read current `INCIDENTS.md` corpus summary;
- preserve evidence provenance;
- preserve time uncertainty;
- construct baseline before ranking;
- use affected/unaffected segments;
- check measurement integrity;
- generate mechanism-based hypotheses;
- search for contradictions;
- version scoring rules;
- validate LLM evidence IDs;
- make safe read-only drill-down explicit;
- record observability gaps;
- support UNRESOLVED;
- add evals for every new reasoning rule;
- record material semantic decisions in `DECISIONS.md`.

Codex MUST NOT:

- infer cause from chronology alone;
- use incident corpus count as causal prior;
- make an external Google event the root cause automatically;
- treat a user report as already verified;
- treat stale/missing data as zero;
- treat raw total GAM revenue as business truth;
- infer hidden SSP/DSP/Google internals;
- create fake numeric confidence;
- suppress contradicting evidence from the report;
- change production configuration;
- allow LLM free-form API execution;
- overwrite historical reports;
- merge private publisher incidents into shared corpus automatically.

---

# 184. Operational references

The reasoning philosophy is aligned with mature troubleshooting/incident-management practice.

Google SRE's effective troubleshooting model emphasizes:
- observing system behavior;
- hypothesizing causes;
- testing hypotheses;
- iterating until the cause is sufficiently understood.

Google SRE incident-management material separates incident mitigation from deeper root-cause/postmortem analysis and emphasizes structured process.

Google's newer SRE material on AI-assisted operations describes an incident hypothesis as a credible lead that should include concrete verification steps rather than an ungrounded answer.

Google Search Central's current traffic-drop guidance explicitly treats Search declines as potentially caused by multiple classes such as technical issues, algorithmic changes, seasonality/demand and site changes; this reinforces the product rule that a Google update is context rather than automatic attribution.

Primary references:
- https://sre.google/sre-book/effective-troubleshooting/
- https://sre.google/workbook/incident-response/
- https://sre.google/resources/practices-and-processes/incident-management-guide/
- https://sre.google/resources/practices-and-processes/ai-engineering-reliable-operations/
- https://developers.google.com/search/docs/monitor-debug/debugging-search-traffic-drops
- https://developers.google.com/search/docs/appearance/core-updates

Current platform-specific mechanism knowledge remains in `DOMAIN.md`.

---

# 185. Final Incident Engine principle

The Incident Engine succeeds when it can turn:

> **"Something got worse around last Tuesday."**

into:

> **"This is what actually changed, this is the affected scope, these are the explanations that fit the mechanism and timing, this is the evidence against them, this is what we cannot observe, and this is the smallest test that would most reduce uncertainty."**

It does not need to sound certain.

It needs to be **correctly uncertain**.

# **Find the first broken link. Follow the evidence chain. Try to falsify the leading explanation. Never manufacture a root cause just to complete the report.**
