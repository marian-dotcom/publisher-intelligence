# Publisher Incident Intelligence

Repository foundation for a publisher operational-memory and incident-intelligence platform.

The product contracts live in the root Markdown files. Engineering work follows `AGENTS.md`, `DECISIONS.md`, `PLANS.md`, and the active ExecPlan under `plans/`.

Completed browser checkpoints persist compact rendered SEO evidence and atomically enqueue
deterministic semantic-event derivation. E1 point transitions are recorded with bounded occurrence
windows. E2 confirms persistent JavaScript errors, aggregates expected-slot loss and broad noindex
across representative URLs, keeps one active condition through repeated observations, and records
evidence-backed resolution without turning events into alerts or causal claims.

## Prerequisites

- Python 3.12
- `uv`
- Node.js 24 LTS
- `pnpm` 11
- Docker with Compose for PostgreSQL and MinIO integration checks
- Playwright's pinned Chromium build for browser checkpoints

## Local setup

```bash
cp .env.example .env
docker compose up -d postgres minio minio-init
uv --directory backend sync --all-groups --locked
uv --directory backend run playwright install --with-deps chromium
pnpm --dir frontend install --frozen-lockfile
uv --directory backend run alembic upgrade head
```

Start each process in a separate terminal:

```bash
make api
make worker
make scheduler
make frontend
```

## Performance-aware browser checkpoints (B8)

Register one explicit public pilot URL. The command also enqueues one immediate legacy B1
diagnostic run so an operator can verify the configuration without waiting for the next window:

```bash
uv --directory backend run python -m app.browser_cli register-and-enqueue \
  --tenant-slug pilot \
  --tenant-name "Pilot Tenant" \
  --publisher-name "Example Publisher" \
  --site-name "Example Site" \
  --url "https://www.example.com/"
```

Run the isolated browser worker in a separate terminal, or use `--once` for one polling cycle:

```bash
make browser-worker
uv --directory backend run python -m app.browser_worker --once
```

The scheduler idempotently materializes one desktop and one mobile run for every active monitored
URL in the site-local 00:00, 06:00, 12:00, and 18:00 windows. Jobs are deterministically staggered
inside the window. Repeated scheduler ticks do not create duplicate windows, runs, or jobs.

Each scheduled run uses a fresh non-persistent Chromium context and a frozen, versioned device and
interaction profile. B2 waits and scrolls deterministically to 25%, 50%, and 75% of the available
document range, records requested/actual positions, and captures the full-page screenshot last.
The versioned manifest preserves complete observer/action provenance and template identity. B3
derives a deterministic structural DOM artifact, stable script/network dependency identities, and
normalized JavaScript-error fingerprints. Article copy, timestamps, random IDs, auction IDs,
cache-busters, and URL query values are excluded from the normalized comparison state.

B4 installs a passive, bounded GPT observer before navigation. It inventories publisher-defined
slots and preserves the independently observed `defined`, `slotRequested`,
`slotResponseReceived`, `slotRenderEnded`, `slotOnload`, and `impressionViewable` stages. Existing
deterministic scroll steps run before the final snapshot, so lazy slots remain distinguishable from
eager slots. Template-configured expectations are merged with discovered slots; an expected slot
that is absent is stored with `present=false` and null lifecycle timestamps rather than invented
zeros. GPT absence and non-observability are explicit collector outcomes and do not erase B1–B3
evidence.

B5 adds a passive TCF observer using `ping`, `addEventListener`, and listener cleanup. Core
desktop/mobile scenarios carry a `PRIMARY` consent path; a separate mobile `REJECT` canary remains
outside the six-hour scheduler allowlist. A checkpoint clicks only an exact selector supplied in
the template's versioned `expected_features.consent_adapter` configuration. It never guesses from
button text or scans for a plausible action. If no CMP/API is present, the checkpoint may remain
complete. If a CMP is present but its required configured action is unavailable or fails, the run
is partial and preserves the evidence already collected.

When a CMP is observed, B5 stores bounded API/UI readiness, action timing/status, safe CMP
identifiers, and only a SHA-256 hash of the TC String. It captures pre/post viewport evidence and
aggregates stable network dependencies into `PRE_CONSENT`, `POST_ACCEPT`, or `POST_REJECT` phases.
Reject completion is valid evidence, not an operational failure or compliance conclusion. The
manifest preserves the frozen consent path and phase evidence alongside B1–B4 output.

B6 installs a passive Prebid observer before navigation without creating or mutating `pbjs` or
its command queue. When the publisher exposes the read-only public event/configuration APIs, the
observer keeps bounded, sanitized auction stages in page memory, replaces raw auction IDs with
run-local keys, and aggregates bidder request/response/no-bid/timeout/win counts plus observable
response timing. It stores only targeting key names, never targeting values, bid prices, deal or
creative data, raw auction/bid IDs, request bodies, headers, cookies, or OpenRTB payloads.

Each observable auction can be correlated with the first sanitized GAM request that starts after
the auction. A visible Prebid Server endpoint without client-side bidder events is recorded as
`NOT_OBSERVABLE`; the checkpoint does not invent hidden server bidders or timing. Prebid absence
is an explicit collector outcome and does not make an otherwise successful checkpoint partial.
Manifest v6 records the bounded Prebid evidence alongside the preserved B1–B5 output.

B7 passively observes native web video elements without invoking playback or modifying player
state. It records a hash-derived structural identity, final presence/visibility/dimensions,
observed sticky/fixed transitions during the existing deterministic scroll profile, readable
autoplay/mute/native-controls state, an accessible dismiss-control signal when present, and
publisher/browser playback-start evidence. Custom or cross-origin player APIs are not
reverse-engineered.

Sanitized network metadata is classified into bounded VAST-request, VAST HTTP/failure, and media
request counts. No VAST XML, response/request body, media bytes, headers, cookies, query values,
tracking URLs, or player/media identifiers are retained. Page-level network counts are assigned to
a player only when exactly one observable player makes the correlation unambiguous. Video network
evidence without an inspectable native player is `NOT_OBSERVABLE`, and a VAST response is never
reported as proof of playback or impression. Manifest v7 records this B7 evidence alongside the
preserved B1–B6 output.

B8 installs a small native PerformanceObserver collector before navigation. After the configured
interaction sequence and before DOM serialization/full-page screenshot work, it snapshots bounded
navigation timing, the latest foreground LCP candidate, standard CLS session windows, Event
Timing interaction latency when a qualifying interaction exists, long-task totals, aggregate
resource timing, and DOM node count. It stores no resource URLs, query values, DOM identities,
layout-shift nodes, task attribution stacks, or trace archives.

Every performance row and manifest section is explicitly `synthetic_browser`, scenario-bound, and
collector-versioned. Missing APIs or missing qualifying interactions remain null with limitation
codes; they are not converted to zero. These values are not real-user p75 Core Web Vitals, a
Lighthouse audit, a performance event, an SEO/ranking conclusion, or causal proof. Manifest v8
records B8 alongside the preserved B1–B7 evidence.

## GA4 read-only connector (C1/C2)

The first business-data connector uses only the Google Analytics Data API read-only scope and two
versioned aggregate reports: `GA4_TRAFFIC_HOURLY_V1` and `GA4_BEHAVIOR_DAILY_V1`. Property metadata
and a small report probe must succeed before a connection becomes `CONNECTED`. The general worker
handles `GA4_EXTRACT` jobs; the scheduler requests low-cardinality traffic data every two hours and
separate mature traffic/behavior reconciliations after 03:00 in the GA4 property timezone.

PostgreSQL stores only the property ID, granted scope, a secret reference, connection health,
immutable extract provenance, canonical metric series, and append-only points. The worker resolves
an access token only at execution time. Job payloads, source extracts, metric rows, errors, and logs
never contain the token. The included `env:NAME` resolver is limited to local/test; production
rejects it until a managed secret provider and OAuth onboarding flow are implemented.

Connector tests use sanitized metadata, complete, behavior, and thresholded fixtures and never
call Google. A missing row produces no point. Thresholding, sampling, restrictions, and
`dataLossFromOtherRow` remain extract limitations; they do not become zero traffic or an incident
conclusion. Preliminary operational data and later mature reconciliation remain separate extracts.

## Google Search Console read-only connector (C3)

The GSC connector accepts only the exact `webmasters.readonly` scope and preserves Domain and
URL-prefix property identifiers without collapsing their semantics. `sites.list` permission
discovery plus safe one-day `web` and `discover` probes must succeed before the connection becomes
`CONNECTED`; a valid Discover probe with zero rows is not a connector failure.

Routine definitions keep Search and Discover separate. Final daily Search/Discover extracts run
as seven-day mature reconciliations, while the low-cardinality hourly Search path runs every four
hours as preliminary evidence. Search Analytics dates/hours remain in
`America/Los_Angeles` source time and are also stored as explicit UTC intervals. `final`, `all`,
and `hourly_all` definitions retain incomplete-data metadata, and each point at or after an
incomplete boundary remains preliminary.

Requests are paged at no more than 25,000 rows and stop at the documented 50,000-row daily/type
exposure cap. The source's top-row limitation is always retained; missing rows never become zero.
Routine cubes exclude the privacy-sensitive query dimension. URL Inspection is read-only and
on-demand, stores only a bounded sanitized current-index view, never claims a live URL test, and a
URL Inspection quota error does not disable routine Search Analytics extraction. Tests use only
sanitized fixtures and never call Google.

## Google Ad Manager read-only connector (C4)

The GAM connector accepts only the exact `admanager.readonly` scope, discovers the configured
numeric network, and preserves its reporting timezone and ISO-4217 currency. Before a connection
becomes `CONNECTED`, it verifies six reusable report resources: TODAY and LAST_7_DAYS profiles for
`GAM_INVENTORY_HEALTH_V1`, `GAM_DEMAND_HEALTH_V1`, and
`GAM_DELIVERY_COMPOSITION_V1`. Every report must match the fixed dimension/metric order, use
historical reporting and publisher time, and keep expanded compatibility disabled.

The current REST API permits report list/get/run/result reads under the narrow scope, while report
creation still requires the broad write scope. A GAM administrator therefore preconfigures the
reusable reports; this connector never creates, patches, or deletes one. Runs are asynchronous,
poll with bounded exponential backoff, fetch every page at up to 10,000 rows, and verify the
provider's total row count before an extract can become COMPLETE. A partial result remains a
connector failure, not zero inventory.

Operational TODAY cubes run every two hours. LAST_7_DAYS reconciliation runs after 06:00 in the
network timezone. Recent network-local hours remain PRELIMINARY; older rows become MATURE in later
extracts rather than overwriting history. Currency is part of GAM series identity and
provenance, but eCPM/value is diagnostic context rather than publisher invoicing truth. Routine
cubes do not collect order or advertiser names, create events, or label direct/programmatic mix as
good or bad. Tests use only sanitized fixtures and never call Google.

## Cross-source normalized metrics (C5)

The metrics service aligns only exact UTC hourly intervals from the fixed GA4 traffic and GAM
inventory definitions. It persists `derived.requests_per_view_v1` and
`derived.impressions_per_view_v1` with their numerator and denominator, strict equal non-stale
freshness, versioned rule/engine/alignment policies, and links to every selected source metric
point. GA4 measured screen/page views remain a measurement denominator, not physical pageview
truth.

Overlapping preliminary and reconciled extracts are not summed twice: one best current observation
is selected per source series and interval, preferring mature evidence and then the latest
retrieval. Re-running identical inputs is idempotent; changed reconciled inputs create a new
immutable derivation. Missing inputs, zero measured views, stale/unknown data, incompatible
freshness, and unequal intervals produce no derived point rather than a fabricated zero.

The scheduler queues a bounded 48-hour `DERIVE_CROSS_SOURCE` pass every two hours for sites with
both GA4 and GAM connections. These jobs run below connector extraction priority. The included
divergence helper compares aligned numeric movement only; it does not create an event, incident,
alert, threshold, or causal conclusion.

## Validated incident drill-downs (C6)

Tier C is on-demand only. The versioned catalog maps twelve semantic requests to fixed GA4, GSC,
or GAM dimensions and metrics; callers and LLM output cannot provide a provider endpoint, query
JSON, dimension, metric, filter operator, or report resource. GA4 exposes only definitions whose
fields passed property metadata validation, GSC uses the fixed Search/Discover shapes proven by
connection validation, and GAM requires optional administrator-created report/profile bindings
whose exact fingerprints passed the same read-only compatibility checks as routine reports.

GA4/GSC requests use explicit windows of at most seven inclusive days. GAM requests use only the
prevalidated `TODAY` or `LAST_7_DAYS` profile. The sole dynamic query value is an exact GSC page
URL for `web_top_queries_for_page`; it is validated as belonging to the configured property and
is placed into a fixed equality filter. Query-level rows remain confidential, top-row/cardinality
limitations remain visible, and absent rows never become zero.

`CONNECTOR_DRILLDOWN` jobs are inserted idempotently under a locked tenant/site/connection gate.
One investigation may request at most four distinct drill-downs and one connection may run at
most eight per UTC day. Jobs contain no credentials or arbitrary query fragments, Tier C has no
scheduler path, and every result remains an immutable `source_extract` with catalog version,
investigation correlation, cost units, exact provider definition, and limitations. The opaque
investigation UUID is correlation only until the incident lifecycle tables land; it grants no
authorization and is never used to access incident data.

Comparison prefers the previous run for the same URL and exact scenario. When an operator retires
one representative URL and creates another under the same template, lineage may fall back to the
same tenant/site/template and exact scenario. The manifest records whether comparison used the
exact URL or template rotation and emits only bounded additions, removals, or structural changes.
These differences are evidence: they are not events, alerts, severity, or causal conclusions.

PostgreSQL stores authoritative metadata; private S3-compatible storage holds viewport/full-page
screenshots, raw DOM, long-lived normalized structural DOM, manifests, and their hashes. Stable
script/network entities and append-only observations live in PostgreSQL. No public artifact URLs
are created, and historical raw checkpoints are never rewritten when a normalizer changes.
Template expectations and specialized append-only GPT slot observations also live in PostgreSQL;
creative and line-item identifiers are observation details and never stable identity.

`BROWSER_ALLOW_PRIVATE_NETWORKS` defaults to `false` and must remain false outside controlled
tests. The application validates DNS destinations and intercepts browser requests, but production
deployment still requires network-level egress enforcement to cover DNS rebinding and browser
runtime failures. B8 does not configure, display, refresh, or click ads; request bids; change ad
targeting; play, seek, mute, dismiss, or otherwise control video; infer CMP actions; decode or
retain raw consent strings; authenticate; bypass paywalls; run stealth; discover templates
automatically; or make compliance, revenue, event, incident, causality, player-quality, or AI
judgments.

Apply or inspect migrations independently:

```bash
make migrate
uv --directory backend run alembic current
uv --directory backend run alembic history
```

## Health endpoints

- `GET /health/live` checks process liveness only.
- `GET /health/ready` checks PostgreSQL and object-storage readiness without returning credentials or connection strings.

## Validation

```bash
make check
make test-integration
```

If Docker is unavailable, run the local unit/lint/build checks and rely on GitHub Actions for PostgreSQL and MinIO integration validation. Do not treat skipped integration tests as passing local integration tests.

## Common setup failures

- A readiness `503` means PostgreSQL or MinIO is unavailable; liveness at `/health/live` remains independent.
- Port conflicts on `5432`, `9000`, or `9001` require stopping the conflicting local service or changing the local Compose mapping and matching `.env` value.
- A locked-install failure means the manifest and lockfile differ; regenerate the relevant lockfile intentionally and include both changes in review.
- Migration errors should be investigated before retrying. Destructive downgrades are only for disposable local or CI databases.
- The values in `.env.example` and Compose are local-only placeholders, never production credentials.

## Repository boundaries

EP-009 completes Browser v1. EP-010 through EP-014 add source persistence, read-only GA4/GSC/GAM
collection, cross-source ratios, factual divergence helpers, and bounded incident drill-down.
EP-015 and EP-016 add deterministic semantic browser events, evidence references, confirmation,
deduplication, active-condition support, and evidence-backed recovery without turning events into
alerts or causal conclusions. EP-017 is in progress: M1 adds immutable robots.txt/ads.txt snapshot
and normalized ads.txt-record persistence, but public HTTP fetching, scheduling, second-check
validation, and E3 event derivation are not implemented yet.

The repository still excludes production OAuth onboarding, a managed secret provider, provider
write access, alert delivery, Home/Timeline UI, automated incident conclusions, LLM-selected
queries, and production rollout. Refresh this summary after no more than three completed EPs, and
earlier whenever an EP materially changes the implemented product or security boundary. Always
state the latest fully covered EP and distinguish partial work from completed capability.
