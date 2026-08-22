# AGENTS.md
## Publisher Incident Intelligence Platform
### Codex Repository Instructions — v1.0

This file is the repository-level operating contract for Codex.

Keep this file concise.

Detailed product, domain, architecture, security and subsystem behavior lives in the canonical documents referenced below.

---

# 1. Mission

Build the smallest reliable system that proves:

> **Better publisher evidence produces better incident decisions.**

The product is:

> **A black-box recorder, operational memory and incident investigator for digital publishers.**

It is not:
- a generic analytics dashboard;
- a revenue optimizer;
- an SEO suite;
- an autonomous remediation agent.

---

# 2. Core operating rule

Before editing code:

1. identify the subsystem;
2. read the relevant canonical docs;
3. inspect the current repository;
4. create/follow an ExecPlan if the work is substantial;
5. implement the smallest valid slice;
6. validate it;
7. fix failures before continuing;
8. update the plan/docs when durable behavior changed.

Do not implement from chat memory alone.

The repository documents are the durable source of truth.

## 2.1 Implementation authorization invariant

Canonical specifications (`PRODUCT.md`, `MVP.md`, `EVENTS.md`, `DATA_MODEL.md`, `INCIDENT.md`,
`EVALS.md`, `BROWSER.md`, `CONNECTORS.md`, and similar files) define constraints, invariants, and
target semantics. They do **not** authorize implementation. Only the currently active authorized
ExecPlan authorizes new capability work.

For large catalogs where future/unimplemented semantics are described alongside implemented ones
(especially `EVENTS.md`), consult the document's implementation-status legend to distinguish
normative-now sections from planned/future sections before treating any described behavior as
buildable scope.

---

# 3. Canonical documents

## Product

Read:

```text
PRODUCT.md
MVP.md
```

Use for:
- what the product is;
- user behavior;
- scope;
- non-goals.

## Architecture

Read:

```text
ARCHITECTURE.md
DATA_MODEL.md
SECURITY.md
DECISIONS.md
```

Use for:
- module boundaries;
- storage;
- jobs;
- tenant/security;
- durable technical choices.

## Domain

Read:

```text
DOMAIN.md
INCIDENTS.md
```

Use for:
- publisher/ad-tech/Search semantics;
- failure modes;
- evidence logic;
- precedent.

## Synthetic browser

Read:

```text
BROWSER.md
```

before any browser/checkpoint/collector/scenario work.

## Connectors

Read:

```text
CONNECTORS.md
```

before GA4/GSC/GAM work.

## Events

Read:

```text
EVENTS.md
```

before event/anomaly/timeline/alert logic.

## Incident reasoning

Read:

```text
INCIDENT.md
EVALS.md
DOMAIN.md
```

before changing Incident Engine reasoning.

## Long work

Read:

```text
PLANS.md
```

and create an ExecPlan under:

```text
plans/EP-NNN-short-name.md
```

---

# 4. Instruction precedence

When instructions conflict:

```text
1. explicit current user/product decision
2. AGENTS.md
3. accepted DECISIONS.md ADR
4. MVP.md
5. relevant subsystem specification
6. SECURITY.md for security constraints
7. ARCHITECTURE.md / DATA_MODEL.md
8. PRODUCT.md
9. current ExecPlan
10. implementation preference
```

`DOMAIN.md` is authoritative for domain semantics.

If a real conflict remains:
record it and ask only when continuing requires a product/security decision.

---

# 5. MVP boundary

Assume:

> **If a feature is not explicitly inside MVP.md or required to implement an included capability, it is out of scope.**

Do not add “helpful” future features.

Examples:

```text
Slack integration
RUM
session replay
extra databases
AI screenshot diagnosis
autonomous remediation
full enterprise RBAC
browser farms
```

unless explicitly approved.

Every ExecPlan must state:

```text
MVP scope impact: NO
```

or:

```text
YES — approved by ADR-XXX
```

---

# 6. KISS architecture

Default stack:

```text
Next.js / React
FastAPI / Python
PostgreSQL
S3-compatible object storage
Playwright + Chromium
PostgreSQL-backed jobs/workers
external LLM API
```

Architecture:

```text
modular monolith
+
separate runtime processes for API / worker / browser-worker / scheduler
```

Do NOT introduce without an accepted ADR:

```text
microservices
Kafka
Kubernetes
Neo4j
ClickHouse
TimescaleDB
Redis
vector database
custom workflow engine
```

---

# 7. Evidence invariants

Never optimize away these semantics:

```text
raw evidence != derived conclusion
checkpoint != event
metric != event
event != incident
incident != cause
```

Raw source evidence is immutable/versioned where specified.

Preserve:

```text
source provenance
time uncertainty
source freshness
scenario/version metadata
numerator + denominator where available
tenant ownership
```

If a parser/rule improves:
derive new output.

Do not rewrite historical fact.

---

# 8. Browser invariants

For browser work:

```text
Playwright + real Chromium
controlled deterministic visit
fresh isolated BrowserContext
representative URLs/templates
fixed six-hour core checkpoint
desktop + mobile core profiles
```

Never:

```text
click ads
bypass paywalls
use real user profiles
use stolen/authenticated sessions
use stealth anti-bot evasion
run arbitrary LLM-generated Playwright code
```

Treat monitored pages as hostile.

Keep Chromium sandbox enabled in production.

Block access to:
- loopback;
- private networks;
- link-local;
- cloud metadata;
- internal services.

Distinguish:

```text
SITE_ERROR
BROWSER_ERROR
TIMEOUT
PARTIAL
COMPLETE
```

Do not retry away real publisher evidence.

---

# 9. Connector invariants

MVP connectors:

```text
GA4
Google Search Console
Google Ad Manager
```

All are:

```text
READ ONLY
```

Use predefined, versioned extract definitions.

Never let an LLM create arbitrary provider queries.

Preserve:

```text
source
query/extract definition
time period
timezone
freshness/maturity
retrieval time
version
```

Missing/stale data is not zero.

---

# 10. Event invariants

Event creation is deterministic and versioned.

LLM does not decide whether an event happened.

Events must preserve:

```text
evidence
scope
timing precision
confirmation
severity
lifecycle
rule version
```

Quiet by default.

Most observations do not become events.

Most events do not become alerts.

External platform events are context, not automatic cause.

---

# 11. Incident reasoning invariants

Always:

```text
baseline first
measurement integrity first
localize before explaining
mechanism before confidence
search for contradictions
```

Use unaffected segments as controls.

Important causal rules:

```text
temporal order is necessary but insufficient
symptom predating candidate strongly weakens causality
intermediate evidence strengthens causality
rollback + recovery strengthens causality
persistence after removal weakens causality when recovery lag permits
external event needs local matching evidence
multi-causal incidents are allowed
descendant metrics must not be double-counted
```

Valid outcomes:

```text
CONFIRMED
PROBABLE
POSSIBLE CONTRIBUTOR
UNRESOLVED
```

`UNRESOLVED` is acceptable.

Never invent a cause merely to complete a report.

---

# 12. LLM boundary

The LLM explains approved evidence.

It is not the source of truth.

LLM may:

```text
summarize
explain mechanisms
compare hypotheses
rewrite Weekly Brief findings
produce structured incident narrative
```

LLM may NOT:

```text
invent evidence
invent timestamps
invent source metrics
run raw SQL
access secrets
generate arbitrary Playwright code
generate arbitrary Google API payloads
change GAM/CMP/Prebid/site configuration
override deterministic confidence gates
access another tenant
```

All important outputs must be structured and validated.

Evidence IDs cited by the model must exist.

---

# 13. Security invariants

Treat:

```text
page = hostile
evidence = confidential
model = untrusted
tenant isolation = non-negotiable
```

Never store/log:

```text
OAuth refresh/access tokens
Authorization headers
cookie values
session IDs
API keys
signed URLs
raw secrets
```

Refresh tokens live in the secret layer, not normal DB rows/jobs.

All tenant-owned reads/writes require server-side tenant authorization.

Every new tenant-owned endpoint requires cross-tenant regression tests.

Object storage:
- private;
- encrypted;
- tenant-authorized;
- short-lived signed access only.

Raw DOM must not be rendered as executable HTML.

LLM output must not be rendered as raw HTML.

---

# 14. Data minimization

Do not collect data merely because it is technically available.

Prefer:

```text
diagnostic fields
normalized identities
bounded evidence
```

over:

```text
full request bodies
full response bodies
all cookie values
all storage values
all Search queries
all GAM rows
```

Retention follows `SECURITY.md`.

Incident-referenced evidence may be pinned.

---

# 15. ExecPlans

For complex features, significant refactors, data-model changes, security-boundary changes or work spanning several implementation loops:

Create and follow an ExecPlan using:

```text
PLANS.md
```

Once an ExecPlan is `READY` and implementation begins:

```text
implement milestone
→ validate
→ fix
→ update plan
→ continue
```

Do not ask “should I continue?” after every milestone if the plan already authorizes the next step.

Stop only for:
- genuine blocker;
- missing credential/access;
- destructive action;
- security/privacy decision;
- architecture/product decision not already settled.

---

# 16. Progress discipline

During an active ExecPlan, update:

```text
Progress
Validation Results
Decision Log
Discoveries / Surprises
Next Step
```

Do not let the plan become stale while code diverges.

---

# 17. Validation rule

Never claim success without running the relevant checks.

Use the cheapest relevant ladder:

```text
format
lint
typecheck
unit tests
integration tests
migration test
build
smoke test
end-to-end behavior
evals
```

If a validation fails:

```text
fix it
→ rerun
```

before continuing, unless the failure is documented as unrelated/pre-existing.

---

# 18. Definition of done

A task is not done because code was written.

Done means, where applicable:

```text
target behavior works
acceptance criteria pass
tests pass
failure path tested
migration works
security constraints pass
tenant isolation tested
docs/plan updated
diff reviewed
no hidden blocker
```

For Incident Engine reasoning:
relevant eval coverage must also pass.

---

# 19. Tests

Prefer meaningful tests over coverage theater.

Required categories where relevant:

```text
happy path
failure path
edge case
regression
tenant boundary
counterexample
```

Browser:
use controlled fixture pages.

Connectors:
use sanitized provider fixtures.

Incident Engine:
use versioned eval cases.

Do not make normal tests depend on live external APIs.

---

# 20. Data model changes

Before schema work:
read `DATA_MODEL.md`.

All schema changes:
- use migrations;
- preserve tenant ownership;
- preserve evidence provenance;
- avoid destructive changes where possible.

Do not create a generic everything/EAV table.

Do not store all core semantics in one JSON blob.

---

# 21. Dependency rule

Before adding a dependency:

```text
Can stdlib/current dependency solve this?
Is the package maintained?
Does it materially simplify the task?
Does it add operational/security risk?
```

Do not add infrastructure/frameworks because they are familiar.

Significant dependencies require rationale in the ExecPlan and possibly ADR.

---

# 22. Refactor rule

Do not refactor unrelated code while implementing a feature.

If a refactor is necessary:
- explain why;
- include it in plan;
- validate before/after.

Optional cleanup becomes a follow-up.

---

# 23. Frontend rule

The frontend should expose product behavior, not reconstruct domain logic.

Backend owns:
- Home status;
- Timeline semantics;
- incident confidence;
- event severity;
- evidence authorization.

Frontend owns:
- presentation;
- interaction;
- loading/error states.

Avoid dashboard walls.

Use progressive disclosure.

---

# 24. API rule

Expose application use cases, not raw database CRUD.

Commands:

```text
start investigation
add note
mark intentional
resolve incident
run diagnostic
connect source
```

Queries:

```text
Home
Timeline
Incident
Evidence
Connector status
```

Authorization happens server-side.

---

# 25. Logging rule

Use structured logs with identifiers such as:

```text
request_id
job_id
tenant_id
site_id
checkpoint_run_id
source_extract_id
incident_id
```

Do not log customer evidence unnecessarily.

Do not use logs as a second database.

---

# 26. Durable decisions

Before changing an accepted architectural/product direction:

read `DECISIONS.md`.

If reality justifies a change:
- create new ADR;
- supersede old ADR;
- record evidence/reason.

Do not silently reopen settled choices.

---

# 27. Open decisions

Do not invent final answers for intentionally open decisions unless the current task requires them.

Examples currently open include:

```text
Python dependency manager
ORM
auth provider
cloud provider
object storage provider
LLM provider/model
email provider
monitoring vendor
PostgreSQL RLS
contractual retention commitments
```

When implementation reaches one:
choose the simplest credible option,
record the ADR,
and continue unless the choice has material business/security consequences requiring user input.

---

# 28. Git / diff discipline

Before finalizing work:

- inspect `git diff`;
- verify only intended files changed;
- check for accidental secrets;
- check docs are still accurate;
- remove dead experimental code;
- ensure generated artifacts are intentional.

Prefer small coherent commits when repository workflow supports them.

---

# 29. Repository hygiene

Do not commit:

```text
.env
credentials
tokens
production dumps
temporary screenshots
local DB files
browser profiles
node_modules
Python virtualenv
build artifacts
```

Generated test fixtures must be sanitized and intentional.

---

# 30. First implementation priority

Until explicitly changed, the first product engineering proof is:

> **One public publisher URL → one reproducible Chromium checkpoint persisted to PostgreSQL + object storage.**

Minimum:

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

No AI required.

Do not jump ahead to Incident Engine before evidence collection works reliably.

---

# 31. Build order

Recommended initial progression:

```text
repository foundation
→ browser checkpoint
→ repeatable comparison
→ semantic diff/events
→ GA4
→ GSC
→ GAM
→ Home/Timeline
→ Incident intake/localization
→ evidence pack
→ hypotheses/contradictions
→ LLM synthesis
→ eval release gate
```

Use `MVP.md`, subsystem milestones and ExecPlans as the authoritative sequence.

Keep `README.md` → `Repository boundaries` current as compact project memory. Refresh it after no
more than three completed EPs, or sooner when an EP materially changes the implemented product,
data, security, or operational boundary. Name the latest fully covered EP and label partial work
explicitly; never describe a planned milestone as shipped.

---

# 32. When to ask the user

Ask only when continuing requires:

```text
new product behavior
MVP expansion
new security/privacy boundary
new production write capability
new major external dependency/service
destructive migration
credential/access the repository cannot obtain
two materially different business tradeoffs
```

Do not ask about:
- ordinary code organization;
- naming;
- routine test choices;
- obvious implementation details.

For low-risk ambiguity:
choose the simplest approach consistent with the canonical docs,
record it,
continue.

---

# 33. Review standard

Before presenting work as complete, ask:

```text
Is it the smallest implementation that satisfies the contract?
Can we prove it works?
Can another session understand why it exists?
Can every important conclusion trace back to evidence?
Did we preserve security and tenant boundaries?
Did we accidentally expand scope?
```

If any answer is no:
the work is not complete.

---

# 34. Final Codex principle

Do not optimize for producing the most code.

Optimize for:

```text
correct product behavior
reliable evidence
small verified milestones
clear boundaries
reproducibility
low noise
epistemic restraint
```

The repository standard is:

# **Observe faithfully. Preserve evidence. Build the smallest valid slice. Validate before moving on. Never manufacture certainty.**
