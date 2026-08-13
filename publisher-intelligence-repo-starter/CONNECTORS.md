# CONNECTORS.md
## External Data Connector Specification
### Publisher Incident Intelligence Platform — v1.0

**Audience:** Codex, backend engineering, product, technical reviewers  
**Status:** MVP implementation contract  
**Primary connectors:** GA4, Google Search Console, Google Ad Manager  
**Depends on:** `DOMAIN.md`, `DATA_MODEL.md`, `EVENTS.md`, `BROWSER.md`, `MVP.md`  
**Feeds:** Metrics, Timeline, Weekly Brief, `INCIDENT.md`, `EVALS.md`

---

# 0. Purpose

The connector layer gives the platform access to publisher business and measurement systems.

Its job is **not** to copy entire Google products into our database, become a BI warehouse, optimize campaigns, write publisher configuration, or continuously poll every possible API endpoint.

Its job is:

> **Collect the minimum structured evidence necessary to detect, localize and investigate publisher incidents.**

For MVP:

```text
GA4
→ traffic + behavior

Google Search Console
→ Search + Discover visibility/performance

Google Ad Manager
→ ad-serving + inventory + demand composition
```

Browser observation remains an independent evidence source.

A connector does not replace browser evidence, and browser evidence does not replace a connector.

---

# 1. Non-negotiable connector rules

## CONN-INV-001 — Read-only by default

All MVP connectors MUST use the narrowest practical read-only authorization.

No production write permission is required for:
- GA4;
- Search Console;
- GAM.

## CONN-INV-002 — Least data necessary

Do not ingest every available dimension/metric because an API exposes it.

Every dataset must answer a product diagnostic question.

## CONN-INV-003 — Provenance always

Every extract MUST preserve:
- source;
- account/property/network;
- query/report definition;
- period;
- source timezone;
- retrieval time;
- API/connector version;
- freshness/completeness metadata.

## CONN-INV-004 — Missing is not zero

If:
- connector fails;
- report is incomplete;
- source does not return a row;

do not silently convert to zero.

## CONN-INV-005 — Preliminary is not final

Recent/incomplete data MUST remain identifiable as preliminary.

A later mature extract may supersede it for current analysis, but MUST NOT overwrite the earlier extract.

## CONN-INV-006 — Source semantics win

Metric names are not enough.

The connector must preserve the exact platform definition.

Do not invent a generic "traffic", "fill" or "revenue" metric detached from source semantics.

## CONN-INV-007 — No causal interpretation in connector

Connector output may say:

```text
Organic Search sessions fell
```

It must not say:

```text
Google update caused traffic loss
```

## CONN-INV-008 — Bounded querying

Use:
- fixed report cubes;
- caching;
- batching;
- incremental windows;
- backoff;
- quota awareness.

Do not query APIs like transactional databases.

## CONN-INV-009 — Idempotent ingestion

Queue retries must not create duplicate logical extracts accidentally.

## CONN-INV-010 — Connector health is separate from publisher health

A failed API call is:

```text
CONNECTOR_EXTRACTION_FAILED
```

not:

```text
publisher traffic = 0
```

---

# 2. Connector architecture

Logical flow:

```text
Scheduler
   ↓
Connector Job
   ↓
Provider Adapter
   ↓
Authentication
   ↓
Capability / Schema Validation
   ↓
Source Query
   ↓
Raw Response
   ↓
Normalization
   ↓
source_extract
   ↓
metric_series + metric_points
   ↓
freshness / quality metadata
   ↓
EVENTS / INCIDENT
```

Provider-specific API objects must not leak deeply into Incident Engine code.

---

# 3. Connector interface

Each connector SHOULD expose a common conceptual interface:

```python
class Connector:
    async def validate_connection(...)
    async def discover_capabilities(...)
    async def run_extract(extract_definition, period)
    async def normalize(response)
    async def health(...)
```

Provider adapters may implement additional methods.

Do not force GA4, GSC and GAM into identical raw API semantics.

Unify only:
- lifecycle;
- provenance;
- errors;
- output contract.

---

# 4. Connection lifecycle

Recommended states:

```text
PENDING
CONNECTED
DEGRADED
AUTH_EXPIRED
PERMISSION_ERROR
DISCONNECTED
```

Do not use `connected=true/false` as the only connection state.

A token may be valid while a publisher removes access to one property/network.

---

# 5. OAuth / credentials

Tokens/secrets MUST NOT live as plaintext in `data_connections`.

Store:
- secure secret reference;
- granted scopes;
- external account/property identifiers;
- permission/capability snapshot.

Use encrypted secret storage.

Refresh tokens are sensitive credentials.

Never put them:
- in logs;
- in artifacts;
- in error messages;
- in Git.

---

# 6. Connection validation

On connect:

1. authenticate;
2. call a cheap read endpoint;
3. verify expected property/network exists;
4. verify permission;
5. discover relevant metadata/capabilities;
6. store capability snapshot;
7. run a small probe extract;
8. mark CONNECTED only when probe succeeds.

Do not accept OAuth completion alone as proof the connector works.

---

# 7. Capability snapshot

Capabilities can differ by:
- GA4 property setup;
- custom dimensions;
- Search Console property type;
- GAM account/network;
- GAM 360 vs non-360;
- report compatibility;
- enabled products.

Store a versioned capability snapshot in connection metadata or a dedicated derived object later.

Example:

```json
{
  "ga4": {
    "property_id": "123",
    "custom_dimensions": ["content_group"]
  }
}
```

or:

```json
{
  "gam": {
    "network_code": "1234",
    "report_api": "REST_BETA",
    "validated_cubes": ["inventory_health_v1", "demand_health_v1"]
  }
}
```

---

# 8. Connector versioning

Every extract carries:

```text
connector_version
```

Changing:
- query definition;
- dimensions;
- normalization;
- source API;
- metric mapping;

may require a new metric semantics version.

Do not let an adapter upgrade silently alter historical comparisons.

---

# 9. Extract definitions live in code/config

Do not let the application dynamically invent arbitrary API queries in MVP.

Use version-controlled definitions:

```text
GA4_TRAFFIC_HOURLY_V1
GA4_PAGE_BEHAVIOR_DAILY_V1
GSC_SEARCH_DAILY_V1
GSC_DISCOVER_DAILY_V1
GAM_INVENTORY_HEALTH_V1
GAM_DEMAND_HEALTH_V1
```

This gives:
- known semantics;
- tested compatibility;
- predictable quotas;
- reproducible results.

---

# 10. Query provenance

Every `source_extract` stores a canonical query definition.

Canonical form should include only relevant semantics.

Example GA4:

```json
{
  "dimensions": ["dateHour", "deviceCategory", "sessionDefaultChannelGroup"],
  "metrics": ["activeUsers", "sessions", "screenPageViews"],
  "filters": null
}
```

Example GSC:

```json
{
  "type": "web",
  "dataState": "final",
  "dimensions": ["date", "device"],
  "aggregationType": "auto"
}
```

Example GAM:

```json
{
  "report_definition": "inventory_health_v1",
  "dimensions": ["DATE", "DEVICE_CATEGORY"],
  "metrics": ["AD_REQUESTS"]
}
```

Preserve source/native names.

---

# 11. Extraction tiers

Use three operational tiers.

## TIER A — Routine monitoring

Small, predictable extracts scheduled continuously.

## TIER B — Reconciliation/backfill

Re-query recent periods after data matures.

## TIER C — Incident drill-down

Temporary queries triggered by an active investigation.

This prevents permanent ingestion of every possible dimension.

---

# 12. Routine vs incident data

Example:

Routine GA4:
```text
hour × device × channel
```

Incident:
```text
hour × device × channel × template/category/page
```

Routine GAM:
```text
hour × device × demand class
```

Incident:
```text
hour × ad unit × device × programmatic channel
```

Do not run Tier C cardinality forever after incident closes.

---

# 13. Data maturity model

Normalize source freshness into:

```text
PRELIMINARY
MATURE
STALE
UNKNOWN
```

This is our internal interpretation.

Always retain source-native metadata too.

Maturity policy is connector-specific.

---

# 14. Reconciliation/backfill principle

Recent data can change.

Therefore:

```text
intraday extract
→ PRELIMINARY

later re-query
→ MATURE
```

Both source extracts remain.

Current views may prefer MATURE.

Incident reports must state if important evidence is preliminary.

---

# 15. Connector scheduling philosophy

Do not synchronize every connector with the six-hour browser checkpoint.

The data sources have different freshness semantics.

Browser:
fixed 6-hour black-box cadence.

GA4:
intraday measurement source.

GSC:
daily + optional fresh/hourly incomplete source.

GAM:
ad-serving reporting with its own report freshness/processing.

Use source-appropriate schedules.

---

# 16. GA4 role

GA4 answers:

> **What happened to measured traffic and user consumption?**

Primary uses:
- traffic volume;
- acquisition-source localization;
- device localization;
- page/template/category localization;
- consumption behavior.

GA4 is a measurement system.

It is not an independent proof of physical traffic.

---

# 17. GA4 authorization

Use:

```text
https://www.googleapis.com/auth/analytics.readonly
```

for MVP.

Do not request write access.

---

# 18. GA4 API choice

Primary:
**Google Analytics Data API v1**

Core methods may include:
- `runReport`;
- `batchRunReports`;
- metadata/compatibility methods.

MVP does not need:
- Realtime API as a health source;
- Funnel API;
- Audience export;
- user-level audience lists.

Do not ingest user-level audience data.

---

# 19. GA4 metadata discovery

At onboarding, call property metadata to discover:
- standard dimensions/metrics;
- registered custom dimensions;
- registered custom metrics.

Use compatibility checks before enabling a report definition if needed.

This matters because publisher-specific:
- category;
- content type;
- author;
- template;

may exist as custom dimensions on some properties and not others.

---

# 20. GA4 standard core metrics

Initial routine metrics:

```text
activeUsers
sessions
screenPageViews
engagedSessions
engagementRate
screenPageViewsPerUser
screenPageViewsPerSession
```

Potential optional:
```text
userEngagementDuration
scrolledUsers
```

Only use optional metrics if implementation quality makes them useful.

Do not ingest ecommerce metrics for a news publisher by default.

---

# 21. GA4 standard dimensions

Initial useful dimensions:

```text
date
dateHour
deviceCategory
country
sessionDefaultChannelGroup
sessionSourceMedium
pagePath / pagePathPlusQueryString where appropriate
landingPage / landingPagePlusQueryString where appropriate
contentGroup if configured/useful
```

Exact names MUST be validated against current Data API metadata.

Do not hard-code every field from the global schema as required.

---

# 22. GA4 content mapping

Preferred mapping priority:

1. publisher-provided custom content/template dimension;
2. GA4 `contentGroup` if clean;
3. deterministic URL → template/category mapping;
4. browser/template mapping;
5. manual mapping.

Every mapped series stores provenance.

Do not pretend inferred categories came directly from GA4.

---

# 23. GA4 routine cube A — traffic health

Suggested:

```text
GA4_TRAFFIC_HOURLY_V1
```

Dimensions:

```text
dateHour
deviceCategory
sessionDefaultChannelGroup
```

Metrics:

```text
activeUsers
sessions
screenPageViews
engagedSessions
```

Purpose:
detect:
- site-wide traffic change;
- channel-specific change;
- device-specific change.

Do not add page dimension here.

Keep cardinality low.

---

# 24. GA4 routine cube B — behavior

Suggested:

```text
GA4_BEHAVIOR_DAILY_V1
```

Dimensions:

```text
date
deviceCategory
```

Optionally:
```text
contentGroup / mapped template
```

Metrics:

```text
activeUsers
sessions
screenPageViews
screenPageViewsPerUser
screenPageViewsPerSession
engagementRate
```

Purpose:
distinguish reach from consumption.

---

# 25. GA4 routine cube C — page/template

Daily, not necessarily hourly:

```text
GA4_PAGE_DAILY_V1
```

Dimensions:

```text
date
pagePath
deviceCategory
```

Metrics:

```text
activeUsers
screenPageViews
```

Purpose:
template/category localization and incident drill-down.

Do not permanently pull every high-cardinality page/query combination at hourly granularity.

---

# 26. GA4 incident drill-down

When incident requires it, temporary dimensions may include:
- landing page;
- page path;
- country;
- source/medium;
- template/category;
- custom publisher dimensions.

Rules:
- bounded date window;
- bounded dimension set;
- log quota cost;
- cache results;
- discard no useful long-tail rows from persistent operational model if not needed.

---

# 27. GA4 `(other)` / high cardinality

Google Analytics can roll high-cardinality dimension combinations into an `(other)` row.

The Data API response metadata can indicate `dataLossFromOtherRow`.

Connector MUST preserve this metadata.

If true:
- mark extract quality limitation;
- do not interpret missing low-volume rows as absence;
- avoid high-cardinality incident conclusions without another query/source.

---

# 28. GA4 thresholding

Response metadata may indicate data thresholding.

If thresholding applies:
- preserve flag;
- lower completeness assumptions;
- do not convert omitted small rows to zero.

This is measurement/reporting behavior.

It is not a publisher traffic event.

---

# 29. GA4 reporting identity

User counts can depend on reporting identity and platform semantics.

Do not use:
`activeUsers`
as an immutable physical count of unique human beings.

For anomaly detection:
consistency over time within the same reporting semantics matters more than philosophical identity.

If property/reporting semantics materially change:
version/annotate.

---

# 30. GA4 quota model

The Data API uses token-based quotas for Core/Realtime/Funnel requests.

Query cost is affected by factors such as:
- rows;
- columns;
- filters;
- date ranges;
- cardinality.

Connector MUST:
- cache;
- batch where useful;
- avoid repeated identical queries;
- request only necessary dimensions/metrics;
- back off on quota errors.

Do not use quota circumvention strategies.

---

# 31. GA4 quota telemetry

Where API response can return property quota information, record it for operational monitoring.

Internal connector metrics:

```text
requests
tokens_consumed
concurrent_request_usage
quota_errors
retry_count
```

Do not expose quota details as publisher business events unless connector becomes impaired.

---

# 32. GA4 routine schedule

Initial MVP recommendation:

## Intraday operational pull
Every **2 hours**.

Query:
current day + previous day at hourly/low-cardinality level.

Mark:
`PRELIMINARY`.

Rationale:
enough temporal resolution for incident onset without aggressive polling.

## Nightly reconciliation
Once daily.

Re-query approximately:
last **3 days**.

## Extended repair
Periodically or after connector outage:
last **7 days**.

These are starting values, not eternal rules.

Record in config/DECISIONS.

---

# 33. GA4 Realtime API

Do not use Realtime as the main baseline source.

Reasons:
- different semantics/window;
- not the same historical comparison surface;
- unnecessary for most incidents.

Realtime MAY later be used as:
- immediate sanity check during an active incident.

If used:
store as a separate metric semantics/source.

Never merge Realtime points with Core historical series.

---

# 34. GA4 extraction quality status

Possible limitations:

```text
OTHER_ROW_DATA_LOSS
THRESHOLDING_APPLIED
HIGH_CARDINALITY
CUSTOM_DIMENSION_MISSING
PROPERTY_PERMISSION_LIMIT
QUOTA_LIMIT
```

Store in `response_metadata`.

Do not create a GA4 business anomaly from an extract with failed/incomplete status.

---

# 35. GA4 event mappings

Potential Event Engine inputs:

```text
GA4_ACTIVE_USERS_BELOW_BASELINE
GA4_SESSIONS_BELOW_BASELINE
GA4_VIEWS_BELOW_BASELINE
GA4_VIEWS_PER_USER_BELOW_BASELINE
GA4_ORGANIC_SEARCH_BELOW_BASELINE
```

Connector itself emits metric points.

EVENTS creates anomaly/events.

---

# 36. GA4 prohibited conclusions

GA4 alone MUST NOT conclude:

- physical site traffic definitely declined;
- Search visibility declined;
- Google update caused decline;
- users saw a browser defect;
- ad monetization failed;
- CMP is broken.

It is one evidence source.

---

# 37. Google Search Console role

GSC answers:

> **How is the site appearing and receiving clicks from Google Search/Discover according to Search Console?**

Primary:
- Search;
- Discover.

Optional:
- Google News;
- News tab;
- image/video if publisher use case justifies.

---

# 38. Search Console authorization

Use:

```text
https://www.googleapis.com/auth/webmasters.readonly
```

MVP does not need read/write scope.

---

# 39. Search Console property types

Search Console property may be:

```text
sc-domain:example.com
```

or URL-prefix:

```text
https://www.example.com/
```

Store the exact source property identifier.

Do not normalize them into one string and lose property semantics.

---

# 40. Search Analytics API semantics

Search Analytics returns grouped performance data:

```text
clicks
impressions
ctr
position
```

Possible dimensions include:
- date;
- hour;
- country;
- device;
- page;
- query;
- searchAppearance.

Search/Discover type is controlled by `type`.

Use source-native semantics.

---

# 41. Search types

Important source types:

```text
web
discover
googleNews
news
image
video
```

For MVP core:

```text
web
discover
```

Do not merge Discover into web Search.

They are different series.

---

# 42. GSC routine cube A — Search health

```text
GSC_SEARCH_DAILY_V1
```

Type:
`web`

Dimensions:

```text
date
device
```

Metrics returned:

```text
clicks
impressions
ctr
position
```

Purpose:
Search visibility/performance trend and device localization.

---

# 43. GSC routine cube B — Search pages

```text
GSC_SEARCH_PAGE_DAILY_V1
```

Type:
`web`

Dimensions:

```text
date
page
device
```

Purpose:
template/page localization.

Use bounded recent periods.

Because page grouping is more expensive/high-cardinality, do not constantly query long historical ranges.

---

# 44. GSC routine cube C — Discover

```text
GSC_DISCOVER_DAILY_V1
```

Type:
`discover`

Dimensions:

```text
date
device
```

Metrics:

```text
clicks
impressions
ctr
position
```

Use position cautiously if source semantics/report availability make it meaningful.

Do not invent Discover ranking logic.

---

# 45. GSC Discover pages

For publishers with material Discover traffic:

```text
GSC_DISCOVER_PAGE_DAILY_V1
```

Dimensions:

```text
date
page
device
```

Use for:
- template/article localization;
- incident drill-down.

---

# 46. GSC query dimension

Query data is useful but high cardinality and privacy-sensitive.

Default MVP:
do NOT continuously ingest every Search query.

Use query dimension:
- during Search incident drill-down;
- for top-query mix analysis;
- bounded date ranges.

Keep:
- top/meaningful rows;
- source extract provenance.

Do not build a full private query warehouse by default.

---

# 47. Search Console top-row limitation

Search Analytics API does not guarantee every row; it returns top rows under internal limitations.

Therefore:

```text
row absent
```

does not necessarily mean:

```text
zero activity
```

This matters especially with:
- page + query;
- long-tail query data.

Incident Engine must know this limitation.

---

# 48. Search Console row limits

Search Analytics supports paging with `rowLimit` and `startRow`.

Current source semantics allow up to 25,000 rows per request, while Google's extraction guidance documents a 50,000-row-per-day-per-search-type maximum.

Connector should:
- paginate where justified;
- stop when no more rows;
- avoid pretending this is a complete raw log.

---

# 49. Search Console dataState

Current Search Analytics supports:

```text
final
all
hourly_all
```

## final
Only finalized data.

Use as mature source.

## all
Includes fresh/incomplete data where available.

Metadata can identify the first incomplete date.

## hourly_all
Allows hourly grouping and can include partial/incomplete data.

Metadata can identify the first incomplete hour.

This is useful for incident onset but must be labeled preliminary.

---

# 50. GSC time-zone semantics

Search Analytics request dates and recent-data metadata use source-defined Pacific / `America/Los_Angeles` semantics.

Store:
- source timezone;
- source-local date/hour;
- converted UTC period for cross-source correlation.

Do not silently assume publisher local time.

---

# 51. GSC routine schedule

Initial MVP recommendation:

## Mature daily
Once per day:
- re-query finalized `web`;
- re-query finalized `discover`;
- last 7 days.

Purpose:
stable baseline and reconciliation.

## Fresh operational
Every **4 hours**:
- query recent `all` or `hourly_all`;
- low-cardinality device/source view;
- mark incomplete intervals `PRELIMINARY`.

Use primarily for:
- early anomaly context;
- incident onset localization.

If fresh Search data proves too noisy for target publishers, reduce cadence.

---

# 52. GSC hourly data policy

Hourly GSC data is useful but incomplete.

It MUST NOT create a critical traffic/Search event without:
- source metadata check;
- persistence/corroboration;
- or strong browser/GA4 evidence.

Hourly data is early evidence.

Finalized daily data is stronger for historical conclusion.

---

# 53. GSC URL Inspection

URL Inspection API can return index-status information for a URL.

MVP use:
**incident-triggered diagnostic tool**, not continuous monitoring of thousands of URLs.

Use for:
- representative affected page;
- unaffected control page.

Do not burn URL Inspection quota continuously.

---

# 54. URL Inspection limitations

URL Inspection is a current Google view of URL/index state.

It does not provide:
- historical state at incident onset;
- complete ranking explanation;
- causal proof.

That is exactly why our own six-hour browser/public-config history matters.

---

# 55. GSC Sitemap API

MVP MAY read sitemap metadata:
- list/get;
- errors;
- warnings;
- last downloaded/submitted;
- pending state.

Do not use write/submit/delete methods.

Use only if Search monitoring benefits.

Public sitemap fetch remains independent evidence.

---

# 56. GSC quota policy

Search Analytics has:
- load quotas;
- short-/long-term load behavior;
- QPS/QPM/QPD limits.

Queries become more expensive with:
- longer date range;
- page dimension;
- query dimension;
- page + query together.

Connector MUST:
- avoid repeated long-range page/query queries;
- spread expensive pulls;
- cache;
- back off after quota errors.

---

# 57. GSC event mappings

Potential Event Engine inputs:

```text
GSC_SEARCH_IMPRESSIONS_BELOW_BASELINE
GSC_SEARCH_CLICKS_BELOW_BASELINE
GSC_SEARCH_CTR_BELOW_BASELINE
GSC_SEARCH_POSITION_WORSENED

GSC_DISCOVER_IMPRESSIONS_BELOW_BASELINE
GSC_DISCOVER_CLICKS_BELOW_BASELINE
```

Connector only supplies metrics/freshness.

EVENTS owns anomaly semantics.

---

# 58. GSC prohibited conclusions

GSC alone MUST NOT conclude:

- technical SEO caused decline;
- Google penalized publisher;
- a Core Update caused decline;
- Discover eligibility was removed;
- Search demand is definitely lower;
- page is healthy in browser.

It is Search visibility evidence.

---

# 59. GA4 + GSC comparison

These sources must remain independent.

Useful patterns:

## Both down similarly

```text
GSC Search clicks ↓
GA4 Organic Search sessions ↓
```

Strengthens:
real Search acquisition decline.

Does not determine cause.

## GA4 down, GSC stable

Raises:
- GA4 measurement;
- consent;
- attribution;
- landing-page tracking.

## GSC down, GA4 stable

Investigate:
- source/channel attribution;
- timing/freshness;
- other acquisition offset;
- measurement definition.

Do not force exact numeric equality.

---

# 60. Google Ad Manager role

GAM answers:

> **What happened in the publisher ad-serving system and demand composition?**

Use:
- requests;
- delivery/impressions;
- programmatic/direct composition;
- demand channel;
- ad unit/inventory structure;
- device/format;
- pricing/restriction context where available.

GAM is not the publisher's accounting ledger.

---

# 61. GAM authorization

Use:

```text
https://www.googleapis.com/auth/admanager.readonly
```

for MVP.

Current Ad Manager API documentation recommends the narrower read-only scope when no writes are required.

User-role/team restrictions still apply.

OAuth scope does not override GAM permissions.

---

# 62. GAM API strategy

The connector must use an **adapter abstraction**, not hard-code Incident Engine to one API generation.

Preferred current path:
**Ad Manager REST API (Beta) Reports** where required data/report compatibility is validated.

The current REST Reports API supports:
- report definitions;
- asynchronous report runs;
- polling operation completion;
- paginated result fetching.

However, GAM reporting compatibility varies by dimensions/metrics/report types.

Therefore:

> **Validate the actual publisher report cubes before declaring the REST path sufficient.**

If a required MVP cube is not available/compatible in the chosen REST API:
use a documented current reporting fallback behind the same connector interface.

Do not make the rest of the product know whether the source was REST Beta or SOAP.

---

# 63. GAM onboarding compatibility probe

At connection time:

1. identify network;
2. validate read permission;
3. inspect network timezone/currency;
4. validate every required report definition;
5. run a short date-range probe;
6. verify result columns/types;
7. record supported/unsupported cubes;
8. mark connector capability state.

A publisher should not complete onboarding with a connector that silently lacks half the required data.

---

# 64. GAM report types

Initial focus:
historical/ad-serving reporting suitable for:
- requests;
- impressions;
- eCPM;
- demand composition.

Potential future/special:
- Ads Traffic Navigator;
- Ad Speed;
- Real-Time Video;

depending account/API availability and validated value.

Do not build MVP assumptions on an advanced report type before pilot validation.

---

# 65. GAM metric semantics

Examples currently documented by GAM include metrics such as:

```text
AD_REQUESTS
AD_EXCHANGE_TOTAL_REQUESTS
AD_EXCHANGE_IMPRESSIONS
AD_EXCHANGE_AVERAGE_ECPM
AVERAGE_ECPM
```

and many specialized metrics.

The connector MUST use the exact source metric.

Do not call:
`AD_EXCHANGE_TOTAL_REQUESTS`

simply:
`requests`

without source/semantic namespace.

---

# 66. GAM routine cube A — inventory health

Concept:

```text
GAM_INVENTORY_HEALTH_V1
```

Goal:
answer:
- are ad requests being generated?
- are impressions being served?
- where?

Preferred dimensions, subject to compatibility:

```text
date/hour
device category
ad unit / ad structure
inventory format
```

Metrics:

```text
ad requests
impressions
unfilled/derived fill components where compatible
```

Do not start with revenue.

---

# 67. GAM routine cube B — demand health

```text
GAM_DEMAND_HEALTH_V1
```

Goal:
distinguish broad inventory problem from demand-channel problem.

Possible dimensions, subject to compatibility:

```text
date/hour
device
programmatic/demand channel
yield partner
```

Metrics may include:
- requests/opportunities;
- impressions;
- eCPM/value;
- demand-specific matched/response measures where appropriate.

Exact cube MUST be validated against API compatibility.

---

# 68. GAM routine cube C — direct/programmatic composition

```text
GAM_DELIVERY_COMPOSITION_V1
```

Goal:
answer:

> Did programmatic decline because direct/reserved delivery increased?

Possible dimensions:
- line item type;
- demand class;
- device;
- date/hour.

Metrics:
- impressions;
- relevant delivery counts;
- contextual revenue if publisher allows.

This cube is important even if we do not ingest financial values.

---

# 69. GAM optional cube D — programmatic value

```text
GAM_PROGRAMMATIC_VALUE_V1
```

Only if publisher permits/wants financial monitoring.

Metrics:
- programmatic revenue;
- eCPM;
- impressions;
- requests.

Always segment enough to avoid raw-total traps.

No critical alert solely on total GAM revenue.

---

# 70. GAM optional diagnostic cube E — restrictions/pricing

Incident-triggered or lower cadence.

Potential dimensions:
- serving restriction;
- unified pricing rule;
- bidder;
- bid rejection reason;
- yield partner;
- requested/delivered size.

Use only when compatible with selected report type/API.

Do not permanently ingest massive combinations.

---

# 71. GAM Ads Traffic Navigator

The current report schema exposes Ads Traffic Navigator metrics for detailed stages such as:
- total/valid ad requests;
- programmatic allowed/valid/ineligible requests;
- bid requests sent;
- bid responses;
- programmatic bids;
- rejected/skipped bids;
- header-bidding-trafficking metrics;
- eligible line items.

This can become extremely valuable for incident drill-down.

MVP stance:

**Do not make it a required baseline dependency until tested in real pilot accounts.**

If available:
use it as a high-information Tier C diagnostic source.

---

# 72. GAM report compatibility

GAM dimensions and metrics are not freely combinable.

Current REST report definitions constrain compatibility and report types.

Therefore:
- store report definition versions;
- validate before deploy;
- tests should run against mock fixtures + pilot capability probe;
- never dynamically add an arbitrary dimension to a production report because Incident Engine asks for it.

Incident Engine chooses from validated drill-down definitions.

---

# 73. GAM expanded compatibility

If the API offers an expanded compatibility mode, do not enable it automatically.

It can change/collapse reservation reporting behavior.

A report semantic change is not a harmless technical flag.

If used:
- give report definition a new semantics version;
- document consequences.

---

# 74. GAM asynchronous reports

For REST reports:

```text
create/get report definition
→ run
→ long-running operation
→ poll
→ fetch rows
```

Connector job status must separate:

```text
API_REQUESTED
REPORT_RUNNING
RESULT_FETCHING
NORMALIZING
COMPLETE
```

Do not block a web request waiting synchronously for long report generation.

Use background jobs.

---

# 75. GAM pagination

Report result fetching may be paginated.

Persist extract as COMPLETE only after:
- all expected result pages successfully retrieved;
- or explicit partial status recorded.

Do not silently store the first page as full report.

---

# 76. GAM report reuse

Prefer reusable/versioned report definitions over generating random new definitions for every run where API semantics allow.

Benefits:
- lower configuration drift;
- reproducibility;
- easier validation.

Do not mutate a report definition in place if doing so changes metric semantics.

Create a new version.

---

# 77. GAM timezone

Ad Manager network timezone is important.

Store:
- network timezone;
- report period;
- source-local hour/day;
- UTC conversion.

Cross-source correlation must not compare:
GAM local day
to
GSC Pacific day
as if bucket boundaries were identical.

---

# 78. GAM currency

Store:
- network/report currency;
- metric unit.

Do not aggregate values across currencies.

MVP does not need FX conversion for root-cause diagnosis.

If added later:
keep original currency/value.

---

# 79. GAM raw revenue rule

Raw ad-server booked revenue may differ from publisher invoiced business revenue.

Therefore:

```text
GAM total revenue ↓
```

is not by itself:

```text
publisher business revenue ↓
```

Event Engine must not critical-alert on it alone.

This is a domain rule, not connector behavior.

---

# 80. GAM direct campaign rule

A new direct/reserved campaign can intentionally reduce programmatic opportunity.

Therefore connector should preserve:
- line-item/demand class;
- direct/programmatic delivery mix.

This is more diagnostically important than an undifferentiated revenue total.

---

# 81. GAM fill semantics

Do not invent a generic fill formula when source semantics are uncertain.

Where possible store:
- request metric;
- impression/matched metric;
- source-reported rate;
- numerator/denominator.

If we derive fill:
give it a distinct metric semantics code/version.

Do not mix:
source-reported fill
and
our derived fill
in one series.

---

# 82. GAM preliminary/freshness policy

GAM reports may have processing/reporting delays and metric-specific freshness.

The connector MUST store retrieval time and report/source metadata.

MVP maturity policy should be empirical:

- recent intraday extracts: PRELIMINARY;
- backfilled stable extracts: MATURE after configured age/consistency check.

Do not hard-code a universal "GAM final after exactly X hours" unless current source docs guarantee it for the selected report.

Pilot calibration required.

---

# 83. GAM routine schedule

Initial MVP recommendation:

## Operational pull
Every **2 hours**.

Low-cardinality:
- inventory health;
- delivery composition;
- demand health if query cost/report duration is acceptable.

Recent window:
current + previous day.

Mark recent periods PRELIMINARY.

## Nightly reconciliation
Re-query:
last **3 days**.

## Extended repair
After outage / weekly:
last **7 days**.

Actual cadence must be validated against:
- report generation time;
- quota;
- network scale;
- data freshness.

---

# 84. GAM quotas and throttling

Ad Manager APIs enforce quotas.

Connector MUST:
- implement per-network rate limiting;
- centralize GAM API concurrency;
- use exponential backoff/jitter;
- respect provider errors;
- avoid polling long-running operations aggressively.

Do not make 40 URLs trigger 40 separate GAM reports.

Browser and GAM are separate data sources.

---

# 85. GAM event mappings

Potential Event Engine inputs:

```text
GAM_REQUESTS_BELOW_BASELINE
GAM_IMPRESSIONS_BELOW_BASELINE
GAM_FILL_BELOW_BASELINE
GAM_ECPM_BELOW_BASELINE
GAM_PROGRAMMATIC_REVENUE_BELOW_BASELINE
GAM_DIRECT_SHARE_INCREASED
GAM_PROGRAMMATIC_SHARE_DECREASED
GAM_SERVING_RESTRICTION_APPEARED
GAM_PRICING_RULE_CHANGED
GAM_LINE_ITEM_DELIVERY_MIX_CHANGED
```

Connector only supplies facts/metrics/config observations.

---

# 86. GAM prohibited conclusions

GAM alone MUST NOT conclude:

- SSP caused revenue loss;
- publisher business revenue fell;
- direct campaign is harmful;
- missing impressions are browser failure;
- CMP caused request loss;
- Google penalized inventory.

Cross-source evidence is needed.

---

# 87. Cross-source time normalization

This is one of the most important connector responsibilities.

Sources may use:
- publisher/site timezone;
- GA4 property timezone;
- GSC Pacific Time;
- GAM network timezone;
- UTC;
- browser actual UTC timestamps.

Store:

```text
source_time
source_timezone
normalized_utc_start
normalized_utc_end
```

Do not throw away source-local semantics.

---

# 88. Cross-source bucket alignment

Do not compare bucket labels naïvely.

Example:

```text
GSC Aug 10
GAM Aug 10
GA4 Aug 10
```

may not cover identical UTC intervals.

For incident correlation:
convert to explicit UTC intervals.

For UI:
display publisher-local time with source note where needed.

---

# 89. Granularity mismatch

Browser:
6-hour samples.

GA4:
hourly/daily.

GSC:
daily or partial hourly.

GAM:
hourly/daily depending report.

The Incident Engine must not interpolate exact causality from coarse data.

Example:

Browser slot disappears between 12:00–18:00.

GAM hourly requests decline at 15:00.

This is useful evidence.

But the browser event did not necessarily happen exactly at 15:00.

Preserve time windows.

---

# 90. Metric namespace

Metric codes MUST be source-namespaced.

Examples:

```text
ga4.active_users
ga4.sessions
ga4.screen_page_views

gsc.web.clicks
gsc.web.impressions
gsc.discover.clicks

gam.ad_requests
gam.ad_exchange_impressions
gam.average_ecpm
```

Our own derived metrics:

```text
derived.gam_fill_v1
derived.requests_per_view_v1
derived.impressions_per_view_v1
```

Do not erase source distinction.

---

# 91. Derived cross-source metrics

Useful examples:

```text
GAM ad requests / GA4 views
GAM impressions / GA4 views
```

Potential diagnostic value:
inventory/request generation per measured consumption.

Rules:
- bucket/timezone align;
- source freshness compatible;
- semantics versioned;
- never pretend denominator is exact physical pageview truth.

These are derived evidence.

---

# 92. Cross-source divergence patterns

High-value patterns include:

```text
GA4 organic ↓ while GSC web clicks stable
GAM requests ↓ while GA4 views stable
GAM impressions ↓ while requests stable
```

Connector layer provides the data.

Event/Incident layers interpret divergence.

---

# 93. Connection health

Each connector needs operational health metrics:

```text
last_success_at
last_attempt_at
auth_status
permission_status
extract_success_rate
average_extract_duration
quota_errors
rate_limit_errors
source_error_count
stale_extract_age
```

Do not expose all of these to publisher Home by default.

---

# 94. Connector health events

Potential DATA_QUALITY events:

```text
GA4_DATA_STALE
GSC_DATA_STALE
GAM_DATA_STALE

CONNECTOR_AUTH_FAILED
CONNECTOR_PERMISSION_CHANGED
CONNECTOR_EXTRACTION_FAILED
CONNECTOR_QUOTA_LIMITED
```

These protect Incident Engine from misleading data.

---

# 95. Authentication expiry behavior

If refresh fails:

1. mark connection AUTH_EXPIRED/PERMISSION_ERROR;
2. stop expensive retries;
3. preserve last successful data;
4. mark new periods missing/stale;
5. show reconnect action;
6. Incident Engine lists source as unavailable.

Do not set metric values to zero.

---

# 96. Backoff

Use provider-specific backoff.

General:

```text
429 / quota
→ exponential backoff + jitter

5xx
→ bounded retry

4xx permission/config
→ do not hammer retry

invalid query
→ code/config error
```

Preserve final error class.

---

# 97. Idempotency

Logical extract key may include:

```text
connection
extract_definition
period
scheduled_run_key
```

A retry creates:
- another attempt,

not:
- a second logical extract unless source is intentionally re-queried as a new reconciliation version.

Distinguish:
**retry**
from
**later backfill**.

---

# 98. Partial extract

If pagination/report retrieval fails halfway:

Possible status:

```text
PARTIAL
```

Do not normalize partial rows into current production metric view as if complete unless definition explicitly supports it.

Persist enough forensic metadata to retry.

---

# 99. Schema/compatibility failure

If a platform deprecates/changes a metric:

Do not silently switch to a similarly named metric.

Flow:

```text
extract fails
→ DATA_QUALITY event
→ validate source docs/schema
→ create new extract definition/version
→ update metric semantics
→ backfill if possible
```

---

# 100. Source API release monitoring

Current platform APIs change.

Track official release notes for:
- GA4 Data API;
- Search Console API;
- GAM API.

Relevant change becomes:
- engineering maintenance task;
- optionally external ruleset/platform event if user-facing behavior matters.

Do not treat every API release note as publisher Timeline event.

---

# 101. Query cost budget

Each connection should have a soft daily budget:

```text
routine queries
backfill queries
incident queries
```

Incident investigation may temporarily use more budget.

But Incident Engine must not create unbounded combinatorial query plans.

A query planner/allowlist of validated extract definitions is safer.

---

# 102. Incident query planner

Incident Engine asks for data semantically:

```text
need Search page/device breakdown
```

Connector maps that request to:

```text
GSC_SEARCH_PAGE_DAILY_V1
```

It does not generate arbitrary JSON query strings from LLM text.

This is a critical safety/reliability boundary.

---

# 103. Allowed incident drill-down catalog

Examples:

GA4:
```text
traffic_by_hour_device_channel
traffic_by_page_device
traffic_by_country_device
landing_page_by_channel
```

GSC:
```text
web_by_page_device
web_top_queries_for_page
discover_by_page_device
```

GAM:
```text
ad_unit_by_device
demand_channel_by_device
line_item_type_by_device
yield_partner_by_ad_unit
restriction_by_inventory
```

Only definitions validated for that connection can run.

---

# 104. LLM boundary

LLM may say:

> We need a mobile/article Search breakdown around Aug 4.

Application maps it to a known query.

LLM MUST NOT receive OAuth credentials.

LLM MUST NOT directly call arbitrary Google APIs with free-form parameters.

LLM MUST NOT select write scopes.

---

# 105. Caching

Cache at two levels.

## Source extract reuse

If an identical mature extract already exists:
reuse it for incident analysis.

## API response cache

Optional short-lived technical cache to reduce repeated queries.

Do not confuse cache with system of record.

`source_extract` remains provenance object.

---

# 106. Re-query policy

Re-query when:
- data is preliminary;
- connector recovered after outage;
- source reports correction;
- incident requires a different validated dimension set;
- extract definition version changed and backfill is justified.

Do not repeatedly re-query mature history without reason.

---

# 107. Data retention

Normalized metric points:
long-term.

Source extract metadata:
long-term.

Raw API response:
selective/shorter depending size/need.

OAuth tokens:
secure token store, lifecycle-based.

Do not retain user-level source data unnecessarily.

---

# 108. Privacy

GA4:
avoid user-level Audience exports.

GSC:
query strings can reveal sensitive intent; ingest minimally.

GAM:
campaign/order names can reveal commercial information; restrict access.

All connector data is tenant-confidential.

No cross-publisher sharing of raw data.

---

# 109. Multi-tenant connection isolation

A connection belongs to one tenant.

Never reuse one publisher's refresh token to query another publisher.

Every source extract must resolve:

```text
tenant_id
connection_id
site_id
```

before storage.

Tenant mismatch is a hard error.

---

# 110. GA4 connection test

Required tests:

1. token works;
2. property accessible;
3. metadata accessible;
4. core dimensions/metrics supported;
5. small report succeeds;
6. response metadata parsed;
7. quota metadata handled if returned;
8. property timezone captured.

If custom category dimension configured:
validate it.

---

# 111. GSC connection test

Required:

1. token works;
2. property accessible;
3. permission verified;
4. `web` query succeeds;
5. Discover capability tested with safe short query;
6. final vs fresh metadata parser works;
7. property identifier stored exactly;
8. timezone semantics known.

Discover returning zero rows is not necessarily connector failure.

---

# 112. GAM connection test

Required:

1. auth works;
2. network accessible;
3. network timezone/currency captured;
4. readonly scope/permission verified;
5. each required cube validates;
6. short report run succeeds;
7. async polling works;
8. all pages fetched;
9. numeric/money/percentage parsing works;
10. unsupported dimensions reported explicitly.

---

# 113. GA4 connector evals

## CONN-GA4-001
Core report succeeds and persists provenance.

## CONN-GA4-002
`dataLossFromOtherRow=true` marks extract limitation.

## CONN-GA4-003
Thresholding metadata does not create zero rows.

## CONN-GA4-004
Custom content dimension missing:
connector degrades mapping, not whole connection.

## CONN-GA4-005
Quota error:
backoff, no duplicate extract.

## CONN-GA4-006
Current-day preliminary extract later reconciles with mature extract without overwrite.

## CONN-GA4-007
Realtime series cannot merge into Core historical series.

---

# 114. GSC connector evals

## CONN-GSC-001
`type=web` and `type=discover` remain separate.

## CONN-GSC-002
`dataState=hourly_all` incomplete hour marked PRELIMINARY.

## CONN-GSC-003
Finalized daily extract becomes MATURE.

## CONN-GSC-004
Missing row is not converted to zero.

## CONN-GSC-005
Pagination respects row limits.

## CONN-GSC-006
Top-row limitation is preserved as completeness warning for long-tail query extraction.

## CONN-GSC-007
Pacific-time bucket converts to explicit UTC interval.

## CONN-GSC-008
URL Inspection quota error does not impair routine Search Analytics.

---

# 115. GAM connector evals

## CONN-GAM-001
Validated cube runs asynchronously and all pages are fetched.

## CONN-GAM-002
Unsupported dimension/metric combination fails onboarding capability, not runtime silently.

## CONN-GAM-003
Direct share rises/programmatic falls: connector preserves composition without labeling failure.

## CONN-GAM-004
Revenue metric contains currency/source semantics.

## CONN-GAM-005
A partial report fetch is not treated COMPLETE.

## CONN-GAM-006
Quota/rate limit triggers backoff.

## CONN-GAM-007
Network timezone is preserved.

## CONN-GAM-008
Report-definition change creates new metric semantics version.

## CONN-GAM-009
REST report unavailable but documented fallback adapter returns same normalized semantic contract.

## CONN-GAM-010
Read-only connector cannot perform write operations.

---

# 116. Cross-source evals

## CONN-X-001
GA4 current data stale:
no traffic-down event.

## CONN-X-002
GSC preliminary Search decline + mature GA4 decline:
evidence carries mixed maturity.

## CONN-X-003
GAM requests fall while GA4 views stable:
derived divergence can be computed with aligned intervals.

## CONN-X-004
GSC day boundary and GAM local day differ:
correlation uses UTC intervals, not labels.

## CONN-X-005
One connector unavailable:
incident continues with explicit observability limitation.

## CONN-X-006
All three connectors healthy but browser unavailable:
metric evidence remains valid; runtime evidence marked unavailable.

---

# 117. MVP implementation order

## C1 — Connection framework

Implement:
- data_connections;
- secret references;
- status;
- health;
- common errors;
- source_extracts.

## C2 — GA4

Implement:
- OAuth readonly;
- metadata;
- traffic hourly;
- behavior daily;
- backfill;
- response metadata.

## C3 — GSC

Implement:
- OAuth readonly;
- web daily;
- Discover daily;
- fresh/hourly optional path;
- backfill;
- URL Inspection on-demand.

## C4 — GAM

Implement:
- readonly auth;
- network discovery;
- report capability probe;
- inventory health;
- direct/programmatic composition;
- demand health.

## C5 — Cross-source normalized metrics

Implement:
- aligned time intervals;
- requests/view;
- impressions/view;
- divergence helpers.

## C6 — Incident drill-down

Implement validated Tier C query catalog.

Do not build C6 as arbitrary LLM-generated API requests.

---

# 118. MVP connector acceptance criteria

CONNECTORS v1 is acceptable when:

1. all production access is read-only;
2. OAuth/credentials are stored securely;
3. GA4/GSC/GAM connections have explicit health state;
4. onboarding runs a real capability probe;
5. source query definitions are versioned;
6. every extract preserves provenance;
7. recent/preliminary data remains distinguishable;
8. later reconciled extracts do not overwrite history;
9. missing data is never silently zero;
10. connector failure cannot generate publisher-business anomaly;
11. GA4 high-cardinality/threshold metadata is preserved;
12. GSC Search and Discover remain separate;
13. GSC final/all/hourly_all states are handled correctly;
14. GSC top-row/data limits are represented as limitations;
15. GAM report compatibility is validated per network;
16. GAM report runs handle asynchronous completion/pagination;
17. GAM network timezone/currency are preserved;
18. raw GAM revenue is contextual, not universal health;
19. direct/programmatic composition is available;
20. quota/rate-limit handling is bounded;
21. routine query set remains small;
22. incident queries come from validated definitions;
23. cross-source time buckets can be aligned explicitly;
24. source metric names/semantics remain namespaced;
25. no user-level analytics/auction warehouse is created;
26. one unavailable connector becomes an observability limitation, not a false conclusion;
27. data can be traced from metric point to source extract/query;
28. metric semantics changes are versioned;
29. tests cover auth, quota, missingness, freshness and partial results;
30. connectors remain implementation details behind common normalized contracts.

---

# 119. Codex rules for connector work

Codex MUST:

- consult current official provider docs before changing provider-specific behavior;
- use readonly OAuth scopes;
- preserve native metric/dimension names;
- version extract definitions;
- store source timezone;
- store retrieval/freshness metadata;
- use bounded retries;
- classify errors;
- cache/reuse mature extracts;
- test pagination;
- test preliminary → mature reconciliation;
- validate GAM report compatibility;
- validate GA4 dimension/metric compatibility where needed;
- treat GSC missing rows carefully;
- keep query dimension ingestion bounded;
- keep secrets out of DB/logs;
- update `DECISIONS.md` for material cadence/source changes.

Codex MUST NOT:

- request write scopes because they are easier;
- build arbitrary LLM-driven API query execution;
- convert missing data to zero;
- overwrite old extracts;
- merge preliminary and mature values without provenance;
- merge source metrics with different semantics;
- equate GA4 users with physical unique humans;
- equate GSC row absence with zero;
- equate GAM revenue with invoiced business revenue;
- create every possible dimension combination;
- ignore source timezone;
- bypass quotas using multiple projects/accounts;
- expose another tenant's connector data.

---

# 120. Current official reference points

The implementation must periodically recheck current official documentation.

## GA4

Primary:
Google Analytics Data API v1.

Current official docs define:
- Core reporting;
- current dimensions/metrics;
- metadata/compatibility;
- response metadata including high-cardinality `(other)` data loss;
- token-based quotas.

## Search Console

Primary:
Search Analytics API.

Current official docs define:
- `type=web/discover/...`;
- clicks/impressions/CTR/position;
- page/query/device/country/date/hour dimensions;
- `dataState=final/all/hourly_all`;
- incomplete-data metadata;
- row/load/quota limits.

## GAM

Primary:
Ad Manager API, with current REST Reports capability where validated.

Current official docs define:
- read-only OAuth scope;
- async report execution;
- dimension/metric/report-type compatibility;
- report result fetching;
- Ad Manager quotas/best practices.

Provider documentation is PLATFORM_CURRENT knowledge.

If docs change:
connector behavior and metric semantics must be reviewed.

---

# 121. Final connector principle

The connector layer succeeds when the Incident Engine can ask:

> **What happened to traffic, Google visibility and ad serving in this exact period and segment?**

and receive:

- a small relevant dataset;
- known semantics;
- known source;
- known time boundaries;
- known freshness;
- known limitations;
- reproducible query provenance.

It fails if it provides a giant pile of numbers without knowing:
- where they came from;
- whether they are complete;
- whether they are comparable;
- or what they actually mean.

# **Collect less. Preserve semantics. Reconcile later. Investigate deeply only when needed.**
