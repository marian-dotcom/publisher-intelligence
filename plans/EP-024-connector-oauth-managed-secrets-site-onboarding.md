# EP-024 — Connector OAuth, Managed Secrets & Site Onboarding

**Status:** M2 implementation COMPLETE; deployment/live validation PENDING
**Owner:** Codex / Engineering
**Created:** 2026-08-23
**Updated:** 2026-08-27
**Target milestone:** Connector OAuth, managed secrets & site onboarding (PLANS.md §76.1)
**MVP scope impact:** NO
**New infrastructure category:** HUMAN GATE — provider selection resolved (OCI Secret Management)

## Progress

- [x] M1a — Privacy-preserving monetization capability semantics (non-gated)
- [x] M1b — Documented non-deceptive User-Agent identity + publisher allowlisting runbook
      (vendor-neutral; no egress architecture chosen)
- [x] M2 — OCI SecretStore provider: implementation COMPLETE; deployment validation PENDING
      (see §M2 IMPLEMENTATION below)

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

## 4a. OPTION C REVISIT TRIGGER (operator-assisted secret-reference path)

Option C is a TEMPORARY Limited-Pilot exception, not an accepted production onboarding
architecture. It MUST be revisited at the earliest of:

1. onboarding of the second simultaneously active external publisher using OAuth-backed
   connectors;
2. any requirement for self-service publisher onboarding;
3. any requirement for automatic credential rotation / reauthorization without operator
   intervention;
4. 30 days after the first external Limited Pilot publisher is connected.

When any trigger fires:

- Option C may not silently continue as the default path;
- the team must explicitly choose either:
  a) proceed with the first-party OAuth flow backed by a production SecretStore implementation; or
  b) record a new human-approved decision extending the exception, with rationale, risks, and a
     new revisit trigger.

Invariant: no new external pilot publisher may be onboarded through Option C after a revisit
trigger has fired unless a new explicit human decision authorizes the extension.

## 5. Non-negotiables carried into M2+

No stealth/evasion/CAPTCHA solving/fingerprint spoofing/proxy rotation (ADR-020); read-only
scopes only; silent connector degradation forbidden; source health ≠ publisher health; stable
documented egress identity requirement stands regardless of vendor choice.

## 5a. APPROVED ARCHITECTURES (human decisions 2026-08-23)

1. OAuth: cloud-agnostic FIRST-PARTY Google OAuth orchestration behind the connector boundary;
   least-privilege read-only scopes declared per connector; no OAuth brokers; refresh/revocation
   behind the boundary; no provider leakage into domain logic.
2. Secrets: cloud-agnostic SecretStore abstraction — PostgreSQL stores references only, never
   tokens. Implemented: InMemorySecretStore (tests), EnvironmentSecretStore (local/dev,
   read-only resolver). Production provider remains a deployment-time human gate.
3. Option C authorized as Limited-Pilot fallback only (§4a triggers binding).
4. Egress: vendor-neutral stable-identity contract documented in the runbook; concrete network
   provider deferred to EP-026/deployment (human gate).
5. Actor contract: opaque tenant-bound `actor_subject_id` for audit provenance; OPEN-003 IdP
   choice deferred to the authenticated product surface.

## 6. Validation (executed for this PR)

- ruff format/check, mypy, unit suite (280 incl. 2 new capability tests), clean-DB upgrade to head
  0022 + targeted downgrade -1, GA4 connector regression subset, secret scan, whitespace: PASS.
- Full integration suite + CI: executed on the Draft PR (see PR #27 checks).

ruff/mypy/unit/integration suites green locally and in CI; migration 0022 upgrade/downgrade cycle
validated in CI PostgreSQL job.

### 2026-08-23 — Option C recorded as temporary exception with hard revisit triggers

**Decision:** The operator-assisted secret-reference path (Option C) is authorized only as a
temporary Limited-Pilot exception with the revisit triggers listed in §4a (second simultaneous
OAuth publisher, self-service onboarding need, automatic rotation/reauthorization need, or
30 days after first external pilot connection — whichever comes first).

**Reason:** Balances pilot speed against credential-handling maturity per ADR-091; explicit
triggers prevent silent normalization of operator-assisted credentials into the default path.

**Alternatives:** Unconditional Option C — rejected: would defer OAuth indefinitely without a
forcing function; immediate full OAuth build — deferred by human gate pending provider decisions.

**Impact:** EP-020+ workflows may consume secret references; onboarding of NEW external
publishers via Option C after a trigger fires requires a new explicit human decision.

---

## M2 IMPLEMENTATION (2026-08-27)

### Provider decision

OCI Secret Management selected as the concrete SecretStore provider for staging/production.
Instance Principal authentication: no API keys on disk.

### What was implemented

1. **`backend/app/secrets/oci.py`** — OCI SecretStore provider:
   - `OciSecretStore`: read-only SecretStore implementation using OCI Vault REST API
     via official OCI SDK (`oci.auth.signers.InstancePrincipalsSecurityTokenSigner`,
     `oci.secrets.SecretsClient`). Write methods (store/replace/delete) raise
     `InvestigationStateError` — consistent with `EnvironmentSecretStore` pattern.
   - `OciAccessTokenResolver`: connector-level credential resolution.
     Reference format: `oci:<secret-ocid>`. Fetches credential bundle from OCI Vault,
     validates structure, exchanges Google refresh token for short-lived access token.
   - `parse_credential_bundle()`: validates Google credential bundle JSON structure.
   - `_refresh_access_token()`: Google token refresh via standard endpoint.
   - Error mapping: OCI ServiceError → SecretResolutionError codes.

2. **`backend/app/config/settings.py`** — secret backend configuration:
   - `secret_backend`: `memory | environment | oci` (default: `environment`)
   - `oci_region`: OCI region for Vault API (default: `eu-frankfurt-1`)
   - Fail-closed validator: staging/production require `secret_backend=oci`

3. **`backend/app/worker.py`** — runtime wiring:
   - `_build_token_resolver(settings)`: factory selects resolver based on `secret_backend`
   - Connectors share a single resolver instance per worker process

4. **`backend/tests/unit/test_oci_secret_store.py`** — 59 unit tests covering:
   - OCID reference format validation
   - OciSecretStore read-only enforcement
   - OciSecretStore.resolve success/failure paths (mocked OCI SDK)
   - Credential bundle parsing (valid/malformed/missing fields)
   - Google token refresh (success, invalid_grant, insufficient_scope, server_error)
   - OciAccessTokenResolver end-to-end (mocked OCI + Google)
   - Settings fail-closed for staging/production
   - Worker factory function
   - No credential material in errors/logs

5. **`backend/pyproject.toml`** — OCI SDK dependency added

### Secret reference format

```
oci:ocid1.secret.oc1.eu-frankfurt-1.xxxxx...
```

PostgreSQL stores only this opaque reference. No credential material enters the database.

### Credential flow (Option C)

```
data_connection.secret_reference: "oci:<secret-ocid>"
        ↓
OciAccessTokenResolver.resolve()
        ↓
OciSecretStore.resolve() → OCI Vault REST API (Instance Principal)
        ↓
Google credential bundle (client_id, client_secret, refresh_token, token_uri)
        ↓
Google token refresh endpoint → short-lived access_token
        ↓
AccessCredential(access_token=...)
```

Refreshed access tokens exist only in process memory. Never persisted.

### Validation

- ruff check: PASS
- mypy: PASS (no errors)
- unit tests: 423 passed (59 new OCI tests + 364 existing)

### M2 status vs Gate N status

- **M2 implementation:** COMPLETE
- **Gate N deployment validation:** PENDING (requires staging deployment + live OCI verification)

### What was NOT done

- No OCI infrastructure created (Vault/key/secret/dynamic group/policy) — requires OCI Console
- No staging deployment — existing release 52b5201 must remain running
- No real publisher credential handling
- No Limited Pilot authorization
