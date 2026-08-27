# EP-024 — Connector OAuth, Managed Secrets & Site Onboarding

**Status:** COMPLETE (Gate N PASS)
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
- [x] M2 — OCI SecretStore provider: implementation COMPLETE; Gate N deployment/live validation
      PASS (see §M2 IMPLEMENTATION below)

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

## 4. Provider decision — HUMAN GATE (RESOLVED 2026-08-23; Gate N PASS 2026-08-27)

**Status: RESOLVED.** The provider/OAuth-secret-storage decision below was made 2026-08-23 and
the concrete OCI Secret Store implementation was live-validated on staging (Gate N) on 2026-08-27.
This section is retained as historical record of the options and resolution.

The decision resolved: OAuth provider architecture + managed-secret storage + production egress
architecture for GA4/GSC/GAM onboarding. Two cloud-agnostic decisions were made (see §5a), and the
concrete secret-storage provider was selected as OCI Secret Management (ADR-132, implemented in the
M2 slice, Gate N PASS on staging).

Alternatives considered:

A. Google-idiomatic OAuth web flow + cloud-provider managed secrets (e.g., provider-native
   secret manager) with NAT-gateway style stable egress.
B. Cloud-agnostic approach: OAuth web flow + external secret manager service + vendor-neutral
   "documented stable egress IP range" commitment (deployment-specific).
C. Defer OAuth entirely; pilot uses operator-supplied refresh tokens injected via a managed
   secret reference only (no UI consent flow) — fastest to pilot, weakest UX.

Implications (credential-blast-radius, auditability, cost, lock-in, and deployment complexity)
differ per option. All preserve read-only scopes and ADR-091's boundary (DB stores references
only).

Resolution: egress architecture and concrete network provider remain a deployment-time human
gate (§5a item 4); OAuth stays cloud-agnostic first-party (§5a item 1); the concrete managed-secret
provider is OCI Secret Management (ADR-132, Gate N PASS on staging).

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
   read-only resolver). OCI Secret Management is the selected concrete staging/production
   SecretStore implementation (ADR-132; `OciSecretStore`, Instance Principal auth, read-only,
   strict Base64 decode, 3-field credential bundle). Staging live validation / Gate N is PASS.
   Production rollout has NOT occurred.
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
   - Strict Base64 decode: validates `content_type == "BASE64"`, non-empty content,
     strict Base64 validation, UTF-8 decode. Malformed content → `SECRET_BUNDLE_INVALID`.
   - `OciAccessTokenResolver`: connector-level credential resolution.
     Reference format: `oci:<vaultsecret-ocid>`. Fetches credential bundle from OCI Vault,
     validates structure, exchanges Google refresh token for short-lived access token.
   - `parse_credential_bundle()`: validates 3-field Google credential bundle JSON
     (client_id, client_secret, refresh_token). Unknown fields ignored.
   - `_refresh_access_token()`: Google token refresh via hardcoded canonical endpoint
     (`https://oauth2.googleapis.com/token`). Cannot be overridden via bundle.
   - Error mapping: OCI ServiceError → SecretResolutionError codes.

2. **`backend/app/config/settings.py`** — secret backend configuration:
   - `secret_backend`: `memory | environment | oci` (default: `environment`)
   - `oci_region`: OCI region for Vault API (default: `eu-frankfurt-1`)
   - Fail-closed validator: staging/production require `secret_backend=oci`

3. **`backend/app/worker.py`** — runtime wiring:
   - `_build_token_resolver(settings)`: factory selects resolver based on `secret_backend`
   - Connectors share a single resolver instance per worker process

4. **`backend/tests/unit/test_oci_secret_store.py`** — 70 unit tests covering:
   - OCID reference format validation (vaultsecret prefix, rejection of ocid1.secret)
   - OciSecretStore read-only enforcement
   - OciSecretStore.resolve: strict Base64 decode tests (valid content, missing bundle,
     unsupported content type, missing/empty/non-string content, malformed Base64,
     invalid UTF-8, unicode JSON)
   - OciServiceError paths (401/403/404/500/secret disabled)
   - Credential bundle parsing (valid/malformed/missing fields, extra fields ignored,
     token_uri extra field ignored)
   - Google token refresh (success, invalid_grant, insufficient_scope, server_error)
   - Adversarial token_uri endpoint pinning (proves attacker URI is never contacted)
   - OciAccessTokenResolver end-to-end (mocked OCI + Google)
   - Settings fail-closed for staging/production
   - Worker factory function
   - No credential material in errors/logs

5. **`backend/pyproject.toml`** — OCI SDK dependency added

### Secret reference format

```
oci:ocid1.vaultsecret.oc1.eu-frankfurt-1.xxxxx...
```

PostgreSQL stores only this opaque reference. No credential material enters the database.

### Credential bundle schema

3-field JSON stored in OCI Vault:

```json
{
  "client_id": "...",
  "client_secret": "...",
  "refresh_token": "..."
}
```

The `token_uri` field is neither required nor recognized. The Google token refresh
endpoint is hardcoded (`https://oauth2.googleapis.com/token`).

OCI Vault stores secret content as Base64-encoded; retrieval decodes at access time
with strict validation (content type must be `BASE64`, content must be valid Base64
and valid UTF-8).

### Credential flow (Option C)

```
data_connection.secret_reference: "oci:<vaultsecret-ocid>"
        ↓
OciAccessTokenResolver.resolve()
        ↓
OciSecretStore.resolve() → OCI Vault REST API (Instance Principal)
        ↓
Base64-decode → UTF-8 decode → credential bundle (client_id, client_secret, refresh_token)
        ↓
Google token refresh endpoint → short-lived access_token
        ↓
AccessCredential(access_token=...)
```

Refreshed access tokens exist only in process memory. Never persisted.

### Validation

- ruff check: PASS
- ruff format: PASS
- mypy: PASS (no errors)
- unit tests: 434 passed (70 OCI tests including Base64 decode, adversarial token_uri, OCID rejection + 364 existing)
- secret scan: PASS
- uv lock --locked: PASS

### M2 status vs Gate N status

- **M2 implementation:** COMPLETE
- **Gate N deployment validation:** PASS (2026-08-27)

### Gate status

- **GATE N:** PASS (OCI SecretStore live staging validation, 2026-08-27)
- **GATE O:** NOT STARTED
- **GATE P:** HUMAN GATE
- **LIMITED PILOT:** NOT AUTHORIZED

## Gate N — Live validation evidence (2026-08-27)

### Deployed release

- OCI staging deployment: commit `810db9ee5c679f9d15c3eebb54767a3d758d94a2` (EP-024 merge to main)
- Previous staging release: `52b5201` (replaced by EP-024 merge)

### OCI staging infrastructure

- Vault: standard vault created in eu-frankfurt-1
- Key: AES-256 software key created
- Secret: synthetic 3-field credential bundle created (client_id, client_secret, refresh_token)
- Dynamic Group: exact-instance membership rule for the staging compute instance
- IAM Policy: least-privilege policy granting Dynamic Group SECRET_BUNDLE_READ only

### Host Instance Principal proof

- Instance Principal from host: PASS
- SECRET_BUNDLE_READ: PASS
- CONTENT_TYPE: BASE64 (strict Base64 decode validated)
- CONTENT_PRESENT: True

### Container-level OciSecretStore proof

- INSTANCE_PRINCIPAL_FROM_CONTAINER: PASS
- OCI_SECRETSTORE_RESOLVE: PASS
- BASE64_UTF8_DECODE: PASS
- CREDENTIAL_BUNDLE_JSON_PARSE: PASS
- Fields exactly client_id, client_secret, refresh_token; no Google token request made

### Runtime config

- SECRET_BACKEND=oci for api, scheduler, worker, browser-worker
- OCI_REGION=eu-frankfurt-1
- BROWSER_ALLOW_PRIVATE_NETWORKS=false

### Regression gates

- HTTPS/auth regression: PASS (login 200, cookies Secure/HttpOnly/SameSite correct, CSRF logout 200, post-logout 401)
- Rate limiting: PASS (6th bad login → 429, spoofed IPs blocked)
- Network/egress: egress 92.5.61.217, raw ports bound to 127.0.0.1 only, externally CLOSED
- Operations endpoint: PASS
- Credential/log leak: NOT PRESENT, PASS

### What was NOT done (still out of scope)

- No real publisher credential handling
- No Limited Pilot authorization
- No full self-service OAuth onboarding UI
