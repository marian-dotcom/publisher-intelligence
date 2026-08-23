# Publisher Allowlisting Runbook (Monitoring Identity)

Publisher Intelligence observes authorized publisher pages with a documented, non-deceptive
identity. Publishers can allowlist this identity to prevent challenge/WAF false positives.

## Monitoring User-Agent

All synthetic browser and public-config fetches identify themselves:

- browser checkpoints use Chromium with a stable locale/timezone profile (no fingerprint
  spoofing);
- public-config fetches send `User-Agent: PublisherIntelligencePublicConfig/1.0`.

## Stable egress identity (requirement)

Production deployments MUST publish a stable, documented set of egress IP addresses/ranges used
exclusively for monitoring traffic so publishers can allowlist them. The specific mechanism
(cloud NAT gateway, dedicated proxy range) is a deployment/human decision — this runbook only
requires that the identity exists, is documented per environment, and changes rarely with notice.

## Onboarding compatibility check

During onboarding, run the bounded EP-018 DIAGNOSTIC checkpoint against representative URLs.
Outcomes map to source health: HEALTHY / DEGRADED / BLOCKED / ACTION_REQUIRED. DOM variance alone
never proves blocking.

## If challenges appear

Do not evade. Contact the publisher with the documented UA + egress ranges and request
allowlisting; re-run diagnostics after remediation.

## Invariants

- No CAPTCHA solving, fingerprint spoofing, residential proxy rotation, or anti-bot bypass
  (ADR-020).
- Observation failure is not evidence of publisher failure.
