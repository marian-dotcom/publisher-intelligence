# EP-024 — Connector OAuth, Managed Secrets & Site Onboarding

**Status:** BLOCKED_AT_HUMAN_GATE (non-gated slice implemented)
**Owner:** Codex / Engineering
**Created:** 2026-08-23
**Updated:** 2026-08-23
**Target milestone:** Connector OAuth, managed secrets & site onboarding (PLANS.md §76.1)
**MVP scope impact:** NO
**New infrastructure category:** HUMAN GATE — provider selection required

## Progress

- [x] M1a — Privacy-preserving monetization capability semantics (non-gated)
- [x] M1b — Documented non-deceptive User-Agent identity + publisher allowlisting runbook
      (vendor-neutral; no egress architecture chosen)
- [ ] M2 — HUMAN GATE: OAuth provider architecture / managed secret storage /
      production egress architecture (see §HUMAN GATE below)

## 1. Purpose and User Outcome

GA4/GSC/GAM connections become usable in a real pilot without env-only secret injection,
with least-privilege read-only scopes, tenant ownership, revoked/expired/degraded consent
handling, capability probing preserved, and explicit monetization-capability semantics:
absolute revenue is never required for monetization intelligence.

## 2. PRIVACY-PRESERVING MONETIZATION METRICS (approved product requirement)

Two connection capability modes:

- `ABSOLUTE` — absolute monetization data authorized;
- `RELATIVE_ONLY` — privacy-preserving/relative data only: percentage deltas, normalized/indexed
  metrics, fill rate, relative eCPM/yield indicators, monetization-health indices,
  recovery/degradation vs baseline.

Absence of absolute revenue MUST NOT be classified as source degradation when sufficient
relative/indexed metrics are available.

## 3. Implemented in this PR (non-human-gated slice)

- migration 0022: `data_connections.monetization_capability` column
  (CHECK `ABSOLUTE|RELATIVE_ONLY|UNKNOWN`, default UNKNOWN) + model mirror + contracts validation;
- documented monitoring identity constants: non-deceptive User-Agent and stable-egress
  REQUIREMENT text (vendor-neutral) in the publisher allowlisting runbook
  (`docs/runbooks/publisher-allowlisting.md`);
- tests: DB constraint coverage via integration suite extension point + contracts unit test.

## 4. HUMAN GATE — decision required before M2+

Decision required: OAuth provider architecture + managed-secret storage + production egress
architecture for GA4/GSC/GAM onboarding.

Alternatives:

A. Google-idiomatic OAuth web flow + cloud-provider managed secrets (e.g., provider-native
   secret manager) with NAT-gateway style stable egress.
B. Cloud-agnostic approach: OAuth web flow + external secret manager service + vendor-neutral
   "documented stable egress IP range" commitment (deployment-specific).
C. Defer OAuth entirely; pilot uses operator-supplied refresh tokens injected via a managed
   secret reference only (no UI consent flow) — fastest to pilot, weakest UX.

Implications: credential-blast-radius, auditability, cost, lock-in, and deployment complexity
differ per option. All preserve read-only scopes and ADR-091's boundary (DB stores references
only).

Recommendation: Option B (cloud-agnostic contract now; concrete provider chosen at deployment),
with Option C acceptable as a Limited-Pilot stopgap if no cloud account exists yet.

What can proceed without the decision: everything already merged in this PR (capability modes,
identity documentation/runbook); token-lifecycle implementation itself cannot proceed.

## 5. Non-negotiables carried into M2+

No stealth/evasion/CAPTCHA solving/fingerprint spoofing/proxy rotation (ADR-020); read-only
scopes only; silent connector degradation forbidden; source health ≠ publisher health; stable
documented egress identity requirement stands regardless of vendor choice.

## 6. Validation (executed for this PR)

- ruff format/check, mypy, unit suite (280 incl. 2 new capability tests), clean-DB upgrade to head
  0022 + targeted downgrade -1, GA4 connector regression subset, secret scan, whitespace: PASS.
- Full integration suite + CI: executed on the Draft PR (see PR #27 checks).

ruff/mypy/unit/integration suites green locally and in CI; migration 0022 upgrade/downgrade cycle
validated in CI PostgreSQL job.
