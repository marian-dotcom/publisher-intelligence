# EVENTS.md
## Semantic Event Engine Specification
### Publisher Incident Intelligence Platform — v1.0

**Audience:** Codex, backend engineering, product, technical reviewers  
**Status:** MVP implementation contract  
**Depends on:** `DOMAIN.md`, `BROWSER.md`, `DATA_MODEL.md`, `PRODUCT.md`, `MVP.md`  
**Feeds:** Timeline, Alerting, Weekly Brief, `INCIDENT.md`, `EVALS.md`

---

# 0. Purpose

The Event Engine converts a continuous stream of raw observations into a small, useful, auditable operational history.

Its job is to answer:

> **What meaningful thing changed, started, stopped, degraded, recovered or happened around the publisher?**

It sits between collection and incident reasoning.

```text
Browser / GA4 / GSC / GAM / public config / external sources / manual changes
        ↓
raw observations + metrics + source facts
        ↓
normalization
        ↓
semantic comparison
        ↓
persistence / corroboration / baseline checks
        ↓
EVENT
        ↓
Timeline / Alerts / Weekly Brief / Incident Engine
```

The Event Engine does **not** determine root cause.

It detects facts and meaningful conditions that may later become evidence.

---

# 1. Non-negotiable invariants

Codex MUST preserve these rules unless `DECISIONS.md` explicitly changes them.

## EVENT-INV-001 — Metric is not event

```text
mobile_fill = 53%
```

is a metric.

```text
mobile_fill_below_baseline
```

may be an anomaly/event.

Do not store every metric point as an event.

## EVENT-INV-002 — State is not event

```text
robots.txt currently contains Disallow
```

is state.

```text
broad robots block was added
```

is an event.

## EVENT-INV-003 — Event is not incident

```text
GPT slot article_mid_2 disappeared
```

is an event.

```text
mobile monetization has been lower since Aug 10
```

is an incident.

An event can exist when no incident exists.

## EVENT-INV-004 — Event is not cause

A script being added before a traffic decline does not mean:

```text
script caused traffic decline
```

The Incident Engine decides causal relevance.

## EVENT-INV-005 — Evidence first

Every automatically derived event MUST link back to source evidence.

No event may exist only because an LLM said it happened.

## EVENT-INV-006 — Deterministic event creation

Initial event detection MUST be deterministic/rule-based.

LLMs MAY:
- rewrite event summaries;
- classify ambiguous text after deterministic evidence exists;
- assist with low-risk labeling.

LLMs MUST NOT:
- invent the event;
- invent the timestamp;
- invent severity;
- invent persistence;
- invent source evidence.

## EVENT-INV-007 — Preserve uncertainty

If the exact change time is not observable, the platform MUST represent an occurrence window.

Do not create false timestamp precision.

## EVENT-INV-008 — Quiet by default

Most observations MUST NOT become alerts.

Most raw diffs MUST NOT even become events.

## EVENT-INV-009 — Recomputable

Event logic is derived logic.

Source evidence remains immutable.

If event rules change:
- recompute;
- version;
- supersede old derived events if necessary;
- never alter the underlying evidence.

## EVENT-INV-010 — KISS

Do not build:
- CEP engines;
- Kafka Streams;
- generic rule-builder UIs;
- graph databases;
- ML anomaly platforms;
- LLM-first event classification;

for the MVP.

Python services + PostgreSQL are sufficient.

---

# 2. Why an Event Engine exists

A publisher page changes constantly.

Raw browser diffs may include:
- article text;
- recommendation ordering;
- timestamps;
- creative URLs;
- auction IDs;
- session IDs;
- cache-busters;
- rotating content;
- ads from different buyers.

If every raw difference enters Timeline, Timeline becomes useless.

The Event Engine exists to compress:

```text
millions of raw values
```

into:

```text
a few meaningful operational facts
```

Examples:

Noise:

```text
script URL query changed from ?cb=9812 to ?cb=1293
```

Meaningful:

```text
a new third-party script dependency appeared on the article template
```

Noise:

```text
current creative is different
```

Meaningful:

```text
expected GPT slot disappeared on mobile article pages
```

---

# 3. Event processing pipeline

The canonical pipeline is:

```text
SOURCE EVIDENCE
    ↓
NORMALIZATION
    ↓
ENTITY RESOLUTION
    ↓
COMPARABLE-STATE SELECTION
    ↓
SEMANTIC DIFF / BASELINE TEST
    ↓
EVENT CANDIDATE
    ↓
CONFIRMATION
    ↓
AGGREGATION / DEDUPLICATION
    ↓
SEVERITY + RISK
    ↓
PERSISTED EVENT
    ↓
ROUTING
```

Routing means:
- Timeline;
- immediate alert;
- Weekly Brief eligibility;
- Incident Engine retrieval.

The candidate stage does not require a permanent database table in MVP.

---

# 4. Source classes

Events can originate from different evidence classes.

## BROWSER

Examples:
- slot disappeared;
- JS error started;
- CMP API missing;
- sticky player appeared;
- page unavailable.

## METRIC

GA4, GSC, GAM.

Examples:
- Search impressions below baseline;
- GAM requests below baseline.

## PUBLIC_CONFIG

Examples:
- robots changed;
- ads.txt became empty.

## CONNECTOR_CONFIGURATION

Examples:
- GAM pricing rule/config change where accessible.

## EXTERNAL_OFFICIAL

Examples:
- Google Core Update;
- GAM incident;
- CDN incident.

## MANUAL

Examples:
- deployment;
- rollback;
- direct campaign launch;
- vendor change.

## DERIVED_CROSS_SOURCE

A small number of useful derived facts may combine multiple sources.

Example:
`ANALYTICS_MEASUREMENT_DIVERGENCE`

But cross-source derived events MUST remain factual and must not become causal conclusions.

---

# 5. Event kinds

Every event definition belongs to one semantic kind.

## STATE_CHANGE

A durable observable state changed.

Examples:
- script added;
- slot removed;
- canonical changed.

## CONDITION

A meaningful condition began and can later resolve.

Examples:
- site unavailable;
- dependency failing;
- GAM requests below baseline.

## EXTERNAL

An ecosystem/platform event.

Example:
- Google Core Update rollout.

## OPERATIONAL

A known human/vendor change.

Example:
- deployment recorded.

## RULESET

A standard/policy rule changed.

Example:
- TCF transition deadline/ruleset change.

These kinds drive lifecycle and timing behavior.

---

# 6. Event time semantics

This is critical.

The system has three different time concepts.

## occurred / started

When the event actually happened or began.

## detected

When our platform recognized it.

## created

When the DB row was written.

They are not interchangeable.

---

# 7. Temporal uncertainty for checkpoint-derived changes

Suppose:

```text
12:00 checkpoint → slot present
18:00 checkpoint → slot absent
```

We do **not** know the exact removal time.

The event occurrence is bounded:

```text
occurred_after_at  = 12:00
occurred_before_at = 18:00
time_precision     = WINDOW
```

The Timeline SHOULD display:

> Slot removed **between 12:00 and 18:00**

not:

> Slot removed at 18:00

`started_at` can remain the first observed new state for sorting, but the user-facing semantics MUST preserve the interval.

---

# 8. Time precision values

Use:

```text
EXACT
WINDOW
SOURCE_REPORTED
APPROXIMATE
UNKNOWN
```

Examples:

### EXACT
Manual deployment timestamp from CI/CD or explicit browser event timestamp.

### WINDOW
Detected only between two periodic checkpoints.

### SOURCE_REPORTED
Google says update started on date/time X.

### APPROXIMATE
User says "around 4 August."

Approximate incident time belongs primarily to `INCIDENT.md`, but event relations must understand it.

---

# 9. Comparable-state selection

A diff is meaningful only between comparable observations.

For browser state, compare in this order:

1. previous successful comparable run for same monitored URL + same scenario;
2. if URL rotated, previous comparable run for same template + same scenario;
3. configured/template expected state where applicable.

Do NOT compare:
- mobile to desktop;
- Accept to Reject;
- old browser profile to a new profile without accounting for version;
- healthy structural state to a browser crash.

---

# 10. Comparable run status

For structural diffing:

Usually valid:
- COMPLETE;
- PARTIAL if the relevant collector succeeded.

Usually invalid:
- BROWSER_ERROR;
- TIMEOUT before relevant state;
- BLOCKED if the block changed observability.

`SITE_ERROR` is evidence for availability but not a valid structural baseline for slot/script comparison.

Collector-level status matters more than whole-run status when only one collector is relevant.

---

# 11. Collector-version comparability

Before generating a state-change event, compare:

```text
collector_version
normalizer_version
scenario_version
browser profile
```

If the relevant collector/normalizer changed, the system must ask:

> Could this diff be generated by our software change?

Options:

1. suppress event until validation;
2. mark event `observer_change_possible`;
3. compare via compatibility adapter;
4. run reference validation.

Never silently treat our own parser upgrade as a publisher deployment.

---

# 12. Normalization

The Event Engine consumes normalized observations.

Normalization must remove known volatility.

Examples normally ignored:
- cache-buster;
- auction ID;
- session ID;
- creative URL;
- recommendation order;
- article text;
- timestamp;
- random DOM IDs.

Examples normally preserved:
- dependency identity;
- expected slot identity;
- player identity;
- CMP behavior;
- robots/noindex/canonical;
- sticky/fixed layout behavior;
- persistent JS errors;
- GPT lifecycle;
- Prebid timeout/config;
- network failure pattern.

The normalization version is part of evidence provenance.

---

# 13. Semantic diff types

MVP needs a small set of reusable diff operators.

## PRESENCE_CHANGE

```text
ABSENT → PRESENT
PRESENT → ABSENT
```

## VALUE_CHANGE

```text
canonical A → canonical B
timeout 1200 → 700
```

## SET_CHANGE

```text
bidders {A,B,C} → {A,C}
```

## STAGE_CHANGE

```text
GPT requested → no longer requested
```

## STATUS_CHANGE

```text
dependency OK → failing
```

## STRUCTURAL_CHANGE

Normalized DOM/template structure changed materially.

## BASELINE_DEVIATION

Metric/runtime numeric signal departs from baseline.

Do not create a unique algorithm for every event when a small operator vocabulary suffices.

---

# 14. Event candidate

A semantic diff becomes an event candidate.

Candidate contains at minimum:

```yaml
event_code:
site_id:
subject_entity:
scope:
before:
after:
source_evidence:
time_window:
rule_version:
```

A candidate is not yet necessarily persisted.

It must pass:
- confirmation;
- noise suppression;
- aggregation;
- event-definition-specific rule.

---

# 15. Confirmation modes

Every event definition MUST declare a confirmation mode.

Allowed MVP modes:

```text
SINGLE_STRONG_OBSERVATION
IMMEDIATE_SECOND_CHECK
TWO_CONSECUTIVE_CHECKPOINTS
MULTI_URL_CORROBORATION
TEMPLATE_MAJORITY
STATISTICAL_PERSISTENCE
EXTERNAL_OFFICIAL
MANUAL
```

These are deterministic strategies.

---

# 16. SINGLE_STRONG_OBSERVATION

Use only where the observation itself is strong and low-noise.

Examples:
- canonical changed;
- Prebid configured timeout changed;
- script dependency added;
- official external event ingested.

This does not mean immediate alert.

Confirmation and notification are separate decisions.

---

# 17. IMMEDIATE_SECOND_CHECK

Use for high-severity conditions where waiting six hours is unacceptable but a false positive would be harmful.

Examples:
- site unavailable;
- broad noindex;
- broad robots block;
- widespread expected ad-slot disappearance.

Flow:

```text
primary observation
→ out-of-band validation run/fetch
→ confirm
→ event/alert
```

The validation run does NOT replace the scheduled six-hour checkpoint.

Both remain evidence.

---

# 18. TWO_CONSECUTIVE_CHECKPOINTS

Use for noisy runtime conditions.

Examples:
- isolated dependency latency regression;
- synthetic performance regression;
- some JS error families.

At six-hour cadence this can imply long confirmation delay.

Therefore it is not appropriate for every critical event.

---

# 19. MULTI_URL_CORROBORATION

Useful for template-level changes.

Example:

```text
3 article URLs all missing expected slot
```

is much stronger evidence of a template change than:
one rotating article URL missing it once.

---

# 20. TEMPLATE_MAJORITY

For a template with multiple representative URLs:

```text
affected_urls / valid_urls >= configured threshold
```

can promote a template-wide event.

Do not hard-code 50%, 67% or another percentage globally.

Initial thresholds live in versioned configuration and require pilot calibration.

---

# 21. STATISTICAL_PERSISTENCE

For time-series anomalies.

Requires:
- minimum volume;
- baseline;
- deviation;
- persistence;
- data freshness.

Example:

```text
GAM mobile requests
below robust hour-of-week baseline
for N consecutive comparable buckets
```

An anomaly can later resolve.

---

# 22. External official confirmation

Official external sources can create event records without local publisher corroboration.

Example:

```text
GOOGLE_CORE_UPDATE
```

But local relevance is separate.

The external event may appear in Timeline as context.

It must not become:
`Google caused traffic decline`.

---

# 23. Manual events

Human/operator-provided changes are preserved as operational evidence.

Examples:
- deployment;
- direct campaign start;
- player migration;
- rollback.

Manual provenance must be explicit.

Manual does not mean automatically correct.

A human can misremember scope/time.

---

# 24. Event scope

Every event MUST carry normalized scope.

Scope can include:

```yaml
site:
templates:
devices:
countries:
traffic_channels:
search_type:
ad_units:
formats:
demand_channels:
bidders:
consent_scenario:
browser_scenario:
```

Only include dimensions actually supported by evidence.

Do not infer:
`site-wide`
from one URL.

---

# 25. Scope hierarchy

Use the narrowest evidence-supported scope.

Example:

Observed:
two mobile article URLs affected.

Valid:

```text
template = article
device = mobile
```

Not valid yet:

```text
site-wide
```

If later desktop + categories + homepage are affected, an aggregate event may broaden the scope.

---

# 26. Blast radius

Blast radius is the extent of observed affected scope.

Suggested ordinal:

```text
0 = isolated
1 = one URL/entity
2 = one template/segment
3 = multiple key templates/segments
4 = site-wide/core
```

This is an internal operational factor.

It is not causal confidence.

---

# 27. Observation confidence

Event observation confidence describes confidence that the **event happened**, not confidence that it caused anything.

Values:

```text
HIGH
MEDIUM
LOW
```

### HIGH
Direct platform/browser/API evidence with stable semantics.

### MEDIUM
Derived from deterministic inference with some observability gaps.

### LOW
Heuristic classification such as visual/policy risk.

Do not confuse with Incident hypothesis confidence.

---

# 28. Event lifecycle

There are two main lifecycle styles.

## POINT EVENT

A change occurred.

Examples:
- script added;
- canonical changed;
- deployment recorded.

Status:

```text
RECORDED
```

Point events do not "resolve."

A reverse change produces another event.

Example:

```text
SCRIPT_DEPENDENCY_ADDED
...
SCRIPT_DEPENDENCY_REMOVED
```

## CONDITION EVENT

A condition begins and later ends.

Examples:
- site unavailable;
- GAM requests below baseline;
- JS error persists.

Status:

```text
ACTIVE
RESOLVED
SUPERSEDED
```

---

# 29. Resolving condition events

Repeated checkpoints supporting the same active condition MUST NOT create a new event every six hours.

Instead:
- link new evidence to active event;
- update latest evidence metadata;
- keep event ACTIVE.

When recovery rule passes:
- set `ended_at`;
- mark RESOLVED;
- link recovery evidence.

Derived event state can be updated narrowly because raw evidence remains immutable.

Do not rewrite what originally triggered the event.

---

# 30. Event deduplication key

Conceptual dedupe key:

```text
site
+ event_code
+ subject_entity
+ normalized_scope
+ active_condition_identity
```

Examples:

One active:

```text
GAM_REQUESTS_BELOW_BASELINE / mobile / site
```

not four events/day.

One point event per semantic transition:

```text
SCRIPT_X ADDED
```

A future remove and re-add are separate transitions.

---

# 31. Aggregation

Raw evidence can produce one higher-level event.

Example:

```text
article URL A → slot missing
article URL B → slot missing
article URL C → slot missing
```

Persist preferably:

```text
GPT_EXPECTED_SLOT_MISSING
scope = article/mobile
affected_urls = 3
```

with three source evidence refs.

Do not clutter Timeline with three nearly identical event rows unless URL-level detail is materially useful.

---

# 32. Parent/child event policy

Do not create a complex event hierarchy in MVP.

Prefer:
- one aggregated event;
- evidence references to individual observations.

If later we need child events for separate entity resolution, event relations can represent them.

KISS.

---

# 33. Severity

User-facing event severity:

```text
INFO
LOW
MEDIUM
HIGH
CRITICAL
```

Severity describes operational risk/importance.

It does not mean:
- causal confidence;
- business loss amount;
- alert delivery automatically.

---

# 34. Severity factors

The deterministic severity model can consider:

1. domain criticality;
2. blast radius;
3. magnitude;
4. persistence;
5. observation confidence.

Separate routing factors:
6. actionability;
7. novelty;
8. publisher importance/configuration.

Do not mix everything into one opaque "AI severity."

---

# 35. Domain criticality

Suggested ordinal:

```text
0 = informational
1 = low-impact component
2 = operationally important
3 = core acquisition/monetization/UX
4 = availability/indexability/core serving
```

Examples:

Broad noindex:
4.

One social widget error:
0–1.

One expected mid-article ad slot removed:
2–3 depending on scope.

---

# 36. Magnitude

Magnitude is event-specific.

Examples:

Traffic:
relative + absolute change.

Slots:
number/proportion of expected slots affected.

Site availability:
fraction of representative pages failing.

JS:
number of templates / persistence.

Performance:
difference vs baseline.

Do not use one global percentage formula for every domain.

---

# 37. Internal event risk score

`events.risk_score` MAY be populated by a simple versioned deterministic formula for sorting.

It is NOT a probability.

Initial conceptual components:

```text
domain_criticality
blast_radius
magnitude
persistence
observation_confidence
```

The exact weights belong in an event-rule version and should be easy to change.

UI should primarily show qualitative severity.

If we cannot explain the score components, do not use the score.

---

# 38. Alertability is separate from severity

A HIGH event may not require immediate notification.

Example:
an official Google Core Update starts.

Potentially HIGH relevance as context,
but no action is required immediately if publisher metrics are healthy.

Conversely:
a broad noindex may require immediate action.

Therefore:

```text
severity != alert
```

---

# 39. Immediate-alert rule

Immediate alert requires all relevant conditions:

1. material symptom/risk;
2. sufficient evidence;
3. meaningful scope;
4. actionable or urgent verification;
5. not known intentional/acknowledged behavior;
6. not duplicate alert noise.

Google SRE guidance emphasizes alerting on meaningful user-facing symptoms and making alerts actionable rather than paging on every possible internal cause. This product follows the same principle.

---

# 40. Immediate critical candidates

Default candidates:

- site unavailable;
- broad noindex;
- broad robots block;
- widespread expected slot disappearance;
- severe persistent ad-request/delivery collapse;
- CMP runtime unavailable across important scope;
- explicit severe serving restriction/policy signal;
- severe persistent performance/UX regression.

Each still requires its event-specific confirmation rule.

---

# 41. Never immediate-alert by itself

By default, do NOT immediate alert solely because of:

- raw total GAM revenue move;
- routine ads.txt change;
- one JS error;
- one failed third-party pixel;
- short eCPM fluctuation;
- one synthetic performance outlier;
- Google Core Update announcement;
- content/headline changes;
- recommendation changes.

These may enter Timeline or Weekly Brief.

---

# 42. Alert validation job

For critical browser/public-config observations, the Event Engine MAY schedule a lightweight validation job.

Examples:

### Broad noindex
Check:
- same page second run;
- second representative URL/template;
- raw HTML/rendered meta.

### Site unavailable
Check:
- lightweight HTTP fetch;
- second browser attempt;
- another key URL.

### Expected slots missing
Check:
- second article URL;
- fresh context;
- same scenario.

A validation job exists to prevent false pages, not to erase the original failure.

---

# 43. Acknowledged intentional changes

A publisher/operator may mark an event/change as intentional.

Intentional does NOT mean delete it.

It can affect routing:

```text
timeline: keep
weekly brief: suppress or demote
immediate alert: suppress if safe
incident engine: retain as evidence
```

The event remains valuable historical memory.

---

# 44. Noise suppression

Suppress from user-facing Timeline by default:

- volatile content;
- one-off creative changes;
- cache IDs;
- random JS console warnings;
- known harmless third-party transient failures;
- low-volume metric noise;
- expected scenario differences;
- observer/collector implementation diffs.

Raw evidence still exists.

---

# 45. Unknown / unclassified change

Do not force every semantic diff into a known category.

If a meaningful structural change cannot be classified:

```text
STRUCTURAL_CHANGE_DETECTED
```

may be used with MEDIUM/LOW confidence.

But this should be uncommon.

The system should prefer a precise observed fact over a vague event.

---

# 46. A/B tests and partial exposure

If two clean synthetic sessions receive different states:
do not immediately create a global change event.

Potential handling:

```text
VARIANT_INSTABILITY_DETECTED
```

or event scope:
`partial exposure`.

Evidence that a change appears in an experiment variant must not be reported as site-wide deployment unless supported.

---

# 47. Browser observer failures

Internal monitor failures are not publisher events.

Examples:
- Chromium crashed;
- object storage unavailable;
- parser bug.

They belong to internal platform observability.

A `BROWSER_ERROR` must not become:

```text
SITE_UNAVAILABLE
```

This distinction is mandatory.

---

# 48. Site errors

If browser/network evidence shows:
- 500;
- 502;
- 503;
- DNS failure from publisher path;
- page timeout attributable to site/dependency;

that can create publisher event candidates.

Retries do not erase the original evidence.

---

# 49. Data-source freshness gate

Metric anomalies require source freshness.

If GAM/GA4/GSC data is stale or extraction failed:

Do NOT create:

```text
TRAFFIC_DOWN
```

from missing data.

Create/route a source-health issue instead:

```text
DATA_SOURCE_STALE
CONNECTOR_EXTRACTION_FAILED
```

These are primarily platform/data-quality events, not proof of publisher business degradation.

---

# 50. Missing versus zero

Mandatory rule:

```text
missing data != zero
```

Examples:

No GAM extract:
not `requests = 0`.

No GSC row:
not necessarily zero Search activity.

No bidder visibility:
not bidder absent.

Event logic must use explicit source status.

---

# 51. Metric anomaly engine

Initial anomaly detection SHOULD remain robust and simple.

Useful primitives:
- rolling median;
- same hour-of-week baseline;
- percentage deviation;
- MAD / robust dispersion;
- minimum-volume gate;
- persistence;
- missingness.

Do not start with opaque ML anomaly detection.

---

# 52. Metric baseline selection

For publisher metrics, prefer comparable periods.

Examples:

Programmatic:
same hour-of-week and recent comparable weekdays.

Traffic:
same hour/day pattern, plus source/device/template segment.

Search Console:
daily/appropriate source cadence, accounting for reporting delay.

Do not compare:
Monday 09:00 with Sunday 03:00
and call the difference anomalous.

---

# 53. Minimum-volume gate

Percentage movement on tiny volume is noisy.

Example:

```text
2 → 1 = -50%
```

may be irrelevant.

Every metric anomaly rule SHOULD include:
- minimum current/baseline volume;
- or an absolute impact gate.

Thresholds are publisher/metric-specific configuration.

No universal 20% rule.

---

# 54. Persistence for metrics

Example:

A one-hour eCPM deviation:
usually not event.

A six-hour sustained request/view drop:
potentially meaningful.

Persistence can mean:
- N consecutive time buckets;
- duration;
- multiple related series.

Exact values are rule configuration.

Do not hard-code the same persistence across Search, GAM and performance.

---

# 55. Metric descendant double-counting

Suppose:

```text
GAM requests ↓
GAM impressions ↓
programmatic revenue ↓
```

Revenue may be a mechanical descendant.

Do not generate three independent high-severity alerts and present them as three separate problems.

Timeline may contain multiple events, but grouping/ranking should recognize dependency.

`metric_parent_of` / `metric_descendant_of` relations help suppress double-counting.

---

# 56. Derived ratio events

Rates must preserve numerator/denominator.

Example:

Fill fell because:
- impressions fell;
- requests rose;
- or both.

An event summary SHOULD say:

> Fill decreased from X to Y; requests were stable / increased / decreased.

Do not report a rate alone when components exist.

---

# 57. Current event families

MVP families:

```text
SITE
BROWSER
DEPENDENCY
JAVASCRIPT
SEO
TRAFFIC_ANALYTICS
SEARCH
DISCOVER
GAM
GPT
PREBID
CONSENT
VIDEO
PERFORMANCE
SUPPLY
POLICY_UX
EXTERNAL
OPERATIONAL
DATA_QUALITY
```

Do not create a separate family for every vendor.

Vendor is a dimension/subject, not taxonomy.

---

# 58. SITE event catalog

## SITE_UNAVAILABLE

Kind:
CONDITION

Trigger:
key public page cannot be successfully served under controlled observation.

Confirmation:
IMMEDIATE_SECOND_CHECK.

Default severity:
CRITICAL for broad/core scope; HIGH for one important template.

Resolve:
successful comparable validations after failure.

Alert:
yes when confirmed and material.

Do not infer cause.

---

## SITE_INTERMITTENT_FAILURE

Kind:
CONDITION

Trigger:
first attempt fails at site layer, later immediate attempt succeeds, or failures recur intermittently.

Severity:
HIGH/MEDIUM depending scope.

Important:
do not discard first failure.

---

## REDIRECT_CHAIN_CHANGED

Kind:
STATE_CHANGE

Trigger:
stable URL begins resolving through materially different redirect chain.

Severity:
LOW to HIGH depending destination/scope.

High-risk examples:
- cross-domain unexpected redirect;
- redirect loop;
- major section migration.

---

## REDIRECT_LOOP_DETECTED

Kind:
CONDITION

Severity:
HIGH/CRITICAL for important scope.

Confirmation:
IMMEDIATE_SECOND_CHECK.

---

# 59. DEPENDENCY event catalog

## THIRD_PARTY_DEPENDENCY_ADDED

Point state change.

Default:
LOW/MEDIUM.

Usually Weekly Brief, not immediate alert.

Raise severity if:
- global template;
- critical rendering/ad/consent path;
- performance degradation appears.

---

## THIRD_PARTY_DEPENDENCY_REMOVED

Point state change.

Same routing principle.

---

## CRITICAL_DEPENDENCY_FAILURE

Condition.

Trigger:
known important dependency repeatedly 5xx/timeouts/unavailable on affected scope.

Examples:
- CMP runtime;
- GPT-related resource;
- player resource;
- critical publisher API.

Do not treat every failed analytics pixel as critical.

---

## DEPENDENCY_LATENCY_REGRESSION

Condition.

Default:
MEDIUM.

Confirmation:
persistence.

Must be based on comparable scenario/network conditions.

---

# 60. JAVASCRIPT event catalog

## JS_ERROR_STARTED

Condition.

Trigger:
new normalized error fingerprint appears and passes relevance/persistence rule.

Default:
LOW/MEDIUM.

Raise if:
- occurs before critical initialization;
- affects multiple representative pages;
- coincides with missing downstream requests.

---

## JS_ERROR_RESOLVED

Represent as resolution of active `JS_ERROR_STARTED` condition where possible.

Do not create a separate Timeline row unless recovery is user-relevant.

---

## CRITICAL_JS_RUNTIME_FAILURE

Condition.

Use only when evidence shows critical page functionality fails.

Example:
uncaught error followed by missing GPT initialization across article template.

This remains a runtime fact, not a revenue-cause conclusion.

---

# 61. SEO event catalog

## ROBOTS_TXT_CHANGED

Point change.

Default:
LOW/MEDIUM.

Usually Weekly Brief.

---

## ROBOTS_BROAD_BLOCK_ADDED

Point change with high risk.

Trigger:
new rules appear to block broad important crawl scope.

Confirmation:
IMMEDIATE_SECOND_CHECK.

Default:
CRITICAL.

Alert:
yes.

Summary must specify observed rule/scope.

---

## ROBOTS_BROAD_BLOCK_REMOVED

Point change.

Usually positive/recovery context.

---

## NOINDEX_ADDED

Point state change.

Scope:
page/template/site according to evidence.

Broad template/site noindex:
CRITICAL.

Single page:
LOW/MEDIUM.

Confirmation:
critical scope gets immediate second check.

---

## NOINDEX_REMOVED

Point state change.

Useful recovery context.

---

## CANONICAL_CHANGED

Point state change.

Default:
MEDIUM.

Raise to HIGH/CRITICAL if:
- broad template;
- unexpected cross-domain;
- points to clearly unrelated target.

---

## CANONICAL_CROSS_DOMAIN_CHANGED

Point event.

Default:
HIGH.

Requires clear evidence.

---

## SEO_HTTP_STATUS_REGRESSION

Condition.

Examples:
important page shifts from 200 to persistent 4xx/5xx.

---

## IMPORTANT_RENDERED_CONTENT_MISSING

Condition/state change.

Medium/High depending template/scope.

Heuristic confidence may be MEDIUM if "important content" detection is template-based.

---

# 62. TRAFFIC_ANALYTICS event catalog

## GA4_ACTIVE_USERS_BELOW_BASELINE

Condition anomaly.

Scope:
dimensions of metric series.

Default:
MEDIUM/HIGH based magnitude/scope/persistence.

No causal language.

---

## GA4_SESSIONS_BELOW_BASELINE

Same semantics.

---

## GA4_VIEWS_BELOW_BASELINE

Same semantics.

---

## GA4_VIEWS_PER_USER_BELOW_BASELINE

Useful consumption/engagement symptom.

Must carry numerator/denominator context where applicable.

---

## GA4_ORGANIC_SEARCH_BELOW_BASELINE

Traffic source-specific condition.

May later be related to GSC Search events.

---

## ANALYTICS_MEASUREMENT_DIVERGENCE

Cross-source derived event.

Trigger example:
GA4 shows a major drop while independent Search/browser evidence does not show matching traffic loss and a measurement/consent change exists.

Observation confidence:
MEDIUM unless directly proven.

This event says:
**measurement sources diverged**.

It does NOT say:
**GA4 is broken**.

---

# 63. SEARCH event catalog

## GSC_SEARCH_IMPRESSIONS_BELOW_BASELINE

Condition.

Useful visibility symptom.

---

## GSC_SEARCH_CLICKS_BELOW_BASELINE

Condition.

---

## GSC_SEARCH_CTR_BELOW_BASELINE

Condition.

Must include:
clicks + impressions context.

---

## GSC_SEARCH_POSITION_WORSENED

Condition.

Be careful with query/page mix.

Do not turn average position into a universal ranking diagnosis.

---

## SEARCH_TECHNICAL_RISK

Optional aggregate event only when multiple deterministic technical Search signals align.

Prefer specific events such as NOINDEX/ROBOTS/CANONICAL whenever possible.

---

# 64. DISCOVER event catalog

## GSC_DISCOVER_CLICKS_BELOW_BASELINE

Condition.

Default:
MEDIUM/HIGH depending materiality.

Never generate:
`GOOGLE_DISCOVER_PENALTY`.

---

## GSC_DISCOVER_IMPRESSIONS_BELOW_BASELINE

Condition where source data supports it.

---

## DISCOVER_VOLATILITY

Optional low-priority event for unusually large but short-lived movement.

Do not overuse; volatility is normal.

---

# 65. GAM event catalog

## GAM_REQUESTS_BELOW_BASELINE

Condition.

This is one of the highest-value monetization events.

Scope:
device/ad unit/format/channel where available.

---

## GAM_IMPRESSIONS_BELOW_BASELINE

Condition.

Relate to requests.

---

## GAM_FILL_BELOW_BASELINE

Condition.

Store numerator/denominator context.

Do not report fill in isolation.

---

## GAM_ECPM_BELOW_BASELINE

Condition.

Default:
MEDIUM.

Usually not immediate alert by itself.

Must preserve:
- volume;
- demand mix;
- device/geo;
- comparable baseline.

---

## GAM_PROGRAMMATIC_REVENUE_BELOW_BASELINE

Condition.

Contextual, not site-health truth.

Never critical solely from this metric.

---

## GAM_DIRECT_SHARE_INCREASED

Condition/change in composition.

Useful context.

May explain programmatic displacement.

Do not label as harmful automatically.

---

## GAM_PROGRAMMATIC_SHARE_DECREASED

Same.

Relate to direct share.

---

## GAM_SERVING_RESTRICTION_APPEARED

State change / condition depending source semantics.

Default:
HIGH when affecting important inventory.

If explicit platform restriction:
high observation confidence.

---

## GAM_PRICING_RULE_CHANGED

Operational/config state change if connector exposes reliable config data.

Usually Weekly Brief unless scope is broad/high risk.

---

## GAM_LINE_ITEM_DELIVERY_MIX_CHANGED

Condition.

Useful for direct/programmatic composition.

Avoid excessive per-line-item events.

Aggregate by meaningful class.

---

# 66. GPT event catalog

## GPT_SLOT_ADDED

Point state change.

Default:
LOW/MEDIUM.

---

## GPT_EXPECTED_SLOT_MISSING

Condition/state loss.

Trigger:
expected template slot not observed.

Confirmation:
MULTI_URL_CORROBORATION or immediate second check for widespread loss.

Severity:
MEDIUM to CRITICAL depending blast radius.

---

## GPT_SLOT_REMOVED

Point state change when we have strong prior/template identity.

May coexist with missing-slot condition.

Avoid duplicate Timeline clutter: prefer one user-facing event.

---

## GPT_REQUEST_MISSING

Condition.

Trigger:
slot exists/defined but expected request stage absent under comparable interaction.

High diagnostic value.

---

## GPT_RESPONSE_MISSING

Condition.

Trigger:
request observed, expected response stage absent.

Do not infer demand cause.

---

## GPT_CREATIVE_LOAD_FAILURE

Condition.

Trigger:
render injection/response exists but expected load/onload stage fails.

---

## GPT_VIEWABILITY_STAGE_REGRESSION

Condition/low priority.

Synthetic evidence only.

Do not confuse with field/programmatic viewability reporting.

---

## GPT_LAZY_BEHAVIOR_CHANGED

Point/condition.

Example:
slot now requests only after materially different scroll threshold.

Default:
LOW/MEDIUM.

Could be intentional optimization.

---

## GPT_REFRESH_BEHAVIOR_CHANGED

Point state change.

Default:
MEDIUM.

Must not say good/bad.

---

# 67. PREBID event catalog

## PREBID_VERSION_CHANGED

Point event.

Weekly Brief by default.

---

## PREBID_BIDDER_ADDED

Point event.

Usually LOW/MEDIUM.

---

## PREBID_BIDDER_REMOVED

Point event.

MEDIUM if important bidder/path.

No revenue implication without evidence.

---

## PREBID_TIMEOUT_CONFIG_CHANGED

Point event.

Store before/after timeout.

---

## PREBID_TIMEOUT_RATE_ABOVE_BASELINE

Condition.

Scope:
bidder/device/ad unit where possible.

---

## PREBID_RESPONSE_RATE_BELOW_BASELINE

Condition.

Do not assume bidder outage; check request eligibility/observability.

---

## PREBID_AUCTION_LATENCY_ABOVE_BASELINE

Condition.

May become performance/ad-latency evidence.

---

## PREBID_TARGETING_MISSING

Condition.

High diagnostic relevance where bids exist but expected GAM targeting is missing/stale.

---

## PREBID_SERVER_VISIBILITY_LIMITED

This is generally a limitation, not a user-facing event.

Store as observation/limitation unless visibility itself changed materially.

---

# 68. CONSENT event catalog

## CMP_ADDED

Point event.

---

## CMP_REMOVED

Point event.

High if site expected consent runtime.

---

## CMP_VENDOR_CHANGED

Point event.

Weekly Brief.

Vendor change alone is not incident.

---

## CMP_API_UNAVAILABLE

Condition.

High if expected across relevant geo/scenario.

---

## CMP_READINESS_LATENCY_ABOVE_BASELINE

Condition.

Requires comparable scenario and persistence.

---

## CMP_CONSENT_ACTION_FAILED

Condition.

Synthetic action failure.

Must distinguish:
- our selector/adapter failed;
- actual CMP UI failed.

Observation confidence may be MEDIUM until validated.

---

## TCF_API_MISSING

Condition/state.

High where expected.

---

## TCF_SIGNAL_MISSING

Condition.

High depending scope.

---

## TCF_ERROR_APPEARED

Condition/state change.

Store explicit error code(s) where available.

---

## CONSENT_NETWORK_BEHAVIOR_CHANGED

Derived state change.

Example:
vendor/ad requests differ materially pre/post consent compared with baseline.

Usually MEDIUM until mechanism is clearer.

---

## ACCEPT_PATH_GAM_REQUESTS_MISSING

High-value condition.

Trigger:
known Accept scenario completes but expected GAM request path does not occur.

Does not state root cause.

---

# 69. VIDEO event catalog

## VIDEO_PLAYER_ADDED

Point event.

---

## VIDEO_PLAYER_REMOVED

Point event.

---

## VIDEO_PLAYER_RUNTIME_FAILURE

Condition.

Examples:
player exists but fails to initialize/start expected behavior.

---

## VIDEO_STICKY_BEHAVIOR_CHANGED

Point/state change.

Weekly Brief or HIGH if disruptive.

---

## VIDEO_AUTOPLAY_BEHAVIOR_CHANGED

Point change.

---

## VIDEO_AUDIBILITY_BEHAVIOR_CHANGED

Point change.

Potential policy relevance depending current ruleset.

---

## VIDEO_CONTROLS_MISSING

Condition.

Potential UX/policy risk.

---

## VAST_REQUEST_FAILURE

Condition.

---

## VAST_ERROR_RATE_ABOVE_BASELINE

Condition.

Synthetic/sample evidence.

---

## VIDEO_PLAYBACK_START_FAILURE

Condition.

Request/VAST may exist but playback does not start.

This stage distinction is important.

---

# 70. PERFORMANCE event catalog

All browser performance events MUST include:

```text
source = synthetic
```

unless separately sourced field data exists.

## SYNTHETIC_LCP_REGRESSION

Condition.

Confirmation:
persistence / multiple runs.

---

## SYNTHETIC_CLS_REGRESSION

Condition.

May be HIGH if severe and template-wide.

Never claim Google ranking impact.

---

## SYNTHETIC_INP_REGRESSION

Condition.

Interaction method must be comparable.

---

## LONG_TASK_REGRESSION

Condition.

Useful supporting signal.

---

## RESOURCE_LATENCY_REGRESSION

Condition.

Prefer dependency-specific evidence.

---

# 71. SUPPLY event catalog

## ADS_TXT_CHANGED

Point event.

Default:
LOW.

Weekly Brief.

---

## ADS_TXT_MISSING

Condition.

Default:
HIGH if previously valid and now unavailable.

Confirmation:
immediate second fetch.

---

## ADS_TXT_EMPTY_200

Condition/state.

High.

This is semantically different from HTTP success.

---

## ADS_TXT_INVALID

Condition.

Severity depends on parse/semantic scope.

---

## ADS_TXT_CRITICAL_SELLER_REMOVED

Point event.

Requires knowledge that seller/path is actually important/active.

Do not infer criticality only from a line deletion.

---

## SELLER_RELATIONSHIP_CHANGED

DIRECT/RESELLER/account identity change.

Usually Weekly Brief.

---

# 72. POLICY_UX event catalog

These are often heuristic observations and must preserve exact evidence.

## AD_OBSCURES_CONTENT

Condition.

Evidence:
screenshot + geometry.

Observation confidence:
MEDIUM/HIGH if deterministic overlap is clear.

---

## DISRUPTIVE_STICKY_BEHAVIOR

Condition/state.

Evidence:
scroll interaction + screenshot + geometry.

---

## VIDEO_POLICY_RISK_DETECTED

Condition/risk event.

Must reference:
- exact observable behavior;
- ruleset/version.

Do not say "publisher violates policy" unless platform source explicitly confirms a restriction.

---

## AD_DENSITY_RISK_DETECTED

Heuristic.

Default:
MEDIUM/LOW.

Store method/version.

Never present approximate density as legal/policy proof.

---

# 73. EXTERNAL event catalog

External events are shared global records in `external_events`.

Relevant types:

```text
GOOGLE_CORE_UPDATE
GOOGLE_SPAM_UPDATE
GOOGLE_DISCOVER_UPDATE
GOOGLE_SEARCH_INDEXING_INCIDENT
GOOGLE_SEARCH_SERVING_INCIDENT
GAM_PLATFORM_INCIDENT
GOOGLE_PUBLISHER_POLICY_CHANGE
TCF_RULESET_CHANGE
BETTER_ADS_RULESET_CHANGE
CDN_PLATFORM_INCIDENT
CMP_VENDOR_INCIDENT
ADTECH_VENDOR_INCIDENT
BROWSER_PLATFORM_CHANGE
```

External records can be mirrored into publisher Timeline only through relevance/routing logic.

---

# 74. External event relevance

For each site, derive:

```text
CONTEXT
POSSIBLE_MATCH
LIKELY_RELEVANT
NOT_MATCHING_SEGMENT
```

Inputs can include:
- time overlap;
- affected product;
- publisher symptom segment;
- geography;
- source/channel;
- external scope.

Do not use:
`CAUSE`.

Incident reasoning may later raise confidence based on more evidence.

---

# 75. OPERATIONAL event catalog

Operational changes come from human/connector/CI data.

Examples:

```text
DEPLOYMENT_RECORDED
ROLLBACK_RECORDED
GAM_CONFIGURATION_CHANGE_RECORDED
CMP_CHANGE_RECORDED
PLAYER_CHANGE_RECORDED
PREBID_CONFIGURATION_CHANGE_RECORDED
DIRECT_CAMPAIGN_STARTED
DIRECT_CAMPAIGN_ENDED
VENDOR_INTEGRATION_STARTED
VENDOR_INTEGRATION_REMOVED
```

These are timeline context.

They are not automatically defects.

---

# 76. Operational change linking

If browser evidence detects a corresponding state change near a recorded deployment:

Possible relation:

```text
INTRODUCED_BY
```

only when the mapping is supported.

Otherwise:
`COINCIDES_WITH`.

Do not infer an actor from browser evidence.

---

# 77. DATA_QUALITY events

These primarily protect the reasoning system.

Examples:

```text
GA4_DATA_STALE
GSC_DATA_STALE
GAM_DATA_STALE
CONNECTOR_AUTH_FAILED
CONNECTOR_EXTRACTION_FAILED
REPORT_SEMANTICS_CHANGED
BROWSER_OBSERVER_VERSION_CHANGED
```

Most are not publisher-health events.

They should appear in:
- connection health;
- internal/platform status;
- incident report limitations if relevant.

Do not pollute the normal publisher Timeline unless they materially affect interpretation.

---

# 78. Event summaries

Event title/summary MUST be factual.

Good:

> Expected GPT slot `article_mid_2` was not observed on mobile article pages in 3 representative URLs.

Bad:

> Missing slot is hurting publisher revenue.

Good:

> GA4 Organic Search sessions are 28% below the comparable baseline for mobile.

Bad:

> Google traffic collapsed because of the latest update.

---

# 79. Observed / Risk / Check

For Weekly Brief and event detail, separate:

## Observed
What evidence says happened.

## Risk
What it could affect.

## Check
What an operator should verify.

Example:

**Observed:** article/mobile now has 3 expected GPT slots instead of 5 across 4 consecutive checkpoints.

**Risk:** fewer monetizable opportunities.

**Check:** confirm whether slot removal was intentional.

This language prevents risk from being mistaken for cause.

---

# 80. Event relations

The Event Engine may create sparse typed relations.

Allowed relation types from DOMAIN/DATA_MODEL:

```text
PRECEDES
COINCIDES_WITH
SAME_SEGMENT_AS
MECHANISTICALLY_CAN_AFFECT
METRIC_PARENT_OF
METRIC_DESCENDANT_OF
INTRODUCED_BY
RESOLVED_AFTER
PERSISTED_AFTER_REMOVAL
EXTERNAL_CONTEXT_FOR
UNKNOWN_RELATION
```

`SUPPORTS` and `CONTRADICTS` are used primarily in incident analysis.

`CAUSES` is reserved for confirmed evidence and should not be emitted by routine event detection.

---

# 81. Do not build a complete graph

Do not connect every event to every other event.

That creates meaningless graph density.

Create relations when:
- they share relevant scope;
- temporal proximity is meaningful;
- DOMAIN contains a mechanism;
- intervention/recovery provides evidence;
- incident analysis requests them.

Sparse graph > giant coincidence graph.

---

# 82. Temporal relation windows

`PRECEDES` does not mean causal relevance.

Routine engine may infer temporal relation only within bounded domain-specific windows.

Examples:
- browser/GAM changes: hours/days;
- Search technical changes: days/weeks;
- official update context: rollout window.

The Incident Engine chooses richer lookback.

Do not create months of `PRECEDES` edges globally.

---

# 83. SAME_SEGMENT_AS

Only create when scope overlaps meaningfully.

Examples:

```text
mobile article
↔ mobile article
```

Strong.

```text
site-wide
↔ mobile article
```

Partial overlap.

```text
desktop homepage
↔ mobile video article
```

Weak/no relation unless a broader mechanism exists.

Store overlap explanation if useful.

---

# 84. MECHANISTICALLY_CAN_AFFECT

This relation comes from DOMAIN knowledge.

Example:

```text
CMP/TCF issue
MECHANISTICALLY_CAN_AFFECT
GAM request eligibility
```

It means:
mechanism exists.

It does NOT mean:
it did cause the observed result.

---

# 85. METRIC_PARENT / DESCENDANT

Useful for avoiding double-counting.

Example conceptual chain:

```text
pageviews
→ ad requests
→ impressions
→ revenue
```

If upstream metric moves, downstream changes may be descendants.

Weekly ranking should avoid presenting every descendant as an independent issue.

---

# 86. INTRODUCED_BY

Use conservatively.

Strong examples:
- deployment explicitly includes new script and browser detects it after deploy;
- manual GAM change corresponds to exact config difference.

If evidence only shows timing:
use `COINCIDES_WITH`.

---

# 87. RESOLVED_AFTER

Example:

```text
ROLLBACK_RECORDED
→ affected condition resolves after plausible latency
```

This is useful intervention evidence.

Do not automatically upgrade to CAUSES.

Incident Engine evaluates counterfactual strength.

---

# 88. PERSISTED_AFTER_REMOVAL

This relation is particularly valuable.

Example:

```text
suspected integration removed
but
traffic decline continues unchanged
```

This is strong negative evidence for later incident reasoning.

The Event Engine should preserve intervention and recovery timelines so Incident Engine can derive this relation.

---

# 89. Ruleset implementation

Event rules SHOULD be code/config reviewed in Git.

Do not build a database-editable user rule engine in MVP.

Suggested code-level structure:

```python
EventRule(
    code="GPT_EXPECTED_SLOT_MISSING",
    kind="CONDITION",
    inputs=[...],
    comparator="presence",
    confirmation="MULTI_URL_CORROBORATION",
    severity_policy="...",
    resolution_policy="...",
    alert_policy="...",
    domain_refs=["F-GAM-001", "F-GPT-001"],
    rule_version="1"
)
```

Seed `event_definitions` from version-controlled definitions.

---

# 90. Event-definition fields

Every event definition SHOULD specify:

```yaml
code:
family:
kind:
description:
input_sources:
subject_kind:
diff_operator:
confirmation_mode:
aggregation_scope:
default_severity:
severity_overrides:
resolution_rule:
alert_policy:
weekly_eligible:
dedupe_strategy:
domain_refs:
noise_notes:
schema_version:
```

This prevents detection behavior from being scattered across random code.

---

# 91. Rule versioning

A rule change can change historical event output.

Every event stores:
- event definition schema version;
- event engine/source version.

If a materially new rule is run over old evidence:
- create newly derived event;
- supersede incompatible old event where needed;
- do not pretend the old event never existed.

---

# 92. Event supersession

Use when:
- previous event was generated by faulty rule;
- later evidence shows semantic aggregation should replace it;
- event taxonomy changed materially.

`SUPERSEDED` is not the same as `RESOLVED`.

Resolved:
condition genuinely ended.

Superseded:
our representation changed.

---

# 93. Reprocessing

Reprocessing pipeline:

```text
select immutable source evidence
→ run new normalizer/ruleset
→ compare derived output
→ write new event versions
→ mark old derived events superseded where appropriate
```

Do not overwrite raw observations.

---

# 94. Event routing destinations

Each persisted event can be eligible for:

```text
TIMELINE
HOME_ATTENTION
IMMEDIATE_ALERT
WEEKLY_BRIEF
INCIDENT_RETRIEVAL
```

Eligibility is deterministic.

LLM should not decide whether something deserves an immediate alert.

---

# 95. Timeline policy

Timeline should show:
- meaningful changes;
- meaningful conditions;
- important recoveries;
- external context;
- operational changes.

Timeline should hide by default:
- low-value internal monitor failures;
- duplicate condition observations;
- content churn;
- low-confidence noise.

Filters expose domain families.

---

# 96. Home status

Home status:

```text
HEALTHY
ATTENTION
INCIDENT
```

is a derived summary.

It is not an event.

Conceptual:

### HEALTHY
No current event meets attention/incident conditions.

### ATTENTION
One or more meaningful noncritical issues/changes deserve review.

### INCIDENT
Active critical/high symptom or explicitly open incident.

Final logic belongs to product/UI implementation.

Do not persist Home status as independent truth unless later needed for historical display.

---

# 97. Weekly Brief eligibility

An event is a candidate when:
- created in reporting period;
- resolved in period;
- active and materially changed;
- still important and not previously acknowledged/resolved.

Default exclusions:
- pure noise;
- repeated unchanged active condition;
- internal-only monitor issue;
- known harmless/intentional change;
- descendant metric duplicate.

---

# 98. Weekly ranking factors

Deterministic ranking:

- severity;
- persistence;
- blast radius;
- observation confidence;
- actionability;
- novelty;
- business relevance.

Then select approximately:
**3–7 findings**.

The LLM may rewrite those selected findings.

It MUST NOT add an eighth finding because it sounds interesting.

---

# 99. Weekly deduplication

Group events into one finding when they represent one operational story.

Example:

```text
GPT slot missing
GAM requests/view down
GAM impressions down
```

May become one weekly finding if strongly related:

> Mobile article ad opportunity decreased.

But wording must still distinguish observed components.

Do not collapse unrelated symptoms just because they share date.

---

# 100. Weekly carry-forward

Do not repeat an unresolved event every week with identical text.

Carry forward only if:
- severity changed;
- new evidence appeared;
- scope expanded;
- condition persists beyond configured duration and remains actionable.

Otherwise keep it in Timeline/Attention state without weekly repetition.

---

# 101. Immediate-alert deduplication

For one active condition:
send one initial alert.

Possible follow-ups:
- severity materially worsens;
- scope materially expands;
- condition resolves;
- condition reopens after recovery.

Do not send an alert every checkpoint.

---

# 102. Alert resolution messages

Recovery notifications can be useful for critical alerts.

Example:

> Site availability has recovered in two independent checks.

But:
resolution of alert does not mean incident root cause is known.

Keep wording factual.

---

# 103. Notification transport is separate

Event creation and notification delivery are separate systems.

The Event Engine decides:
`alert_eligible`.

A notification service handles:
- email;
- Slack;
- app push;
- retry;
- delivery logs.

Do not embed SMTP/Slack delivery logic inside event rules.

When external delivery is implemented, add a dedicated notification-delivery data model.

---

# 104. External event routing

Official external events generally go to:
- Timeline;
- Weekly Brief if relevant;
- Incident context.

They do not automatically change Home to INCIDENT.

Example:
Google Core Update begins while publisher Search is stable.

Home can remain HEALTHY.

Timeline can still show external context.

---

# 105. Event evidence chain

Every event detail page should be able to answer:

```text
What triggered this?
Which evidence was used?
What was before?
What was after?
How was it confirmed?
Which rule/version created it?
How precise is the timing?
What scope is actually observed?
```

If these questions cannot be answered, the event is not sufficiently auditable.

---

# 106. Critical rule: visual evidence

For visual/UX events, attach screenshot evidence.

Examples:
- overlay;
- sticky player;
- obscured content;
- layout shift.

Do not rely on text description only.

For changes:
prefer before + after screenshots when available.

---

# 107. Critical rule: structural evidence

For:
- slot removal;
- script addition;
- canonical/noindex;
- dependency change;

attach normalized state/diff evidence.

Screenshot alone is insufficient if the technical state is available.

---

# 108. Critical rule: metric evidence

For anomaly events, attach:
- series definition;
- time window;
- baseline method/version;
- observed;
- expected;
- deviation;
- numerator/denominator where relevant;
- source extract/freshness.

Do not show a red percentage without context.

---

# 109. Critical rule: external evidence

External event must store:
- source;
- official title;
- event start/end/rollout if available;
- affected product;
- source URL;
- evidence tier/version.

Do not ingest rumors as official events.

Community reports belong to incident corpus/discovery, not external authoritative timeline.

---

# 110. Example — slot removal

Evidence:

```text
12:00 article/mobile:
expected article_mid_2 present

18:00 article/mobile:
expected article_mid_2 absent
```

Candidate:

```text
GPT_EXPECTED_SLOT_MISSING
```

Confirmation:
second representative article also missing.

Persist:

```yaml
event_code: GPT_EXPECTED_SLOT_MISSING
kind: CONDITION
scope:
  template: article
  device: mobile
severity: HIGH
observation_confidence: HIGH
occurred_after_at: 12:00
occurred_before_at: 18:00
time_precision: WINDOW
```

Timeline:

> Expected mid-article ad slot disappeared on mobile article pages between 12:00 and 18:00.

Not:

> Revenue loss caused by deleted slot.

---

# 111. Example — JS failure

Checkpoint A:
no error.

Checkpoint B:
new uncaught error.

GPT:
no request after error.

Persist:

```text
JS_ERROR_STARTED
```

Potential relation:

```text
JS_ERROR_STARTED
PRECEDES
GPT_REQUEST_MISSING

JS_ERROR_STARTED
MECHANISTICALLY_CAN_AFFECT
GPT_REQUEST_MISSING
```

Still no CAUSES.

Incident Engine later evaluates.

---

# 112. Example — lazy loading

Before:
slot requested at initial load.

After:
slot requested only after 50% scroll.

Event:

```text
GPT_LAZY_BEHAVIOR_CHANGED
```

Severity:
LOW/MEDIUM.

If GAM requests/view decline:
that is separate metric evidence.

Do not classify lazy-load change as defect automatically.

---

# 113. Example — broad noindex

Checkpoint:
article template gets `noindex`.

Validation:
second article + fresh fetch confirm.

Persist:

```text
NOINDEX_ADDED
scope = article template
severity = CRITICAL
```

Immediate alert:
yes.

Observed:
noindex added.

Risk:
Search indexability.

Do not claim:
Google has already deindexed every article.

---

# 114. Example — GAM fill drop

Metric:

```text
requests stable
impressions down
fill down
```

Create:
`GAM_FILL_BELOW_BASELINE`

Evidence summary must mention:
requests were stable.

If direct share rose materially:
create/relate:
`GAM_DIRECT_SHARE_INCREASED`.

Do not immediately blame SSP demand.

---

# 115. Example — raw revenue drop

```text
GAM revenue -25%
direct campaign delivery +40%
programmatic share lower
```

Revenue event may exist as context.

Immediate alert:
no.

Weekly finding may focus on composition instead of saying "monetization failure."

---

# 116. Example — GA4 vs GSC

GA4 Organic Search:
-30%.

GSC clicks:
stable.

Browser:
normal.

Recent analytics/consent change:
yes.

Possible derived factual event:

```text
ANALYTICS_MEASUREMENT_DIVERGENCE
```

Summary:

> GA4 Organic Search diverged materially from Search Console during the same period.

Not:

> GA4 tracking is broken.

---

# 117. Example — Google update

External source:
Core Update starts Aug 10.

Publisher:
Search decline began Aug 5.

Persist external event as context.

Incident relation:
timing contradicts onset explanation.

Do not suppress the external event; preserve it so the Incident Engine can use it as negative evidence.

---

# 118. Example — publisher deployment

Manual/CI event:

```text
DEPLOYMENT_RECORDED 14:02
```

Browser change observed between:
12:00 and 18:00.

A matching script appears.

Relation:
`COINCIDES_WITH` initially.

If deployment manifest explicitly contains script:
`INTRODUCED_BY` may be justified.

Traffic changes later:
separate.

---

# 119. Example — rollback and no recovery

Operational:
suspected player removed.

Browser:
player absent.

Metric:
traffic decline continues on same trajectory.

Preserve:
- rollback;
- removal event;
- continuing anomaly.

Incident Engine can derive:
`PERSISTED_AFTER_REMOVAL`.

This is valuable evidence against the player as primary cause.

---

# 120. Event taxonomy anti-patterns

Do NOT create codes like:

```text
BAD_MONETIZATION
GOOGLE_PENALTY
SSP_BROKEN
CMP_CAUSED_REVENUE_LOSS
WEBSITE_BAD
SEO_PROBLEM
```

These are conclusions/judgments.

Event codes must describe observable facts.

---

# 121. Naming convention

Event codes:

```text
UPPER_SNAKE_CASE
```

Prefer:

```text
SUBJECT + CONDITION/CHANGE
```

Examples:

```text
GPT_EXPECTED_SLOT_MISSING
GAM_REQUESTS_BELOW_BASELINE
TCF_ERROR_APPEARED
ROBOTS_BROAD_BLOCK_ADDED
```

Avoid vendor names unless event is vendor-specific by definition.

---

# 122. Summary grammar

Point change:

> X changed from A to B on scope S.

Condition:

> X has been below/above/unavailable since T on scope S.

Uncertain time:

> X changed between T1 and T2.

External:

> Official source reported X beginning T.

Operational:

> Operator recorded deployment X at T.

Keep language factual.

---

# 123. Threshold configuration

Thresholds MUST be configurable/versioned by:
- event code;
- publisher/site;
- metric series family;
- template where necessary.

Fallback:
global conservative defaults.

Do not put dozens of magic numbers directly in Python branches.

---

# 124. Calibration

Initial thresholds are hypotheses.

Pilot process:

```text
event fires
→ operator marks useful/noisy
→ inspect missed incidents
→ tune rule
→ version
```

Do not tune solely to reduce event count.

Optimize for:
- useful signal;
- low noise;
- incident reconstruction value.

---

# 125. Feedback labels

Future useful labels:

```text
USEFUL
EXPECTED_CHANGE
NOISE
FALSE_POSITIVE
IMPORTANT
MISCLASSIFIED
```

These can support calibration later.

Do not build a machine-learning feedback system before basic operator feedback exists.

---

# 126. Event rule tests

Every event rule MUST have tests for:

1. positive detection;
2. no-change;
3. noisy input;
4. recovery where condition;
5. missing data;
6. incompatible collector version where relevant;
7. scope;
8. dedupe.

High-risk rules additionally require:
9. validation-run behavior;
10. alert routing.

---

# 127. Required cross-event evals

## EV-001
One JS error on social widget:
no critical event.

## EV-002
New persistent JS error before GPT initialization + missing requests:
separate factual events + mechanistic relation, no automatic cause.

## EV-003
Expected slot missing on one URL once:
candidate only or low confidence.

## EV-004
Expected slot missing on 3 article/mobile URLs:
template-scoped event.

## EV-005
Broad noindex:
immediate validation + critical event.

## EV-006
Noindex appears because collector parsing changed:
must not create publisher event.

## EV-007
GAM requests missing because extract failed:
DATA_QUALITY, not GAM requests=0.

## EV-008
Fill falls because requests increase:
event preserves numerator/denominator.

## EV-009
eCPM one-hour spike/drop:
no immediate alert.

## EV-010
Direct delivery rises while programmatic share falls:
no automatic monetization-failure alert.

## EV-011
Google Core Update with no local Search anomaly:
external Timeline context only.

## EV-012
Google update begins after traffic decline:
event preserved; Incident Engine can use contradicting timing.

## EV-013
CMP version changes but behavior unchanged:
point change only, no CMP failure event.

## EV-014
TCF errors + Accept-path GAM requests missing:
two high-value consent/request events; no root-cause claim yet.

## EV-015
ads.txt file returns 200 but empty:
ADS_TXT_EMPTY_200.

## EV-016
Routine valid reseller line added:
ADS_TXT_CHANGED low priority; no alert.

## EV-017
Synthetic CLS one bad run:
no persistent high alert.

## EV-018
Synthetic CLS severe across repeated mobile article runs:
performance event, explicitly synthetic.

## EV-019
Site 503 then healthy retry:
SITE_INTERMITTENT_FAILURE; do not erase first observation.

## EV-020
Chromium crash:
internal monitor issue, not SITE_UNAVAILABLE.

---

# 128. Event Engine implementation milestones

## E1 — Semantic browser diffs

Implement:
- script presence;
- dependency presence;
- JS errors;
- SEO state;
- expected GPT slot presence;
- event definition registry;
- event evidence refs.

No metric anomalies yet.

---

## E2 — Persistence + dedupe + lifecycle

Implement:
- active condition dedupe;
- resolution;
- multi-URL aggregation;
- time uncertainty;
- severity.

---

## E3 — Public configuration

Implement:
- robots;
- ads.txt;
- high-risk validation checks.

---

## E4 — Metric anomalies

Implement:
- metric baseline model;
- minimum-volume gate;
- persistence;
- anomaly → event promotion;
- rate components.

Start with a small number of metrics:
- GA4 traffic;
- GSC Search/Discover;
- GAM requests/impressions/fill/eCPM.

---

## E5 — Ad stack depth

Add:
- GPT lifecycle;
- CMP/TCF;
- Prebid;
- video;
- policy/UX rules.

Only as BROWSER collectors become reliable.

---

## E6 — Routing

Implement:
- Timeline;
- Home Attention;
- immediate alert eligibility;
- Weekly Brief deterministic ranking.

No LLM decides selection.

---

# 129. Event Engine acceptance criteria

EVENTS v1 is acceptable when:

1. raw diff is not automatically an event;
2. metric is not automatically an event;
3. event is not incident/cause;
4. every event has source evidence;
5. event timing preserves uncertainty;
6. comparable scenarios are enforced;
7. collector-version changes cannot silently create false publisher changes;
8. persistence strategies are event-specific;
9. high-risk events can trigger immediate validation;
10. routine noise is suppressed;
11. one active condition does not generate duplicate events every checkpoint;
12. recovery closes conditions without erasing history;
13. event scope never exceeds observed evidence;
14. blast radius is separate from causal relevance;
15. severity is separate from alertability;
16. metric anomalies respect freshness and missingness;
17. rates preserve numerator/denominator context;
18. downstream metric events can be grouped to avoid double-counting;
19. external events remain context until publisher-specific evidence exists;
20. operational changes remain separate from detected site changes;
21. event graph is sparse and relational in PostgreSQL;
22. critical alerts are actionable and low-noise;
23. Weekly Brief selection is deterministic before LLM rewriting;
24. synthetic performance is labeled synthetic;
25. observer failures cannot masquerade as publisher failures;
26. rollback/no-recovery evidence can be preserved;
27. event rules and thresholds are versioned;
28. reprocessing does not rewrite source evidence;
29. user-facing summaries state observations, not invented causes;
30. tests cover positive, negative, noisy and recovery cases.

---

# 130. Codex rules for event work

Codex MUST:

- read `DOMAIN.md` before creating a new event category;
- read `BROWSER.md` before using browser observations;
- read `DATA_MODEL.md` before altering persistence;
- use versioned deterministic rules;
- preserve source evidence links;
- keep event codes factual;
- preserve occurrence-time uncertainty;
- distinguish source missingness from zero;
- distinguish monitor failure from publisher failure;
- preserve rate components where available;
- aggregate repeated evidence instead of duplicating events;
- keep severity separate from causal confidence;
- keep alert routing separate from event existence;
- write tests for noise suppression;
- write tests for resolution/deduplication;
- update `DECISIONS.md` for material semantic changes.

Codex MUST NOT:

- use an LLM to decide if a raw diff happened;
- create an event from a dashboard screenshot alone when structured source exists;
- create `CAUSES` edges from temporal coincidence;
- create a critical alert from raw total GAM revenue alone;
- create a Google-cause event from an update announcement;
- generate site-wide scope from one page observation;
- hide failed validation attempts;
- mutate source checkpoints;
- hard-code publisher-specific selectors/rules into global event logic.

---

# 131. Current primary operational references

The event philosophy intentionally borrows from mature observability practice:

- monitoring should support alerting, investigation, visualization, trend analysis and before/after comparison;
- urgent alerts should be actionable and oriented toward meaningful symptoms rather than every internal cause;
- excess paging creates alert fatigue and reduces the value of serious alerts;
- structured events benefit from consistent semantic names and attributes.

These principles are adapted to publisher operations, not copied as infrastructure-SRE semantics.

The publishing-specific event taxonomy remains governed by `DOMAIN.md` and empirical `INCIDENTS`.

---

# 132. Final Event Engine principle

The Event Engine succeeds when a publisher can look at a week of history and see:

> **the few things that actually changed or degraded**

instead of:

> **everything the website happened to do.**

It should preserve enough evidence for deep investigation while keeping normal operation quiet.

The central rule is:

# **Events describe what happened. Incidents explain why it might matter. Evidence decides how much we should believe.**
