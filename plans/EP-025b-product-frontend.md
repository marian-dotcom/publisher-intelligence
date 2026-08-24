# EP-025b — Product Frontend

**Status:** READY
**Owner:** Codex / Engineering
**Created:** 2026-08-24
**Target milestone:** EP-025b — authenticated product frontend consuming EP-025a contracts (PLANS.md §76.1)
**MVP scope impact:** NO — implements the approved EP-025 product surface on the merged EP-025a backend
**New infrastructure category:** NO

## Progress

- [x] M0 — Frontend contract & design reconciliation (this milestone):
      TypeScript API contracts derived from actual backend responses
      (`frontend/lib/api-types.ts`); route map fixed; data-fetching decision =
      native typed fetch wrapper (no TanStack Query); UI primitives decision =
      tiny local components over plain CSS (no Tailwind/shadcn adoption — see
      §8 rationale); semantic component inventory defined; auth client state
      machine defined; test strategy defined.
- [x] M1 — Login/session + authenticated shell + typed fetch wrapper + CSRF handling
      COMPLETE: auth state machine checking→authenticated|unauthenticated via
      GET /auth/session on mount (async apply, no sync setState-in-effect);
      typed fetch wrapper lib/api.ts (same-origin credentials, ApiError kinds
      unauthorized/forbidden/not_found/server/network, X-CSRF-Token injected
      from server-set pi_csrf double-submit cookie on writes); login page
      (email/password/tenant_id → generic failure only); protected shell
      (Home/Timeline/Incidents nav + Investigate CTA placeholder disabled +
      functional logout) with no-protected-flash guard and 401 redirect;
      route map /(protected) group; local primitives (Button/Input/Field/Card/
      LoadingState/ErrorState/EmptyState); design tokens in styles.css.
      Contract note: logout does not require CSRF header per merged backend
      (frontend sends it when present — harmless/future-proof); CSRF after
      session restore is available via the server-set pi_csrf cookie, so no
      backend contract gap exists. Tests: 12 passed across api/auth/shell/
      login suites. Validation: lint clean; typecheck clean; 12 tests passed;
      build compiled. Dependency footprint remains ZERO new runtime deps.
- [ ] M2 — Home/status + source health + site selection
- [ ] M3 — Timeline
- [ ] M4 — Incident list/detail + hypotheses/evidence/LKG/monetization + evidence pack view
- [ ] M5 — Minimal Investigate form (the only write)
- [ ] M6 — Responsive/a11y/error-empty-state contract validation sweep
- [ ] M7 — Adversarial review / release-readiness / CI verification

## 1. Purpose and User Outcome

Operators get a usable, authenticated, predominantly read-only view of the
operational memory collected by the engine: what changed (Home/Timeline), what
might explain it (ranked hypotheses with supporting/contradicting/missing
evidence), and what the last known good baseline was — plus exactly one write:
minimal Investigate intake.

## 2. Scope and Non-Goals

In: login/session shell; Home/status + source health; site selection; Timeline;
incident list/detail; hypotheses + evidence relationships; LKG references;
evidence pack view; monetization capability-aware display; Investigate form;
loading/empty/error states; responsive + accessibility pass.

Out (non-goals): vanity dashboards/charts, ticketing/chat/collaboration,
billing, enterprise RBAC, admin tooling, analytics/tracking, new backend
endpoints, auth-model changes, LLM anything.

## 3. Canonical References

- `PLANS.md` §76.1 (EP-025 product-surface description)
- `PRODUCT.md` §30/§31 (Investigate workflow), §18 (LKG)
- `INCIDENT.md` §88–90 (LKG semantics), ADR-005/047/049/060/061
- Merged EP-025a routes: `backend/app/api/{product,memory,investigations}.py`,
  `backend/app/auth/routes.py`
- `frontend/lib/api-types.ts` (M0 contract inventory)

## 4. Route Map

```text
/login              unauthenticated only
/                   Home: selected-site banner, source-health strip, recent activity, Investigate CTA
/timeline           full timeline (machine_observed + human_reported)
/incidents          incident list
/incidents/[id]     detail: symptom, segments, ranked hypotheses + evidence, LKG refs, monetization
/evidence/[id]      frozen evidence-pack view
```

Investigate is a **modal/sheet from the authenticated shell**, not a dedicated
route: it is a short three-field action ("what / when / which site") whose
success navigates to the created incident detail. A separate route would imply
an investigation-management surface that is out of scope.

## 5. Data-Fetching Decision (M0)

**Decision: native typed fetch wrapper. No TanStack Query in EP-025b.**

Rationale for this product shape: cookie-session auth with server-side CSRF;
~8 low-frequency read surfaces; one mutation; no polling/realtime requirement;
Next.js App Router server components already cover initial loads. TanStack
Query's cache-invalidation machinery adds runtime weight (~13kB gz) and test
complexity without materially improving correctness here. Revisit only if a
future EP adds polling/realtime or heavy client-side filtering.

The wrapper (`frontend/lib/api.ts`, built in M1) centralizes: JSON fetch,
credentials inclusion, X-CSRF-Token injection from the session bootstrap,
401 → redirect-to-login mapping, 403 → explicit error state, typed responses.

## 6. UI Primitives Decision (M0)

**Decision: tiny local components over plain CSS. No Tailwind. No shadcn/ui
adoption in EP-025b.**

shadcn assumes Tailwind; adopting it means a design-system/tooling migration
(Tailwind config, PostCSS, class-utility conventions) that is a HUMAN GATE and
disproportionate to our needs: the required primitive set is small (Button,
Card, Badge, Input, Select, Dialog/Sheet, Field) with domain-specific rendering
that shadcn does not provide anyway. Radix dialog/select behavior (focus trap,
escape, aria) can be met initially with native `<dialog>` and native `<select>`.
Revisit shadcn/Radix if a future surface genuinely needs complex overlay
semantics.

Required local primitives (M1+): Button, Card, Badge, Input, Select, Modal
(native dialog), Field/label. Estimated ~200 lines total CSS + components.

## 7. Semantic Component Inventory (contractual)

| Component | Domain values | Visual meaning | Forbidden inference |
|---|---|---|---|
| SiteCondition | site status string | publisher/site health card | must never derive from SourceHealthBadge |
| SourceHealthBadge | HEALTHY/DEGRADED/UNAVAILABLE/ACTION_REQUIRED/BLOCKED/UNKNOWN | per-source observation health; UNKNOWN = "no evidence" | never mutates SiteCondition; DEGRADED ≠ UNKNOWN |
| ProvenanceBadge | machine_observed / human_reported | evidence origin chip | never merges classes |
| TemporalUncertainty | exact ts / window start+end / unknown | "at X" vs "between X–Y" vs "time unknown" | never renders window as exact; unknown stays visible |
| SeverityBadge | LOW/MEDIUM/HIGH/CRITICAL/null | severity ramp | null severity ≠ LOW |
| HypothesisRank | LEADING/CONTENDER/WEAKENED/UNRESOLVED + rank | ordered list, LEADING outlined as current ranking | LEADING must never be worded/displayed as "cause" |
| EvidenceRelation | SUPPORTS/CONTRADICTS/CONTEXT + source_kind | supports=green, contradicts=red, context=neutral; OBSERVATION_GAP renders "not observed/unavailable" | OBSERVATION_GAP must never render as CONTRADICTS |
| LastKnownGoodReference | canonical ref fields | "frozen baseline at {selected_at}" card | never presented as current truth |
| MonetizationCapability | ABSOLUTE/RELATIVE_ONLY/UNKNOWN | capability chip; RELATIVE_ONLY copy says relative-only | RELATIVE_ONLY never shows/implies absolute revenue; UNKNOWN fails closed |
| EmptyState / ErrorState / LoadingState | — | consistent patterns per screen | error states must not fabricate data |

## 8. Design Tokens (M1)

Plain-CSS custom properties in `styles.css`: spacing scale (4px base),
type ramp, radius/border tokens, surface tokens, semantic status tokens
(healthy/degraded/unavailable/action-required/blocked/unknown), provenance
tokens (machine/human), severity ramp, evidence-relation tokens
(supports/contradicts/context/gap), focus-visible/disabled/error states.
No Tailwind unless separately approved (HUMAN GATE).

## 9. Auth Client Contract (M1)

State machine: `unknown → checking(GET /auth/session) → authenticated | unauthenticated`;
login POST success → store CSRF token in memory only → authenticated;
401 anywhere → transition to unauthenticated → redirect `/login`;
403 → inline error (CSRF failure), no redirect loop.
CSRF token lives in memory only (never localStorage); sent as `X-CSRF-Token`
on POST /investigations and POST /auth/logout. HttpOnly session cookie is the
only credential carrier. Logout calls backend then clears memory state.

## 10. Test Strategy (M1–M7)

- Pure semantic component tests (Vitest + Testing Library): each §7 component
  against its forbidden-inference rules
- API wrapper tests: 401/403/404 mapping, CSRF header injection (mock fetch)
- Screen-level tests: Home, Timeline, Incident detail, Investigate form
- CI: pnpm lint/typecheck/test/build with frozen lockfile (existing job)
- No Playwright/e2e tooling in this EP (HUMAN GATE to add later)

## 11. Human Gates

Tailwind adoption · shadcn/Radix runtime dependencies · TanStack Query · form
library · icon library · routing architecture change · any backend/auth/API
change · analytics/tracking · external SaaS/provider.

## 12. Deferred Debt (EP-026)

Session cookie `secure=False` (`auth/routes.py::_set_session_cookies`) —
deployment hardening for pre-Limited-Pilot; untouched in EP-025b.

## 13. Validation Commands

```bash
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend test
pnpm --dir frontend build
```

All four must pass at every milestone gate.
