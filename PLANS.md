# PLANS.md
## Codex Execution Plans for Publisher Incident Intelligence
### v1.0 — Repository Planning Contract

**Audience:** Codex, engineering, technical reviewers  
**Status:** Mandatory planning contract for complex work  
**Project:** Publisher Incident Intelligence Platform

---

# 0. Purpose

This file defines how Codex must plan and execute substantial work in this repository.

An **ExecPlan** is a living implementation document for one coherent engineering outcome.

It is not:
- a brainstorm;
- a backlog;
- a product roadmap;
- a loose todo list;
- a replacement for `PRODUCT.md`, `MVP.md`, `ARCHITECTURE.md`, or DOMAIN specifications.

Its purpose is:

> **Turn a complex engineering task into a sequence of small, verifiable milestones that can be implemented end-to-end without losing product intent, evidence semantics, or architectural constraints.**

For difficult work, Codex should be able to restart from:
- the current repository;
- the relevant canonical specification files;
- the single active ExecPlan;

and understand:
- what is being built;
- why;
- what is already done;
- what remains;
- what decisions were made;
- how to verify success.

---

# 1. When an ExecPlan is mandatory

Create and maintain an ExecPlan when the task is:

- expected to take several implementation loops;
- cross-cutting across multiple modules;
- architecturally important;
- data-model changing;
- difficult to validate mentally;
- likely to contain unknowns;
- a new major subsystem;
- a significant refactor;
- a production migration;
- a complex connector integration;
- a new Incident Engine reasoning capability;
- a new browser collector affecting evidence semantics.

Examples:

```text
Implement the six-hour Playwright checkpoint pipeline.
Implement GA4 ingestion end-to-end.
Implement the Event Engine.
Implement Incident Investigation v1.
Introduce tenant isolation across existing data.
Migrate checkpoint artifact storage.
```

---

# 2. When an ExecPlan is NOT required

Do not create an ExecPlan for:

- typo fixes;
- small isolated bug fixes;
- one-file refactors with obvious behavior;
- documentation wording;
- trivial test additions;
- small UI polish;
- dependency patch with no architecture impact.

Use judgment.

Do not turn every 20-minute task into ceremony.

---

# 3. Canonical repository documents

An ExecPlan does not replace canonical specifications.

Before planning, Codex MUST read the relevant canonical docs.

## Product intent

```text
PRODUCT.md
MVP.md
```

## Architecture

```text
ARCHITECTURE.md
DATA_MODEL.md
SECURITY.md
```

when they exist.

## Domain semantics

```text
DOMAIN.md
INCIDENTS.md
```

## Subsystem contracts

```text
BROWSER.md
EVENTS.md
CONNECTORS.md
INCIDENT.md
EVALS.md
```

## Repository rules

```text
AGENTS.md
DECISIONS.md
PLANS.md
```

If a referenced canonical file does not yet exist:
state that explicitly in the ExecPlan.

Do not invent its contents.

---

# 4. Precedence

When instructions appear to conflict, use this precedence:

```text
1. explicit current user/product decision
2. AGENTS.md
3. MVP.md
4. subsystem contract relevant to the task
5. DATA_MODEL.md / ARCHITECTURE.md
6. PRODUCT.md
7. current ExecPlan
8. implementation convenience
```

`DOMAIN.md` is authoritative for domain semantics.

`DECISIONS.md` is authoritative for accepted architecture/product decisions unless later superseded explicitly.

If conflict remains:
record it in the ExecPlan under **Open Decision** and stop only if implementation cannot safely proceed.

---

# 5. KISS rule

Every ExecPlan must prefer the smallest architecture that satisfies the milestone.

For this project, default assumptions remain:

```text
modular monolith
Python / FastAPI
PostgreSQL
Playwright / Chromium
S3-compatible object storage
Next.js / React
background jobs/workers
LLM API only where reasoning/explanation requires it
```

Do not introduce:

```text
Kafka
Kubernetes
Neo4j
ClickHouse
microservices
custom event-stream infrastructure
complex workflow engines
```

unless:
- an actual validated requirement exists;
- the existing architecture cannot satisfy it;
- the ExecPlan documents evidence;
- `DECISIONS.md` records the decision.

---

# 6. One ExecPlan = one coherent outcome

Good:

```text
Implement browser checkpoint milestone B1.
Implement GAM connector C4.
Implement incident evidence pack I2.
```

Bad:

```text
Build backend, frontend, AI, security, billing and deploy production.
```

If work contains several independent outcomes:
split into separate ExecPlans.

---

# 7. ExecPlan file location

Store active plans in:

```text
plans/
```

Naming:

```text
plans/EP-001-browser-checkpoint-b1.md
plans/EP-002-browser-repeatable-runs-b2.md
plans/EP-003-ga4-connector-c2.md
```

Use:

```text
EP-NNN-short-kebab-name.md
```

Numbers are monotonic.

Do not reuse an old number.

---

# 8. ExecPlan lifecycle

Statuses:

```text
DRAFT
READY
IN_PROGRESS
BLOCKED
COMPLETE
SUPERSEDED
ABANDONED
```

A plan begins as DRAFT.

It becomes READY only when:
- scope is clear;
- validation is defined;
- unknowns are acceptable;
- dependencies are identified.

When implementation begins:
`IN_PROGRESS`.

When all acceptance criteria pass:
`COMPLETE`.

Do not mark complete because code exists.

---

# 9. Living-document rule

The ExecPlan MUST be updated during implementation.

At every meaningful stopping point, update:

```text
Progress
Discoveries
Decisions
Validation Results
Next Step
```

Do not leave a stale plan describing work that no longer matches the code.

A new Codex session should be able to understand the current state from the plan.

---

# 10. Self-contained enough to resume

An ExecPlan must explain the task sufficiently for a developer unfamiliar with the active conversation.

But it should not duplicate entire canonical documents.

Good:

> BROWSER.md requires every core checkpoint to preserve immutable evidence and distinguish SITE_ERROR from BROWSER_ERROR. This plan implements that contract in the B1 pipeline.

Bad:

Copying 40 pages of `BROWSER.md` into the plan.

Reference canonical sections and restate only the constraints essential to this task.

---

# 11. Required ExecPlan structure

Every substantial plan MUST contain these sections:

```text
1. Title / Metadata
2. Purpose and User Outcome
3. Scope
4. Non-Goals
5. Canonical References
6. Current State
7. Target Behavior
8. Architecture / Data Flow
9. Files and Modules Affected
10. Milestones
11. Acceptance Criteria
12. Validation Commands
13. Test Cases
14. Data / Migration Impact
15. Security / Privacy Impact
16. Observability / Failure Handling
17. Rollback Strategy
18. Progress Log
19. Decision Log
20. Discoveries / Surprises
21. Known Risks
22. Final Outcome / Retrospective
```

For a very small but still plan-worthy task, some sections can be short.

Do not omit:
- Purpose;
- Milestones;
- Acceptance Criteria;
- Validation;
- Progress Log.

---

# 12. Purpose and User Outcome

Begin with the behavior enabled by the work.

Example:

> After this plan is complete, a configured publisher URL can be opened by a controlled Chromium session and the platform will persist a reproducible checkpoint containing screenshots, DOM, network dependencies, JavaScript errors, final URL and environment provenance.

Do not begin with:

> Create classes X, Y and Z.

Implementation exists to produce behavior.

---

# 13. Scope

State exactly what this plan implements.

Example:

```text
IN:
- one monitored URL
- one Chromium scenario
- viewport screenshot
- full-page screenshot
- raw DOM
- script inventory
- network domain inventory
- JS/page errors
- final URL/status
- artifact manifest
```

---

# 14. Non-Goals

State what is intentionally excluded.

Example:

```text
OUT:
- GPT lifecycle
- CMP Accept/Reject
- Prebid
- video
- anomaly detection
- AI interpretation
- dashboard
```

Non-goals prevent scope creep.

---

# 15. Canonical references

List exact files Codex must read.

Example:

```text
AGENTS.md
MVP.md
BROWSER.md
DATA_MODEL.md
DECISIONS.md
```

State the relevant contract, e.g.:

```text
BROWSER-INV-002 — checkpoint evidence is immutable.
```

Do not rely on memory of another chat.

---

# 16. Current state

Describe the repo as it exists before implementation.

Include:
- relevant modules;
- existing migrations;
- tests;
- dependencies;
- known gaps.

Codex MUST inspect the repository before writing this section.

Do not assume a file exists because the product spec says it eventually should.

---

# 17. Target behavior

Describe externally observable behavior.

Use examples where useful.

Example:

```text
Input:
https://publisher.example/article

Run:
python -m app.browser.run_checkpoint ...

Expected:
checkpoint persisted
3 artifacts stored
network summary stored
JS errors stored
run status COMPLETE
```

Target behavior should be testable.

---

# 18. Architecture / data flow

Show only what this task needs.

Example:

```text
Browser Job
   ↓
Playwright Worker
   ↓
Collectors
   ↓
Artifact Store
   ↓
Checkpoint Repository
   ↓
PostgreSQL
```

Explain boundaries.

Do not redesign unrelated parts of the system.

---

# 19. Files and modules affected

Before coding, identify likely paths.

Example:

```text
backend/browser/runner.py
backend/browser/collectors/network.py
backend/db/models/checkpoint.py
backend/db/repositories/checkpoints.py
tests/browser/
migrations/...
```

If paths do not yet exist:
say `to create`.

If repository inspection changes this:
update the plan.

---

# 20. Milestone philosophy

Milestones must be small enough to:

```text
implement
→ run
→ verify
→ repair
```

inside one coherent loop.

Each milestone must produce observable progress.

Avoid:

```text
M1 Build backend
M2 Build frontend
```

Prefer:

```text
M1 Navigate and persist run metadata
M2 Capture and persist screenshots
M3 Capture DOM/network/errors
M4 Add failure classification
M5 Add integration test
```

---

# 21. Milestone format

Each milestone MUST include:

```text
Goal
Implementation
Acceptance criteria
Validation
Expected observable result
```

---

# 22. Stop-and-fix rule

After every milestone:

1. run required validation;
2. if validation fails, fix it;
3. rerun;
4. only continue after passing.

Do not accumulate known failures to "fix at the end."

Exceptions:
- explicitly documented external blocker;
- known unrelated pre-existing failure.

Record exception.

---

# 23. Validation ladder

Use the cheapest relevant checks first:

```text
format
lint
typecheck
unit tests
integration tests
build
migration test
smoke test
end-to-end behavior
```

Not every milestone needs every level.

The final plan should run the full relevant suite.

---

# 24. Required final validation

Before marking COMPLETE, Codex must run, when applicable:

```text
backend tests
frontend tests
lint
typecheck
build
database migrations from clean state
targeted integration test
manual/smoke demonstration
```

Exact commands belong in repo docs/AGENTS once known.

Do not claim checks passed without actually running them.

---

# 25. Acceptance criteria

Acceptance criteria describe observable truth.

Good:

```text
[ ] a 503 page produces SITE_ERROR
[ ] Chromium crash produces BROWSER_ERROR
[ ] both attempts remain queryable after retry
```

Bad:

```text
[ ] error handling implemented
```

Criteria must permit a reviewer to decide pass/fail.

---

# 26. Test cases

Plans must specify tests for:
- happy path;
- failure path;
- edge cases relevant to contract;
- regression case if fixing a bug.

For domain logic:
include negative/counterexample tests.

---

# 27. Data-model changes

If schema changes:

Plan MUST include:
- tables/columns;
- constraints;
- indexes;
- migration;
- backwards compatibility;
- backfill if needed;
- rollback concern.

Read `DATA_MODEL.md`.

Never allow implementation code to silently redefine data semantics.

---

# 28. Migration rule

Database changes require migrations.

No manual production DB edits.

Before plan COMPLETE:
test migration on a clean database.

If destructive:
include explicit review and rollback strategy.

---

# 29. Evidence semantics rule

Any feature touching evidence MUST preserve:

```text
raw source evidence
provenance
timestamp semantics
source version
immutability where required
```

Examples:
- browser checkpoints;
- connector extracts;
- incident evidence.

Do not optimize storage by destroying forensic history.

---

# 30. Event semantics rule

If work creates/modifies event behavior:

Read `EVENTS.md`.

Plan must identify:
- event code;
- confirmation;
- scope;
- deduplication;
- lifecycle;
- severity;
- alertability;
- evidence refs;
- rule version.

Do not create event logic as incidental UI behavior.

---

# 31. Incident semantics rule

If work changes Incident Engine:

Read:
```text
INCIDENT.md
EVALS.md
DOMAIN.md
```

Plan must specify:
- evidence required;
- hypothesis behavior;
- contradiction handling;
- confidence behavior;
- eval changes.

No Incident Engine reasoning change is complete without relevant eval coverage.

---

# 32. Connector semantics rule

If work changes GA4/GSC/GAM:

Read `CONNECTORS.md`.

Plan must include:
- read-only scope;
- extract definition/version;
- freshness;
- missingness;
- timezone;
- quota/backoff;
- provenance;
- compatibility tests.

Do not add arbitrary LLM-generated provider queries.

---

# 33. Browser semantics rule

If work changes synthetic browser collection:

Read `BROWSER.md`.

Plan must preserve:
- controlled visit;
- scenario identity;
- browser version;
- no ad clicking;
- no stealth;
- bounded waits;
- partial evidence;
- site failure vs monitor failure.

---

# 34. Security / privacy impact

Every substantial plan must ask:

```text
Does this touch credentials?
Does this store new user/publisher data?
Does it add artifacts?
Does it alter tenant boundaries?
Does it log URLs/headers/cookies?
Does it change retention?
```

If yes:
state mitigation.

If no:
write `No material security/privacy impact`.

Do not leave section blank.

---

# 35. Secret handling

Plans MUST NOT contain:
- real API keys;
- OAuth refresh tokens;
- publisher secrets;
- production credentials.

Use placeholders.

---

# 36. Observability of our own system

A feature that can fail operationally should expose enough internal state to diagnose it.

Examples:
- job status;
- structured error;
- duration;
- retry count;
- collector status.

Do not confuse our platform health with publisher health.

---

# 37. Failure taxonomy

Where relevant, use project error classes:

```text
SOURCE_ERROR
SITE_ERROR
CONNECTOR_ERROR
BROWSER_ERROR
PARSER_ERROR
STORAGE_ERROR
TIMEOUT
AUTH_ERROR
RATE_LIMIT
```

Do not build logic around arbitrary exception strings.

---

# 38. Retry behavior

ExecPlan must state:
- what retries;
- how many;
- which errors are retryable;
- how evidence is preserved.

Do not "retry away" a real publisher failure.

---

# 39. Rollback strategy

Every significant plan needs a rollback path.

Examples:
- revert commit;
- disable feature flag;
- rollback migration;
- restore previous connector definition;
- revert rule version.

Rollback must not delete existing evidence.

---

# 40. Feature flags

Use feature flags only when they reduce rollout risk.

Good candidates:
- new connector source;
- new event rule family;
- new incident ranking engine;
- new browser scenario.

Do not add flags around every tiny feature.

---

# 41. Unknowns and prototypes

If a major technical unknown exists, the plan should include an early proof-of-concept milestone.

Example:

```text
Can GAM REST Beta provide the exact cube on a pilot network?
```

Do not design the entire subsystem assuming yes.

Milestone:

```text
M0 capability probe
```

Then update plan based on result.

---

# 42. Discoveries / surprises

During implementation, record findings that alter assumptions.

Do not leave important discoveries only in chat/terminal history.

---

# 43. Decision log

ExecPlan contains task-local decisions.

Format:

```text
Date:
Decision:
Reason:
Alternatives:
Impact:
```

If decision is durable across the repository:
also add it to `DECISIONS.md`.

---

# 44. Progress log

Keep chronological updates.

Example:

```text
2026-09-02 10:15
M1 complete.
Navigation + checkpoint_run persistence passes tests.
Next: screenshot artifact persistence.
```

A reader should know exactly where the task stands.

---

# 45. Progress checklist

At top of active plan maintain:

```markdown
- [x] M0 repo inspection
- [x] M1 schema/migrations
- [ ] M2 runner
- [ ] M3 integration test
- [ ] M4 final validation
```

Update immediately as milestones change.

---

# 46. No hidden work

If Codex changes scope or implementation approach:
update ExecPlan first or at the same time.

Do not finish a completely different design while leaving the plan stale.

---

# 47. Commit discipline

For long plans:
commit at meaningful stable milestones when repository workflow permits.

Prefer scoped commits.

If commits are not part of the environment:
still keep logical changes scoped.

---

# 48. Diff discipline

Before each milestone is considered done:
review the diff.

Ask:
- unrelated files changed?
- scope expanded?
- duplicated abstractions?
- tests meaningful?
- accidental secrets?
- docs now stale?

Fix before proceeding.

---

# 49. Dependency rule

Do not add a dependency if standard library or existing dependency solves the task adequately.

For every new significant dependency:
state why needed and alternatives considered.

Avoid framework shopping.

---

# 50. Refactor rule

Do not refactor unrelated code "while here."

If a necessary refactor is substantial:
- state why;
- include it as milestone;
- validate behavior before/after.

If optional:
create follow-up, not scope creep.

---

# 51. Frontend rule

UI work must demonstrate user behavior.

A plan is not complete because React components compile.

It must show:
- route works;
- state works;
- error/loading states;
- relevant API integration;
- visual behavior.

Do not overbuild design systems before product flow exists.

---

# 52. API rule

For new endpoints:
plan must specify:
- request;
- response;
- auth/tenant behavior;
- errors;
- idempotency where relevant;
- pagination if needed;
- tests.

Avoid exposing database models directly.

---

# 53. Performance rule

Do not optimize speculative bottlenecks.

If performance is a goal:
define a measurable target.

Otherwise:
prefer clarity.

---

# 54. Scale assumptions

Use MVP reality.

Initial scale is small.

Do not design for:
- thousands of tenants;
- billions of auction events;
- global browser fleet;

unless a current plan explicitly targets that scale.

---

# 55. "Done" definition

An ExecPlan is COMPLETE only if:

1. target behavior exists;
2. acceptance criteria pass;
3. tests pass;
4. migrations work;
5. failure paths tested;
6. docs updated;
7. no known blocker is hidden;
8. plan reflects final implementation;
9. diff reviewed;
10. user/reviewer can reproduce the result.

---

# 56. Final retrospective

When complete, add:

```text
What shipped
What changed from original plan
Validation performed
Known limitations
Follow-ups
Lessons for AGENTS/DECISIONS
```

---

# 57. Superseding a plan

If architecture changes enough that the active plan is misleading:

1. mark old plan SUPERSEDED;
2. state why;
3. create new plan;
4. link both;
5. preserve old plan.

---

# 58. Abandoning a plan

If feature is canceled:

```text
status = ABANDONED
```

Record:
- reason;
- what code was created;
- whether reverted;
- reusable learning.

---

# 59. Example: B1 plan decomposition

A good B1 ExecPlan:

```text
M0 — inspect repo and bootstrap browser module
M1 — add checkpoint run + artifact persistence
M2 — navigate one URL in isolated Chromium context
M3 — capture viewport + full-page screenshots
M4 — capture DOM/scripts/network/errors
M5 — classify COMPLETE/SITE_ERROR/BROWSER_ERROR
M6 — integration fixture and smoke command
M7 — full validation + documentation
```

Not:

```text
M1 — implement BROWSER.md
```

---

# 60. Example: connector plan decomposition

For GA4:

```text
M0 — OAuth/provider capability probe
M1 — connection model + token storage interface
M2 — metadata discovery
M3 — GA4_TRAFFIC_HOURLY_V1
M4 — source_extract + metric persistence
M5 — preliminary/mature reconciliation
M6 — quota/backoff
M7 — connector health + tests
```

---

# 61. Example: Incident Engine plan decomposition

```text
M0 — fixture/harness
M1 — intake normalization
M2 — window/baseline selection
M3 — evidence pack
M4 — candidate generation
M5 — contradiction engine
M6 — deterministic ranking
M7 — LLM structured synthesis
M8 — eval suite
M9 — end-to-end incident demo
```

Do not start with:
"ask LLM what caused it."

---

# 62. ExecPlan skeleton

Use this skeleton for new plans.

```markdown
# EP-NNN — <Title>

**Status:** DRAFT
**Owner:** Codex / Engineering
**Created:** YYYY-MM-DD
**Updated:** YYYY-MM-DD
**Target milestone:** <B1/C2/I4/etc.>

## Progress

- [ ] M0 ...
- [ ] M1 ...
- [ ] M2 ...

## 1. Purpose and User Outcome

What becomes possible after this ships?

## 2. Scope

### In
- ...

### Out
- ...

## 3. Canonical References

Read:
- `AGENTS.md`
- `MVP.md`
- `<SUBSYSTEM>.md`
- `DATA_MODEL.md`
- `DECISIONS.md`

Relevant invariants:
- ...

## 4. Current State

What exists in the repository now?

## 5. Target Behavior

Concrete observable example.

## 6. Architecture / Data Flow

```text
...
```

## 7. Files and Modules Affected

Existing:
- ...

To create:
- ...

## 8. Milestones

### M0 — Repo inspection / prerequisite validation

Goal:
...

Acceptance:
- [ ] ...

Validation:
```bash
...
```

### M1 — ...

...

## 9. Final Acceptance Criteria

- [ ] ...
- [ ] ...

## 10. Final Validation

```bash
...
```

## 11. Test Cases

Happy path:
- ...

Failures:
- ...

Regression:
- ...

## 12. Data / Migration Impact

...

## 13. Security / Privacy Impact

...

## 14. Observability / Failure Handling

...

## 15. Rollback Strategy

...

## 16. Known Risks

...

## 17. Open Decisions

...

## 18. Decision Log

...

## 19. Discoveries / Surprises

...

## 20. Progress Log

...

## 21. Final Outcome / Retrospective

...
```

---

# 63. Required behavior when implementing an ExecPlan

Once a READY ExecPlan has been approved or Codex has been instructed to execute it:

1. read the complete plan;
2. read referenced canonical docs;
3. inspect current repository;
4. update Current State if needed;
5. implement next milestone;
6. validate;
7. repair failures;
8. update plan;
9. continue;
10. stop only for a true blocker or product decision.

Do not repeatedly ask:

> "Should I continue?"

between milestones if the plan already authorizes the next step.

---

# 64. When Codex should ask the user

Ask only when:

- product behavior is genuinely ambiguous;
- two options have materially different business consequences;
- security/privacy permission is required;
- destructive migration/action lacks authorization;
- canonical docs conflict;
- required credential/external access is missing;
- continuing would force a new product decision.

Do not ask for normal implementation choices.

---

# 65. Autonomous resolution rule

For low-risk implementation ambiguity:

Codex should:
- choose the simplest approach consistent with canonical docs;
- record the decision in the plan;
- continue.

Do not block the user.

---

# 66. User review points

Meaningful review points:

```text
architecture-changing decision
new external service/dependency
new data collection category
security boundary change
new production write capability
major UX flow change
new causal reasoning rule
MVP scope expansion
```

Routine code does not require founder approval line-by-line.

---

# 67. Plan-mode relationship

Native Codex Plan mode may be used to reason before editing.

`PLANS.md` remains the durable repository contract for longer work.

Plan mode is temporary interaction state.

ExecPlan is persistent project memory.

For long-running implementation:
the final agreed plan should be written to `plans/EP-...md`.

---

# 68. AGENTS.md relationship

When `AGENTS.md` is created, it should contain only a short pointer:

```markdown
## ExecPlans

For complex features, significant refactors, data-model changes, or work expected to span multiple implementation loops, create and follow an ExecPlan using `PLANS.md`.

Once an ExecPlan is READY and implementation begins, proceed milestone by milestone, validate after each milestone, update the plan continuously, and stop only for a genuine blocker or product decision.
```

Keep detailed planning rules here.

---

# 69. DECISIONS.md relationship

ExecPlan:
local implementation memory.

`DECISIONS.md`:
durable repository/product decisions.

If a plan decides something that affects future work:
record it in `DECISIONS.md`.

Do not put trivial coding choices there.

---

# 70. EVALS relationship

Any plan that changes Incident Engine reasoning must identify:
- existing evals affected;
- new evals required;
- expected regression risk.

A reasoning feature is not done if eval coverage remains stale.

---

# 71. MVP protection rule

Every ExecPlan must state:

> **Does this expand MVP scope?**

Allowed answers:

```text
NO
YES — approved in DECISIONS.md <ADR>
```

If YES without approval:
stop and request product decision.

---

# 72. Architecture protection rule

Every plan must state:

> **Does this introduce a new infrastructure category?**

Examples:
- queue system;
- database;
- cache;
- search engine;
- SaaS dependency;
- browser fleet;
- observability vendor.

If yes:
justify and record durable decision.

---

# 73. Evidence protection rule

Before deleting/compacting/migrating evidence:

ExecPlan MUST answer:

```text
Can old incident reports still be traced?
Can old checkpoints still be interpreted?
Are hashes/provenance preserved?
Is retention policy respected?
```

If not:
do not proceed.

---

# 74. Project-specific “never optimize away” list

Do not remove these to simplify implementation:

```text
checkpoint immutability
source provenance
event/metric separation
time uncertainty
source freshness
numerator/denominator where available
contradicting evidence
observability limitations
incident report versioning
tenant isolation
```

They are product semantics, not implementation overhead.

---

# 75. Project-specific “do not build early” list

Unless explicitly approved:

```text
microservices
Kafka
Kubernetes
Neo4j
ClickHouse
TimescaleDB
custom RUM SDK
session replay
residential proxy fleet
autonomous remediation
automatic GAM writes
arbitrary LLM API queries
visual AI root-cause engine
multi-browser matrix
full enterprise RBAC
```

---

# 76. Planned implementation sequence

The original v1.0 suggestion below was executed with reasonable variations: EP-001–EP-017 shipped
the repository foundation, Browser v1 (B1–B8), read-only connectors (C2–C4), cross-source metrics
(C5), incident drill-downs (C6), semantic browser events (E1) and event lifecycle (E2), and public
configuration observation with its own event catalog (E3).

```text
EP-001 — Repository bootstrap and local development environment
EP-002 — Browser checkpoint B1
EP-003 — Repeatable browser runs B2
EP-004 — Template-aware browser evidence B3
EP-005 — GPT lifecycle B4
EP-006 — GA4 connector C2
EP-007 — GSC connector C3
EP-008 — GAM connector C4
EP-009 — Event Engine E1/E2
```

## 76.1 Approved forward sequence (2026-08 architecture reconciliation, amended 2026-08-22)

The following sequence was approved by product/architecture decision and supersedes the
remaining v1.0 suggestions. Remaining P0 invariants are implemented inside the EP that needs
them; there is no separate architecture-precondition project.

Engine track:

```text
EP-018 — Observation run semantics & trigger provenance (ADR-130) — COMPLETE
   ↓
EP-019 — Investigation foundations (schema, LKG freeze, comparability, budget, holds)
   ↓
EP-020 — Incident intake & localization
   ↓
EP-021 — Evidence pack & typed relationships
   ↓
EP-022 — Inspect AI eval runtime integration (ADR-129)
   ↓
EP-023 — Hypotheses, contradictions & deterministic ranking
   ↓
Limited-pilot engine readiness
```

Parallel product/operations track:

```text
EP-019 ──→ EP-024 — Connector OAuth & managed secrets        [HARD PILOT BLOCKER]
EP-021 ──→ EP-025 — Home / Timeline read-only product surface [HARD PILOT BLOCKER]

EP-024 + EP-025 + EP-023
   ↓
EP-026 — Pilot reliability & operational readiness
   ↓
LIMITED PILOT
   ↓
LLM synthesis (incident narrative/report generation)
```

Boundary rules:

- **One coherent outcome per ExecPlan; one active ExecPlan at a time.** The parallel tracks above
  express dependency order only; execution still authorizes one plan at a time unless explicitly
  changed.
- **EP-024 Connector OAuth & managed secrets** makes GA4/GSC/GAM connections usable in a real
  pilot without env-only/local secret injection: OAuth consent/onboarding, token lifecycle and
  refresh handling, production-suitable managed secret resolution, revoked/expired consent
  handling, tenant ownership, secure credential storage boundary. Read-only scopes are preserved;
  capability probing is preserved. Provider/vendor selection and any new secret-provider
  architecture decision remain human gates (OPEN-003/OPEN-005 territory).
- **EP-025 Home / Timeline read-only surface** gives publishers/operators a usable view of the
  operational memory already collected: authenticated read-only shell, site selection, Timeline,
  event/incident detail, source/connector health distinct from publisher health, evidence links,
  Last Known Good references where available. Operational-memory-first, not generic-BI-first:
  no vanity dashboards, billing, write operations, enterprise RBAC, or broad admin tooling.
- **EP-026 Pilot reliability & operational readiness** includes retention/deletion enforcement,
  connector staleness detection, source health exposure, cost telemetry roll-up with hard caps and
  circuit breakers, cross-source DST/timezone hardening, AND a minimal self-observability baseline
  (queue depth/backlog visibility, stale lease/job detection visibility, run duration/failure-rate
  metrics, scheduler/worker health). Not a full observability platform — enough operational
  telemetry to run a real pilot safely.
- **Inspect AI stays one coherent ExecPlan (EP-022)** placed after the evidence pack so the
  deterministic engine has meaningful behavior to evaluate, and before hypothesis ranking so
  ranking is developed against an active eval runtime. ADR-129 is unchanged: "Inspect is the eval
  engine. EVALS.md remains the contract."
- **LLM synthesis** remains a later milestone AFTER deterministic hypothesis ranking exists, the
  Inspect release gate is active, and Limited Pilot feedback is available. It is not a pilot
  prerequisite. The Limited Pilot validates operational memory, incident workflow, evidence
  quality, deterministic hypotheses/ranking, Timeline usability, connector onboarding, and
  operational reliability.
- **Known deferred gap:** full DOM/GPT-slot → GAM ad unit → placement mapping provenance/lifecycle
  stays deferred until a concrete Incident Engine feature relies on persistent cross-system
  mapping; it then becomes mandatory. This gap must remain visible here.
- **Module-size refactor rule:** `backend/app/worker.py` and `backend/app/browser/persistence.py`
  are growing but are NOT scheduled for standalone cleanup. Split/refactor them only when future
  in-scope work touches them and the refactor measurably reduces implementation risk.
- **Catalog breadth rule:** do not schedule more collectors or more event-rule breadth merely
  because canonical docs describe them. The shortest path to demonstrated pilot value outranks
  catalog completeness.
- Detailed ExecPlans are created one at a time, when an EP becomes active. Do not pre-create
  detailed plans for later EPs.

This sequence may still change if reality justifies it; changes go through this file plus, where
durable, a new ADR.

---

# 77. First engineering success

The first meaningful product proof should remain small:

> **Given one public publisher URL, run a controlled Chromium observation and persist a reproducible black-box checkpoint with screenshots, DOM, network, JS errors, status and environment provenance.**

No AI is required for this milestone.

That is intentional.

---

# 78. Final planning principle

The plan is not useful because it is detailed.

It is useful because it creates a reliable execution loop:

```text
understand
→ implement a small slice
→ verify
→ fix
→ record
→ continue
```

A good ExecPlan prevents two failure modes:

```text
Codex builds something impressive but wrong
```

and:

```text
Codex builds the correct idea but cannot prove it works
```

The standard is:

# **Small milestones. Observable behavior. Validation at every step. No hidden scope expansion.**
