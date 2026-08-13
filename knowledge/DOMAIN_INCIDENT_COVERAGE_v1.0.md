# DOMAIN_INCIDENT_COVERAGE_v1.0.md
## Empirical coverage bridge: DOMAIN ↔ INCIDENTS

**Purpose:** show where DOMAIN failure modes have public incident evidence and where expert/pilot evidence is still needed.

Important: counts measure public-corpus coverage, **not real-world prevalence**.

| DOMAIN mapping | Records | High-evidence | Confirmed RCA |
|---|---:|---:|---:|
| `google_external_event` | 192 | 68 | 26 |
| `F-GAM-005` | 122 | 3 | 2 |
| `reporting_freshness_or_platform_incident` | 117 | 0 | 0 |
| `F-SEO-007` | 71 | 57 | 16 |
| `external_dependency_failure` | 14 | 13 | 13 |
| `F-VID-002` | 12 | 11 | 6 |
| `F-CMP-003` | 10 | 10 | 5 |
| `observability_error` | 9 | 6 | 4 |
| `reporting_discrepancy` | 9 | 3 | 1 |
| `cwv_regression` | 9 | 8 | 2 |
| `F-CMP-004` | 8 | 8 | 4 |
| `F-HB-004` | 8 | 7 | 3 |
| `F-CMP-005` | 8 | 7 | 4 |
| `ads_txt_integrity` | 8 | 0 | 0 |
| `site_availability` | 8 | 8 | 8 |
| `F-VID-001` | 7 | 6 | 2 |
| `F-HB-007` | 7 | 7 | 4 |
| `F-HB-006` | 7 | 7 | 6 |
| `F-CMP-002` | 7 | 6 | 6 |
| `policy_risk` | 7 | 0 | 0 |
| `F-GAM-007` | 6 | 6 | 6 |
| `F-HB-002` | 6 | 6 | 4 |
| `F-HB-005` | 6 | 5 | 1 |
| `ad_serving_limit` | 6 | 0 | 0 |
| `F-GAM-002` | 5 | 3 | 3 |
| `gpt_refresh_state` | 5 | 5 | 2 |
| `F-AN-004` | 5 | 1 | 0 |
| `F-BR-003` | 5 | 5 | 3 |
| `race_condition` | 4 | 3 | 2 |
| `F-GAM-004` | 4 | 0 | 0 |
| `F-SEO-006` | 4 | 2 | 0 |
| `rate_denominator_discipline` | 3 | 1 | 1 |
| `F-GAM-006` | 3 | 0 | 0 |
| `F-SEO-004` | 3 | 1 | 0 |
| `configuration_change` | 3 | 3 | 3 |
| `third_party_dependency` | 3 | 3 | 1 |
| `cmp_vendor_incident` | 3 | 0 | 0 |
| `duplicate_delivery_risk` | 2 | 2 | 2 |
| `F-CMP-001` | 2 | 2 | 1 |
| `F-GAM-003` | 2 | 0 | 0 |
| `ad_refresh` | 2 | 0 | 0 |
| `M-002` | 2 | 0 | 0 |
| `IR-007` | 2 | 1 | 0 |
| `F-SEO-010` | 2 | 0 | 0 |
| `F-SEO-002` | 2 | 1 | 0 |
| `F-AN-003` | 2 | 0 | 0 |
| `reporting_freshness` | 2 | 1 | 1 |
| `network_configuration` | 2 | 2 | 2 |
| `counterexample` | 2 | 0 | 0 |
| `supply_path_complexity` | 2 | 0 | 0 |
| `reporting_or_state_anomaly` | 1 | 1 | 1 |
| `passback_failure` | 1 | 0 | 0 |
| `F-VID-003` | 1 | 0 | 0 |
| `M-001` | 1 | 0 | 0 |
| `M-004` | 1 | 1 | 1 |
| `F-GAM-001` | 1 | 0 | 0 |
| `F-SEO-005` | 1 | 0 | 0 |
| `IR-003` | 1 | 1 | 0 |
| `IR-005` | 1 | 0 | 0 |
| `F-SEO-001` | 1 | 1 | 0 |
| `F-AN-002` | 1 | 0 | 0 |
| `measurement_change` | 1 | 0 | 0 |
| `ad_slot_layout` | 1 | 1 | 0 |
| `viewability_tradeoff` | 1 | 0 | 0 |
| `site_feature_failure` | 1 | 1 | 1 |
| `human_change` | 1 | 1 | 1 |
| `video_dependency` | 1 | 1 | 1 |
| `cascading_failure` | 1 | 1 | 1 |
| `cache_configuration` | 1 | 1 | 1 |
| `data_loss` | 1 | 1 | 1 |
| `network_congestion` | 1 | 1 | 1 |
| `external_network_event` | 1 | 1 | 1 |
| `traffic_confounder` | 1 | 1 | 1 |
| `dns_dependency` | 1 | 1 | 1 |
| `reporting_or_bid_anomaly` | 1 | 1 | 1 |
| `external_demand_event` | 1 | 1 | 1 |
| `ad_server_outage` | 1 | 1 | 1 |
| `security_incident` | 1 | 1 | 1 |
| `control_plane` | 1 | 0 | 0 |
| `implementation_error` | 1 | 1 | 0 |
| `gam_video_configuration` | 1 | 1 | 0 |
| `supply_authorization_failure` | 1 | 0 | 0 |
| `direct_or_channel_displacement` | 1 | 0 | 0 |

## Interpretation

- High public coverage around Google external events is largely a consequence of Google's public status histories.
- High Prebid coverage reflects open-source issue visibility.
- Lower SSP/server-side and proprietary-player coverage is an observability/public-data gap, not evidence those failures are rare.
- Pilot incidents should progressively replace public-source bias with publisher-specific evidence.