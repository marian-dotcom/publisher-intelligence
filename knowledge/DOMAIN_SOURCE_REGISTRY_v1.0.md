# DOMAIN_SOURCE_REGISTRY_v1.0.md
## Source provenance and freshness

**Research pass:** 2026-08-12

Source precedence: current official standards/platform docs → primary research → current technical material → durable book concepts → operational/incident evidence.

| Key | Type | Source | Role | Location |
|---|---|---|---|---|
| `PRODUCT-SPEC` | uploaded | New platform.docx | Product overview and reviewer annotations | conversation file |
| `SRC-ADTECH-BOOK` | uploaded | The AdTech Book — New 2026 Edition | Modern AdTech terminology, ad-server anatomy, auctions, HB, discrepancies | conversation file |
| `SRC-KOSORIN` | uploaded | Dominik Kosorin — Introduction to Programmatic Advertising | Durable programmatic terminology; older edition, current specs override | conversation file |
| `SRC-BUSCH` | uploaded | Oliver Busch (ed.) — Programmatic Advertising | Publisher economics, yield, Deal IDs, historical context | conversation file |
| `SRC-HPBN` | uploaded | Ilya Grigorik — High Performance Browser Networking | Durable latency/network/browser foundations | conversation file |
| `SRC-DDIA` | uploaded | Kleppmann & Riccomini — Designing Data-Intensive Applications, 2nd ed. 2026 | Systems of record, derived data, event log/materialized views, KISS | conversation file |
| `INCIDENT-CORPUS` | generated | Public Publisher Incident Corpus v0.5 | Empirical failure modes/counterexamples | /mnt/data/incidents_v0.5.yaml |
| `SRC-GAM-REPORTS-2026` | web | Google Ad Manager API (Beta) — Create and run reports | Async Interactive Reports API, report definitions/results | https://developers.google.com/ad-manager/api/beta/reports |
| `SRC-GAM-API-QUOTA` | web | Google Ad Manager API best practices | Quotas, paging, batching, least privilege | https://developers.google.com/ad-manager/api/bestpractices |
| `SRC-GAM-REPORT-DIMS` | web | Google Ad Manager report dimensions/metrics | Demand channel, serving restriction, pricing rule, bidder, sizes | https://developers.google.com/ad-manager/api/reference/ |
| `SRC-GAM-SELECTION` | web | Google Ad Manager ad selection / line item priority | Eligibility and selection semantics | https://support.google.com/admanager/ |
| `SRC-GAM-DYNAMIC` | web | Google Ad Manager dynamic allocation | Competition with reserved/non-guaranteed demand | https://support.google.com/admanager/ |
| `SRC-GAM-UNFILLED` | web | Google Ad Manager unfilled impressions troubleshooting | Unfilled request semantics and troubleshooting | https://support.google.com/admanager/ |
| `SRC-GAM-VAST-ERRORS` | web | Google Ad Manager — Understand VAST error codes | Creative render rate and video drop-offs | https://support.google.com/admanager/answer/4442429 |
| `SRC-GPT-EVENTS` | web | Google Publisher Tag reference | slotRequested/response/render/onload/viewable lifecycle | https://developers.google.com/publisher-tag/reference |
| `SRC-GPT-LAZY` | web | Google Publisher Tag lazy loading/best practices | Lazy-load request/render behavior | https://developers.google.com/publisher-tag/guides/ad-best-practices |
| `SRC-GPT-REFRESH` | web | Google Publisher Tag refresh guidance | Refresh lifecycle and declarations | https://developers.google.com/publisher-tag/guides/control-ad-loading |
| `SRC-GA4` | web | Google Analytics Data API overview | GA4 programmatic reporting | https://developers.google.com/analytics/devguides/reporting/data/v1 |
| `SRC-GA4-DATA` | web | Google Analytics Data API quotas | Token/concurrency/request cost model | https://developers.google.com/analytics/devguides/reporting/data/v1/quotas |
| `SRC-GA4-EXPECTATIONS` | web | GA4 reporting data expectations | Thresholding, high cardinality, reporting identity | https://developers.google.com/analytics/devguides/reporting/data/v1/reporting-data-expectations |
| `SRC-SEARCH-HOW` | web | Google Search — How Search works | Crawling/indexing/serving model | https://developers.google.com/search/docs/fundamentals/how-search-works |
| `SRC-SEARCH-ROBOTS` | web | Google Search robots.txt documentation | Crawler access semantics | https://developers.google.com/search/docs/crawling-indexing/robots/intro |
| `SRC-SEARCH-NOINDEX` | web | Google Search noindex documentation | Indexing directive semantics | https://developers.google.com/search/docs/crawling-indexing/block-indexing |
| `SRC-SEARCH-CANONICAL` | web | Google Search canonicalization | Canonical methods/signals | https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls |
| `SRC-SEARCH-JS` | web | Google JavaScript SEO | Rendering/JS implications | https://developers.google.com/search/docs/crawling-indexing/javascript/javascript-seo-basics |
| `SRC-SEARCH-MOBILE` | web | Google mobile-first indexing | Mobile content/indexing guidance | https://developers.google.com/search/docs/crawling-indexing/mobile/mobile-sites-mobile-first-indexing |
| `SRC-DISCOVER` | web | Google Discover and your website | Discover eligibility and volatility | https://developers.google.com/search/docs/appearance/google-discover |
| `SRC-GSC-API` | web | Search Console API Search Analytics | Clicks/impressions/CTR/position queries | https://developers.google.com/webmaster-tools/v1/searchanalytics |
| `SRC-GSC-LIMITS` | web | Search Console API limits | Row/query limits | https://developers.google.com/webmaster-tools/limits |
| `SRC-IAB-ADSTXT` | web | IAB Tech Lab ads.txt v1.1 | Authorized digital sellers | https://iabtechlab.com/ads-txt/ |
| `SRC-IAB-SUPPLY` | web | IAB Tech Lab supply-chain standards | sellers.json and SupplyChain | https://iabtechlab.com/standards/supply-chain-foundations/ |
| `SRC-IAB-VALIDATION` | web | IAB Tech Lab Supply Chain Validation | Automated ads.txt/sellers.json validation patterns | https://iabtechlab.com/ |
| `SRC-PREBID-EVENTS` | web | Prebid publisher events API | Auction/bid/timeout/ad-server/render events | https://docs.prebid.org/dev-docs/publisher-api-reference/getEvents.html |
| `SRC-PREBID-TIMEOUTS` | web | Prebid Timeouts | Client/server timeout interactions | https://docs.prebid.org/features/timeouts.html |
| `SRC-PREBID-CONSENT` | web | Prebid TCF Consent Management | CMP discovery/timeout behavior | https://docs.prebid.org/dev-docs/modules/consentManagementTcf.html |
| `SRC-PREBID-USERID` | web | Prebid User ID module | User-sync/identity controls | https://docs.prebid.org/dev-docs/modules/userId.html |
| `SRC-PREBID-VIDEO` | web | Prebid.js video overview | VAST cache/ad-server/player flow | https://docs.prebid.org/prebid-video/video-overview.html |
| `SRC-TCF-23` | web | IAB Europe TCF v2.3 transition/current resources | Mandatory Disclosed Vendors and current technical context | https://iabeurope.eu/tcf-supporting-resources/ |
| `SRC-OMSDK` | web | IAB Tech Lab Open Measurement SDK | Standardized impression/viewability measurement | https://iabtechlab.com/standards/open-measurement-sdk/ |
| `SRC-GOOGLE-VIDEO-POLICY` | web | Google Publisher Policies — Video inventory restrictions | Current placement/audibility/autoplay/sticky requirements | https://support.google.com/publisherpolicies/answer/15208072 |
| `SRC-GOOGLE-PUBLISHER-RESTRICTIONS` | web | Google Publisher Restrictions | Demand eligibility and behavioral/video restrictions | https://support.google.com/publisherpolicies/answer/10437795 |
| `SRC-BETTER-ADS` | web | Coalition for Better Ads — updated desktop/mobile standards | Current disruptive format/density/sticky-video standards | https://www.betterads.org/ |
| `SRC-SRE` | web | Google SRE Incident Management Guide | Symptom-based, actionable alerting | https://sre.google/resources/practices-and-processes/incident-management-guide/ |
| `SRC-SRE-MONITORING` | web | Google SRE Workbook — Monitoring | Freshness, before/after comparison, structured events | https://sre.google/workbook/monitoring/ |
| `SRC-SRE-TIMESERIES` | web | Google SRE — Practical Alerting | Time-series/labels/alert concepts | https://sre.google/sre-book/practical-alerting/ |
| `SRC-RTB-RESEARCH` | web | Primary RTB/header-bidding measurement literature | Temporal patterns, auction/latency measurement | https://arxiv.org/ |

## Maintenance notes

- Recheck PLATFORM_CURRENT sources before major releases and whenever a connector starts failing.
- Keep TCF technical version separate from TCF policy version.
- Keep GAM report/API version with every stored extract.
- Keep incident evidence separate from canonical definitions.
- Older programmatic books are retained for durable mechanisms and publisher economics, not current platform behavior.


## Additional source keys referenced by DOMAIN

| Key | Type | Source | Role | Location |
|---|---|---|---|---|
| `SRC-GAM` | web | Google Ad Manager Help / API documentation | Current GAM platform semantics | https://support.google.com/admanager/ |
| `SRC-IAB` | web | IAB Tech Lab standards | Programmatic standards umbrella | https://iabtechlab.com/standards/ |
| `SRC-PREBID` | web | Prebid documentation | Current Prebid.js publisher architecture | https://docs.prebid.org/ |
| `SRC-PREBID-CONFIG` | web | Prebid `setConfig` reference | Timer/config behavior | https://docs.prebid.org/dev-docs/publisher-api-reference/setConfig.html |
| `SRC-PREBID-FLOORS` | web | Prebid Price Floors module | Floor mechanics | https://docs.prebid.org/dev-docs/modules/floors.html |
| `SRC-PREBID-SERVER` | web | Prebid Server documentation | Server-side auction/timeout model | https://docs.prebid.org/prebid-server/ |
| `SRC-TCF` | web | IAB Europe Transparency & Consent Framework | Framework components | https://iabeurope.eu/transparency-consent-framework/ |
| `SRC-VAST` | web | IAB Tech Lab VAST | Current video ad-serving standard (VAST 4.3 + addenda) | https://iabtechlab.com/standards/vast/ |
| `SRC-WEB-VITALS` | web | web.dev Core Web Vitals | Field/lab metrics and thresholds | https://web.dev/articles/vitals |
| `SRC-CWV-ADS` | web | web.dev / Publisher Ads performance guidance | Advertising impact on CWV and page performance | https://web.dev/ |
| `SRC-GA4-GSC` | web | Google Search Central — GA4 and Search Console together | Measurement-definition differences | https://developers.google.com/search/docs/monitor-debug/google-analytics-search-console |
| `SRC-SEARCH` | web | Google Search Central | Current Search technical documentation | https://developers.google.com/search/docs |
| `SRC-SEARCH-SITEMAP` | web | Google Search sitemap overview | Discovery semantics / no indexing guarantee | https://developers.google.com/search/docs/crawling-indexing/sitemaps/overview |
| `SRC-SEARCH-STATUS` | web | Google Search Status Dashboard | External Search incidents and updates | https://status.search.google.com/summary |
