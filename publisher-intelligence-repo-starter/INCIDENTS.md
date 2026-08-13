# INCIDENTS.md
## Public Publisher Incident Corpus — v0.5

**Records:** 343  
**Distinct DOMAIN mappings:** 83

This is the empirical companion to `DOMAIN.md`. It deliberately preserves confirmed incidents, technical bugs, external events, publisher field cases, counterexamples, unresolved investigations and research evidence.

## Evidence tiers
- **A** — official status/postmortem, primary technical issue/research, official case study.
- **B** — strong field case with meaningful chronology/evidence/resolution.
- **C** — useful but incomplete/unverified RCA.
- **D** — anecdotal; discovery only.

## Corpus composition
- Families: `{'gam_adserving': 146, 'video': 18, 'consent_cmp': 23, 'search_discover': 80, 'prebid_header_bidding': 24, 'programmatic_market': 4, 'reporting_discrepancy': 5, 'policy_compliance': 9, 'analytics_measurement': 8, 'browser_performance': 12, 'external_infrastructure': 14}`
- Evidence tiers: `{'A': 248, 'C': 47, 'B': 46, 'D': 2}`
- Root-cause status: `{'unresolved': 182, 'confirmed': 77, 'not_applicable': 47, 'probable': 37}`
- Record types: `{'external_platform_incident': 139, 'platform_incident_case': 14, 'external_search_event': 40, 'technical_bug': 53, 'publisher_field_case': 55, 'analytics_measurement_case': 8, 'publisher_performance_case': 12, 'research_evidence': 4, 'external_infrastructure_incident': 13, 'adtech_vendor_incident': 2, 'cmp_vendor_incident': 3}`

## Central rule
External event != publisher-specific root cause. Attribution requires time + affected product/source + segment match + plausible mechanism + intermediate evidence + contradiction check.

## Why unresolved cases stay
The Incident Engine must learn to say `unresolved`. Wrong hypotheses and failed attribution attempts are part of the knowledge base.

## Coverage by family
- **gam_adserving:** 146
- **search_discover:** 80
- **prebid_header_bidding:** 24
- **consent_cmp:** 23
- **video:** 18
- **external_infrastructure:** 14
- **browser_performance:** 12
- **policy_compliance:** 9
- **analytics_measurement:** 8
- **reporting_discrepancy:** 5
- **programmatic_market:** 4

## Highest-coverage DOMAIN mappings
- `google_external_event` — 192 records; 68 high-evidence; 26 confirmed RCA; **well_supported**
- `F-GAM-005` — 122 records; 3 high-evidence; 2 confirmed RCA; **well_supported**
- `reporting_freshness_or_platform_incident` — 117 records; 0 high-evidence; 0 confirmed RCA; **supported**
- `F-SEO-007` — 71 records; 57 high-evidence; 16 confirmed RCA; **well_supported**
- `external_dependency_failure` — 14 records; 13 high-evidence; 13 confirmed RCA; **well_supported**
- `F-VID-002` — 12 records; 11 high-evidence; 6 confirmed RCA; **well_supported**
- `F-CMP-003` — 10 records; 10 high-evidence; 5 confirmed RCA; **well_supported**
- `cwv_regression` — 9 records; 8 high-evidence; 2 confirmed RCA; **well_supported**
- `observability_error` — 9 records; 6 high-evidence; 4 confirmed RCA; **well_supported**
- `reporting_discrepancy` — 9 records; 3 high-evidence; 1 confirmed RCA; **well_supported**
- `F-CMP-004` — 8 records; 8 high-evidence; 4 confirmed RCA; **well_supported**
- `F-CMP-005` — 8 records; 7 high-evidence; 4 confirmed RCA; **well_supported**
- `F-HB-004` — 8 records; 7 high-evidence; 3 confirmed RCA; **well_supported**
- `ads_txt_integrity` — 8 records; 0 high-evidence; 0 confirmed RCA; **supported**
- `site_availability` — 8 records; 8 high-evidence; 8 confirmed RCA; **well_supported**
- `F-CMP-002` — 7 records; 6 high-evidence; 6 confirmed RCA; **well_supported**
- `F-HB-006` — 7 records; 7 high-evidence; 6 confirmed RCA; **well_supported**
- `F-HB-007` — 7 records; 7 high-evidence; 4 confirmed RCA; **well_supported**
- `F-VID-001` — 7 records; 6 high-evidence; 2 confirmed RCA; **well_supported**
- `policy_risk` — 7 records; 0 high-evidence; 0 confirmed RCA; **supported**
- `F-GAM-007` — 6 records; 6 high-evidence; 6 confirmed RCA; **well_supported**
- `F-HB-002` — 6 records; 6 high-evidence; 4 confirmed RCA; **well_supported**
- `F-HB-005` — 6 records; 5 high-evidence; 1 confirmed RCA; **well_supported**
- `ad_serving_limit` — 6 records; 0 high-evidence; 0 confirmed RCA; **supported**
- `F-AN-004` — 5 records; 1 high-evidence; 0 confirmed RCA; **supported**
- `F-BR-003` — 5 records; 5 high-evidence; 3 confirmed RCA; **well_supported**
- `F-GAM-002` — 5 records; 3 high-evidence; 3 confirmed RCA; **well_supported**
- `gpt_refresh_state` — 5 records; 5 high-evidence; 2 confirmed RCA; **well_supported**
- `F-GAM-004` — 4 records; 0 high-evidence; 0 confirmed RCA; **supported**
- `F-SEO-006` — 4 records; 2 high-evidence; 0 confirmed RCA; **supported**

## Important bias warning
Counts are **evidence coverage, not real-world prevalence**. Google is over-represented because GAM/Search publish unusually rich status histories; Prebid is over-represented among client-side bugs because it is open source. Proprietary SSP/player and publisher-internal configuration incidents are under-represented.

## High-value resolved cross-layer example
The corpus now includes a particularly useful AMP case: stable publisher traffic/upstream SSP request context, falling GAM requests and impressions/pageview, followed by a reported resolution identifying outdated TCF strings and GAM TCF error 3.3. This is exactly the type of multi-layer evidence chain the future Incident Engine needs.

## Companion files
- `incidents_v0.5.yaml`
- `incidents_v0.5.csv`
- `incident_patterns_v0.5.yaml`
- `coverage_matrix_v0.5.csv`
- `INCIDENT_SOURCE_REGISTRY_v0.5.md`
- `INCIDENT_CORPUS_MANIFEST_v0.5.json`
