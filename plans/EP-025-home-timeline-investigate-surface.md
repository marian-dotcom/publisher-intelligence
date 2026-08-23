# EP-025 — Home / Timeline & Minimal Investigate Product Surface

**Status:** BLOCKED_AT_HUMAN_GATE (authentication architecture)
**Owner:** Codex / Engineering
**Created:** 2026-08-23

## Scope (approved)

Operational-memory-first product surface: Home, Timeline, Incidents, Investigations, evidence
visibility (machine_observed vs human_reported; observed_at vs occurred_at), LKG visibility,
source health distinct from publisher/site health, minimal Investigate intake (what happened /
when started / site+scope) on EP-020 intake, leading-hypothesis status with supporting/
contradicting/missing sections and ranking rationale (EP-023), privacy-preserving monetization
rendering (% vs baseline / indexed health; absolute values only when capability=ABSOLUTE).
No billing/chat/ticketing/collaboration/RBAC/LLM/EP-026 scope.

## HUMAN GATE — authentication/IdP/session architecture

An authenticated product shell cannot ship without selecting: session model (server-side cookie
vs token), identity store, and whether an external IdP is used.

Alternatives:
A) Server-side session cookie auth with operator accounts stored in PostgreSQL (opaque
   actor_subject_id already contract-ready); no external IdP.
B) External IdP/broker (Auth0/Clerk/WorkOS/Cognito/Firebase) — fastest UX, external dependency +
   data-processing implications.
C) Defer login entirely for single-operator Limited Pilot: network-level protection +
   EP-024 Option-C-style operator assumption, clearly documented as temporary with revisit
   triggers mirroring Option C.

Implications: A is self-contained and matches the opaque actor contract; B adds vendor risk/cost;
C minimizes work but weakens the audit story and must not silently persist past pilot.

Recommendation: A (self-contained server-side sessions), with C acceptable if pilot timing
dominates; both preserve the existing actor_subject_id boundary.

## What EP-025 can proceed with WITHOUT the decision

All backend read-only query endpoints (Home status, Timeline, incident/investigation detail,
evidence pack view, source health vs publisher health, hypothesis display incl.
supporting/contradicting/missing + rationale) and the frontend component/route skeleton wired to
those endpoints behind a stubbed actor header — leaving only the login/session layer gated.

## Non-goals
Billing, chat, ticketing, collaboration, enterprise RBAC, LLM synthesis, causal-certainty
wording beyond deterministic statuses.
