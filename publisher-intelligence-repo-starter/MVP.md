# MVP.md
## Publisher Incident Intelligence Platform — MVP Scope Contract
### v1.0

**Audience:** Product, Codex, engineering, technical reviewers  
**Status:** Canonical MVP boundary  
**Purpose:** Define exactly what the first commercially testable version includes and excludes  
**Depends on:** `PRODUCT.md` when available, `DOMAIN.md`, `BROWSER.md`, `DATA_MODEL.md`, `EVENTS.md`, `CONNECTORS.md`, `INCIDENT.md`, `EVALS.md`, `PLANS.md`  
**Authority:** Any feature outside this file requires an explicit decision recorded in `DECISIONS.md`

---

# 0. MVP principle

The MVP is not a smaller version of every future idea.

It is the smallest product that can prove the central thesis:

> **If we continuously preserve the technical and business state of a publisher, we can reconstruct incidents much faster and with materially less guesswork than current publisher workflows.**

The MVP must prove four things:

```text
1. We can observe reliably.
2. We can preserve useful operational memory.
3. We can detect meaningful changes without overwhelming users.
4. We can investigate a reported incident and produce a grounded, useful explanation.
```

Anything that does not materially help prove one of these four claims should remain outside MVP.

---

# 1. Product thesis

Digital publishers operate as systems made of many interacting components:

```text
website/templates
JavaScript
CMP
GPT
Prebid
video players
CDN
analytics
Search
GAM
demand partners
external platforms
```

When something goes wrong, publishers often lack a unified history of what changed.

The result is frequently:

```text
symptom appears
→ multiple teams/vendors speculate
→ several components are disabled
→ revenue or traffic is lost
→ root cause remains uncertain
```

The MVP must create a persistent operational memory that allows the publisher to ask:

> **What changed before this problem started, what evidence supports each explanation, and what should we test next?**

---

# 2. Primary user

The MVP is designed for:

- digital publishers;
- publisher ad-ops/commercial teams;
- product/technical managers;
- audience/SEO teams;
- publisher executives who understand industry concepts but are not deeply technical.

It should also be useful to:
- ad-tech partners;
- monetization vendors;
- technical consultants;

when investigating publisher incidents together.

The MVP is not built primarily for:
- software engineers debugging backend microservices;
- advertisers;
- agencies buying media;
- general website monitoring customers.

---

# 3. Initial commercial target

Pilot target:

```text
1–3 publishers
```

Potential production target after validation:

```text
small number of publisher organizations
multiple sites per publisher
```

The system should be multi-tenant from the data/security model, but the MVP does not need enterprise-scale administration.

---

# 4. MVP user promise

The MVP should credibly promise:

> **We continuously record the most important technical and business state of your publishing operation. When something goes wrong, we reconstruct what changed, identify the affected layer, rank the most plausible explanations, show the evidence for and against them, and recommend the safest next diagnostic step.**

It should NOT promise:

- guaranteed root cause;
- guaranteed revenue increase;
- guaranteed Google traffic recovery;
- prediction of Google algorithms;
- complete policy compliance;
- complete monitoring of every user/device;
- autonomous remediation.

---

# 5. Core MVP workflow

The end-to-end MVP workflow is:

```text
Publisher onboarded
        ↓
Representative pages selected
        ↓
6-hour synthetic browser checkpoints
        +
GA4 / GSC / GAM read-only telemetry
        +
public configuration / external context
        ↓
Operational timeline created
        ↓
Meaningful events detected
        ↓
Weekly brief / rare critical alerts
        ↓
Publisher notices problem
        ↓
Investigate
        ↓
Symptom localized
        ↓
Baseline + Last Known Good reconstructed
        ↓
Relevant changes/events retrieved
        ↓
Hypotheses ranked
        ↓
Supporting + contradicting evidence shown
        ↓
Next low-risk test recommended
```

This entire loop must work before we consider the MVP successful.

---

# 6. MVP screens

The MVP should have only three primary user-facing product areas.

## 6.1 Home

Purpose:
answer:

> **Is anything important happening right now?**

Home should show:

```text
HEALTHY
ATTENTION
INCIDENT
```

plus:

- latest meaningful findings;
- unresolved critical attention items;
- latest weekly brief;
- quick entry into Investigate.

Home is not a dashboard full of charts.

---

## 6.2 Timeline

Purpose:

> **Show the operational memory of the publisher.**

Timeline includes:

- browser-detected changes;
- meaningful anomalies;
- external official events;
- operational/manual changes;
- recoveries;
- relevant source/data-quality events where useful.

Filters:

```text
Site
Traffic
Search
Monetization
Google
CMP
Video
Performance
External
```

Do not expose every raw observation.

---

## 6.3 Investigate

Purpose:

> **Help the publisher investigate a problem.**

Input:

```text
What happened?
When did it start?
Optional context / affected area / evidence
```

Then:

```text
Investigate
```

Output:

- observed symptom;
- affected scope;
- baseline;
- timeline;
- Last Known Good;
- ranked hypotheses;
- supporting evidence;
- contradicting evidence;
- unknowns;
- external context;
- recommended next test;
- confidence label.

---

# 7. No fourth core screen in MVP

Do not add dedicated primary screens for:

- Changes;
- Raw logs;
- Network;
- Scripts;
- GPT;
- Prebid;
- CMP;
- SEO;
- Performance;
- Reports;
- Assets;
- Settings analytics.

These can appear:
- inside Timeline event details;
- inside incident evidence;
- inside technical drill-down panels.

A separate screen is justified later only if real users repeatedly need it.

---

# 8. Onboarding

MVP onboarding should support:

```text
Publisher
→ Site
→ Representative URLs/templates
→ Browser scenarios
→ GA4
→ Search Console
→ GAM
```

Public monitoring can begin before every connector is available.

Connector availability is shown explicitly.

Do not block the whole product because one optional source is missing.

---

# 9. Representative URLs

Target:

```text
approximately 20–40 representative URLs per site
```

depending on publisher complexity.

Typical templates:

- homepage;
- category;
- standard article;
- video article;
- gallery;
- live article if relevant;
- special content format if materially different.

The product monitors templates, not every article on the internet.

---

# 10. Template-first monitoring

The MVP needs a stable template model.

Example:

```text
homepage
article
category
video_article
gallery
```

A concrete article URL may rotate over time.

The template identity remains stable.

This allows the product to detect:

```text
article template changed
```

instead of:

```text
article #438725 changed
```

---

# 11. Synthetic Browser & 6-Hour Black Box

This is a core MVP capability, not an optional technical feature.

Every representative URL receives a scheduled core observation approximately every:

```text
6 hours
```

using:

```text
Playwright
+
real Chromium
```

The checkpoint is created even when nothing appears wrong.

Its purpose is historical evidence.

---

# 12. Core browser scenarios

MVP core scenarios:

```text
Desktop
Mobile
```

Both use:

- clean isolated BrowserContext;
- first-visit state;
- known locale/timezone;
- deterministic interaction;
- environment provenance.

Do not build a huge device matrix.

---

# 13. Consent behavior

Core browser run should observe:

```text
pre-consent
→ configured primary consent path
→ post-consent
```

where safely supported.

Reject scenario:

- canary URLs;
- lower cadence;
- incident-triggered where useful.

Do not run every possible consent scenario on every URL every six hours.

---

# 14. Browser interaction

Browser should not merely open and screenshot.

Representative article flow can include:

```text
open
→ wait
→ observe consent
→ consent action
→ scroll ~25%
→ wait
→ scroll ~50%
→ wait
→ scroll ~75%
→ inspect sticky/video
→ capture final evidence
```

This makes lazy loading, sticky behavior, GPT lifecycle and player behavior observable.

---

# 15. Browser checkpoint evidence

MVP browser checkpoint should capture, where applicable:

- viewport screenshot;
- final full-page screenshot;
- raw DOM/HTML;
- normalized structural DOM;
- script inventory;
- third-party dependency inventory;
- network request summary;
- request failures;
- console/JS errors;
- final URL/status;
- redirect behavior;
- GPT slots/lifecycle;
- CMP behavior;
- Prebid observable state;
- video/player state;
- SEO runtime state;
- synthetic performance indicators;
- browser/scenario/environment metadata.

Not every collector must be complete on day one.

Implementation follows browser milestones B1–B8.

---

# 16. Browser checkpoint immutability

Completed raw evidence is immutable.

If:
- parser improves;
- normalizer changes;
- event logic changes;

derive new output from old evidence.

Never rewrite historical checkpoint facts.

---

# 17. Browser failure semantics

MVP must distinguish:

```text
SITE_ERROR
BROWSER_ERROR
TIMEOUT
BLOCKED
PARTIAL
COMPLETE
```

A publisher 503 is evidence.

A Chromium crash is our failure.

They must never be confused.

---

# 18. Browser non-goals

MVP does NOT include:

- real-user monitoring SDK;
- session replay;
- residential proxy network;
- stealth/anti-bot bypass;
- browser fingerprint evasion;
- large geography matrix;
- Firefox/Safari matrix;
- every mobile device;
- automatic ad clicking;
- authenticated publisher-user flows;
- paywall bypass.

---

# 19. Screenshots

Screenshots are first-class evidence.

MVP must allow:

```text
Last Known Good
vs
Incident state
```

visual comparison.

Advanced computer vision is not required.

Initial UI may use:
- side-by-side comparison;
- timestamp/scenario;
- manual visual inspection.

---

# 20. DOM / structural diff

MVP must normalize high-noise page changes.

Ignore by default:

- article copy;
- headlines;
- recommendation order;
- timestamps;
- auction IDs;
- random IDs;
- creative URLs;
- cache-busters.

Preserve:

- ad-slot structure;
- player structure;
- key scripts;
- CMP;
- sticky/fixed elements;
- canonical/noindex;
- dependencies.

---

# 21. JavaScript errors

Collect all meaningful JS/page errors.

But do not immediately surface every error.

MVP should:
- fingerprint;
- count;
- track persistence;
- relate to critical runtime stages.

One unrelated widget error should not create an alert.

---

# 22. GPT

MVP should support core GPT lifecycle observation:

```text
expected slot
→ defined
→ request
→ response
→ render
→ onload
→ viewable
```

The product does not need to expose every GPT API feature.

Primary diagnostic objective:

> **Where did the slot lifecycle stop?**

---

# 23. Expected slot model

MVP must preserve expected slot identity by template.

Otherwise a deleted slot simply disappears and the platform cannot know it used to exist.

Example:

```text
article/mobile expects:
top
mid_1
mid_2
footer
```

Current checkpoint:

```text
mid_2 absent
```

This must be diagnosable.

---

# 24. Prebid

MVP should observe client-side Prebid where present.

Useful fields:

- Prebid presence/version;
- auctions;
- bidder requests;
- responses;
- no-bids;
- timeouts;
- auction duration;
- basic targeting state;
- GAM request timing.

Do not build a full auction analytics platform.

---

# 25. Prebid Server

Server-side details may be partially hidden.

MVP must support:

```text
NOT_OBSERVABLE
```

Do not invent bidder-level server behavior.

---

# 26. CMP / TCF

MVP should observe behavior, not merely version.

Useful:

- CMP present;
- API/stub ready;
- UI;
- Accept;
- Reject where configured;
- TCF signal;
- timing;
- errors;
- network effects;
- GAM/Prebid consequences.

CMP version change by itself should remain low relevance unless behavior changes.

---

# 27. Video

MVP should observe:

- player presence;
- dimensions;
- sticky/fixed state;
- autoplay;
- audibility/mute;
- controls;
- VAST/network behavior;
- playback-start evidence.

Do not rebuild every proprietary player API.

Use generic evidence first.

Vendor adapters only after repeated pilot value.

---

# 28. SEO/public state

MVP monitors:

- HTTP status;
- redirect;
- robots;
- meta robots/noindex;
- canonical;
- sitemap where useful;
- mobile rendered content;
- key SEO runtime state.

The platform does not become a general SEO suite.

---

# 29. ads.txt

MVP monitors:

- accessibility;
- HTTP status;
- parseability;
- empty 200;
- added/removed lines;
- DIRECT/RESELLER;
- key seller/account identity.

Routine change:
Weekly Brief.

Critical path removal:
may rise in severity.

Do not infer revenue impact from line change alone.

---

# 30. sellers.json

MVP may use sellers.json for:

- supply-chain identity;
- seller validation;
- DIRECT/RESELLER context.

It is not a performance metric.

Keep scope limited.

---

# 31. Synthetic performance

Collect a small set:

```text
LCP
CLS
INP proxy where feasible
navigation timing
long tasks
resource timing
```

MVP is not a Lighthouse replacement.

Always label:

```text
synthetic
```

Do not claim these are field p75 metrics.

---

# 32. Business connectors

MVP core connectors:

```text
GA4
Google Search Console
Google Ad Manager
```

All read-only.

No write capability.

---

# 33. GA4 MVP role

GA4 provides:

- measured traffic;
- sessions;
- active users;
- views;
- channel;
- device;
- page/template/category localization;
- engagement/consumption context.

GA4 is not physical truth.

Measurement integrity remains a hypothesis.

---

# 34. GA4 MVP cadence

Starting recommendation:

```text
operational pull ~ every 2 hours
nightly reconciliation
recent-period backfill
```

Cadence is configuration.

It may change based on pilot quotas/noise.

---

# 35. Search Console MVP role

GSC provides:

```text
web Search
Discover
```

with:

- clicks;
- impressions;
- CTR;
- position;
- device;
- page;
- bounded query drill-down.

Search and Discover remain separate.

---

# 36. GSC fresh versus final

MVP supports:
- final/mature daily data;
- preliminary recent data where source API supports it.

Incomplete data must remain marked preliminary.

Do not alert from missing/incomplete rows as if zero.

---

# 37. URL Inspection

MVP uses URL Inspection only:

```text
on demand during incident investigation
```

Not continuous mass polling.

---

# 38. GAM MVP role

GAM provides:

- ad requests;
- impressions;
- demand composition;
- direct/programmatic composition;
- eCPM/value where useful;
- ad unit/device/format localization;
- relevant restrictions/config context where accessible.

GAM is not an accounting ledger.

---

# 39. GAM minimum cubes

MVP should aim for:

```text
GAM_INVENTORY_HEALTH_V1
GAM_DEMAND_HEALTH_V1
GAM_DELIVERY_COMPOSITION_V1
```

Potential optional:

```text
GAM_PROGRAMMATIC_VALUE_V1
```

Exact compatibility is validated per publisher/network.

---

# 40. GAM report compatibility

Do not assume every report definition works everywhere.

Onboarding must probe:

- dimensions;
- metrics;
- network permissions;
- timezone;
- currency;
- report API support.

Unsupported cubes become explicit limitations.

---

# 41. GAM revenue rule

Do not use raw total GAM revenue as default site health.

Reasons include:
- direct campaign accounting;
- booked values;
- sponsorship;
- zero/nominal line items;
- actual invoicing differences.

Use normalized programmatic/contextual value where appropriate.

---

# 42. Connector non-goals

MVP does NOT include:

- arbitrary LLM-generated provider queries;
- provider write access;
- huge historical warehouse;
- user-level GA4 data;
- full Search query warehouse;
- impression-level GAM/auction logs;
- bidstream ingestion.

---

# 43. Event Engine

MVP needs a low-noise Event Engine.

Its job:

```text
raw observations
→ meaningful operational events
```

Not:
every difference → event.

---

# 44. Event classes

Core MVP families:

```text
SITE
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

Implementation may begin with a subset.

---

# 45. Event timing

If:

```text
12:00 state A
18:00 state B
```

MVP must represent:

```text
change occurred between 12:00 and 18:00
```

not:

```text
change occurred exactly at 18:00
```

Time uncertainty is core product semantics.

---

# 46. Event severity

User-facing:

```text
INFO
LOW
MEDIUM
HIGH
CRITICAL
```

Severity is NOT:
- causal confidence;
- alertability;
- financial impact probability.

---

# 47. Event alert policy

Immediate alerts only for high-value serious issues.

Examples:

- site unavailable;
- broad robots/noindex;
- widespread expected slot loss;
- severe request/delivery collapse;
- CMP runtime unavailable;
- severe serving restriction;
- severe persistent UX/performance regression.

Routine changes should not page users.

---

# 48. Weekly Brief

Every Monday, publisher receives approximately:

```text
3–7 findings
```

Each should answer:

```text
Observed
Risk
Check
```

Example:

```text
Observed:
Article/mobile has 2 fewer expected GPT slots across 4 checkpoints.

Risk:
Fewer monetizable ad opportunities.

Check:
Confirm whether article template inventory reduction was intentional.
```

Do not write:
"Revenue is down because developers removed ads"
unless proven.

---

# 49. Weekly selection

Selection is deterministic first.

Rank by:

- severity;
- persistence;
- blast radius;
- confidence;
- actionability;
- novelty;
- relevance.

Then LLM rewrites selected findings.

LLM cannot invent additional findings.

---

# 50. Immediate alerts

MVP may initially deliver alerts via:

- in-app;
- email.

Slack or other channels may be added only if pilot requires.

Do not build a notification-platform product.

---

# 51. External events

MVP tracks relevant official external context.

Examples:

- Google Search updates/incidents;
- GAM platform incidents;
- major vendor/CDN incidents;
- standards/policy changes.

External event:

```text
context
```

not automatic publisher root cause.

---

# 52. Manual operational changes

MVP should allow a lightweight manual entry:

```text
deployment
rollback
GAM config change
CMP change
player change
direct campaign start
vendor integration
```

This preserves operational memory.

Do not build Jira/project management.

---

# 53. Last Known Good

MVP must support:

```text
Last Known Good
```

per:
- incident;
- scope;
- template/scenario where relevant.

It is a comparison reference.

It is NOT:
- one global site checkpoint;
- an automatic rollback target.

---

# 54. Investigate input

Keep extremely simple.

Fields:

```text
What happened?
When did it start?
Optional context/evidence
```

Optional guided chips:

```text
Traffic
Search
Discover
Monetization
Ads
Performance
Video
Site
Other
```

Do not force the user into technical diagnosis.

---

# 55. Investigation baseline

Every investigation must build:

- baseline;
- pre-incident window;
- incident window;
- optional recovery/comparison.

No universal ±24 hours.

---

# 56. Localization

Before ranking causes:

determine whether issue is:

- global/local;
- mobile/desktop;
- Search/Discover/other;
- page/template;
- geography;
- ad unit;
- format;
- demand source;
- consent path.

Unaffected segments become controls.

---

# 57. Measurement integrity

MVP Incident Engine must explicitly consider:

```text
GA4 measurement issue
GSC preliminary/incomplete data
GAM reporting problem
browser collector problem
```

before concluding business reality changed.

---

# 58. Candidate hypotheses

Candidates come from:

```text
DOMAIN failure modes
relevant events
manual changes
external events
incident corpus patterns
metric decomposition
```

Not from free-form model imagination.

---

# 59. Causal rules

MVP must implement at least these reasoning rules:

```text
baseline first
localize before explaining
temporal order necessary but insufficient
mechanism required
same segment increases weight
intermediate signal chain increases weight
search for contradictions
rollback + recovery increases weight
persistence after removal decreases weight
external context requires local match
multi-causal allowed
descendant metrics not independent evidence
recovery lag depends on symptom
```

---

# 60. Contradiction search

For top hypotheses, MVP must check:

- symptom predates candidate?;
- wrong segment?;
- unaffected control?;
- expected intermediate signal missing?;
- component removed but symptom persists?;
- source stale?;
- stronger alternative?;

This is mandatory.

---

# 61. Confidence labels

User-facing:

```text
CONFIRMED
PROBABLE
POSSIBLE CONTRIBUTOR
UNRESOLVED
```

Do not show:

```text
82.7% causal probability
```

until calibrated with real evidence at scale.

---

# 62. No Strong Local Cause

MVP should support:

```text
UNRESOLVED
+
NO_STRONG_LOCAL_CAUSE
```

Example:

- Search decline real;
- local state stable;
- local candidates contradicted;
- external/content factors remain uncertain.

This is a valuable output.

---

# 63. Investigation report

Minimum output:

```text
Incident summary
What we observed
Affected scope
Baseline / onset
Relevant timeline
Last Known Good
Top hypotheses
Supporting evidence
Contradicting evidence
Unknowns / missing sources
External context
Recommended next test
Conclusion
```

---

# 64. Counterfactual testing

MVP can recommend:

- Accept vs Reject synthetic;
- mobile vs desktop;
- affected vs unaffected template;
- one ad unit;
- one bidder;
- targeted rollback;
- staging comparison.

The test should state:

```text
If H is true → expect X
If H is false → expect Y
```

---

# 65. Safe automatic diagnostics

MVP may automatically run:

- additional synthetic browser checks;
- additional screenshots;
- second representative URL;
- controlled consent scenario;
- validated connector drill-down query.

These are read-only.

---

# 66. No autonomous production remediation

MVP may NOT automatically:

- change GAM;
- deploy code;
- modify CMP;
- change Prebid;
- disable bidders;
- remove players;
- change robots/noindex;
- rollback production.

Human approval/execution remains mandatory.

---

# 67. Incident corpus

MVP uses curated corpus:

```text
INCIDENTS.md / incidents_v0.5.yaml
```

as precedent.

It does not use:
- frequency as prevalence;
- anecdotal case as proof.

Private pilot incidents remain private unless explicitly reviewed/promoted later.

---

# 68. Evals

MVP Incident Engine is not considered ready until eval harness covers:

- positive diagnosis;
- counterexamples;
- unresolved cases;
- external context;
- measurement integrity;
- rollback/recovery;
- test design.

Hard fails include invented evidence and false cause certainty.

---

# 69. AI role

AI should perform:

- explanation;
- structured comparison;
- synthesis;
- mechanism narration;
- evidence-based hypothesis summary.

AI should NOT be the source of truth.

Deterministic code controls:

- source data;
- event creation;
- evidence IDs;
- source freshness;
- ranking components;
- contradiction checks;
- allowed queries;
- alert selection.

---

# 70. LLM implementation

MVP uses external LLM API.

No model training required.

No custom foundation model.

No fine-tuning required for first pilot.

Use:

```text
structured context
+
structured output
+
evidence references
```

---

# 71. LLM context limits

Do not send:

- full raw DOM history;
- every GAM row;
- every Search query;
- every JS error;
- whole incident corpus.

Build a bounded evidence packet first.

---

# 72. Data architecture

MVP uses:

```text
PostgreSQL
+
S3-compatible object storage
```

PostgreSQL stores:

- entities;
- checkpoints;
- metrics;
- events;
- incidents;
- hypotheses;
- evidence refs;
- metadata.

Object storage stores:

- screenshots;
- raw DOM;
- traces;
- large forensic artifacts.

---

# 73. Backend

MVP backend:

```text
Python
FastAPI
```

Use modular monolith.

Do not split into microservices.

---

# 74. Frontend

MVP frontend:

```text
Next.js / React
```

Keep UI simple.

Priority:
- clarity;
- evidence;
- incident workflow.

Not:
highly customized visualization system.

---

# 75. Scheduler / jobs

MVP needs:

- scheduled browser jobs;
- scheduled connector pulls;
- event processing;
- weekly report generation;
- incident drill-down jobs.

Initial implementation:

```text
Postgres-backed job table / simple worker
```

or equivalently simple queue.

Do not introduce Kafka.

Redis/Celery/RQ only if real implementation need appears.

---

# 76. Deployment

MVP should run on simple cloud infrastructure.

Need:

- backend service;
- frontend;
- Postgres;
- object storage;
- background worker;
- Chromium-compatible runtime;
- secure secret management.

Do not use Kubernetes unless deployment provider requires it for a compelling reason.

---

# 77. Environment model

Minimum:

```text
local
staging
production
```

Staging should allow:
- synthetic test sites;
- safe connector test properties;
- migrations;
- evals.

---

# 78. Security

Before real publisher pilot:

MVP must have:

- encrypted OAuth/secret storage;
- read-only source scopes;
- tenant isolation;
- private object storage;
- access control;
- log redaction;
- no raw secrets in logs;
- configurable retention;
- no ad clicking;
- no user-level tracking ingestion.

Detailed contract belongs to `SECURITY.md`.

---

# 79. Tenant model

MVP supports:

```text
Tenant
→ Publisher
→ Site
```

Even if first pilot uses one tenant.

Do not build enterprise organization hierarchy beyond this.

---

# 80. Roles

Initial roles can remain minimal:

```text
Admin
Member
```

or even one authenticated publisher role during earliest pilot if secure.

Do not build complex RBAC matrices yet.

---

# 81. Auditability

Any incident conclusion must trace:

```text
Report
→ Hypothesis
→ Evidence
→ Source observation/extract/artifact
```

If that chain breaks:
the MVP reasoning feature is incomplete.

---

# 82. Evidence retention

Longer-term:

- checkpoint manifest;
- normalized state;
- important screenshots;
- metrics;
- events;
- incident reports.

Shorter/conditional:

- raw DOM;
- full network traces;
- Playwright trace.

Exact retention policy goes into `SECURITY.md`.

---

# 83. No irreversible evidence deletion

Do not delete evidence referenced by an active or retained incident report without retention policy handling.

Incident history is core product value.

---

# 84. MVP non-goals — product

Explicitly OUT:

- revenue optimization engine;
- automatic yield management;
- SSP bidding optimizer;
- Google ranking predictor;
- SEO content recommendation suite;
- content writing;
- ad campaign manager;
- publisher CMS;
- full BI dashboard;
- project management;
- ticketing;
- CRM;
- billing automation.

---

# 85. MVP non-goals — infrastructure

Explicitly OUT:

```text
microservices
Kafka
Kubernetes
Neo4j
ClickHouse
TimescaleDB
global browser fleet
residential proxy mesh
custom observability platform
multi-region active-active
```

---

# 86. MVP non-goals — browser

Explicitly OUT:

- real-user monitoring SDK;
- session replay;
- browser stealth;
- adblock population measurement;
- authenticated browsing;
- paywall bypass;
- every browser/device;
- automatic visual AI diagnosis.

---

# 87. MVP non-goals — AI

Explicitly OUT:

- autonomous remediation;
- direct production writes;
- arbitrary tool use;
- arbitrary provider query generation;
- self-modifying rules;
- unsupervised learning from private incidents;
- agent swarm architecture;
- custom foundation model training.

---

# 88. MVP non-goals — commercial data

Explicitly OUT:

- invoicing reconciliation;
- full accounting;
- exact publisher P&L;
- contract management;
- advertiser billing;
- financial ERP integration.

Revenue remains diagnostic/contextual.

---

# 89. MVP non-goals — alerts

Do not build:

- PagerDuty clone;
- complex escalation chains;
- multi-channel notification routing engine;
- custom alert-builder UI.

A few useful notifications are enough.

---

# 90. MVP non-goals — policy

Product does not provide:

- legal advice;
- guaranteed compliance certification;
- automatic policy appeal;
- automatic remediation.

It records observable behavior and platform signals.

---

# 91. MVP success metrics

We should measure:

```text
Time to symptom localization
Time to first useful hypothesis
Time to useful investigation report
False-cause rate
UNRESOLVED correctness
Number of destructive isolation tests avoided
User-rated usefulness
Weekly Brief usefulness/noise
Critical alert precision
```

---

# 92. Primary MVP success KPI

The strongest business/product KPI is:

> **Mean Time To Investigate**

Not:
number of alerts.

Not:
number of events.

Not:
AI messages generated.

---

# 93. Secondary KPI

A critical secondary KPI:

> **False-cause rate**

We want the system to reduce:
wrong vendor blame,
wrong Google attribution,
wrong technical conclusions.

A more cautious UNRESOLVED result is preferable to false certainty.

---

# 94. Weekly Brief KPI

Measure:

```text
useful findings / total findings
```

Publisher should not feel:
"I need to ignore this."

If weekly report consistently produces seven low-value items:
ranking failed.

---

# 95. Alert KPI

Measure:

```text
actionable critical alerts / all critical alerts
```

Target high precision.

Do not optimize for alert volume.

---

# 96. Pilot success criteria

A pilot is successful if, across real publisher use:

1. checkpoints run reliably;
2. Timeline preserves meaningful changes;
3. Weekly Brief is viewed as useful;
4. critical alerts are rare and useful;
5. at least several incidents can be reconstructed faster than current manual process;
6. engine demonstrates ability to reject wrong hypotheses;
7. user trusts evidence/provenance;
8. cost per site remains economically viable;
9. operation does not require constant engineering intervention.

---

# 97. Cost target

Initial target COGS:

```text
~€25–50/site/month
```

Conservative ceiling during early pilot:

```text
~€60/site/month
```

These are product targets, not guaranteed architecture results.

Track actual:

- Chromium compute;
- storage;
- Postgres;
- connector calls;
- LLM;
- egress.

---

# 98. Cost-control principles

To stay viable:

- monitor representative URLs, not all URLs;
- fixed 6-hour core cadence;
- limited consent scenarios;
- no continuous AI analysis;
- deterministic event processing;
- LLM weekly/on-demand;
- store normalized evidence long-term;
- shorter raw artifact retention;
- bounded incident drill-down.

---

# 99. Pricing hypothesis

Not part of engineering acceptance, but MVP should support a plausible value model.

Initial hypothesis:

```text
Core ~€249–299/site/month
Pro ~€449–599/site/month
Media Group ~€1,000–2,500+/month
```

Pricing requires market validation.

Do not hard-code pricing into architecture.

---

# 100. MVP implementation phases

Recommended phases:

```text
Phase A — Foundation
Phase B — Browser Black Box
Phase C — Connectors
Phase D — Event Memory
Phase E — UI Timeline/Home
Phase F — Investigate
Phase G — Evals + Pilot Hardening
```

---

# 101. Phase A — Foundation

Includes:

- repo;
- dev environment;
- backend;
- frontend shell;
- Postgres;
- object storage;
- migrations;
- job/worker foundation;
- tenant/site/template config;
- auth baseline.

No intelligence yet.

---

# 102. Phase B — Browser Black Box

Follow BROWSER milestones:

```text
B1 minimal real-browser checkpoint
B2 repeatable 6-hour-compatible run
B3 template-aware monitoring
B4 GPT
B5 CMP
B6 Prebid
B7 video
B8 performance
```

We do not need all B5–B8 before first internal demo.

---

# 103. Phase C — Connectors

Order:

```text
GA4
GSC
GAM
```

or adjust based on pilot access.

Minimum:
enough business metrics to correlate browser events with real symptoms.

---

# 104. Phase D — Event Memory

Implement:

- semantic diffs;
- selected anomalies;
- persistence/deduplication;
- event severity;
- Timeline;
- external context;
- manual changes.

Do not implement every event definition at once.

Start with highest-value types.

---

# 105. Initial event subset

Recommended first set:

```text
SITE_UNAVAILABLE
THIRD_PARTY_DEPENDENCY_ADDED/REMOVED
JS_ERROR_STARTED
ROBOTS_BROAD_BLOCK_ADDED
NOINDEX_ADDED
CANONICAL_CHANGED
GA4_ORGANIC_SEARCH_BELOW_BASELINE
GSC_SEARCH_CLICKS/IMPRESSIONS_BELOW_BASELINE
GAM_REQUESTS_BELOW_BASELINE
GAM_FILL_BELOW_BASELINE
GPT_EXPECTED_SLOT_MISSING
GPT_REQUEST_MISSING
CMP_API_UNAVAILABLE
TCF_ERROR_APPEARED
ADS_TXT_EMPTY_200
SYNTHETIC_CLS_REGRESSION
```

Expand after pilots.

---

# 106. Phase E — UI

Build:

```text
Home
Timeline
```

before deep Incident UI polish.

The user should already see value from operational memory.

---

# 107. Phase F — Investigate

Follow Incident milestones:

```text
I1 intake + windows + localization
I2 evidence pack
I3 candidate generation
I4 contradiction/ranking
I5 report synthesis
I6 counterfactual tests
I7 revisions/recovery
```

No autonomous remediation.

---

# 108. Phase G — Evals/hardening

Before strong pilot claims:

- reasoning eval harness;
- critical release-gating evals;
- security review;
- failure handling;
- source freshness;
- browser reliability;
- cost tracking;
- incident-report provenance.

---

# 109. First internal demo

The first meaningful internal demo should be:

```text
Enter one publisher URL
→ Chromium opens it
→ checkpoint created
→ screenshot stored
→ DOM stored
→ scripts shown
→ network dependencies shown
→ JS errors shown
→ final status shown
```

No AI needed.

If this is not reliable:
do not move quickly into Incident AI.

---

# 110. Second internal demo

```text
Two checkpoints
→ meaningful diff
→ Timeline event
```

Example:

```text
script added
slot removed
noindex added
```

This proves operational memory.

---

# 111. Third internal demo

```text
GA4/GSC/GAM data connected
→ metric anomaly
→ browser/metric timeline aligned
```

This proves cross-source observability.

---

# 112. Fourth internal demo

```text
User reports incident
→ baseline built
→ LKG selected
→ relevant events retrieved
→ top hypotheses shown
→ contradiction included
→ next test proposed
```

This proves product thesis.

---

# 113. Pilot-ready definition

MVP becomes pilot-ready only when:

- one real publisher can be onboarded;
- checkpoints run for at least several days reliably;
- connector pulls are stable;
- Timeline does not drown user in noise;
- Home status makes sense;
- Weekly Brief can be generated;
- Investigate works on at least several test incidents;
- evidence is auditable;
- tenant/security boundaries exist;
- costs are measurable.

---

# 114. Commercial MVP definition

Commercial MVP requires more than technical demo.

Needs:

- stable onboarding;
- basic account access;
- reliable scheduler;
- alert delivery;
- usable Home/Timeline/Investigate;
- evidence/artifact retention;
- connector reconnect flow;
- support/debug visibility;
- acceptable uptime;
- reasonable COGS.

---

# 115. Do not wait for perfection

Commercial MVP does NOT require:

- every player vendor;
- every CMP adapter;
- every GAM metric;
- every Prebid feature;
- complete Search diagnosis;
- automatic root cause every time.

It requires useful results in a constrained, transparent observability envelope.

---

# 116. Failure is allowed if explicit

Valid output:

```text
We cannot determine whether bidder-side logic changed because this publisher uses server-side bidding and bidder internals are not observable.
```

Invalid:

```text
Bidder X reduced demand.
```

when we cannot observe it.

Transparency is part of MVP quality.

---

# 117. MVP readiness checklist

## Product

- [ ] Home exists
- [ ] Timeline exists
- [ ] Investigate exists
- [ ] Weekly Brief exists
- [ ] rare critical alerts work

## Browser

- [ ] scheduled checkpoints
- [ ] desktop/mobile
- [ ] screenshots
- [ ] DOM
- [ ] scripts/dependencies
- [ ] JS errors
- [ ] GPT core
- [ ] consent baseline
- [ ] failure distinction

## Connectors

- [ ] GA4
- [ ] GSC
- [ ] GAM
- [ ] freshness metadata
- [ ] read-only scopes
- [ ] reconnect/permission errors

## Events

- [ ] semantic diff
- [ ] dedupe
- [ ] severity
- [ ] scope
- [ ] occurrence window
- [ ] source evidence

## Incident

- [ ] symptom intake
- [ ] baseline
- [ ] localization
- [ ] LKG
- [ ] hypotheses
- [ ] contradictions
- [ ] confidence labels
- [ ] next test
- [ ] report revision

## Security

- [ ] tenant isolation
- [ ] secret storage
- [ ] private artifacts
- [ ] log redaction
- [ ] no write scopes

## Quality

- [ ] eval harness
- [ ] counterexamples
- [ ] unresolved cases
- [ ] false-cause monitoring
- [ ] cost telemetry

---

# 118. MVP change control

Any proposed feature must answer:

```text
Does it help prove:
1. reliable observation?
2. operational memory?
3. meaningful low-noise detection?
4. better incident investigation?
```

If not:
likely post-MVP.

If yes but scope is substantial:
record explicit decision in `DECISIONS.md`.

---

# 119. Codex MVP rule

Codex MUST assume:

> **If a feature is not explicitly inside MVP.md or required to implement an included capability, it is out of scope.**

Codex should not add "helpful future features."

Examples:

```text
"while we're here, add Slack"
"while we're here, add RUM"
"while we're here, add AI screenshot analysis"
```

No.

Create a follow-up proposal instead.

---

# 120. ExecPlan rule

Every ExecPlan must include:

```text
MVP scope impact:
NO
```

or:

```text
YES — approved by ADR-XXX
```

No other answer.

---

# 121. Definition of MVP success

The MVP succeeds if we can show, on a real publisher incident:

```text
Before:
publisher spends hours/days guessing

After:
platform immediately reconstructs:
- affected scope
- baseline
- relevant changes
- technical/business evidence
- plausible causes
- contradicting evidence
- next diagnostic action
```

Even if final conclusion remains:

```text
UNRESOLVED
```

the product can still have delivered major value by eliminating wrong causes and destructive tests.

---

# 122. Final MVP principle

The MVP is not:

> **An AI that knows why publisher traffic or revenue changed.**

It is:

> **A black-box recorder, operational memory, and disciplined incident investigator for digital publishers.**

The product should first become excellent at:

```text
Observe
→ Remember
→ Localize
→ Explain evidence
```

Only later:

```text
Predict
Optimize
Act automatically
```

# **MVP means proving that better evidence produces better incident decisions.**
