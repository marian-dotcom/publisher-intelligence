# DECISIONS.md
## Publisher Incident Intelligence Platform
### Architecture & Product Decision Record — v1.0

**Audience:** Codex, engineering, product, technical reviewers  
**Status:** Canonical decision log  
**Purpose:** Preserve durable product, architecture, data, security and reasoning decisions so implementation does not repeatedly reopen settled questions  
**Depends on:** `PRODUCT.md`, `MVP.md`, `ARCHITECTURE.md`, `SECURITY.md`, `DATA_MODEL.md`, `BROWSER.md`, `EVENTS.md`, `CONNECTORS.md`, `INCIDENT.md`, `EVALS.md`, `PLANS.md`

---

# 0. ADR purpose

This file records decisions that are expected to remain relevant across multiple implementation tasks.

It exists to prevent:

```text
same question
→ new session
→ new opinion
→ architecture drift
```

Examples of questions that belong here:

```text
PostgreSQL or ClickHouse?
Monolith or microservices?
6-hour checkpoints or event-triggered crawling?
Read-only connectors or write access?
Qualitative or numeric causal confidence?
Raw evidence mutable or immutable?
LLM decides evidence or only explains it?
```

---

# 1. ADR rule

An ADR records:

```text
Context
Decision
Reason
Consequences
Alternatives considered
Revisit trigger
```

Do not use ADRs for trivial implementation choices such as:
- variable names;
- function names;
- CSS details;
- one test helper.

---

# 2. ADR statuses

Use:

```text
PROPOSED
ACCEPTED
SUPERSEDED
REJECTED
DEPRECATED
```

Existing decisions in this v1.0 file are:

```text
ACCEPTED
```

unless explicitly stated otherwise.

---

# 3. Changing a decision

Do NOT silently rewrite historical rationale.

If a durable decision changes:

1. mark old ADR `SUPERSEDED`;
2. reference replacement ADR;
3. preserve the old record;
4. explain why evidence changed.

---

# 4. Product decisions

---

# ADR-001 — Product category is publisher operational memory + incident intelligence

**Status:** ACCEPTED

## Context

The product touches:
- traffic;
- Search;
- monetization;
- browser behavior;
- ad tech;
- performance;
- policy context.

It could easily drift into a generic analytics or optimization platform.

## Decision

The canonical category is:

> **Publisher operational memory and incident intelligence.**

Primary positioning:

> **Black-box recorder + incident investigator for digital publishers.**

## Reason

The differentiated value is:
- preserved historical evidence;
- synchronized operational timeline;
- cross-layer incident reconstruction;
- contradiction-aware diagnosis.

Not:
- another dashboard;
- another revenue optimizer.

## Consequences

Every feature should answer:

```text
Does this improve observation,
memory,
meaningful detection,
or incident investigation?
```

## Alternatives considered

- AI analytics platform
- publisher BI platform
- revenue optimization platform
- SEO monitoring platform

Rejected because they weaken the central product thesis.

## Revisit trigger

Only if real customer usage shows a materially different recurring job-to-be-done.

---

# ADR-002 — Product has three primary MVP surfaces

**Status:** ACCEPTED

## Decision

Primary UX:

```text
Home
Timeline
Investigate
```

No fourth primary product area in MVP.

## Reason

These correspond directly to:
- current state;
- operational memory;
- incident diagnosis.

## Consequences

Technical domains such as:
- GPT;
- CMP;
- Prebid;
- Network;
- Performance;

appear as evidence/drill-down, not top-level products.

## Revisit trigger

Repeated pilot demand for a dedicated workflow that does not fit the three surfaces.

---

# ADR-003 — Quiet-by-default product

**Status:** ACCEPTED

## Decision

Immediate alerts are rare.

Routine changes appear in:
- Timeline;
- Weekly Brief.

## Reason

Alert fatigue would destroy product trust.

## Consequences

The system must optimize for:
- alert precision;
- event relevance;

not event volume.

---

# ADR-004 — Weekly Brief contains only a few meaningful findings

**Status:** ACCEPTED

## Decision

Typical Weekly Brief:

```text
3–7 findings maximum
```

Fewer is acceptable.

## Reason

The user should read every item.

## Consequences

No quota-filling.

LLM may rewrite selected findings but cannot invent additional ones.

---

# ADR-005 — Incident intake starts from symptom, not suspected cause

**Status:** ACCEPTED

## Decision

User input begins with:

```text
What happened?
When did it start?
Optional context/evidence
```

## Reason

Starting from suspected cause introduces anchoring bias.

## Consequences

Incident Engine localizes symptom before causal ranking.

---

# ADR-006 — UNRESOLVED is a valid product result

**Status:** ACCEPTED

## Decision

The Incident Engine may conclude:

```text
UNRESOLVED
```

including:

```text
NO_STRONG_LOCAL_CAUSE
```

## Reason

Evidence can be incomplete or mechanisms unobservable.

False certainty is more harmful than acknowledged uncertainty.

## Consequences

Product success is not measured by “root cause found rate.”

---

# ADR-007 — No fake numeric causal confidence

**Status:** ACCEPTED

## Decision

User-facing labels:

```text
CONFIRMED
PROBABLE
POSSIBLE CONTRIBUTOR
UNRESOLVED
```

No public:

```text
87.3% probability
```

## Reason

No calibrated statistical basis exists yet.

## Revisit trigger

Large validated incident dataset with demonstrated calibration.

---

# 5. Browser / evidence decisions

---

# ADR-008 — Synthetic Browser is a core product subsystem

**Status:** ACCEPTED

## Decision

Synthetic browser monitoring is central to MVP.

It is not an optional diagnostic utility.

## Reason

The product requires historical proof of how the site actually behaved.

---

# ADR-009 — Playwright controls real Chromium

**Status:** ACCEPTED

## Decision

Synthetic browser implementation:

```text
Playwright
+
Chromium
```

## Reason

Needed for:
- real JS runtime;
- network observation;
- consent;
- lazy loading;
- GPT;
- Prebid;
- video;
- screenshots.

## Alternatives considered

- HTTP crawler only
- headless HTML parser
- Selenium-first
- custom browser instrumentation

Rejected for MVP.

---

# ADR-010 — Fixed 6-hour black-box checkpoints

**Status:** ACCEPTED

## Decision

Core representative URLs receive approximately:

```text
one immutable checkpoint every 6 hours
```

even when no change is detected.

## Reason

The product needs historical state before an incident.

Event-trigger-only monitoring cannot reconstruct what it never recorded.

## Consequences

Checkpoint = evidence/state.

Checkpoint is NOT:
- event;
- alert;
- cause.

---

# ADR-011 — Template-first monitoring

**Status:** ACCEPTED

## Decision

Monitor representative page types/templates rather than all URLs.

Initial target:

```text
~20–40 representative URLs/site
```

## Reason

This creates:
- stable comparison;
- manageable cost;
- high diagnostic value.

## Consequences

URL sample can rotate while template identity remains stable.

---

# ADR-012 — Two core browser device classes

**Status:** ACCEPTED

## Decision

Core:

```text
Desktop
Mobile
```

No large browser/device matrix in MVP.

## Reason

Maximum useful coverage with low complexity.

---

# ADR-013 — Consent matrix is deliberately limited

**Status:** ACCEPTED

## Decision

Core run:
- observe pre-consent;
- use configured primary consent path.

Reject:
- canary/lower cadence;
- incident-driven.

## Reason

Avoid Cartesian explosion in browser jobs.

---

# ADR-014 — Browser executes deterministic interaction scripts

**Status:** ACCEPTED

## Decision

Browser observation includes controlled interactions such as:
- consent;
- scroll;
- wait;
- sticky/player inspection.

## Reason

Lazy-loaded and viewport-dependent publisher behavior cannot be observed reliably from page open alone.

---

# ADR-015 — Full-page screenshot occurs after core runtime evidence

**Status:** ACCEPTED

## Decision

Capture final full-page screenshot after important runtime observations/interactions.

## Reason

Full-page screenshot generation itself can affect lazy loading/render state.

---

# ADR-016 — Raw checkpoint evidence is immutable

**Status:** ACCEPTED

## Decision

After finalization, source checkpoint evidence is not rewritten.

New parser/normalizer:
- derives new output;
- does not mutate historical fact.

## Reason

Incident forensics require stable historical truth.

---

# ADR-017 — Browser observer provenance is mandatory

**Status:** ACCEPTED

## Decision

Store:
- Playwright version;
- Chromium version;
- scenario version;
- viewport/device;
- locale/timezone;
- collector versions;
- interaction profile.

## Reason

We must distinguish:

```text
publisher changed
```

from:

```text
observer changed
```

---

# ADR-018 — Browser failure and site failure remain distinct

**Status:** ACCEPTED

## Decision

Examples:

```text
publisher 503 → SITE_ERROR
Chromium crash → BROWSER_ERROR
collector failure → PARTIAL / collector ERROR
```

## Reason

Monitoring failure must not become publisher evidence.

---

# ADR-019 — No ad clicking

**Status:** ACCEPTED

## Decision

Synthetic browser never intentionally clicks ads.

## Reason

Avoid:
- invalid traffic;
- commercial side effects;
- unwanted navigation/download.

---

# ADR-020 — No stealth / anti-bot evasion in MVP

**Status:** ACCEPTED

## Decision

No:
- stealth plugins;
- residential proxy evasion;
- browser fingerprint manipulation intended to bypass controls.

## Reason

The product observes authorized/publisher-approved behavior.

---

# 6. Data architecture decisions

---

# ADR-021 — PostgreSQL is the only structured database in MVP

**Status:** ACCEPTED

## Decision

Use:

```text
PostgreSQL
```

for:
- entities;
- time series;
- events;
- incidents;
- jobs;
- metadata.

## Reason

Pilot scale does not justify multiple data systems.

## Alternatives rejected

- ClickHouse
- TimescaleDB
- MongoDB
- Neo4j

## Revisit trigger

Measured production bottleneck that Postgres cannot reasonably solve.

---

# ADR-022 — S3-compatible object storage for large forensic artifacts

**Status:** ACCEPTED

## Decision

Large artifacts live outside PostgreSQL.

Examples:
- screenshots;
- raw DOM;
- traces;
- large source artifacts.

## Reason

Relational DB remains queryable and manageable.

---

# ADR-023 — Raw evidence and derived data are separate

**Status:** ACCEPTED

## Decision

System-of-record evidence remains distinct from:

```text
normalized state
diff
event
hypothesis
report
```

## Reason

Derived logic changes over time.

Raw evidence should remain reproducible.

---

# ADR-024 — Event is not metric

**Status:** ACCEPTED

## Decision

Examples:

```text
GAM requests = metric
GAM_REQUESTS_BELOW_BASELINE = event
```

Do not combine them.

## Reason

Metric history and operational interpretation have different semantics/lifecycles.

---

# ADR-025 — Checkpoint is not event

**Status:** ACCEPTED

## Decision

Checkpoint records observed state.

Event records meaningful derived change/anomaly.

## Consequences

No checkpoint is automatically visible on Timeline.

---

# ADR-026 — Relational event graph, no graph database

**Status:** ACCEPTED

## Decision

Use typed relational edges such as:

```text
event_relations
hypothesis_evidence
incident_evidence
```

in PostgreSQL.

## Reason

Graph semantics are useful.

Graph infrastructure is unnecessary.

---

# ADR-027 — Core semantics relational; flexible evidence JSONB

**Status:** ACCEPTED

## Decision

Use typed relational fields for:
- IDs;
- status;
- timestamps;
- tenant ownership;
- relationships.

Use JSONB for:
- provider-specific metadata;
- collector payload details;
- flexible evidence.

## Reason

Avoid both:
- rigid schema explosion;
- “everything in JSON”.

---

# ADR-028 — Preserve numerator and denominator

**Status:** ACCEPTED

## Decision

Whenever a rate is stored/derived, preserve numerator + denominator where available.

Examples:

```text
fill
requests/view
CTR
```

## Reason

Rates alone are diagnostically ambiguous.

---

# ADR-029 — Time uncertainty is first-class

**Status:** ACCEPTED

## Decision

Support:

```text
exact timestamp
metric interval
bounded occurrence window
approximate reported onset
external rollout interval
```

Do not collapse everything to one timestamp.

---

# ADR-030 — Store source timezone semantics

**Status:** ACCEPTED

## Decision

Internal storage uses UTC timestamps, but preserves:
- GAM network timezone;
- source timezone;
- browser scenario timezone.

## Reason

Cross-source incident timelines otherwise become misleading.

---

# 7. Connector decisions

---

# ADR-031 — MVP connectors are GA4, GSC and GAM

**Status:** ACCEPTED

## Decision

Core business/API integrations:

```text
Google Analytics 4
Google Search Console
Google Ad Manager
```

## Reason

Together they cover:
- traffic/behavior;
- Search/Discover;
- monetization/ad serving.

---

# ADR-032 — All external platform connectors are read-only

**Status:** ACCEPTED

## Decision

No provider write operations in MVP.

## Reason

Reduces blast radius and security risk.

The product diagnoses.

Humans act.

---

# ADR-033 — Connector extracts are predefined and versioned

**Status:** ACCEPTED

## Decision

Use named extract definitions such as:

```text
GA4_TRAFFIC_HOURLY_V1
GSC_SEARCH_DAILY_V1
GAM_INVENTORY_HEALTH_V1
```

## Reason

Reproducibility and source semantics.

## Consequence

LLM does not construct arbitrary provider queries.

---

# ADR-034 — Connector source freshness is explicit

**Status:** ACCEPTED

## Decision

Data can be:

```text
PRELIMINARY
MATURE
STALE
UNKNOWN
```

or equivalent.

## Reason

Missing or incomplete source data must not become business zero.

---

# ADR-035 — GA4 is measurement, not physical truth

**Status:** ACCEPTED

## Decision

Incident Engine must consider tracking integrity.

## Reason

GA4 can change because:
- consent;
- implementation;
- pageview behavior;
- source attribution.

---

# ADR-036 — Search and Discover remain separate surfaces

**Status:** ACCEPTED

## Decision

Do not combine Search and Discover into generic “Google traffic.”

## Reason

They have different behavior, volatility and diagnostics.

---

# ADR-037 — URL Inspection is incident-driven

**Status:** ACCEPTED

## Decision

No continuous mass URL Inspection polling.

Use during bounded investigation.

## Reason

Cost/quota/noise.

---

# ADR-038 — GAM is diagnostic, not accounting ledger

**Status:** ACCEPTED

## Decision

Raw GAM total revenue is not default site health metric.

Use:
- delivery;
- request;
- impression;
- demand;
- normalized value context.

## Reason

GAM booked/reported values can diverge from actual publisher financial reality.

---

# ADR-039 — GAM analysis follows the dependency chain

**Status:** ACCEPTED

## Decision

Default diagnostic chain:

```text
Traffic
→ Pageviews
→ Eligible slot opportunities
→ GAM requests
→ Eligibility/demand
→ Impressions
→ eCPM/value
→ Programmatic revenue
```

## Reason

“Revenue down” is a symptom, not a root cause.

---

# 8. Event decisions

---

# ADR-040 — Event Engine is deterministic

**Status:** ACCEPTED

## Decision

Raw observation → event promotion is rule-based/versioned.

LLM does not decide whether an event exists.

## Reason

Operational history must be reproducible.

---

# ADR-041 — Event severity is separate from causal relevance

**Status:** ACCEPTED

## Decision

A CRITICAL event is not automatically the cause of an incident.

A LOW event may be highly causally relevant.

## Reason

Severity and causality answer different questions.

---

# ADR-042 — Event severity is separate from alertability

**Status:** ACCEPTED

## Decision

Event has:
- severity;
- persistence;
- blast radius;
- confidence;
- alert policy.

These are separate.

---

# ADR-043 — Event lifecycle uses persistence and dedupe

**Status:** ACCEPTED

## Decision

Do not create a new event on every repeated observation.

Events can:
- start;
- persist;
- update;
- resolve.

## Reason

Timeline must remain readable.

---

# ADR-044 — External events are context, not cause

**Status:** ACCEPTED

## Decision

Examples:
- Google Core Update;
- GAM outage;
- CDN incident;

appear as external context.

They become causal only with matching local evidence.

---

# ADR-045 — Manual operational changes are first-class evidence

**Status:** ACCEPTED

## Decision

Users may record:
- deploy;
- rollback;
- CMP change;
- player change;
- GAM change;
- vendor launch;
- direct campaign.

## Reason

Browser cannot infer actor/reason/intent reliably.

---

# 9. Incident reasoning decisions

---

# ADR-046 — Incident Engine = deterministic core + LLM synthesis

**Status:** ACCEPTED

## Decision

Architecture:

```text
deterministic evidence/reasoning core
+
LLM explanation
```

## Reason

LLM should explain evidence.

It should not define reality.

---

# ADR-047 — Baseline before causal ranking

**Status:** ACCEPTED

## Decision

Incident workflow starts with:
- baseline;
- onset;
- affected period;
- controls.

## Reason

Without baseline, normal variability becomes fake incident evidence.

---

# ADR-048 — Detect contaminated baseline

**Status:** ACCEPTED

## Decision

If degradation started before reported onset:
pre-incident window must be adjusted.

## Reason

A degraded period cannot be used as “healthy” baseline.

---

# ADR-049 — Localize before explaining

**Status:** ACCEPTED

## Decision

Determine:

```text
what is affected
what is not affected
```

before candidate ranking.

## Reason

Scope is powerful causal evidence.

---

# ADR-050 — Temporal order is necessary but insufficient

**Status:** ACCEPTED

## Decision

A candidate must precede a symptom to explain onset.

But temporal overlap alone does not prove causality.

---

# ADR-051 — Mechanism is required

**Status:** ACCEPTED

## Decision

A top hypothesis must state:

```text
candidate
→ mechanism
→ intermediate effect
→ symptom
```

Not just:
“CMP issue”
or
“Google update”.

---

# ADR-052 — Prefer change → intermediate signal → symptom

**Status:** ACCEPTED

## Decision

Intermediate evidence increases hypothesis weight.

Example:

```text
TCF error
→ GAM requests fall
→ impressions fall
```

is stronger than:

```text
CMP changed
→ revenue fell
```

---

# ADR-053 — Contradiction search is mandatory

**Status:** ACCEPTED

## Decision

For top hypotheses, actively search evidence against them.

Checks include:
- onset before candidate;
- wrong segment;
- unaffected controls;
- missing expected signal;
- persistence after removal;
- failed rollback.

## Reason

Prevents confirmation bias.

---

# ADR-054 — Onset-before-candidate strongly weakens causal attribution

**Status:** ACCEPTED

## Decision

If measurable symptom begins before candidate exists:

candidate cannot explain initial onset.

It may remain:
- later contributor;
- aggravating factor;

only with evidence.

---

# ADR-055 — Persistence after removal lowers confidence

**Status:** ACCEPTED

## Decision

If:
- suspected component removed;
- plausible recovery interval passes;
- symptom continues;

primary-cause confidence declines.

## Caveat

Recovery latency is symptom-specific.

Search may lag longer than JS/runtime behavior.

---

# ADR-056 — Rollback + recovery strongly increases evidence

**Status:** ACCEPTED

## Decision

Pattern:

```text
introduced
→ symptom
→ removed
→ recovery
```

is strong causal evidence when timing/mechanism align.

---

# ADR-057 — Unaffected segments are active evidence

**Status:** ACCEPTED

## Decision

Controls are not just display context.

They are used to:
- strengthen;
- weaken;
- reject;

hypotheses.

---

# ADR-058 — Multi-causal incidents are allowed

**Status:** ACCEPTED

## Decision

Incident Engine need not force one root cause.

Possible:
- primary cause;
- contributors;
- unresolved factors.

---

# ADR-059 — Do not double-count descendant metrics

**Status:** ACCEPTED

## Decision

Example:

```text
requests ↓
impressions ↓
revenue ↓
```

may be one causal chain, not three independent confirmations.

---

# ADR-060 — Last Known Good is incident-specific

**Status:** ACCEPTED

## Decision

LKG depends on:
- incident;
- affected scope;
- scenario/template;
- baseline.

No single global site LKG.

---

# ADR-061 — Last Known Good is reference, not auto-rollback

**Status:** ACCEPTED

## Decision

LKG supports comparison only.

MVP does not automatically restore it.

---

# ADR-062 — Counterfactual tests minimize blast radius

**Status:** ACCEPTED

## Decision

Prefer:
- one variable;
- control;
- prediction;
- bounded duration.

Avoid:
- disabling all monetization systems.

---

# ADR-063 — Next test must be falsifiable

**Status:** ACCEPTED

## Decision

Recommended test states:

```text
If H true → X
If H false → Y
```

## Reason

Testing should reduce uncertainty, not merely “try something.”

---

# ADR-064 — Incident corpus is precedent, not truth

**Status:** ACCEPTED

## Decision

Public incident history supports:
- mechanism retrieval;
- examples;
- hypothesis generation.

It does NOT establish:
- prevalence;
- probability;
- proof.

---

# ADR-065 — Private publisher incidents do not automatically become shared knowledge

**Status:** ACCEPTED

## Decision

Tenant incidents remain private by default.

No silent cross-tenant training/sharing.

---

# 10. AI decisions

---

# ADR-066 — LLM receives bounded evidence packets

**Status:** ACCEPTED

## Decision

LLM input contains:
- structured incident;
- evidence;
- hypotheses;
- contradictions;
- allowed evidence IDs;
- allowed tests.

Not:
- raw DB;
- arbitrary logs;
- full DOM history.

---

# ADR-067 — LLM cannot create evidence

**Status:** ACCEPTED

## Decision

Evidence comes from:
- browser;
- connectors;
- manual input;
- external official context.

LLM may only interpret.

---

# ADR-068 — LLM cannot strengthen confidence beyond deterministic gate

**Status:** ACCEPTED

## Decision

If deterministic engine allows maximum:

```text
POSSIBLE CONTRIBUTOR
```

LLM may not output:

```text
PROBABLE
```

or:
```text
CONFIRMED
```

---

# ADR-069 — LLM outputs must be structured and validated

**Status:** ACCEPTED

## Decision

Important LLM outputs use schema validation.

Evidence IDs and allowed test IDs must exist.

---

# ADR-070 — No arbitrary LLM tools

**Status:** ACCEPTED

## Decision

LLM cannot:
- run SQL;
- write Playwright code;
- construct arbitrary Google API requests;
- call production actions.

It may select semantic approved actions.

---

# ADR-071 — No AI analysis running continuously by default

**Status:** ACCEPTED

## Decision

LLM used:
- Weekly Brief;
- incident investigation;
- selected explanations.

Not:
- every checkpoint;
- every metric point;
- every event.

## Reason

Cost, noise, reproducibility.

---

# 11. Evaluation decisions

---

# ADR-072 — Evals are part of product architecture

**Status:** ACCEPTED

## Decision

Reasoning changes require eval coverage.

## Reason

Incident intelligence cannot be tested with software unit tests alone.

---

# ADR-073 — False-cause rate is a critical quality metric

**Status:** ACCEPTED

## Decision

A system that confidently asserts unsupported root causes is failing even if it “answers” most incidents.

---

# ADR-074 — Counterexamples are release-gating

**Status:** ACCEPTED

## Decision

Permanent important evals include:
- candidate introduced after onset;
- suspected cause removed but symptom persists;
- external update after onset;
- broad shutdown/confounded test.

---

# ADR-075 — UNRESOLVED precision and recall are measured

**Status:** ACCEPTED

## Decision

Do not optimize:
- always choose cause;
or:
- always say unresolved.

Both precision and recall matter.

---

# ADR-076 — Public incident frequency is not prior probability

**Status:** ACCEPTED

## Decision

Corpus counts are never used as epidemiological priors.

## Reason

Source availability is heavily biased.

---

# ADR-077 — Hybrid engine is target architecture

**Status:** ACCEPTED

## Decision

Compare:

```text
RULE-ONLY
LLM-ONLY
HYBRID
```

Target:
HYBRID outperforms especially on:
- contradictions;
- provenance;
- epistemic restraint.

---

# 12. Architecture decisions

---

# ADR-078 — Modular monolith

**Status:** ACCEPTED

## Decision

One codebase/application with clear modules.

Separate runtime processes:
- API;
- general worker;
- browser worker;
- scheduler.

Not microservices.

---

# ADR-079 — Browser worker is separate from API process

**Status:** ACCEPTED

## Reason

Chromium:
- memory-heavy;
- crash-prone;
- different concurrency profile.

A browser crash must not kill API.

---

# ADR-080 — Background jobs are required

**Status:** ACCEPTED

## Decision

Browser, connectors, event processing, weekly brief and incident background work run through jobs.

Long work does not happen inside request lifecycle.

---

# ADR-081 — PostgreSQL-backed job queue first

**Status:** ACCEPTED

## Decision

Start with:
```text
PostgreSQL job table + workers
```

## Alternatives deferred

- Redis/Celery/RQ
- cloud queues
- Kafka

## Revisit trigger

Measured queue contention/reliability need.

---

# ADR-082 — Scheduler inserts jobs only

**Status:** ACCEPTED

## Decision

Scheduler:
- decides what is due;
- inserts jobs.

It does not execute domain logic directly.

---

# ADR-083 — One shared codebase, multiple process types

**Status:** ACCEPTED

## Decision

Deploy:
- API;
- worker;
- browser-worker;
- scheduler;

from same repository/version.

This is workload separation, not microservices.

---

# ADR-084 — No Kubernetes in MVP

**Status:** ACCEPTED

## Decision

Use simple managed/container deployment.

## Revisit trigger

Only if provider/scale creates concrete operational benefit.

---

# ADR-085 — No Redis dependency by default

**Status:** ACCEPTED

## Decision

Do not add Redis for:
- queue;
- cache;
- sessions;

unless measured need requires it.

---

# ADR-086 — No vector database by default

**Status:** ACCEPTED

## Decision

Incident corpus retrieval starts with:
- deterministic filters;
- Postgres search;
- simple in-process logic.

A vector DB is not justified by MVP.

---

# ADR-087 — Simple cloud deployment

**Status:** ACCEPTED

## Decision

MVP production needs:
- frontend;
- API;
- workers;
- Postgres;
- object storage;
- secret store.

No platform engineering program.

---

# 13. Security decisions

---

# ADR-088 — Customer data is confidential by default

**Status:** ACCEPTED

## Decision

Screenshots, DOM, metrics, incidents, reports and operational history are tenant-confidential.

Public source origin does not automatically make derived analysis public.

---

# ADR-089 — Tenant isolation is mandatory from first implementation

**Status:** ACCEPTED

## Decision

Tenant scoping is not deferred until “enterprise.”

All tenant-owned objects have deterministic tenant ownership.

---

# ADR-090 — Shared database with application tenant scoping for MVP

**Status:** ACCEPTED

## Decision

Use shared PostgreSQL.

Authorization/repository layer enforces tenant scope.

## Revisit trigger

Security/commercial requirements justify physical tenant isolation or RLS.

---

# ADR-091 — Google connector tokens stored outside normal DB rows

**Status:** ACCEPTED

## Decision

Refresh tokens live in secret manager/secure secret layer.

DB stores reference + metadata only.

---

# ADR-092 — Browser treats monitored site as hostile

**Status:** ACCEPTED

## Decision

Browser worker:
- isolated;
- non-root;
- Chromium sandbox;
- private-network egress blocked;
- no sensitive host mounts.

---

# ADR-093 — Browser SSRF protection is network-level + application-level

**Status:** ACCEPTED

## Decision

Do not rely only on URL regex/validation.

Need:
- target validation;
- DNS/IP validation;
- private/reserved range blocking;
- egress control;
- subresource protection;
- redirect control.

---

# ADR-094 — Object storage is private

**Status:** ACCEPTED

## Decision

Evidence is never public-read.

Access requires tenant authorization.

Use short-lived signed URLs or authenticated proxy.

---

# ADR-095 — Signed evidence URLs are short-lived

**Status:** ACCEPTED

## Decision

Initial target TTL:

```text
~5 minutes
```

Do not persist signed URLs in DB/email.

---

# ADR-096 — Bounded raw evidence retention

**Status:** ACCEPTED

## Decision

Initial defaults:

```text
core normalized evidence: ~24 months
screenshots: ~90 days
raw DOM: ~30 days
detailed network rows: ~30 days
connector raw responses: ~30 days
Playwright traces: ~7 days
```

Incident-referenced evidence may be pinned longer.

## Note

These are engineering defaults, not contractual/legal guarantees.

---

# ADR-097 — Incident evidence can be pinned

**Status:** ACCEPTED

## Decision

Material evidence referenced by retained incident reports can move to:

```text
INCIDENT_PINNED
```

## Reason

Report must remain traceable.

---

# ADR-098 — LLM is untrusted security-wise

**Status:** ACCEPTED

## Decision

Authorization, data access and action permission are enforced outside prompts.

Prompt text is never a security boundary.

---

# ADR-099 — Raw DOM not passed to LLM by default

**Status:** ACCEPTED

## Decision

Use:

```text
raw page
→ collectors/normalization
→ structured evidence
→ LLM
```

## Reason

Privacy, cost and prompt injection risk.

---

# ADR-100 — No authenticated browser monitoring in MVP

**Status:** ACCEPTED

## Decision

No:
- customer login credentials;
- paywall bypass;
- employee sessions;
- authenticated publisher user profiles.

## Revisit trigger

Specific validated use case + security review.

---

# 14. Cost and scale decisions

---

# ADR-101 — MVP optimized for small publisher count

**Status:** ACCEPTED

## Decision

Initial architecture targets:

```text
1–3 pilot publishers
```

then small commercial rollout.

Not global hyperscale.

---

# ADR-102 — Representative monitoring controls cost

**Status:** ACCEPTED

## Decision

Do not monitor every URL.

Use:
- templates;
- representative pages;
- low scenario count;
- 6-hour cadence.

---

# ADR-103 — LLM cost is incident/weekly, not continuous

**Status:** ACCEPTED

## Decision

No per-checkpoint LLM reasoning.

## Reason

Target COGS remains viable.

---

# ADR-104 — Initial site COGS target

**Status:** ACCEPTED as product target

## Decision

Target:

```text
€25–50/site/month
```

Early conservative ceiling:

```text
~€60/site/month
```

## Note

This is a hypothesis to measure, not an engineering guarantee.

---

# 15. Operational decisions

---

# ADR-105 — Local / staging / production environments

**Status:** ACCEPTED

## Decision

Minimum three environment classes.

Production publisher data does not flow into local by default.

---

# ADR-106 — GitHub from day one

**Status:** ACCEPTED

## Decision

Repository is source of truth for:
- code;
- specs;
- ExecPlans;
- ADRs;
- eval assets.

---

# ADR-107 — ExecPlans for substantial work

**Status:** ACCEPTED

## Decision

Use `PLANS.md`.

Complex work receives:

```text
plans/EP-NNN-*.md
```

with milestones, validation and progress.

---

# ADR-108 — Stop-and-fix after each milestone

**Status:** ACCEPTED

## Decision

ExecPlan flow:

```text
implement
→ validate
→ fix
→ validate
→ continue
```

Do not accumulate known failures to the end.

---

# ADR-109 — Documentation is implementation contract, not commentary

**Status:** ACCEPTED

## Decision

Canonical specs constrain Codex.

If implementation discovers a required durable change:
update decision/spec intentionally.

Do not silently diverge.

---

# ADR-110 — MVP scope expansion requires ADR

**Status:** ACCEPTED

## Decision

Every ExecPlan declares:

```text
MVP scope impact: NO
```

or:

```text
YES — approved by ADR-XXX
```

---

# 16. Initial implementation sequence decisions

---

# ADR-111 — First engineering proof is browser checkpoint, not AI

**Status:** ACCEPTED

## Decision

First meaningful product behavior:

```text
one public URL
→ Chromium
→ checkpoint
→ screenshot
→ DOM
→ scripts/network/errors
→ persisted evidence
```

## Reason

Incident intelligence is useless without trustworthy historical evidence.

---

# ADR-112 — Second proof is semantic change memory

**Status:** ACCEPTED

## Decision

Two comparable checkpoints:

```text
A
vs
B
→ normalized diff
→ meaningful event
```

before deep AI.

---

# ADR-113 — Business connectors before full Incident Engine

**Status:** ACCEPTED

## Decision

Add GA4/GSC/GAM enough to correlate:
- technical state;
- business symptom;

before mature RCA.

---

# ADR-114 — Incident Engine built incrementally

**Status:** ACCEPTED

## Decision

Recommended progression:

```text
intake
→ windows
→ localization
→ evidence pack
→ candidates
→ contradictions
→ ranking
→ LLM report
```

Not:
```text
one prompt: "what caused this?"
```

---

# ADR-115 — Evals become release gate for reasoning

**Status:** ACCEPTED

## Decision

Incident reasoning cannot become trusted pilot functionality until critical eval slices pass.

---

# 17. Rejected architecture directions

---

# ADR-116 — REJECTED: microservices-first

**Status:** REJECTED

## Reason

Adds operational complexity without pilot value.

---

# ADR-117 — REJECTED: Kafka/event-stream-first

**Status:** REJECTED

## Reason

Current event volume and reliability needs do not justify it.

---

# ADR-118 — REJECTED: graph database for Event Graph

**Status:** REJECTED

## Reason

Typed relational edges are sufficient.

---

# ADR-119 — REJECTED: warehouse-first architecture

**Status:** REJECTED

## Reason

Product requires incident evidence and bounded metrics, not enterprise BI warehouse.

---

# ADR-120 — REJECTED: LLM as primary anomaly detector

**Status:** REJECTED

## Reason

Would be:
- expensive;
- non-deterministic;
- hard to evaluate;
- noisy.

---

# ADR-121 — REJECTED: AI-selected root cause without contradiction checks

**Status:** REJECTED

## Reason

Violates core epistemic design.

---

# ADR-122 — REJECTED: “monitor everything” browser model

**Status:** REJECTED

## Reason

Unbounded:
- cost;
- traffic;
- storage;
- noise.

Template-first representative coverage is preferred.

---

# ADR-123 — REJECTED: autonomous production remediation in MVP

**Status:** REJECTED

## Reason

Insufficient trust/calibration/security maturity.

---

# ADR-124 — REJECTED: revenue as sole/top-level health signal

**Status:** REJECTED

## Reason

Revenue is downstream and confounded by:
- volume;
- price;
- direct delivery;
- accounting/reporting.

---

# ADR-125 — REJECTED: external Google update = cause

**Status:** REJECTED

## Reason

Temporal overlap is context only until publisher-specific evidence matches.

---

# ADR-126 — Repository bootstrap toolchain uses uv and pnpm

**Status:** ACCEPTED  
**Date:** 2026-08-13

## Context

The canonical architecture selected FastAPI/Python and Next.js/React but intentionally left the Python dependency manager and exact repository tooling open. EP-001 needs reproducible local and CI installs without maintaining multiple competing workflows.

## Decision

Backend:

```text
Python 3.12
uv
FastAPI
Ruff
mypy
pytest
```

Frontend:

```text
Node.js LTS pinned by repository version metadata
pnpm pinned through packageManager metadata
Next.js / React / TypeScript
ESLint
TypeScript typecheck
focused frontend test runner
```

Commit one backend lockfile and one frontend lockfile. CI and documentation use only these package-manager paths.

Exact library patch versions are selected and frozen during EP-001 implementation. They are implementation locks, not new product decisions.

## Reason

`uv` provides a fast, low-ceremony Python environment and lockfile workflow that fits the available Python 3.12 runtime. `pnpm` provides deterministic Node installs with efficient dependency handling. The selected quality tools are established and small enough for the modular-monolith foundation.

## Consequences

- `OPEN-001` is resolved.
- Poetry, pip-tools, npm, and yarn are not parallel supported workflows.
- Backend and frontend CI can use locked/frozen installs.
- Node LTS and package-manager versions must be explicit in repository metadata.
- Significant new tooling still requires normal dependency review.

## Alternatives considered

- Poetry
- pip-tools
- npm
- yarn
- supporting several package managers

Rejected because parallel workflows increase drift and onboarding cost without MVP benefit.

## Revisit trigger

Revisit only if the selected manager becomes unmaintained, cannot support required reproducible builds, or creates a measured deployment/security blocker.

---

# ADR-127 — Persistence uses SQLAlchemy 2.x, psycopg 3, and Alembic

**Status:** ACCEPTED  
**Date:** 2026-08-13

## Context

The system requires PostgreSQL, tenant-aware relational modeling, migrations, ordinary repository queries, and explicit concurrency SQL for job claiming. `OPEN-002` left the ORM undecided.

## Decision

Use:

```text
SQLAlchemy 2.x typed declarative models
psycopg 3 PostgreSQL driver
AsyncEngine / AsyncSession application convention
Alembic migrations
```

The relational schema is the contract. Use explicit SQL where it is clearer or required for PostgreSQL-specific primitives such as `FOR UPDATE SKIP LOCKED`, partial indexes, and fenced queue transitions.

All schema changes are version-controlled migrations. Application runtime and migration credentials/configuration remain separable.

## Reason

This stack is mature, explicit, well supported by FastAPI, and preserves access to PostgreSQL semantics. It avoids using a convenience model layer as the source of domain or database truth.

## Consequences

- `OPEN-002` is resolved.
- EP-001 must establish one documented session and transaction convention.
- Alembic is mandatory for schema changes.
- Queue primitives may use reviewed SQL without creating a second persistence architecture.
- Core semantics remain typed relational columns; JSONB remains bounded and purposeful.

## Alternatives considered

- SQLModel
- raw SQL for every persistence path
- another ORM/migration framework

Rejected because SQLModel adds another abstraction over SQLAlchemy while raw SQL everywhere would increase routine persistence work without improving the queue-specific operations that already remain explicit.

## Revisit trigger

Revisit only if the stack produces a measured correctness, maintainability, or performance blocker that cannot be solved with explicit SQL inside the same PostgreSQL architecture.

---

# ADR-128 — PostgreSQL jobs use explicit reclaim, fencing, and split idempotency namespaces

**Status:** ACCEPTED  
**Date:** 2026-08-13

## Context

ADR-081 requires a PostgreSQL-backed job queue. The architecture describes transactional claims and leases, but EP-001 needs precise behavior for crash recovery, stale workers, tenant/global jobs, idempotency, and initial status scope.

Without an explicit contract:

- a stale worker may complete work after another worker reclaimed it;
- normal claiming may silently steal expired RUNNING work;
- nullable `tenant_id` uniqueness may treat global and tenant jobs incorrectly;
- an attempt-history table and extra statuses may be added before a product need exists.

## Decision

### Status vocabulary

EP-001 uses exactly:

```text
PENDING
RUNNING
RETRY
COMPLETE
FAILED
```

Do not add `CANCELLED` in EP-001.

### Claiming

Normal claim selects eligible `PENDING` or `RETRY` rows with transactional PostgreSQL locking equivalent to:

```sql
FOR UPDATE SKIP LOCKED
```

Every successful claim creates a new opaque `lock_token`, records worker ownership and lease expiry, and transitions the job to `RUNNING`.

### Fencing

Heartbeat, completion, retry, and failure updates require all of:

```text
job id
status = RUNNING
matching lock_token
```

An update that affects no row is a lost/stale lease, not success.

### Reclaim

Expired `RUNNING` jobs are handled by a separate reclaim operation. Normal claim does not silently reclaim them.

Reclaim:

- identifies expired leases;
- transitions retryable work to `RETRY` with bounded backoff;
- transitions exhausted work to `FAILED`;
- clears worker ownership, `lock_token`, and lease fields;
- preserves attempt count and stable error metadata.

The reclaimed row can be claimed normally only after reclaim completes.

### Attempts

EP-001 stores the current attempt count and last error metadata on `jobs`.

Do not create a `job_attempts` table in EP-001. Domain attempts such as future checkpoint attempts remain separate domain truth.

### Idempotency namespaces

Use two partial unique indexes for non-null `idempotency_key` values:

```sql
UNIQUE (tenant_id, idempotency_key)
WHERE tenant_id IS NOT NULL
  AND idempotency_key IS NOT NULL
```

and:

```sql
UNIQUE (idempotency_key)
WHERE tenant_id IS NULL
  AND idempotency_key IS NOT NULL
```

This preserves one namespace per tenant and a distinct namespace for explicitly global jobs.

### Security boundary

Tenant-owned jobs carry `tenant_id`. Job payloads contain identifiers/references, never raw OAuth tokens, API keys, passwords, or signing secrets. Workers validate job tenant ownership against referenced objects before executing future domain handlers.

## Reason

Separate reclaim makes ownership transitions observable and testable. A per-claim token fences stale workers even if worker identity is reused. Partial indexes model PostgreSQL NULL behavior correctly for tenant and global work. Avoiding premature status and attempt-history expansion keeps the first queue understandable.

## Consequences

- claim, reclaim, and finalization are separate repository operations;
- queue tests must include concurrent claims, expired leases, stale tokens, and both idempotency namespaces;
- retries do not erase domain run/attempt evidence;
- cancellation requires a later concrete use case and ADR/update;
- detailed infrastructure attempt history may be added later only if operational evidence justifies it;
- older architecture examples that list `CANCELLED` are generic and are specialized by this accepted decision for EP-001.

## Alternatives considered

- reclaim expired RUNNING rows inside normal claim;
- fence only by `locked_by` worker name;
- use one ordinary unique constraint with nullable `tenant_id`;
- create `job_attempts` immediately;
- include `CANCELLED` before cancellation semantics exist.

Rejected because they create ambiguous ownership, incorrect uniqueness, or premature workflow complexity.

## Revisit trigger

Revisit when a real product workflow requires cancellation, per-attempt infrastructure forensics, substantially different scheduling semantics, or measured PostgreSQL queue limitations.

---

# 18. Open decisions

These are intentionally NOT locked yet.

They should be decided during repository bootstrap or implementation and added as new ADRs.

## OPEN-001 — Python dependency manager — RESOLVED

**Resolved by:** ADR-126

Selected:

```text
uv
```

## OPEN-002 — ORM — RESOLVED

**Resolved by:** ADR-127

Selected:

```text
SQLAlchemy 2.x + psycopg 3 + Alembic
```

## OPEN-003 — Authentication provider

Candidates:
```text
managed auth provider
framework-compatible established library
```

## OPEN-004 — Cloud provider

Need simple:
- app/container;
- Postgres;
- object storage;
- secret manager.

## OPEN-005 — Object storage provider

Need S3-compatible/private storage.

## OPEN-006 — LLM provider/model

Must support:
- structured outputs;
- strong reasoning;
- acceptable privacy/data controls;
- cost tracking.

## OPEN-007 — Email provider

Only when alert/Weekly delivery implemented.

## OPEN-008 — Internal application monitoring vendor

Could begin with provider-native/basic tooling.

## OPEN-009 — PostgreSQL RLS

MVP defaults to application-layer scoping.

Reevaluate after security review.

## OPEN-010 — Exact production retention commitments

Engineering defaults exist in `SECURITY.md`.

Contractual promises require legal/commercial decision.

---

# 19. ADR review checklist

Before adding a new durable decision, ask:

```text
Will this affect multiple future implementation tasks?
Will Codex otherwise reopen the question?
Does it affect architecture, security, product semantics or data meaning?
```

If yes:
ADR.

---

# 20. ADR template

Use:

```markdown
# ADR-XXX — <Decision title>

**Status:** PROPOSED / ACCEPTED / SUPERSEDED / REJECTED
**Date:** YYYY-MM-DD
**Supersedes:** ADR-XXX if relevant

## Context

Why does this decision exist?

## Decision

What are we doing?

## Reason

Why?

## Consequences

What becomes easier/harder?

## Alternatives considered

What did we reject?

## Revisit trigger

What concrete evidence would justify reopening this?
```

---

# 21. Codex rules for decisions

Codex MUST:

- read this file before making architecture-changing choices;
- follow ACCEPTED ADRs;
- reference ADR IDs in relevant ExecPlans;
- create/propose a new ADR for a durable new direction;
- preserve superseded history;
- not reopen accepted decisions without a concrete trigger;
- distinguish implementation detail from product/architecture decision.

Codex MUST NOT:

- introduce a rejected technology because it is familiar;
- silently add Redis/Kafka/Neo4j/ClickHouse/Kubernetes;
- silently expand OAuth permissions;
- silently alter checkpoint cadence;
- silently change confidence semantics;
- silently introduce cross-tenant knowledge sharing;
- silently change raw evidence retention;
- silently let LLM perform new privileged actions;
- silently widen MVP scope.

---

# 22. Decision hierarchy

When implementation choices conflict:

```text
current explicit user decision
→ accepted ADR
→ MVP.md
→ relevant subsystem spec
→ ARCHITECTURE.md
→ PRODUCT.md
→ current ExecPlan
→ implementation preference
```

`DOMAIN.md` remains authoritative for domain semantics.

`SECURITY.md` remains authoritative for security constraints.

---

# 23. Final decision principle

The purpose of this file is not to freeze the product forever.

It is to make change explicit.

A healthy architecture changes when evidence changes.

It should not change because:

```text
a new coding session preferred another stack
```

The standard is:

# **Decide once. Record why. Reopen only when reality gives us a reason.**
