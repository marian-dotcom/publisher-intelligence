# ARCHITECTURE.md
## Publisher Incident Intelligence Platform
### Technical Architecture — v1.0

**Audience:** Codex, engineering, technical reviewers, product  
**Status:** Canonical implementation architecture  
**Purpose:** Define the concrete technical structure of the MVP and the boundaries between collection, evidence, events, incident reasoning, UI, storage and AI  
**Depends on:** `PRODUCT.md`, `MVP.md`, `DOMAIN.md`, `BROWSER.md`, `DATA_MODEL.md`, `EVENTS.md`, `CONNECTORS.md`, `INCIDENT.md`, `EVALS.md`, `PLANS.md`  
**Security details live in:** `SECURITY.md`  
**Durable decisions live in:** `DECISIONS.md`

---

# 0. Architectural principle

The architecture exists to support one product loop:

```text
Observe
→ Preserve Evidence
→ Normalize
→ Detect Meaningful Events
→ Reconstruct Incidents
→ Explain Evidence
```

The MVP architecture must optimize for:

```text
clarity
traceability
reproducibility
low operational complexity
easy debugging
safe iteration
```

It should not optimize prematurely for:
- extreme scale;
- distributed infrastructure elegance;
- theoretical throughput;
- autonomous AI orchestration.

---

# 1. Architectural style

The MVP uses:

> **A modular monolith with background workers.**

Core stack:

```text
Frontend:
Next.js / React

Backend:
Python / FastAPI

Database:
PostgreSQL

Large evidence:
S3-compatible object storage

Synthetic browser:
Playwright + Chromium

Background work:
PostgreSQL-backed jobs + worker processes

AI:
external LLM API

Deployment:
simple managed cloud services / containers
```

No microservices are required.

---

# 2. Why modular monolith

The platform has multiple logical domains:

```text
browser
connectors
events
incidents
reports
users
sites
```

But they share:

- one tenant model;
- one evidence model;
- one event vocabulary;
- one incident graph;
- one relational database;
- strong transactional relationships.

Splitting these into separate services would create:
- network boundaries;
- distributed transactions;
- versioning overhead;
- deployment overhead;
- debugging complexity;

without meaningful MVP benefit.

Logical modularity is required.

Physical service fragmentation is not.

---

# 3. High-level system

```text
                           ┌──────────────────────┐
                           │      Next.js UI      │
                           └──────────┬───────────┘
                                      │ HTTPS
                                      ▼
                           ┌──────────────────────┐
                           │       FastAPI        │
                           │  Application Server  │
                           └──────────┬───────────┘
                                      │
                     ┌────────────────┼────────────────┐
                     │                │                │
                     ▼                ▼                ▼
              ┌────────────┐   ┌──────────────┐  ┌──────────────┐
              │ PostgreSQL │   │ Object Store │  │  Job Queue   │
              │  metadata  │   │ raw evidence │  │  PostgreSQL  │
              └──────┬─────┘   └──────────────┘  └──────┬───────┘
                     │                                    │
                     │                                    ▼
                     │                           ┌──────────────────┐
                     │                           │ Background Worker │
                     │                           └───────┬──────────┘
                     │                                   │
          ┌──────────┼───────────────┬───────────────────┼─────────────┐
          │          │               │                   │             │
          ▼          ▼               ▼                   ▼             ▼
   ┌────────────┐ ┌───────┐   ┌────────────┐     ┌────────────┐ ┌──────────┐
   │ Playwright │ │  GA4  │   │ Search     │     │    GAM     │ │ Incident │
   │ Chromium   │ │       │   │ Console    │     │            │ │ Engine   │
   └────────────┘ └───────┘   └────────────┘     └────────────┘ └────┬─────┘
                                                                      │
                                                                      ▼
                                                               ┌───────────┐
                                                               │  LLM API  │
                                                               └───────────┘
```

---

# 4. Runtime components

The MVP has five deployable runtime types.

## 4.1 Web frontend

```text
Next.js
```

Responsibilities:
- authentication UX;
- Home;
- Timeline;
- Investigate;
- incident report;
- evidence viewer;
- onboarding/configuration.

## 4.2 API application

```text
FastAPI
```

Responsibilities:
- HTTP API;
- auth/tenant authorization;
- domain/application services;
- read models;
- job scheduling requests;
- incident commands;
- connector configuration;
- evidence metadata access.

## 4.3 General worker

Responsibilities:
- connector ingestion;
- normalization;
- event processing;
- weekly report jobs;
- incident evidence assembly;
- incident deterministic reasoning;
- LLM report synthesis.

## 4.4 Browser worker

Responsibilities:
- Playwright/Chromium;
- synthetic scenarios;
- screenshots;
- DOM;
- network;
- runtime collectors.

Browser work SHOULD run separately from API process because:
- Chromium is memory-heavy;
- browser crashes should not kill API;
- concurrency differs from API workloads.

The code can remain in the same repository/application.

## 4.5 Scheduler

Can initially be:

```text
one lightweight scheduler process
```

that inserts jobs into PostgreSQL.

Do not build a distributed scheduler.

---

# 5. Deployment units versus code modules

Deployable processes are not microservices.

Example:

```text
same repository
same application packages
same PostgreSQL
same release version

process 1: api
process 2: worker
process 3: browser-worker
process 4: scheduler
```

This provides workload isolation while preserving architectural simplicity.

---

# 6. Canonical module boundaries

Suggested backend package structure:

```text
backend/
  app/
    api/
    auth/
    tenants/
    publishers/
    sites/
    templates/

    browser/
      runner/
      scenarios/
      collectors/
      normalization/
      diffs/

    connectors/
      core/
      ga4/
      gsc/
      gam/

    metrics/
    events/
    incidents/
    reports/
    external_events/
    operational_changes/

    jobs/
    storage/
    db/
    security/
    llm/
    common/
```

Exact directories may evolve.

The logical boundaries should remain.

---

# 7. Frontend structure

Suggested:

```text
frontend/
  app/
    home/
    timeline/
    investigate/
    incidents/
    onboarding/
    settings/

  components/
    evidence/
    timeline/
    incidents/
    status/
    charts/

  lib/
    api/
    auth/
    types/
```

Do not build a large component/design framework before real screens exist.

---

# 8. Core domain ownership

Each module owns meaning.

## Browser module

Owns:
- synthetic observation;
- runtime evidence;
- scenario identity;
- checkpoint creation.

Does NOT own:
- causal conclusions;
- business anomalies.

## Connector module

Owns:
- provider APIs;
- source extracts;
- freshness;
- normalization into metric series.

Does NOT own:
- incident conclusions.

## Metrics module

Owns:
- metric semantics;
- time-series storage;
- baseline helpers;
- derived metrics.

## Events module

Owns:
- semantic change detection;
- anomaly promotion;
- event lifecycle;
- severity;
- dedupe.

## Incidents module

Owns:
- incident intake;
- baseline/windows;
- localization;
- evidence pack;
- hypotheses;
- contradiction;
- report.

## LLM module

Owns:
- provider abstraction;
- structured invocation;
- schema validation;
- prompt/version metadata.

Does NOT own:
- evidence;
- event truth;
- causal confidence rules.

---

# 9. Systems of record

The architecture distinguishes raw/system-of-record data from derived data.

## System-of-record evidence

Examples:

```text
checkpoint artifacts
browser observations
connector raw/normalized extracts
manual changes
external official events
user incident statements
```

## Derived

Examples:

```text
normalized DOM
semantic diffs
metric anomalies
events
Last Known Good selection
hypotheses
incident reports
weekly summaries
```

Derived data must be reproducible from source evidence where feasible.

---

# 10. PostgreSQL role

PostgreSQL is the primary structured data store.

It should store:

```text
tenants
users
publishers
sites
templates
monitored URLs
browser scenarios
checkpoint windows
checkpoint runs
collector results
artifact metadata
connections
source extracts
metric definitions
metric series
metric points
events
event evidence refs
operational changes
external events
incidents
incident windows
hypotheses
hypothesis evidence
reports
jobs
audit metadata
```

Postgres is sufficient for MVP.

---

# 11. Why no time-series database

Initial dataset does not justify another database.

Metric volume is bounded because we intentionally ingest:
- selected dimensions;
- selected report cubes;
- low-cardinality monitoring series.

Postgres can handle this comfortably at pilot scale.

If real measured production volume later requires:
- partitioning;
- Timescale;
- ClickHouse;

that becomes a new ADR based on evidence.

---

# 12. Why no graph database

Incident reasoning needs relationships.

It does not need a graph database.

Use relational tables such as:

```text
event_relations
hypothesis_evidence
incident_evidence
```

Edges are typed.

Queries remain manageable.

Do not introduce Neo4j for conceptual elegance.

---

# 13. Object storage role

Large forensic artifacts live in S3-compatible object storage.

Examples:

```text
viewport screenshots
full-page screenshots
raw HTML/DOM
normalized DOM snapshots if large
Playwright traces
network trace artifacts
large connector raw responses if retained
incident attachments
```

Postgres stores:
- URI/key;
- type;
- size;
- content hash;
- timestamps;
- provenance;
- retention class.

---

# 14. Object naming

Object keys should be deterministic enough for operations but not become the source of truth.

Concept:

```text
tenant/<tenant_id>/
site/<site_id>/
checkpoints/<checkpoint_run_id>/
screenshots/final.webp
dom/raw.html.gz
traces/browser.zip
```

Database references remain authoritative.

Do not encode all metadata only in paths.

---

# 15. Content hashing

Artifacts SHOULD store:

```text
sha256
```

or equivalent strong content hash.

Uses:
- integrity;
- deduplication opportunity;
- forensic verification;
- detecting unchanged evidence.

Do not use hash as semantic equality without normalization rules.

---

# 16. Job architecture

Use a PostgreSQL-backed job queue initially.

Conceptual table:

```text
jobs
```

Fields:

```text
id
tenant_id
job_type
payload
status
priority
scheduled_at
available_at
started_at
finished_at
attempt
max_attempts
locked_by
lock_expires_at
last_error_class
last_error_message
created_at
```

Implementation detail may vary based on `DATA_MODEL.md`.

---

# 17. Job statuses

Use:

```text
PENDING
RUNNING
RETRY
COMPLETE
FAILED
CANCELLED
```

For long source reports:
job-local substatus may exist in job metadata.

Do not create dozens of workflow states globally.

---

# 18. Job claiming

Workers should claim jobs transactionally.

Use PostgreSQL row locking pattern such as:

```text
SELECT ... FOR UPDATE SKIP LOCKED
```

or an equivalent safe mechanism.

Goal:
- multiple workers;
- one job execution;
- crash recovery;
- no duplicate simultaneous ownership.

---

# 19. Job heartbeats

Long browser/connector jobs may update:

```text
heartbeat_at
```

or lock expiry.

If worker dies:
job becomes retryable after lease expires.

Do not permanently strand RUNNING jobs.

---

# 20. Idempotency

Every job type must define idempotency semantics.

Example browser scheduled checkpoint:

Logical identity:

```text
checkpoint_window
+ monitored_url
+ scenario
```

Retries may produce multiple attempts/run records.

They must not corrupt/erase earlier attempts.

Example connector extract:

```text
connection
+ extract_definition
+ period
+ extraction generation
```

Retry is different from later reconciliation.

---

# 21. Scheduler

Scheduler creates jobs for:

```text
browser checkpoint windows
GA4 pulls
GSC pulls
GAM pulls
weekly brief
external event refresh
retention cleanup
```

Incident-triggered work is inserted by application commands.

Scheduler does not execute business logic.

---

# 22. Browser scheduling

Core browser checkpoint:

```text
every 6 hours
```

Prefer stable wall-clock windows.

Example:

```text
00:00
06:00
12:00
18:00
publisher/site timezone or configured canonical schedule
```

Actual execution can begin slightly later.

Store:
- scheduled window;
- actual start/end.

Do not pretend execution time equals event time.

---

# 23. Browser concurrency

Browser concurrency must be bounded.

Initial simple configuration:

```text
BROWSER_CONCURRENCY = small fixed number
```

Reasons:
- Chromium memory;
- publisher load;
- storage;
- debugging.

Scale with observed need.

Do not run a browser storm at every 6-hour boundary.

---

# 24. Browser politeness

Synthetic browser is not load testing.

Rules:
- representative URLs only;
- few scenarios;
- low request frequency;
- no ad clicking;
- no infinite scrolling;
- bounded interaction;
- no stealth bypass;
- normal browser behavior.

---

# 25. Browser execution flow

```text
job claimed
↓
load site/template/scenario config
↓
create isolated BrowserContext
↓
attach collectors
↓
navigate
↓
capture pre-consent state
↓
perform configured consent action
↓
run deterministic interaction script
↓
capture lifecycle observations
↓
capture final artifacts
↓
persist artifact metadata
↓
persist collector outputs
↓
finalize checkpoint run
↓
schedule derived normalization/diff job
```

---

# 26. Browser collectors

Collectors should remain modular.

Examples:

```text
page_state
screenshots
dom
scripts
network
javascript_errors
gpt
prebid
cmp
video
seo
performance
```

A collector has:

```text
name
version
status
started_at
finished_at
structured_output
artifact_refs
errors
```

Collector failure does not necessarily invalidate entire checkpoint.

---

# 27. Browser collector interface

Conceptual:

```python
class BrowserCollector:
    name: str
    version: str

    async def attach(context): ...
    async def before_navigation(page): ...
    async def after_navigation(page): ...
    async def before_interaction(page): ...
    async def after_interaction(page): ...
    async def finalize(page): ...
```

Not every collector needs every hook.

Keep implementation simple.

---

# 28. Scenario definition

A browser scenario is versioned configuration.

Example:

```yaml
name: article_mobile_accept_v1
device_class: mobile
viewport:
  width: 390
  height: 844
consent_action: ACCEPT
interaction_script: ARTICLE_SCROLL_V1
locale: ro-RO
timezone: Europe/Bucharest
```

Do not embed scenario behavior randomly inside runner code.

---

# 29. Scenario versioning

If scroll timing/viewport/consent logic changes:

create a new scenario version when the change materially affects comparability.

Otherwise false diffs can arise from our own observer.

---

# 30. Normalization pipeline

Browser raw data is normalized after checkpoint.

```text
raw checkpoint
↓
collector-specific normalization
↓
entity identity mapping
↓
normalized state
↓
semantic diff
```

Examples:
- volatile URL params removed;
- script identity normalized;
- error fingerprints normalized;
- slot identity normalized;
- DOM structure reduced.

Normalization code is versioned.

---

# 31. Semantic diff pipeline

Comparison selection:

```text
same URL/scenario previous comparable run
```

or:

```text
same template/scenario previous comparable run
```

Then:

```text
presence change
value change
set change
stage change
status change
structural change
```

Output:
event candidates.

The browser module does not directly decide alerting.

---

# 32. Connector architecture

Each provider has:

```text
auth adapter
capability discovery
extract definitions
provider client
normalizer
source extract persistence
health
```

Common contract lives in:

```text
connectors/core/
```

Provider-specific semantics stay in provider package.

---

# 33. Connector data flow

```text
scheduled job
↓
load connection
↓
decrypt/access secret reference
↓
validate token if necessary
↓
execute versioned extract definition
↓
persist source_extract
↓
normalize metrics
↓
persist metric_series / metric_points
↓
update source freshness
↓
schedule anomaly/event processing
```

---

# 34. Connector isolation

Connector failure should not block:
- browser checkpoints;
- other connectors;
- Timeline browsing;
- historical incidents.

Example:

```text
GSC permission expired
```

means:
- GSC source degraded;
- Search incident observability reduced.

Not:
platform unavailable.

---

# 35. Connection secrets

Application data stores a secret reference.

Credential storage may use:
- managed secrets service;
- encrypted application secret storage;

defined in `SECURITY.md`.

Connector code receives secrets only at execution time.

Never persist secrets into:
- source extracts;
- jobs payloads;
- logs.

---

# 36. Metric architecture

Metric data is modeled through:

```text
metric_definition
metric_series
metric_point
```

or the canonical equivalent from `DATA_MODEL.md`.

Definition owns:
- semantics;
- unit;
- source;
- numerator/denominator relation;
- version.

Series owns:
- dimensions/scope.

Point owns:
- time interval;
- value;
- source extract/provenance;
- maturity.

---

# 37. Metric interval semantics

Every point should represent explicit interval boundaries where possible:

```text
period_start
period_end
source_timezone
```

Do not rely solely on labels like:

```text
2026-08-10
```

because GSC/GAM/GA4 may use different time boundaries.

---

# 38. Metric baseline service

Create a simple metrics/baseline module.

Responsibilities:
- comparable historical periods;
- rolling median;
- same hour-of-week;
- percentage deviation;
- MAD/robust dispersion;
- minimum-volume gate;
- persistence.

Do not put baseline logic in UI SQL.

---

# 39. Derived metrics

Derived metrics are versioned.

Examples:

```text
requests_per_view_v1
impressions_per_view_v1
derived_fill_v1
```

They store:
- numerator definition;
- denominator definition;
- interval alignment;
- source freshness requirements.

Do not calculate them ad hoc differently in different screens.

---

# 40. Event Engine architecture

Event processing is background-derived logic.

Pipeline:

```text
new normalized state / metric points
↓
select event definitions affected
↓
evaluate candidates
↓
confirmation
↓
dedupe/aggregate
↓
persist event
↓
route to timeline/home/alert/weekly
```

Rules remain deterministic.

---

# 41. Event definition registry

Version-controlled code/config.

Concept:

```python
EventDefinition(
    code="GPT_EXPECTED_SLOT_MISSING",
    family="GPT",
    kind="CONDITION",
    input_requirements=[...],
    confirmation=...,
    severity_policy=...,
    resolution_policy=...,
)
```

Database may mirror definitions for reporting.

Code/config is canonical for behavior.

---

# 42. Event reprocessing

Because events are derived:

```text
raw evidence stays immutable
```

If rule changes:
- run new rule version;
- create/supersede derived events where necessary;
- preserve historical audit.

Do not mutate old evidence to match new logic.

---

# 43. Event routing

After persistence:

```text
Timeline eligibility
Home attention eligibility
Immediate alert eligibility
Weekly Brief eligibility
Incident retrieval
```

Routing policies are deterministic.

Notification delivery is a separate concern.

---

# 44. Notifications

MVP notification pipeline:

```text
alert event
↓
notification record/job
↓
email or in-app
↓
delivery status
```

Do not couple SMTP directly to Event Engine.

Slack can be added later.

---

# 45. Weekly Brief pipeline

```text
weekly scheduler
↓
select eligible events
↓
rank deterministic
↓
group descendant/related events
↓
choose top 3–7
↓
build evidence packet
↓
LLM rewrites/explains
↓
validate output
↓
store report
↓
deliver/show
```

LLM cannot select unrelated extra findings.

---

# 46. Incident architecture

Incident Engine consists of two layers:

```text
Deterministic Investigation Core
+
LLM Synthesis
```

The deterministic core owns the evidence and causal constraints.

---

# 47. Incident deterministic core

Modules:

```text
incidents/intake.py
incidents/windows.py
incidents/localization.py
incidents/evidence_pack.py
incidents/candidates.py
incidents/contradictions.py
incidents/ranking.py
incidents/tests.py
```

Exact filenames may differ.

Do not create one giant `incident_engine.py`.

---

# 48. Incident intake

Input:

```text
symptom text
approximate onset
optional family
optional context
```

Output:
structured reported symptom.

LLM may assist with language normalization if needed.

But:
original user text is preserved.

---

# 49. Incident window service

Responsibilities:
- normalize reported onset interval;
- select baseline;
- detect contaminated baseline;
- create pre/incident/recovery windows;
- expose interval uncertainty.

Rules differ by symptom family.

---

# 50. Localization service

Uses available metrics/events to identify:

```text
affected
unaffected
unknown
```

across:
- source;
- device;
- template;
- page;
- geo;
- ad unit;
- demand channel;
- consent scenario.

Output becomes part of evidence pack.

---

# 51. Evidence pack builder

Builds a bounded structured packet from:

```text
incident
windows
metrics
LKG
events
operational changes
external events
source quality
corpus patterns
```

Do not send raw database contents to LLM.

---

# 52. Last Known Good service

Input:
- incident;
- affected scope;
- baseline window;
- available checkpoints.

Output:
- selected reference;
- selection reason;
- relevant scenario/template;
- evidence ID.

LKG selection is derived and versioned.

---

# 53. Candidate generator

Inputs:

```text
symptom family
first broken stage
relevant events
DOMAIN failure modes
external context
incident corpus patterns
```

Output:
bounded candidate list.

Candidate generation is deterministic/knowledge-driven.

LLM may help phrase candidate title.

---

# 54. Failure-mode registry

Canonical failure modes live in:

```text
DOMAIN.md
domain_knowledge_v*.yaml
```

Application should load a machine-readable registry.

Do not parse the Markdown at runtime.

---

# 55. Incident corpus retrieval

Machine-readable corpus:

```text
incidents_v0.5.yaml
```

Use indexed fields such as:
- family;
- mappings;
- status;
- evidence tier;
- tags.

MVP retrieval can be:
- deterministic filtering;
- simple text/vector search later if necessary.

Do not add a vector database automatically.

Postgres full-text or in-memory selection may suffice first.

---

# 56. Contradiction engine

For every top candidate, evaluate:

```text
onset before candidate?
scope mismatch?
control affected?
expected intermediate missing?
persists after removal?
wrong external product/time?
source stale?
```

Output:
typed contradiction evidence.

This is not delegated entirely to LLM.

---

# 57. Ranking engine

Internal score is deterministic and versioned.

Possible components:

```text
temporal
segment
mechanism
intermediate evidence
control evidence
intervention
magnitude
source quality
contradiction penalties
observability penalties
```

Output:
ordered candidates + component breakdown.

Not:
public probability.

---

# 58. Confidence label mapping

Deterministic/rule-assisted mapping into:

```text
CONFIRMED
PROBABLE
POSSIBLE CONTRIBUTOR
UNRESOLVED
```

LLM may explain the label.

LLM should not choose a stronger label than permitted by deterministic constraints.

---

# 59. LLM architecture

Create one application-level LLM provider abstraction.

Example:

```text
llm/
  client.py
  schemas.py
  prompts/
  validators.py
```

Responsibilities:
- call provider;
- enforce structured output;
- record model/version;
- validate evidence references;
- redact secrets;
- control retries/timeouts.

---

# 60. LLM use cases

MVP:

```text
incident report synthesis
weekly brief rewriting
possibly intake text normalization
possibly evidence explanation
```

Do not use LLM for:
- checkpoint truth;
- event detection;
- metric calculation;
- source freshness;
- alert eligibility;
- production writes.

---

# 61. LLM context packet

LLM input should contain:

```text
structured incident
structured evidence
candidate hypotheses
score components
contradictions
allowed evidence IDs
allowed next tests
source limitations
```

Not:
- SQL access;
- OAuth token;
- arbitrary API credentials;
- unrestricted corpus.

---

# 62. Structured LLM output

All important LLM calls use validated schema.

Example:

```json
{
  "summary": "...",
  "hypotheses": [
    {
      "hypothesis_id": "...",
      "explanation": "...",
      "supporting_evidence_ids": ["..."],
      "contradicting_evidence_ids": ["..."]
    }
  ],
  "recommended_next_test_id": "...",
  "unknowns": ["..."]
}
```

If evidence ID does not exist:
reject/retry.

---

# 63. LLM provider neutrality

Architecture should not scatter provider-specific code across Incident Engine.

One adapter boundary.

This makes:
- testing;
- model upgrades;
- cost control;

simpler.

---

# 64. LLM failure behavior

If LLM call fails:

Incident deterministic result should still exist.

UI can show:
- structured evidence;
- candidate ranking;
- temporary "explanation unavailable."

Do not make LLM availability a dependency for raw monitoring.

---

# 65. External events architecture

Separate module ingests official external context.

Examples:
- Google Search updates;
- Search incidents;
- GAM status;
- selected vendor/CDN status.

Store:
- provider;
- event type;
- start/end;
- announcement time;
- source URL;
- product/scope;
- source quality.

Do not build a general news crawler.

---

# 66. Manual operational changes

API allows lightweight creation of:

```text
deployment
rollback
CMP change
player change
GAM config
vendor integration
direct campaign
note
```

Store:
- actor;
- timestamp;
- scope;
- description;
- source/manual provenance.

These become incident evidence.

---

# 67. API architecture

FastAPI endpoints should expose application use cases.

Suggested groups:

```text
/api/auth
/api/sites
/api/templates
/api/monitoring
/api/timeline
/api/incidents
/api/connectors
/api/reports
/api/evidence
```

Avoid CRUD-for-every-table architecture.

---

# 68. API command/query split

Conceptually distinguish:

## Commands

```text
create site
connect source
start investigation
add incident note
mark event intentional
resolve incident
run diagnostic
```

## Queries

```text
get home
get timeline
get incident
get evidence
get connector status
```

No need for CQRS infrastructure.

This is merely API design discipline.

---

# 69. Tenant authorization

Every application query/command must resolve:

```text
authenticated user
→ tenant
→ authorized publisher/site
```

Never trust tenant/site ID from client alone.

Authorization filters happen server-side.

---

# 70. Evidence download access

Evidence artifact URLs should not be public.

Use:
- authenticated proxy;
- short-lived signed URL;

depending storage/provider.

Authorization checked before issuing access.

---

# 71. Frontend data strategy

Use normal API fetching.

No need for:
- GraphQL;
- complex global state framework;

unless implementation later proves necessary.

Server/client component strategy can follow current Next.js best practice at build time.

Product architecture only requires clear API boundaries.

---

# 72. Home read model

Home endpoint should aggregate:

```text
site status
active attention events
active incident
weekly brief
connection limitations
```

Prefer a purpose-built query/service.

Do not make frontend independently reconstruct health from raw data.

---

# 73. Timeline read model

Timeline query returns normalized items:

```text
event
external event
operational change
incident milestone
recovery
```

with:
- time interval;
- category;
- severity;
- scope;
- summary;
- evidence links.

Frontend should not merge 5 raw APIs itself.

---

# 74. Incident read model

Incident endpoint returns:

```text
reported symptom
observed symptom
status
severity
windows
scope
timeline
LKG
hypotheses
evidence
unknowns
next test
report versions
```

This is an application read model, not direct ORM serialization.

---

# 75. Evidence API

Evidence endpoint can expose typed summaries.

Examples:

```text
browser screenshot
DOM diff
GPT lifecycle
metric chart
connector source extract metadata
manual note
external event
```

Do not expose unrestricted object-store browsing.

---

# 76. Authentication

Detailed implementation belongs in `SECURITY.md`.

Architecture assumption:

```text
standard secure session/auth provider
```

MVP should not build custom identity cryptography.

Use established library/service.

Keep user/tenant mapping in application DB.

---

# 77. Audit logs

Do not build a massive audit platform.

But sensitive actions should record:

```text
user
action
tenant
object
timestamp
request correlation ID
```

Examples:
- connector connected/disconnected;
- incident resolved;
- event marked intentional;
- manual operational change;
- evidence exported/accessed where necessary.

---

# 78. Logging

Use structured application logs.

Fields:

```text
timestamp
level
service/process
request_id
job_id
tenant_id
site_id
module
error_class
```

Do NOT log:
- OAuth token;
- cookies;
- full headers;
- potentially sensitive raw API payload by default.

---

# 79. Correlation IDs

HTTP request:
```text
request_id
```

Background work:
```text
job_id
```

Browser:
```text
checkpoint_run_id
```

Connector:
```text
source_extract_id
```

Incident:
```text
incident_id
```

These IDs make forensic debugging easier.

---

# 80. Our own observability

MVP internal metrics:

```text
API request success/latency
job backlog
job failure rate
browser run success
browser run duration
connector success/freshness
LLM latency/error/cost
object-storage errors
database health
```

Can begin with standard application monitoring.

Do not build the product to monitor itself.

---

# 81. Platform error taxonomy

Use typed error classes.

Examples:

```text
AUTH_ERROR
PERMISSION_ERROR
RATE_LIMIT
PROVIDER_ERROR
SITE_ERROR
BROWSER_ERROR
COLLECTOR_ERROR
PARSER_ERROR
STORAGE_ERROR
DATABASE_ERROR
TIMEOUT
LLM_ERROR
VALIDATION_ERROR
```

UI maps only relevant ones to user language.

---

# 82. Failure isolation

A browser worker crash should not:
- kill API;
- invalidate existing checkpoints;
- stop connector pulls.

A GAM outage should not:
- stop GA4;
- stop browser;
- hide historical Timeline.

An LLM outage should not:
- stop monitoring;
- destroy incident evidence.

Subsystems should fail independently.

---

# 83. Partial success

Many jobs can succeed partially.

Example checkpoint:

```text
navigation good
screenshot good
DOM good
GPT collector good
video collector failed
```

Store:

```text
checkpoint = PARTIAL
```

with collector statuses.

Do not discard useful evidence because one collector failed.

---

# 84. Retry architecture

Retries are bounded by job type.

Example:

## Browser

Retry:
- browser crash;
- transient infrastructure failure.

Do not erase:
- first publisher 503.

## Connector

Retry:
- 429;
- 5xx;
- transient network.

Do not repeatedly retry:
- permission denied;
- invalid report definition.

## LLM

Retry:
- transient error;
- invalid schema once with repair.

Do not retry indefinitely.

---

# 85. Deployment architecture — MVP

A simple production topology:

```text
Managed/container platform

frontend service
api service
worker service
browser-worker service
scheduler service

managed PostgreSQL
managed object storage
managed secrets
```

Could run in one cloud provider.

Do not require Kubernetes.

---

# 86. Resource isolation

Browser workers need different resources than API.

Example:

```text
API:
low/moderate CPU/RAM

Browser worker:
higher memory
bounded Chromium concurrency

Worker:
moderate CPU/RAM
```

Deploy them as separate process/service classes.

---

# 87. Local development

Use a simple local environment.

Suggested:

```text
Docker Compose:
PostgreSQL
MinIO or local S3-compatible store

Host/container:
FastAPI
worker
scheduler
Next.js
Playwright
```

Exact developer workflow will be defined during EP-001.

Do not create complex local orchestration.

---

# 88. Test environments

Minimum:

```text
local
staging
production
```

Staging should have:
- synthetic test domains;
- safe Google test connections if available;
- separate secrets;
- separate storage/database.

Do not use production publisher credentials in local development.

---

# 89. Database migrations

Use standard Python migration tool appropriate to ORM stack.

Likely:

```text
Alembic
```

if SQLAlchemy is used.

Architecture does not require a specific ORM, but the project should choose one convention and record it in `DECISIONS.md`.

All schema changes go through migrations.

---

# 90. ORM versus SQL

Use ORM for:
- standard entity persistence;
- application queries.

Use explicit SQL where useful for:
- job claiming;
- complex time-series/event queries;
- performance-critical reads.

Do not force every query through ORM abstraction if SQL is clearer.

---

# 91. Repository structure

Recommended top-level:

```text
/
  AGENTS.md
  PRODUCT.md
  MVP.md
  ARCHITECTURE.md
  DATA_MODEL.md
  DOMAIN.md
  INCIDENTS.md
  BROWSER.md
  EVENTS.md
  CONNECTORS.md
  INCIDENT.md
  EVALS.md
  PLANS.md
  DECISIONS.md
  SECURITY.md

  backend/
  frontend/
  plans/
  evals/
  scripts/
  infra/
```

Some files may be introduced progressively.

---

# 92. Machine-readable domain assets

Place canonical machine-readable files in a stable location.

Example:

```text
knowledge/
  domain_knowledge_v1.0.yaml
  incidents_v0.5.yaml
  incident_patterns_v0.5.yaml
```

Do not leave runtime assets scattered in root with generated exports forever.

Migration into repo structure occurs during bootstrap.

---

# 93. Eval assets

Suggested:

```text
evals/
  incident_evals_v0.1.yaml
  eval_rubric_v0.1.yaml
  eval_coverage_v0.1.csv
  results/
```

Evaluation harness reads versioned datasets.

Do not modify historical versions silently.

---

# 94. Configuration

Configuration classes:

## Application

```text
DB URL
object storage
secret store
LLM provider
```

## Runtime

```text
worker concurrency
browser concurrency
timeouts
```

## Product/site

```text
checkpoint cadence
templates
representative URLs
scenarios
event thresholds
```

Do not mix product/site config with environment secrets.

---

# 95. Feature flags

Simple database/config flags if needed.

Examples:

```text
enable_prebid_collector
enable_video_collector
enable_incident_llm
```

Do not add a dedicated feature-flag SaaS during MVP unless needed.

---

# 96. Versioning

Important derived outputs store version information.

Examples:

```text
collector_version
normalizer_version
scenario_version
connector_version
extract_definition_version
event_rule_version
baseline_version
incident_engine_version
domain_version
incident_corpus_version
llm_prompt_version
model
```

This protects against confusing:
publisher change
with
our software change.

---

# 97. Clock/time handling

Internal timestamps:

```text
UTC timestamptz
```

Additionally preserve source timezone/time semantics.

UI displays publisher/site timezone by default.

Never drop:
- GSC source timezone;
- GAM network timezone;
- scenario timezone.

---

# 98. Time-window types

Architecture must support:

```text
exact point
bounded occurrence window
metric interval
approximate user-reported interval
external rollout interval
```

Do not collapse all into one `timestamp`.

---

# 99. Data consistency philosophy

Strong consistency where business/domain identity matters:

```text
tenant ownership
incident/evidence references
job ownership
event relations
```

Eventual/background derivation is acceptable for:

```text
diffs
anomalies
weekly summaries
incident explanation
```

User should see processing status where needed.

---

# 100. Transaction boundaries

Examples:

## Finalize checkpoint

Transaction:
- checkpoint run status;
- collector metadata;
- artifact DB refs.

Artifact object upload may occur before transaction.

If DB finalization fails:
cleanup/reconciliation job can detect orphan artifacts.

## Create incident

Transaction:
- incident;
- reported symptom;
- initial window/state.

Long evidence assembly happens background.

---

# 101. Orphan artifact cleanup

Object storage upload can succeed while DB write fails.

Store upload keys deterministically enough for cleanup.

Periodic job:
- identify orphaned temporary objects;
- retain grace period;
- delete safely.

Do not accidentally delete evidence referenced by DB.

---

# 102. Retention architecture

Retention class on artifacts:

```text
CORE_LONG
RAW_MEDIUM
TRACE_SHORT
INCIDENT_PINNED
```

Example:

```text
normalized checkpoint metadata: long
important screenshots: long/medium
raw DOM: medium
Playwright trace: short
incident-referenced evidence: pinned
```

Exact durations live in `SECURITY.md`.

---

# 103. Evidence pinning

When incident report references artifact:
retention policy should prevent accidental deletion during report retention.

Implementation may mark:

```text
retention_hold
```

or derive references during cleanup.

---

# 104. Data export/deletion

Future privacy/account requirements may need:
- tenant export;
- tenant deletion.

Architecture should preserve tenant IDs across all data.

MVP security contract defines exact behavior.

Do not mix data without tenant ownership.

---

# 105. Multi-tenancy

Shared application/database initially.

Every tenant-owned table includes:
```text
tenant_id
```

or inherits through a guaranteed relation.

Server-side repository/query layer always scopes by tenant.

Do not rely on frontend filters.

---

# 106. Database row-level security

PostgreSQL RLS may be considered later.

MVP may enforce tenancy at application/repository layer if:
- tests are comprehensive;
- query patterns are controlled.

Decision belongs in `SECURITY.md`/ADR.

Do not introduce RLS accidentally in one module only.

---

# 107. Browser network privacy

Network collection should prefer:

```text
URL/domain/method/status/type/timing
```

and avoid retaining:
- full request bodies;
- cookies;
- authorization headers;
- unnecessary query secrets.

Redaction rules belong in `SECURITY.md`.

---

# 108. Screenshot privacy

Publisher pages may contain:
- user-specific content;
- login widgets;
- personal data;
- ads.

Synthetic contexts should avoid authenticated users.

Store screenshots privately.

Access is tenant-controlled.

---

# 109. Connector privacy

Do not ingest user-level Analytics exports.

Use aggregate reporting.

GSC query data:
bounded/on-demand.

GAM campaign/order names:
treated as confidential commercial data.

---

# 110. API pagination

Timeline/event/incident lists use cursor or simple stable pagination.

Do not return entire historical tables.

For MVP:
simple cursor-based pagination preferred where ordering by time.

---

# 111. Search inside product

MVP does not require Elasticsearch.

Simple:
- timeline filters;
- incident lookup;
- Postgres text search;

are sufficient.

If later user needs rich global search:
new ADR.

---

# 112. Caching

Use caching only where it materially reduces expensive work.

Examples:
- mature connector extract reuse;
- external event source fetch;
- expensive Home read model if necessary.

Do not introduce Redis solely for general caching in MVP.

---

# 113. Rate limiting

Need basic protection for:
- auth endpoints;
- expensive diagnostic endpoints;
- incident starts;
- artifact signed URLs.

Provider quotas are separately controlled in connector module.

No sophisticated API gateway required initially.

---

# 114. Incident drill-down budget

Incident Engine must enforce:

```text
max extra browser runs
max connector drill-downs
max candidate count
max LLM passes
```

Budget can vary by severity.

Do not allow an LLM loop to consume unlimited external operations.

---

# 115. Browser diagnostic requests

Incident Engine may request semantically:

```text
mobile article Accept validation
```

Application maps to:
versioned safe scenario.

LLM does not construct arbitrary Playwright code.

---

# 116. Connector diagnostic requests

Incident Engine may request:

```text
Search by page/device
GAM by ad-unit/device
```

Application maps to:
validated extract definition.

LLM does not generate raw Google API payloads.

---

# 117. Evidence IDs

Every evidence object exposed to Incident Engine gets stable ID.

Examples:

```text
EV-BROWSER-...
EV-METRIC-...
EV-EVENT-...
EV-MANUAL-...
EV-EXTERNAL-...
```

Exact format can be UUID + type.

LLM only cites allowed IDs.

---

# 118. Report versioning

Incident report:

```text
incident_report_version
```

Every revision persists.

Stores:
- evidence set;
- hypotheses;
- engine version;
- prompt/model;
- generated text;
- conclusion.

Do not overwrite report v1 with v2.

---

# 119. Weekly report versioning

Weekly Brief is similarly stored with:
- reporting period;
- selected events;
- ranking version;
- prompt/model;
- final text.

Historical reports should remain explainable.

---

# 120. Reprocessing boundaries

Safe to reprocess:

```text
normalization
diffs
events
baseline
incident ranking
reports
```

from immutable evidence.

Do not automatically re-run all historical incident reports after every code deploy.

Reprocess only:
- active incidents;
- requested cases;
- migration/eval tasks.

---

# 121. Schema evolution

Prefer additive changes early.

Avoid:
- renaming core semantics repeatedly;
- destructive migrations;
- storing opaque JSON for everything.

Use JSONB where schema is:
- provider-specific;
- flexible evidence payload.

Use typed columns for:
- core identifiers;
- timestamps;
- statuses;
- relationships.

---

# 122. JSONB rule

Good JSONB uses:

```text
raw/normalized provider metadata
event scope
collector-specific detail
source response metadata
```

Bad:

```text
all incident data in one JSON blob
```

Core queryable semantics belong in relational fields.

---

# 123. Indexing strategy

Initial indexes:

- tenant/site/time;
- checkpoint URL/scenario/time;
- event site/time/status/code;
- metric series/time;
- incident site/status/time;
- job status/available_at;
- source extract connection/period.

Do not create dozens of speculative indexes.

Use query measurements later.

---

# 124. Partitioning

Do not partition initially unless data volume demands.

Likely future candidate:
```text
metric_points
```

But pilot volume should first be measured.

---

# 125. Backup/recovery

Managed PostgreSQL:
- automated backups;
- point-in-time recovery if provider supports.

Object storage:
- durable private bucket;
- lifecycle configuration.

MVP does not need multi-region disaster recovery.

---

# 126. Secrets/deploy configuration

Use environment variables only for secret references/config.

Do not commit:
```text
.env
credentials
OAuth secrets
```

Provide:
```text
.env.example
```

with placeholders.

---

# 127. Dependency management

Backend:
one standard Python dependency manager/lockfile.

Frontend:
one Node package manager/lockfile.

Decision recorded during EP-001.

Avoid multiple package managers.

---

# 128. Code quality

Backend:
- formatting;
- lint;
- static/type checks where practical;
- unit/integration tests.

Frontend:
- lint;
- typecheck;
- build;
- focused component/integration tests.

Exact tools chosen in EP-001/ADR.

---

# 129. Test pyramid

## Unit

- normalization;
- event rules;
- baselines;
- causal rules;
- redaction.

## Integration

- Postgres repositories;
- object storage;
- job claiming;
- connector adapters with fixtures;
- browser collector against controlled pages.

## End-to-end

Small number:
- site onboarding → checkpoint;
- two checkpoints → timeline event;
- incident → evidence → report.

## Evals

Reasoning quality.

Evals are not a replacement for software tests.

---

# 130. Controlled browser fixtures

Create local/staging test pages that deliberately contain:

- slot present/absent;
- JS error;
- lazy-load slot;
- overlay;
- noindex;
- canonical change;
- CMP mock;
- Prebid mock where possible;
- VAST/player fixture.

These make browser tests deterministic.

Do not test everything only against unpredictable live publisher sites.

---

# 131. Connector fixtures

Store sanitized provider-response fixtures.

Examples:

```text
GA4 complete
GA4 thresholded
GSC final
GSC preliminary
GAM complete
GAM partial
GAM direct displacement
```

Tests should not require live API access.

---

# 132. Incident fixtures

Use:
- `incident_evals_v0.1.yaml`;
- synthetic evidence fixtures;
- staged cases.

Incident Engine development should run against reproducible test packets.

---

# 133. CI

Initial CI should run:

```text
backend lint/test
frontend lint/typecheck/build
migration validation
selected integration tests
eval smoke slice
```

Full expensive browser/eval suites can run:
- nightly;
- before release;
- on demand.

Do not make every commit wait on long external integrations.

---

# 134. Release process

MVP can use:

```text
main branch
staging deploy
smoke tests
manual approval
production deploy
```

No need for complex release trains.

Incident Engine changes may require eval release gate.

---

# 135. Database migration release rule

Production deploy involving schema changes:

```text
backup
→ compatible migration
→ deploy application
→ verify
```

Prefer backwards-compatible transitions.

Avoid one-step destructive changes.

---

# 136. Browser rollout rule

New collector/scenario:

```text
staging fixture
→ one pilot site
→ compare noise/failure
→ enable broader
```

Do not activate a noisy collector across all sites immediately.

---

# 137. Event rule rollout

New high-severity event rule:

```text
shadow mode
→ review candidate events
→ calibrate
→ Timeline
→ alert eligibility
```

Do not go directly from code to critical notifications.

---

# 138. Incident reasoning rollout

New causal rule:

```text
DOMAIN update
→ eval added
→ benchmark
→ shadow report comparison
→ release
```

Do not change production reasoning without eval coverage.

---

# 139. Feature maturity levels

Useful internal concept:

```text
EXPERIMENTAL
PILOT
STABLE
```

Examples:
- Prebid Server deep diagnostics may stay EXPERIMENTAL.
- Core browser checkpoint becomes STABLE first.

Do not expose unnecessary maturity labels to users unless useful.

---

# 140. Infrastructure progression

MVP:

```text
Postgres job queue
```

Later, only if measured need:

```text
Redis queue
```

Further later, only if truly needed:

```text
specialized queue/stream
```

Do not jump directly to Kafka.

---

# 141. Database progression

MVP:

```text
PostgreSQL
```

Later:
- partitions;
- read replicas;
- specialized analytics store;

only after real query/storage pressure.

---

# 142. Browser progression

MVP:

```text
few workers
few scenarios
representative URLs
```

Later:
- region workers;
- additional browsers;
- field/RUM;

only with validated need.

---

# 143. AI progression

MVP:

```text
structured LLM synthesis
```

Later:
- improved retrieval;
- specialized reasoning models;
- safe automated remediation;

only after evals/trust.

Do not begin with agents coordinating agents.

---

# 144. Key architectural invariants

Codex MUST preserve:

```text
ARCH-INV-001
Raw evidence and derived conclusions remain separate.

ARCH-INV-002
Browser checkpoint evidence is immutable after finalization.

ARCH-INV-003
Metric, event, incident and hypothesis are separate entities.

ARCH-INV-004
LLM cannot create source-of-truth evidence.

ARCH-INV-005
LLM cannot perform arbitrary production/API actions.

ARCH-INV-006
All tenant data access is server-side authorized.

ARCH-INV-007
Large artifacts live outside PostgreSQL.

ARCH-INV-008
PostgreSQL is the only structured database in MVP.

ARCH-INV-009
Background work is asynchronous and bounded.

ARCH-INV-010
Browser crashes do not crash API.

ARCH-INV-011
Connector failure does not become business zero.

ARCH-INV-012
Time uncertainty is preserved.

ARCH-INV-013
Source freshness is preserved.

ARCH-INV-014
Derived rules are versioned.

ARCH-INV-015
Incident reports are versioned.

ARCH-INV-016
Event/incident reasoning changes require eval coverage.

ARCH-INV-017
No new infrastructure category without ADR.

ARCH-INV-018
No microservices unless explicitly approved later.
```

---

# 145. Architecture anti-patterns

Do not implement:

## God service

```text
monitoring_service.py
```

containing browser, GAM, events, AI and alerts.

## Everything JSONB

Makes semantics impossible to query/test.

## LLM orchestration first

Evidence pipeline must exist before AI.

## Browser tied to API request

Checkpoint work must be background.

## Frontend-derived business logic

Health/event/incident logic belongs backend.

## Direct provider SDK calls from Incident Engine

Use connector abstraction.

## Raw object storage as database

Metadata/provenance remain in Postgres.

---

# 146. First repository bootstrap target

EP-001 should establish:

```text
backend/
frontend/
Postgres
object storage
migration framework
job worker
scheduler skeleton
test framework
CI
environment configuration
```

Do not implement deep product features yet.

---

# 147. First product implementation target

EP-002:

> **One public URL → one reproducible Chromium checkpoint.**

Minimum evidence:

```text
run metadata
final URL/status
viewport screenshot
full-page screenshot
raw DOM
script inventory
third-party domains
network failures
JS errors
environment provenance
```

Persisted into:
```text
Postgres + object storage
```

---

# 148. Second product target

Two comparable runs:

```text
checkpoint A
checkpoint B
↓
normalized comparison
↓
meaningful diff
```

No LLM required.

This establishes operational memory.

---

# 149. Third product target

Connect business telemetry.

```text
GA4
GSC
GAM
```

Then:

```text
browser event
+
metric movement
```

can share a timeline.

---

# 150. Fourth product target

Incident Engine.

Use stored evidence.

Do not bypass architecture by:
scraping live data ad hoc inside an LLM call.

---

# 151. Architecture acceptance criteria

ARCHITECTURE v1 is satisfied when implementation follows these truths:

1. codebase is modular monolith;
2. API and browser execution are separate processes;
3. PostgreSQL is structured system of record;
4. object storage holds large artifacts;
5. jobs are background and retryable;
6. scheduler inserts jobs rather than running domain logic;
7. checkpoint evidence is immutable;
8. collector outputs preserve provenance/version;
9. connector source extracts preserve freshness;
10. metric semantics are versioned;
11. event rules are deterministic/versioned;
12. event routing is separate from notification delivery;
13. Incident Engine has deterministic core + LLM synthesis;
14. LLM receives bounded evidence packet;
15. evidence IDs are validated;
16. Last Known Good is derived per incident/scope;
17. report versions are immutable/history-preserving;
18. source failures remain distinct from publisher failures;
19. partial evidence is preserved;
20. tenant boundaries apply to every data path;
21. artifact access is private;
22. secrets never enter evidence/logs;
23. no arbitrary LLM provider/API queries;
24. no autonomous production writes;
25. no graph DB;
26. no separate time-series DB;
27. no Kafka/Kubernetes requirement;
28. CI validates core software;
29. reasoning changes run evals;
30. architecture can be run locally/staging/production without a large platform team.

---

# 152. Codex architecture rules

Codex MUST:

- read `ARCHITECTURE.md` before creating major modules;
- read subsystem docs before implementing subsystem behavior;
- prefer existing modules over new infrastructure;
- use background jobs for browser/connectors/long reasoning;
- preserve tenant ownership;
- preserve evidence provenance;
- use object storage for large artifacts;
- keep LLM behind one adapter;
- validate structured LLM outputs;
- update `DECISIONS.md` for durable architecture changes;
- create an ExecPlan for substantial changes.

Codex MUST NOT:

- introduce microservices;
- introduce another database;
- introduce a queue/stream platform;
- introduce Kubernetes;
- add a vector DB merely for incident retrieval;
- put OAuth tokens in job payloads;
- let browser run inside normal API request;
- let LLM write provider configurations;
- let frontend infer causal confidence;
- silently change metric/event semantics;
- delete evidence needed by incident history.

---

# 153. What is intentionally undecided

These implementation details should be chosen during repository bootstrap and recorded in ADRs:

```text
Python package/dependency manager
ORM choice
exact PostgreSQL job library versus small custom implementation
auth provider/library
cloud provider
object-storage provider
LLM provider/model
email provider
logging/monitoring vendor
```

The architecture constrains behavior, not vendor preference.

Choose the simplest credible option.

---

# 154. Architecture review trigger

Revisit this architecture only when measured evidence shows one of:

```text
Postgres cannot sustain workload
browser throughput cannot meet schedule
job queue causes operational instability
object storage model prevents evidence access
single deployment becomes release bottleneck
tenant/security requirement demands isolation
incident retrieval needs fundamentally different search
```

Do not redesign because a more sophisticated architecture exists.

---

# 155. Final architecture principle

The system should make one thing easy:

> **Trace a conclusion all the way back to what was actually observed.**

The architecture therefore follows:

```text
Source
→ Evidence
→ Derived State
→ Event
→ Hypothesis
→ Report
```

and never:

```text
LLM
→ plausible story
→ assumed evidence
```

The architectural standard is:

# **Simple runtime. Strong evidence boundaries. Explicit provenance. Background work. Deterministic truth, AI explanation.**
