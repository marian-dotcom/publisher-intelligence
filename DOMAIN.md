# DOMAIN.md
## Publisher Incident Intelligence — Domain Knowledge Base v1.0

**Status:** MVP foundation / expert-review candidate  
**Last research pass:** 2026-08-12  
**Primary product role:** domain model for monitoring, normalization, event correlation, incident investigation, Codex implementation and evals  
**Initial operating scope:** one to a few news/media publisher domains  
**Primary connected data:** GA4, Google Search Console, Google Ad Manager read-only reporting/configuration metadata, browser checkpoints  
**Browser observation cadence:** full checkpoint every 6 hours, regardless of whether a change is detected

---

This document is intentionally deeper than a glossary.

For each important component it tries to capture:

**definition → mechanism → inputs → outputs → dependencies → observability → normal variation → failure modes → downstream effects → confounders → diagnostic tests → exclusion tests → recovery expectations → evidence class → source freshness**

The aim is not to make the software “know AdTech vocabulary.”  
The aim is to give the Incident Engine enough domain structure to reason like a disciplined senior publisher operator rather than a generic anomaly detector.

---

# 1. Product domain and non-goals

The product is a **Publisher Incident Intelligence** system: an operational memory and investigation layer for digital publishers.

It continuously:
- observes the public/runtime state of representative pages;
- records immutable periodic checkpoints;
- ingests selected publisher metrics and configuration state;
- records external ecosystem events;
- normalizes meaningful changes into events;
- builds a chronological and relational event graph;
- helps reconstruct context when the publisher reports a problem.

The product is **not** primarily:
- a generic SEO auditor;
- a revenue optimizer;
- a replacement for GAM;
- a replacement for GA4;
- a generic uptime tool;
- a deterministic Google-ranking predictor;
- an autonomous production-change agent in the MVP.

The product may observe revenue-related symptoms, but raw total GAM revenue is **not a default health SLI** because direct/guaranteed campaigns, booked rates, zero/nominal values, sponsorships and commercial accounting can make ad-server revenue diverge from the publisher’s true invoiced business result. Revenue becomes diagnostically useful when decomposed into comparable demand/inventory segments and when the publisher explicitly wants it investigated.

Product principle:

> **Observe broadly. Store evidence. Alert rarely. Investigate deeply on demand.**

[PRODUCT-SPEC]

# 2. Knowledge classes and epistemic discipline

Every knowledge item and every incident conclusion must carry a class.

## 2.1 CANONICAL_CURRENT
Current official platform documentation or current technical standard.

Examples:
- current GAM report semantics;
- current GPT event semantics;
- current ads.txt specification;
- current TCF specification;
- current Google Search documentation.

## 2.2 CANONICAL_DURABLE
Fundamental mechanism likely to remain stable even if implementations evolve.

Examples:
- latency is composed of multiple delays;
- a rate has numerator and denominator;
- an ad server performs eligibility/selection/delivery;
- a browser-side JS failure can prevent downstream requests.

## 2.3 DERIVED
A logical relationship inferred from canonical facts.

Example:
stable pageviews + fewer GAM requests weakens a pure traffic-loss hypothesis and increases the relevance of request-generation mechanisms.

## 2.4 OPERATIONAL
A practitioner heuristic. Useful, but not guaranteed.

Example:
compare monetization at the same hour/day pattern before treating a short eCPM move as an incident.

## 2.5 INCIDENT_BACKED
A pattern supported by one or more documented real incidents in the incident corpus.

It is stronger than an unsupported heuristic but does not become universal law.

## 2.6 OBSERVED
Publisher-specific evidence collected by the platform:
- API extract;
- browser event;
- checkpoint;
- screenshot;
- DOM state;
- network request;
- external event.

## 2.7 UNKNOWN / CONTESTED
Evidence is insufficient, hidden, vendor-specific or contradictory.

The engine must be allowed to return:
**UNRESOLVED — no strong cause identified.**

## 2.8 Source precedence
When sources conflict:

1. current official specification / current platform docs;
2. current official implementation docs;
3. primary research;
4. current technical/practitioner material;
5. durable concepts from books;
6. expert operational knowledge;
7. community incidents.

Older books never override current GAM, GPT, Search, TCF, Prebid or IAB specifications.

[SRC-DDIA] [SRC-ADTECH-BOOK] [SRC-GAM] [SRC-IAB] [SRC-TCF]

# 3. Core causal reasoning rules

## IR-001 — Baseline first
Never investigate only the post-incident period.

At minimum construct:
- baseline;
- pre-incident;
- incident;
- post-intervention/recovery when available.

## IR-002 — Localize before explaining
Before ranking causes, determine whether the symptom is:
- site-wide or local;
- Search/Discover/direct/social-specific;
- desktop/mobile-specific;
- geography-specific;
- category/template-specific;
- ad-unit/format-specific;
- bidder/demand-channel-specific.

## IR-003 — Temporal order is necessary but not sufficient
A candidate normally must precede the symptom at a plausible latency, but precedence alone does not prove causation.

## IR-004 — Require a mechanism
A useful hypothesis must explain **how** the candidate could produce the observed symptom.

## IR-005 — Match the affected segment
A candidate affecting the same device/template/geo/source/ad unit receives more causal weight.

## IR-006 — Use intermediate metrics
Prefer:
`change → intermediate signal → symptom`
over:
`change → symptom`.

## IR-007 — Search for evidence against every top hypothesis
Explicitly ask:
- did the decline begin earlier?
- are unaffected pages using the same component?
- did a rollback fail?
- did a control segment remain stable?
- is a platform-wide event a better explanation?

## IR-008 — Intervention evidence is strong
`introduced → symptom → removed → recovery`
is powerful evidence when recovery latency is plausible.

## IR-009 — Failed rollback matters
If a suspected component is removed and the symptom continues on the same trajectory, reduce confidence that it was the primary cause.

## IR-010 — External cohort evidence matters
When comparable publishers experience the same source/product-specific anomaly in the same window, external-cause relevance rises.

## IR-011 — Do not force a single cause
Incidents may be:
- multi-causal;
- cascading;
- partially explained;
- unresolved.

## IR-012 — Do not double-count descendants
If impressions fall and revenue falls mechanically because of fewer impressions, those are not two independent pieces of causal evidence.

## IR-013 — Recovery latency is symptom-dependent
Ad request/runtime fixes may be visible rapidly. Search/indexing recovery may take materially longer.

[SRC-SRE] [SRC-DDIA] [INCIDENT-CORPUS]

# 4. System-of-systems model of a publisher

A modern publisher is simultaneously:

### Content system
CMS, article templates, category structure, metadata, media, internal linking.

### Browser application
HTML, CSS, JavaScript, third-party dependencies, iframes, storage, rendering.

### Traffic system
Search, Discover, Direct, Social, Referral, newsletters/push and other acquisition sources.

### Measurement system
GA4, Search Console and platform-specific ad reporting.

### Inventory generator
Templates create potential monetizable positions and video opportunities.

### Ad-serving system
GPT, GAM, direct/guaranteed delivery, Ad Exchange, Open Bidding, deals and possibly header bidding.

### Supply-chain participant
ads.txt, sellers.json, SupplyChain information and seller relationships.

### Consent/privacy runtime
CMP, TCF signals, vendor eligibility and consent-dependent execution.

### Video runtime
Player, VAST, renderer, autoplay/mute/controls/sticky state and video demand.

### Search participant
crawlability, indexability, canonicalization, rendering, ranking/serving and Discover.

### Operational organization
Humans and vendors deploy code/configuration and approve or reverse changes.

A symptom in one layer may be caused upstream and observed downstream.  
The Incident Engine must therefore reason across layers, not inside a single dashboard.

[PRODUCT-SPEC] [SRC-ADTECH-BOOK]

# 5. Publisher entity ontology

The platform should use stable entities rather than raw page strings.

## Core entities
- Publisher
- Domain
- Site
- Page
- Template
- Content category
- Browser checkpoint
- Script dependency
- Network dependency
- CMP
- Video player
- GPT slot
- GAM ad unit
- GAM order
- GAM line item
- Creative
- Demand channel
- Yield partner
- Prebid ad unit
- Bidder
- Deal
- Pricing rule
- ads.txt seller record
- Search page/query
- External ecosystem event
- Operational change
- Incident
- Hypothesis
- Evidence item
- Last Known Good checkpoint

## Important namespace rule
Terms that look identical can describe different objects.

For example:
- visible DOM ad position;
- GPT slot;
- GAM ad unit;
- Prebid `adUnit`.

They may correspond to each other, but must not be merged solely by human-readable names.

Entity linking should store:
- source system;
- native ID if available;
- normalized name;
- inferred relationships;
- confidence.

[SRC-ADTECH-BOOK] [SRC-GAM] [SRC-PREBID]

# 6. Template-first site modeling

Monitoring should reason primarily in **template classes**, not only individual URLs.

Typical news publisher templates:
- homepage;
- category/section;
- standard article;
- video article;
- gallery;
- live blog;
- tag/topic;
- special project.

Why:
a URL changes content constantly, while a template contains the repeatable technical structure that generates incidents.

## Template fingerprint
Potential stable fingerprint inputs:
- DOM structural tree after volatile-content removal;
- stable CSS/class patterns;
- script inventory;
- GPT slot set/order;
- player presence/config signature;
- metadata patterns;
- canonical/robots directives;
- content-type clues.

## High-value localization
If only video articles degrade:
global-demand hypotheses weaken and player/template-specific hypotheses rise.

If every template degrades:
global site, analytics, consent, GAM or external events rise.

[PRODUCT-SPEC] [DERIVED]

# 7. Browser checkpoint model — the black box

Every representative page receives a **full immutable checkpoint every 6 hours**, even if nothing appears to have changed.

This is deliberate.

A change may occur at 14:00 and a failure may emerge at 22:00 because:
- cache expires;
- a remote config activates;
- demand changes;
- a scheduled campaign starts;
- consent/runtime path changes;
- an external dependency becomes unavailable.

If the system only records when it detects a diff, it may lose the clean state needed to reconstruct the transition.

## Checkpoint contents
- timestamp;
- representative URL and template;
- full-page screenshot;
- viewport screenshot where useful;
- normalized DOM representation;
- relevant computed structural properties;
- script inventory;
- third-party/network-domain inventory;
- important request timings/errors;
- console/page errors;
- GPT slot/lifecycle state;
- Prebid state where detectable;
- CMP/TCF observable state;
- video/player observable state;
- robots/meta/canonical state;
- synthetic performance metrics;
- observation environment.

## Checkpoint is not an event
A checkpoint is evidence/state.

An event is a meaningful interpretation of change:
`robots_broad_block_detected`,
not merely:
`checkpoint_2026_08_12_18`.

[PRODUCT-SPEC] [SRC-DDIA]

# 8. Observation environment and reproducibility

Every browser observation must store the environment because page behavior is conditional.

At minimum:
- browser build;
- viewport/device profile;
- user agent;
- region/egress location;
- navigation URL;
- cache state;
- cookie/storage state;
- consent scenario;
- interaction script;
- network emulation if any;
- experiment/variant clues where detectable.

## Controlled scenarios
Useful MVP scenarios:
1. clean first visit;
2. consent accepted;
3. consent rejected where feasible;
4. desktop;
5. mobile.

Do not multiply scenarios until a pilot proves diagnostic value.

## Reproducibility rule
A diff between two checkpoints is high confidence only when observation conditions are sufficiently comparable.

[SRC-HPBN] [DERIVED]

# 9. Browser/network mechanics relevant to diagnosis

Network time is not one thing.

Durable contributors include:
- propagation delay;
- transmission delay;
- processing delay;
- queuing delay;
- connection setup;
- TLS/security negotiation;
- connection reuse;
- cache behavior;
- server response time;
- resource size;
- browser scheduling.

A third-party resource may be:
- not requested;
- queued;
- DNS/connection delayed;
- redirected;
- blocked;
- timed out;
- downloaded slowly;
- loaded successfully but executed late;
- served from cache.

The monitor should preserve this distinction.

## Diagnostic consequence
A header-bidding or CMP script can exist in DOM/HTML and still fail operationally because its request or execution is delayed.

Likewise, a visual page can appear normal while an analytics or ad measurement pixel fails.

[SRC-HPBN]

# 10. Network dependency inventory

Normalize network activity by **dependency identity**, not full volatile URLs.

Store:
- registrable domain;
- host;
- path family where meaningful;
- initiator;
- resource type;
- first-party vs third-party;
- functional category;
- status/error;
- repeated timing summary.

Suggested categories:
- publisher/API;
- CDN;
- analytics;
- Google ad serving;
- header bidding/SSP;
- CMP/privacy;
- player/video;
- recommendation;
- social;
- verification/measurement;
- unknown.

## Event candidates
- new persistent third-party dependency;
- dependency disappeared;
- latency regression;
- repeated 4xx/5xx;
- CSP/network blocking;
- new redirect chain.

One failed pixel in one checkpoint is not automatically an incident.

[SRC-HPBN] [SRC-ADTECH-BOOK]

# 11. JavaScript runtime model

Collect **all** console/page JavaScript errors, but classify them before surfacing.

The product should not alert the publisher every time a social widget logs an error.

## High relevance characteristics
- new relative to Last Known Good;
- persistent across checkpoints;
- appears on affected templates;
- occurs before GPT/Prebid/CMP/player initialization;
- prevents expected network requests;
- breaks DOM/slot creation;
- originates in publisher-owned critical code.

## Lower relevance
- transient creative errors;
- isolated third-party widgets;
- one-off blocked trackers;
- browser-extension-like noise;
- errors on unaffected templates.

## Strong evidence chain
`new uncaught exception`
→ `GPT initialization not reached`
→ `slotRequested absent`
→ `GAM request volume falls`
→ `impressions fall`

This is stronger than:
`JS error appeared near revenue decline`.

[PRODUCT-SPEC] [DERIVED] [INCIDENT-CORPUS]

# 12. Content Security Policy, browser restrictions and blocking

Browser security/privacy controls can selectively prevent scripts, frames or network calls.

Relevant observable classes:
- Content Security Policy errors;
- mixed-content blocks;
- CORS failures;
- blocked third-party cookies/storage;
- browser privacy restrictions;
- ad blockers in real-user populations.

The synthetic MVP browser should normally be clean and controlled.  
Therefore it cannot measure population-level ad-block usage by itself.

If browser-specific or user-specific blocking is suspected, the engine should say:
**not directly observable with current synthetic checkpoint**.

[DERIVED] [SRC-ADTECH-BOOK]

# 13. Core Web Vitals and performance provenance

Core Web Vitals:
- **LCP** — loading performance;
- **INP** — interaction responsiveness;
- **CLS** — visual stability.

Reference good thresholds remain:
- LCP ≤ 2.5 s;
- INP ≤ 200 ms;
- CLS ≤ 0.1;
typically evaluated at the 75th percentile for field data.

## Critical distinction
Synthetic checkpoint performance and real-user field data are different evidence classes.

Store:
`performance_source = synthetic | field | publisher_rum`

## Publisher-specific failure mechanisms
### CLS
- missing reserved ad space;
- late ad resizing;
- player insertion/resizing;
- sticky/floating transitions;
- consent UI;
- embeds/iframes;
- dynamic modules.

### LCP
- TTFB;
- resource load delay;
- large media;
- render-blocking resources;
- third-party competition;
- JS/render delay.

### INP
- long tasks;
- heavy JS;
- third-party execution;
- event-handler work.

## Prohibited inference
`CWV got worse → Google penalized the site`

is not allowed.

A valid statement is:
`CWV worsened; this is a real UX regression and a documented page-experience signal, but it does not prove a ranking cause.`

[SRC-WEB-VITALS] [SRC-CWV-ADS] [SRC-SEARCH]

# 14. Field versus lab blind spots

Field and lab can disagree for legitimate reasons.

Examples:
- real users have different devices/networks;
- consent paths differ;
- post-load interactions trigger layout shifts;
- cross-origin iframe shifts can be hard for lab tooling to attribute;
- ads and creative randomness differ;
- synthetic crawler may not scroll or interact like users.

The incident corpus contains publisher cases where lab CLS looked healthy while field CLS remained poor, reinforcing the rule that synthetic monitoring is evidence, not universal production truth.

Diagnostic output should always name measurement provenance.

[SRC-WEB-VITALS] [INCIDENT-CORPUS]

# 15. GA4 role in the MVP

GA4 is the primary publisher traffic/behavior telemetry source.

## Useful metric families
- active users;
- sessions;
- views;
- engaged sessions;
- engagement rate;
- events;
- views per user;
- optionally scroll/engagement events if implementation quality is known.

## Useful dimensions
- date/hour;
- landing page;
- page path;
- source/medium;
- default channel group;
- device category;
- country;
- publisher content/category dimension where configured.

## Category mapping preference
1. publisher-provided clean custom dimension;
2. deterministic URL taxonomy;
3. crawler-derived template/category;
4. manual map.

Store mapping provenance.

[SRC-GA4]

# 16. GA4 is measurement, not physical truth

GA4 reports are shaped by measurement configuration and reporting semantics.

Current Data API caveats include:
- reporting identity affects user deduplication/counts;
- high-cardinality dimensions can create an `(other)` row;
- data thresholding can exclude small rows;
- response metadata can expose thresholding/data-loss conditions;
- quotas depend on query complexity, rows, columns, filters and date ranges.

Therefore:

## Measurement integrity is a first-class hypothesis
A drop in GA4 can be caused by:
- tag removed;
- consent gating;
- duplicate/suppressed page_view;
- SPA/history tracking change;
- channel attribution change;
- reporting/data maturity issue.

## Required metadata
For every API extraction store:
- query definition;
- dimension/metric set;
- property;
- time zone context;
- retrieval time;
- response metadata;
- thresholding/data-loss flags;
- quota metadata if requested.

[SRC-GA4-DATA] [SRC-GA4-EXPECTATIONS] [INCIDENT-CORPUS]

# 17. GA4 traffic diagnostic decomposition

When a publisher reports “traffic down,” decompose before causal search.

## T-001 — Site-wide measured decline
Users, sessions and views down across most sources/templates.

Investigate:
- GA4 instrumentation;
- site availability;
- broad site change;
- major acquisition/editorial change.

## T-002 — Google-only decline
Search/Discover down, Direct/Social relatively stable.

Increase relevance:
- Search technical;
- Google external event;
- content/query demand.

Decrease relevance:
- generic site-wide analytics outage, unless Search instrumentation differs.

## T-003 — Mobile-only decline
Increase relevance:
- mobile template;
- CMP/browser runtime;
- mobile rendering;
- device-specific acquisition.

## T-004 — Users stable, views/user down
Potential:
- engagement/navigation;
- gallery/infinite scroll;
- internal linking;
- measurement.

Do not call it audience/reach loss without further evidence.

[DERIVED] [INCIDENT-CORPUS]

# 18. Behavioral ratios

Ratios help distinguish audience volume from consumption behavior.

Examples:
- views / active user;
- sessions / user;
- ad requests / view;
- impressions / view;
- impressions / ad request;
- viewable impressions / measurable impressions.

For every rate:
**store numerator and denominator**.

A rate can change because:
- numerator changed;
- denominator changed;
- both changed.

Never treat a rate as an atomic fact.

[PRODUCT-SPEC] [DERIVED]

# 19. Google Search observable model

Google publicly describes broad stages:
1. crawling;
2. indexing;
3. serving/ranking.

The exact ranking system is not fully observable.

The product can observe:
- technical accessibility;
- indexability directives;
- Search Console outputs;
- published updates/incidents;
- page/template changes;
- mobile/rendered state.

The product cannot truthfully say:
“Google reduced ranking because hidden factor X changed by Y%.”

[SRC-SEARCH-HOW]

# 20. Crawlability

High-value crawlability signals:
- HTTP status;
- DNS/availability;
- robots.txt;
- redirects;
- resource accessibility;
- rendered links/content;
- sitemap changes.

## robots.txt
robots.txt controls crawler access.

Critical events:
- broad new Disallow;
- important section blocked;
- unexpected user-agent rule;
- complete file replacement;
- file unavailable/malformed if behavior changes materially.

Important:
blocking a URL in robots.txt is not equivalent to a reliable de-indexing instruction.

[SRC-SEARCH-ROBOTS]

# 21. Indexability and canonicalization

## noindex
A noindex directive can prevent indexing when Google can crawl and read it.

Important interaction:
if robots blocks crawling, Google may be unable to read the noindex directive.

## canonical
Canonicalization signals the preferred representative among duplicate/near-duplicate URLs.

Monitor:
- self-canonical changed;
- canonical target domain/path changed;
- canonical disappears;
- template-wide canonical pattern change.

Treat a broad incorrect canonical change as high severity.

## sitemap
Sitemaps help discovery/monitoring but do not guarantee indexing.

[SRC-SEARCH-NOINDEX] [SRC-SEARCH-CANONICAL] [SRC-SEARCH-SITEMAP]

# 22. JavaScript SEO and mobile state

Google can process JavaScript, but rendering and content availability still matter.

Monitor on representative mobile pages:
- important content present after render;
- title/meta/canonical after render;
- links;
- blocked resources;
- JS exceptions;
- mobile/desktop structural divergence.

Google uses mobile-first indexing, so mobile-specific differences deserve elevated Search relevance.

The crawler should not pretend that successful visual rendering in one Chromium session guarantees identical Googlebot processing.

[SRC-SEARCH-JS] [SRC-SEARCH-MOBILE]

# 23. Search Console diagnostic semantics

Search Console gives a different view than GA4.

Core Search performance metrics:
- clicks;
- impressions;
- CTR;
- average position.

High-value decompositions:
- query;
- page;
- device;
- country;
- search appearance;
- date.

## Diagnostic patterns

### Impressions down
Visibility/search demand/indexing/ranking hypotheses rise.

### Impressions stable, CTR down
Potential:
- SERP composition;
- title/snippet;
- query mix;
- competition.

### Position down
Ranking/content/competitive/system factors rise.

### Position stable, clicks down
CTR/search-demand/query-mix explanations become important.

## API limitation
Search Analytics API is not a full raw query log; row limits and data aggregation mean absence of a row is not proof of zero activity.

[SRC-GSC-API] [SRC-GSC-LIMITS]

# 24. GA4 versus Search Console discrepancies

GA4 and Search Console should not be forced to match exactly.

They differ in:
- source of measurement;
- canonical URL treatment;
- non-HTML/Search destinations;
- bot/measurement behavior;
- session/user versus Search click semantics;
- consent/browser execution.

Use them as **independent perspectives**.

Diagnostic value rises when:
- GSC Search clicks drop and GA4 Organic Search sessions drop similarly;
- one changes while the other remains stable, indicating measurement/definition issues worth investigating.

[SRC-GA4-GSC]

# 25. Google Discover

Discover is personalized and inherently more volatile than ordinary Search.

A page can be technically eligible without receiving distribution.

Documented causes of change include:
- user interests;
- content types represented;
- system changes;
- policy/manual-action effects.

## Rules
### D-001
Discover update + publisher decline = external event relevance, not proof.

### D-002
Discover-only decline with stable Direct/Social/Search can be a Discover-specific distribution event.

### D-003
Template-specific technical change + template-specific Discover decline raises local relevance.

### D-004
Do not promise Discover eligibility or recovery.

### D-005
Do not infer a technical cause solely because the publisher wants a technical explanation.

[SRC-DISCOVER] [INCIDENT-CORPUS]

# 26. Google external intelligence layer

Google-originated events are first-class external timeline events.

Track:
- Core Updates;
- Spam Updates;
- Discover updates;
- Search ranking/serving/indexing incidents;
- Publisher Policy changes;
- GAM platform incidents;
- GPT releases/behavior changes;
- API/reporting changes relevant to our connectors.

Each record stores:
- official source;
- announced start;
- rollout/end if known;
- affected product;
- description;
- version/freshness.

## Rule
An external event is context until matched to a publisher symptom by:
- timing;
- product/source;
- segment;
- plausible mechanism;
- contradicting evidence.

[INCIDENT-CORPUS] [SRC-SEARCH-STATUS]

# 27. AdTech vocabulary — publisher perspective

## Inventory
Overall monetizable advertising supply/opportunity.

## Ad slot
Publisher-defined page/player container for advertising.

## Ad request
A request entering an ad-serving/auction process under source-specific counting semantics.

## Creative
The actual ad asset/markup/media.

## Impression
A platform-counted delivery/render event. Exact count point varies by system.

## Viewable impression
An impression satisfying a defined viewability criterion. It is not equivalent to served impression.

## Ad server
System managing inventory, campaign eligibility, selection, delivery and reporting.

## SSP
Sell-side technology connecting publisher inventory to demand and applying controls such as floors, deals and auction logic.

## DSP
Buy-side system making campaign/bidding decisions.

## Ad exchange
Marketplace/technical layer facilitating impression-level transactions.

## Deal ID
Identifier representing negotiated programmatic terms/access.

## PMP
Restricted/private programmatic marketplace/access.

## Passback/fallback
A mechanism that sends an unfilled opportunity to another monetization path.

[SRC-ADTECH-BOOK] [SRC-KOSORIN] [SRC-BUSCH]

# 28. Ad server decision model

Conceptually, publisher ad serving separates:

1. request initiation;
2. campaign/demand eligibility;
3. prioritization/selection;
4. creative/ad-code response;
5. browser delivery/render;
6. measurement/reporting.

This separation matters because the same symptom “no ad” can occur at different stages.

Examples:
- no slot/request → browser/tag problem;
- request exists but no eligible demand → targeting/demand/pricing;
- server returns creative but browser does not render → render/creative/runtime;
- ad renders but advertiser pixel does not fire → measurement discrepancy.

[SRC-ADTECH-BOOK]

# 29. Google Ad Manager role

GAM is the publisher-side ad server/system of record for the MVP’s ad-serving context.

The connector should use **minimum necessary read-only access**.

The product needs enough data to understand:
- inventory/ad structure;
- delivery by ad unit/device/format;
- demand composition;
- relevant line-item/configuration changes where accessible;
- programmatic channel/yield partner;
- serving restrictions;
- pricing-rule context;
- reporting health/freshness.

Financial metrics can be optional depending on publisher permissions and use case.

[SRC-GAM] [PRODUCT-SPEC]

# 30. GAM line-item and demand classes

GAM does not contain one undifferentiated auction.

Relevant families include:
- reserved/guaranteed line items;
- non-guaranteed line items;
- Ad Exchange;
- Open Bidding/yield partners;
- programmatic deals;
- house/internal demand.

Line-item type and priority are part of selection, but not the only selection factor.

## Operational implication
Programmatic delivery can fall because:
- traffic/request supply fell;
- direct/reserved delivery rose;
- targeting changed;
- pricing/floors changed;
- demand changed;
- consent/policy eligibility changed;
- technical render/request path broke.

Never map:
`programmatic impressions down`
directly to:
`programmatic partner failed`.

[SRC-GAM-SELECTION] [SRC-GAM-DYNAMIC]

# 31. Direct campaign displacement and the revenue trap

A publisher may run a large direct campaign whose ad-server booked value does not represent invoiced commercial reality.

Therefore:
- raw GAM revenue can fall while business revenue rises;
- programmatic impressions can fall intentionally because direct campaigns occupy inventory;
- a zero/nominal-rate direct campaign can make total ad-server revenue misleading.

## MVP rule
Always decompose programmatic incidents by:
- line-item/demand class;
- ad unit/ad structure;
- device;
- format;
- comparable time periods.

By default:
**do not send a critical alert solely because raw total GAM revenue moved.**

Revenue remains useful as:
- user-reported symptom;
- normalized segment metric;
- contextual outcome after demand decomposition.

[PRODUCT-SPEC] [OPERATIONAL]

# 32. Dynamic allocation and competition

GAM dynamic allocation allows eligible Google non-guaranteed demand to compete while considering guaranteed delivery requirements.

Diagnostic implication:
a change in Google/programmatic delivery can occur without a browser-side integration change.

Possible drivers:
- guaranteed-demand pressure;
- targeting;
- price;
- inventory mix;
- buyer demand.

The Incident Engine should inspect composition before assuming a platform malfunction.

[SRC-GAM-DYNAMIC]

# 33. GAM reporting model and 2026 API reality

As of the current research pass, Google’s newer Ad Manager Reports API supports Interactive Reports through asynchronous report runs:
- create/read a report definition;
- run it asynchronously;
- poll operation state;
- fetch paginated result rows.

Dimension/metric compatibility remains constrained.

## Connector principles
- define a small set of tested report cubes;
- reuse definitions;
- batch where supported;
- cache locally;
- respect quota/backoff;
- record report freshness;
- do not query GAM like a real-time transactional database.

## Suggested MVP report cubes

### Inventory health
time × ad structure/ad unit × device/format

### Demand health
time × demand/programmatic channel × device

### Direct/programmatic composition
time × line-item type/demand class

### Exception drill-down
serving restriction / pricing rule / bidder / yield partner where current report compatibility permits.

The exact cube must be validated against the pilot network’s available dimensions/metrics.

[SRC-GAM-REPORTS-2026] [SRC-GAM-API-QUOTA]

# 34. GAM report provenance

Every stored GAM observation must preserve:
- network;
- report type;
- metric name;
- dimension set;
- currency;
- network time zone;
- queried period;
- retrieval timestamp;
- freshness/maturity state;
- API/report version.

Why:
two similarly named metrics can have different denominators or report compatibility.

Never compare a metric across report definitions without checking semantics.

[CANONICAL_CURRENT]

# 35. GAM request/fill/eCPM decomposition

Conceptual health chain:

`eligible page/ad opportunity`
→ `GAM ad request`
→ `eligible demand/selection`
→ `served response/impression`
→ `realized value`

## M-GAM-001 — requests fall, traffic stable
Prioritize upstream:
- slot;
- GPT;
- lazy loading;
- consent gate;
- template;
- JS;
- refresh behavior.

## M-GAM-002 — requests stable, served/impressions fall
Prioritize downstream:
- eligibility;
- targeting;
- pricing;
- demand;
- direct displacement;
- consent;
- policy.

## M-GAM-003 — delivery stable, eCPM falls
Prioritize:
- demand/mix;
- geo/device mix;
- floor;
- buyer mix;
- seasonality;
- inventory quality/viewability.

## M-GAM-004 — impressions and revenue fall similarly, eCPM stable
Volume is a stronger first explanation than price.

## M-GAM-005 — programmatic falls, direct rises
Potential intentional displacement; not necessarily monetization failure.

[DERIVED] [INCIDENT-CORPUS]

# 36. Unfilled inventory

In GAM, an unfilled request is tied to the absence of eligible line-item/demand delivery for that request under GAM’s semantics.

Possible reasons span:
- no eligible line items;
- targeting mismatch;
- pricing/floors;
- demand unavailable;
- creative/size constraints;
- consent/policy;
- competing delivery logic.

An increase in unfilled requests is a symptom location, not a root cause.

[SRC-GAM-UNFILLED]

# 37. GAM serving restrictions and pricing-rule context

Current GAM reporting exposes dimensions that can help isolate:
- serving restrictions;
- unified pricing rules;
- programmatic channel;
- yield partner;
- bidder;
- bid rejection reason;
- requested/ad-delivered size;
- device/inventory format.

Availability/compatibility is report-specific.

These dimensions are valuable because they turn:
“fill is down”
into:
“fill is down only for this restriction/channel/format.”

[SRC-GAM-REPORT-DIMS]

# 38. Google Publisher Tag lifecycle

GPT provides browser-observable events that allow the ad lifecycle to be decomposed.

Important events:
- slot requested;
- slot response received;
- creative code injected (`slotRenderEnded`);
- creative iframe loaded (`slotOnload`);
- impression viewable;
- slot visibility change.

Important distinction:
`slotRenderEnded` fires when creative code is injected, before all creative resources are necessarily loaded.

Therefore:
`renderEnded` ≠ `creative fully loaded`.

## Diagnostic stages
1. expected slot exists;
2. slot defined;
3. request fired;
4. response received;
5. creative injected;
6. iframe/creative resources load;
7. viewability achieved.

[SRC-GPT-EVENTS]

# 39. GPT failure localization

## GPT-001 — slot expected but absent
Likely:
- template;
- conditional rendering;
- DOM/config.

## GPT-002 — slot defined but no request
Likely:
- lazy-loading conditions;
- consent gate;
- JS;
- service/config initialization.

## GPT-003 — request but no useful response
Move investigation toward:
- GAM eligibility;
- demand;
- pricing;
- policy/consent.

## GPT-004 — response/render event but no loaded creative
Investigate:
- creative/resource;
- iframe;
- network;
- browser error.

## GPT-005 — loaded but not viewable
Investigate:
- slot placement;
- viewport;
- layout;
- user scroll;
- sticky/lazy behavior.

This lifecycle is one of the MVP’s strongest deterministic diagnostic tools.

[SRC-GPT-EVENTS]

# 40. GPT lazy loading

Lazy loading intentionally delays fetching/rendering until an ad approaches the viewport.

It can:
- reduce unnecessary requests;
- improve page performance;
- improve viewability;
- change requests per pageview.

Therefore:
`pageviews stable + requests down`
may be expected after a lazy-load change.

The product should compare:
- config;
- viewport;
- scroll behavior;
- slot position;
- request/view ratios.

Do not alert on raw request decline without context.

[SRC-GPT-LAZY]

# 41. GPT refresh

Refresh creates additional ad lifecycles without a new pageview.

Consequences:
- requests/pageview can rise;
- impressions/pageview can rise;
- inventory quality/mix can change;
- stale targeting/state can cause implementation bugs;
- refresh declarations/policies matter.

The checkpoint should detect:
- whether refresh exists;
- cadence where observable;
- visibility conditions;
- whether a fresh Prebid auction precedes refreshed GAM targeting where applicable.

[INCIDENT-CORPUS] [SRC-GPT-REFRESH]

# 42. Header bidding model

Header bidding lets multiple demand sources submit bids before the final primary ad-server decision.

Client-side flow:
browser
→ Prebid/wrapper
→ bidder/SSP calls
→ bid responses/timeouts
→ targeting values
→ GAM request
→ ad-server selection
→ creative render.

The uploaded current AdTech reference also emphasizes the latency trade-off: slow demand can miss a configured timeout.

[SRC-ADTECH-BOOK] [SRC-PREBID]

# 43. Client-side versus server-side header bidding

## Client-side
Higher browser observability:
- bidder requests;
- response times;
- auction events;
- targeting keys;
- JS failures.

Costs:
- browser JS/network work;
- timeouts;
- user-sync complexity.

## Server-side
Auction orchestration is remote.

Benefits can include reduced browser fan-out.

Observability limitation:
the synthetic browser may only see the single server endpoint and final response, not each hidden bidder/server decision.

The Incident Engine must lower confidence when the relevant failure point is hidden server-side.

[SRC-ADTECH-BOOK] [SRC-PREBID-SERVER]

# 44. Prebid event ontology

Where Prebid is detectable, collect normalized events such as:
- auction start/end;
- bidder request;
- bid response;
- no bid;
- bid timeout;
- bid won;
- ad-server request;
- ad render succeeded/failed where exposed.

Also fingerprint:
- Prebid version;
- configured bidders;
- modules;
- ad units;
- timeout;
- floors/currency;
- consent modules;
- user ID modules;
- server-side config.

Do not store volatile bid IDs as structural changes.

[SRC-PREBID-EVENTS]

# 45. Header bidding timeout reasoning

Timeout is a deadline, not a measure of bidder quality by itself.

## Too short
Possible:
- slow-but-valid bidders excluded;
- lower bid density;
- reduced competition.

## Too long
Possible:
- GAM request delayed;
- render delayed;
- users leave;
- page/ad latency rises.

Prebid Server commonly uses a lower server-side timeout than the total client auction window to allow network return time.

JavaScript timers themselves are approximate and can execute later than the nominal delay if the event loop is busy.

## Diagnostic test
Compare:
- configured timeout;
- actual bidder response distribution;
- timeout rate;
- GAM request start;
- device/network segment;
- before/after config.

[SRC-PREBID-TIMEOUTS] [SRC-PREBID-CONFIG] [INCIDENT-CORPUS]

# 46. Prebid targeting propagation

A successful bidder response does not guarantee that demand competes correctly in GAM.

Failure points include:
- missing/stale `hb_*` targeting;
- wrong price bucket;
- stale targeting after refresh;
- line-item targeting mismatch;
- auction concurrency/race.

Strong pattern:
`bids exist`
+ `expected targeting absent/wrong`
+ `GAM header-bid delivery drops`
→ targeting propagation becomes high relevance.

[INCIDENT-CORPUS] [SRC-PREBID]

# 47. Price floors are non-monotonic

A floor is a minimum pricing/eligibility rule.

Floors may exist in:
- Prebid floor module;
- GAM Unified Pricing Rules;
- SSP;
- deal;
- other vendor layers.

## High floor
Can:
- reject more bids;
- reduce fill;
- raise realized CPM on surviving impressions.

## Low floor
Can:
- increase eligibility/fill;
- lower price mix.

Therefore:
`floor up → revenue up`
and
`floor down → revenue down`
are both prohibited simplifications.

Always inspect:
- bid density;
- rejection reasons;
- fill;
- eCPM;
- total value;
- affected segment.

[SRC-ADTECH-BOOK] [SRC-PREBID-FLOORS] [INCIDENT-CORPUS]

# 48. Auction mechanics, OpenRTB and historical-source warning

IAB Tech Lab currently maintains the OpenRTB 2.x line in GitHub; the current public standards page centers on OpenRTB 2.6 and subsequent dated 2.6 updates. VAST's current main specification is 4.3, supplemented by later addenda.

These standards are versioned. The platform should store the standard/version relevant to any decoded object or rule rather than assume one timeless schema.

Modern programmatic markets commonly use first-price auction behavior, with buyer-side bid shading used in many contexts.

Older books contain detailed second-price-era mechanics and publisher strategy. They are retained for conceptual/historical context but must not define current platform behavior.

The product normally does **not** need to reconstruct the hidden auction mathematically. It needs to understand how:
- floor;
- bid response;
- competition;
- deal;
- demand mix;
- timeout;
can alter downstream fill/value.

[SRC-ADTECH-BOOK] [SRC-BUSCH]

# 49. Programmatic deals and private access

Deal identifiers can encode negotiated access/terms.

Potential incident events:
- deal begins/ends;
- deal ID changes;
- targeting changes;
- buyer eligibility changes;
- price/floor changes;
- deal volume displaces open auction.

A deal-specific decline should not be generalized to total demand.

[SRC-KOSORIN] [SRC-BUSCH] [SRC-GAM]

# 50. ads.txt — what it is

ads.txt is a publisher/distributor public declaration of companies authorized to sell digital inventory.

Relevant record semantics include:
- advertising system domain;
- publisher account/seller ID;
- DIRECT or RESELLER relationship;
- certification authority ID where used;
plus v1.1 directives such as ownership/manager relationships.

MVP use:
**supply authorization/integrity signal**.

It is not a live revenue ledger.

[SRC-IAB-ADSTXT]

# 51. ads.txt — what the product should monitor

Monitor semantic state, not just file text.

High-value checks:
- file exists and is parseable;
- unexpected empty `200 OK`;
- seller line added/removed;
- account ID changed;
- DIRECT/RESELLER changed;
- duplicate/malformed records;
- ownership/manager directives changed;
- known active partner becomes unauthorized;
- cross-check with sellers.json where feasible.

## Alert philosophy
A routine ads.txt diff belongs in the weekly report unless:
- it removes a known critical demand path;
- file becomes invalid/empty/unreachable;
- large replacement looks accidental.

[INCIDENT-CORPUS] [SRC-IAB-ADSTXT] [SRC-IAB-VALIDATION]

# 52. ads.txt causality limits

Do not infer:
`ads.txt changed → revenue changed`.

Stronger evidence requires:
- the affected seller/path;
- authorization actually used by buyers;
- corresponding partner/demand loss;
- matching timing;
- no better explanation.

Do not recommend deleting reseller lines automatically.  
A reseller path can carry unique buyer/deal demand.

[INCIDENT-CORPUS] [OPERATIONAL]

# 53. sellers.json and SupplyChain

sellers.json provides seller/intermediary identity transparency.

SupplyChain (`schain`) represents the sequence of entities involved in selling/reselling a bid request.

Together with ads.txt they support supply-path validation.

MVP use:
- integrity;
- identity;
- relationship checks;
- anomaly/context.

Not:
- performance attribution by themselves.

[SRC-IAB-SUPPLY]

# 54. CMP/TCF model — current version

The current research pass uses **TCF v2.3** technical context.

TCF includes:
- policies;
- implementation guidance;
- TC String/GVL format;
- CMP API;
- Global Vendor List;
- operational disclosures.

TCF v2.3 made the Disclosed Vendors section mandatory after the transition deadline, reducing a prior signaling ambiguity.

Important namespace:
- TCF technical version;
- TCF policy version;
- CMP software version;
are different things.

[SRC-TCF-23]

# 55. Consent observability strategy

The MVP should not try to reverse-engineer every CMP UI.

Monitor behavior:

### Presence/readiness
- CMP API/stub detectable;
- response timing;
- TC String available where expected.

### Controlled paths
- first visit;
- accept;
- reject.

### Network consequences
- vendor requests before/after decision;
- Prebid consent behavior;
- Google ad behavior;
- analytics behavior.

### Segment
- EU/geo-specific differences where test infrastructure supports them.

A CMP version change alone is weak evidence.

[SRC-TCF] [SRC-PREBID-CONSENT]

# 56. Consent timing and auction interaction

Consent can become a timing dependency.

For Prebid TCF integration, the configured timeout controls how long Prebid waits for an **already discovered CMP interface** to return consent data; it is not a polling window for a CMP interface that does not yet exist.

Potential failure classes:
- CMP unavailable;
- CMP API discovered late;
- CMP slow;
- invalid/missing TC String;
- vendor mapping/eligibility issue;
- accept/reject path changed.

## Strong evidence
`EU mobile only`
+ `CMP timing changed`
+ `TCF errors`
+ `GAM requests/fill changed`
is materially stronger than:
`CMP updated near revenue decline`.

[SRC-PREBID-CONSENT] [INCIDENT-CORPUS]

# 57. Identity/user sync

Identity/user-sync systems can affect buyer addressability and bidder behavior.

Potential mechanisms:
- cookie/ID sync unavailable;
- consent blocks sync;
- server/client identity differences;
- user-ID module latency;
- vendor mapping.

The uploaded programmatic literature explains the durable requirement for ID reconciliation between SSP/DSP domains, but current browser/privacy behavior must be sourced from current platform documentation.

MVP rule:
identity degradation is usually a **possible contributor**, not a confirmed cause, unless bidder-level evidence exists.

[SRC-KOSORIN] [SRC-PREBID-USERID] [INCIDENT-CORPUS]

# 58. Video inventory ontology

Video has a separate lifecycle from display.

Important entities:
- content player;
- placement type;
- ad request;
- VAST response/wrapper;
- media file/renderer;
- playback;
- tracking events;
- viewability;
- sticky state;
- controls;
- audibility.

Current Google placement concepts include:
- in-stream;
- accompanying content;
- interstitial;
- standalone.

The monitor must distinguish them because policy and demand expectations differ.

[SRC-GOOGLE-VIDEO-POLICY] [SRC-VAST]

# 59. Current Google video restrictions to monitor

Current Google publisher restrictions include important observable requirements/signals such as:
- accurate placement declaration;
- accurate audibility signaling;
- functional/unobstructed controls;
- constraints on autoplay with sound;
- visibility before autoplay;
- dismissibility for sticky video;
- transition rules for in-stream/accompanying content becoming sticky.

The product should detect objective observable behavior and attach the exact current rule version.

It should not issue a blanket “Google compliant” certificate.

[SRC-GOOGLE-VIDEO-POLICY]

# 60. VAST and video render chain

Simplified chain:

player
→ ad tag/request
→ ad server
→ VAST response/wrapper chain
→ media/renderer retrieval
→ start
→ quartiles/complete/tracking.

Failure points:
- no VAST response;
- VAST error;
- wrapper timeout/depth;
- unsupported media;
- renderer/player incompatibility;
- creative load failure;
- user leaves before render;
- tracking discrepancy.

Google documents creative render-rate gaps where code served can materially exceed impressions due to player/user latency, crashes, exits or prefetching.

[SRC-VAST] [SRC-GAM-VAST-ERRORS]

# 61. Prebid video

In Prebid video integrations:
- demand responds with video bids;
- bids may be cached server-side;
- cache IDs/key-values are passed to the ad server;
- the player calls the ad server;
- a winning creative/VAST chain is returned and rendered.

This creates additional failure points:
- cache;
- key-value propagation;
- GAM line item;
- VAST;
- renderer;
- player.

A successful bid is not equivalent to a played video impression.

[SRC-PREBID-VIDEO] [INCIDENT-CORPUS]

# 62. Open Measurement and viewability

Open Measurement provides standardized measurement interfaces for impression/viewability/verification across supported environments, including web video.

Important product distinction:
- served;
- rendered;
- measurable;
- viewable;
are separate states.

The product should preserve measurement provider/method provenance rather than assuming all viewability values are interchangeable.

[SRC-OMSDK]

# 63. Reporting discrepancies

Discrepancies between publisher, SSP, advertiser and verification systems are normal enough to deserve a first-class model.

Common mechanisms:
- different counting points;
- different time zones;
- invalid-traffic filters;
- client-side pixel failure;
- JS/browser restrictions;
- network latency;
- creative load failure;
- different viewability rules;
- server-side versus client-side measurement.

## Reconciliation method
Compare:
- exact time window;
- time zone;
- campaign/line item/creative IDs;
- source counting definition;
- eligible/measurable denominators;
- segment.

A discrepancy is a **signal**, not proof that one platform is wrong.

[SRC-ADTECH-BOOK] [INCIDENT-CORPUS]

# 64. Viewability

Viewability depends on:
- placement;
- viewport;
- scroll;
- slot size;
- sticky behavior;
- lazy loading;
- player state;
- user behavior;
- measurement method.

Potential trade-off:
more aggressive lazy loading can improve measured viewability while reducing total request volume.

Do not encode:
`higher viewability → higher revenue`
as a guaranteed rule.

[DERIVED] [SRC-ADTECH-BOOK]

# 65. Programmatic demand and seasonality

Fill/eCPM are partly market outputs.

External variation can come from:
- hour of day;
- weekday;
- month/quarter;
- holidays;
- advertiser budgets;
- geography;
- device;
- news cycle;
- buyer/SSP outages.

Primary research on production RTB exchanges has observed temporal patterns in auction activity, supporting time-aware baselines.

## Baseline rule
For monetization, prefer comparison to:
- same hour-of-week;
- recent comparable weekdays;
- rolling robust baseline;
not only:
`previous hour`.

[SRC-RTB-RESEARCH] [OPERATIONAL]

# 66. Monetization dependency graph

A simplified causal skeleton:

Traffic
→ page views
→ eligible slot opportunities
→ ad requests
→ consent/demand eligibility
→ auction/selection
→ served/rendered impressions
→ viewability/quality
→ realized price mix
→ programmatic revenue

Modifiers:
- direct campaigns;
- lazy loading;
- refresh;
- ad blockers;
- format;
- geo/device;
- floors;
- deals;
- identity;
- policy;
- market demand.

This graph is not a one-to-one formula.

It is a diagnostic topology.

[DERIVED]

# 67. Rate denominator discipline

Never store only a derived rate when raw components are available.

Examples:
- fill = filled / requests under exact source definition;
- CTR = clicks / impressions;
- viewability = viewable / measurable;
- timeout rate = timed-out / eligible bidder requests;
- consent rate = defined numerator / eligible users.

A rate anomaly must first be decomposed.

This prevents false explanations caused by denominator movement.

[CANONICAL_DURABLE]

# 68. Absolute versus percentage impact

A 50% change from 2 to 1 events may be noise.

A 7% change across tens of millions of requests can be material.

Anomaly significance should consider:
- volume;
- historical variance;
- persistence;
- blast radius;
- business importance.

No universal percentage threshold belongs in DOMAIN.

Thresholds are calibrated per publisher/metric.

[OPERATIONAL]

# 69. Refresh and inventory-per-view

Refresh decouples traffic from impression volume.

A publisher can have:
- stable pageviews;
- more requests;
- more impressions;
without new users.

Likewise, changed user scroll depth can alter lazy-loaded inventory without a technical defect.

Useful ratios:
- expected slots/template;
- requested slots/view;
- impressions/view;
- refresh impressions/view;
where observable.

[DERIVED]

# 70. Ad density and inventory quality

More ad slots do not guarantee more revenue.

Possible downstream effects of higher density:
- more theoretical opportunities;
- lower viewability;
- higher page cost;
- more CLS/INP pressure;
- demand cannibalization;
- worse user experience;
- policy/standards risk.

Likewise, reducing slots can sometimes improve value/UX.

The engine should describe trade-offs, not assume monotonicity.

[SRC-CWV-ADS] [SRC-BETTER-ADS] [DERIVED]

# 71. Better Ads / disruptive-format monitoring

The Coalition for Better Ads updated desktop/mobile web standards with additional problematic combinations, including high ad density and sticky video patterns.

The platform can monitor objective experience properties such as:
- approximate ad density;
- sticky/pop-out video;
- large inline + sticky combinations;
- overlays;
- autoplay with sound;
- content obstruction.

Standards are versioned external rulesets.

Do not conflate:
- Coalition standard;
- Google Publisher Policy;
- browser ad filtering;
into one generic “policy.”

[SRC-BETTER-ADS]

# 72. Google Publisher restrictions

Google Publisher Restrictions can reduce eligible advertising demand without necessarily producing total ad-serving failure.

Potential outcomes:
- fewer eligible advertising sources;
- lower fill;
- different buyer mix;
- lower revenue.

Therefore:
`fill/eCPM down`
can be consistent with a restriction, but is not evidence of one.

High-quality evidence:
- Policy Center/serving restriction signal;
- GAM serving restriction dimension;
- content/behavior matching an explicit current restriction.

[SRC-GOOGLE-PUBLISHER-RESTRICTIONS]

# 73. Policy/UX event severity

High-severity observable candidates:
- content obscured by Google-served ad;
- ad controls obscured;
- video controls non-functional;
- prohibited autoplay/audibility behavior;
- sticky behavior without required dismissibility;
- major ad-density violation against a selected current standard.

Policy detections should include:
- standard/policy name;
- version/date;
- evidence screenshot/DOM;
- page/template;
- confidence;
- exact observable behavior.

Do not make legal conclusions.

[SRC-GOOGLE-PUBLISHER-RESTRICTIONS] [SRC-GOOGLE-VIDEO-POLICY] [SRC-BETTER-ADS]

# 74. External infrastructure

Publisher incidents can originate outside the publisher/ad stack:
- CDN;
- DNS;
- cloud;
- remote script host;
- consent vendor;
- adtech platform.

The incident corpus contains confirmed vendor outages where:
- traffic failed due network/config changes;
- analytics/logging failed while core serving continued;
- dependencies cascaded.

This supports a crucial rule:
**monitor control-plane/reporting health separately from actual user-serving health.**

[INCIDENT-CORPUS]

# 75. Control plane versus data plane

A dashboard/API can fail while ads/pages still serve.

Conversely, dashboard data can look normal while browser render fails.

Classify evidence:

### Data plane
What the end user/browser actually receives:
- page;
- request;
- creative;
- player;
- render.

### Control/measurement plane
- dashboards;
- reporting APIs;
- configuration interfaces;
- logs.

Do not infer production failure solely from control-plane failure.

[INCIDENT_BACKED]

# 76. Data freshness is diagnostic metadata

Slow/incomplete data can cause false causal inference.

Examples:
- recent GAM report not mature;
- GA4 processing;
- Search Console latency;
- external status page published later.

Every metric source needs:
- expected freshness;
- retrieval time;
- mature/preliminary state if known.

SRE guidance emphasizes that monitoring freshness affects incident decisions: delayed cause→effect visibility can make an intervention look ineffective or create false correlation.

[SRC-SRE-MONITORING]

# 77. Time-series model

Metrics should be stored as time series with explicit dimensions.

Conceptual key:
`metric + publisher + entity + segment + source + timestamp`.

Useful dimensions:
- device;
- source/channel;
- template/category;
- ad unit/structure;
- format;
- geo;
- demand channel.

## Baseline primitives
- same-hour/day historical comparison;
- rolling median;
- robust dispersion;
- persistence;
- structural break/change point;
- missingness.

Avoid:
`current < previous = incident`.

[SRC-SRE-TIMESERIES] [DERIVED]

# 78. Event versus metric versus state

## Metric
A numeric observation:
`mobile_programmatic_fill = 53.2%`.

## State
A configuration/runtime snapshot:
`robots rule set`, `slot inventory`, `scripts`.

## Event
A meaningful fact/change:
`robots_block_was_added`.

## Anomaly
A statistical/semantic finding:
`mobile_fill_departed_from_baseline`.

## Incident
A user/business problem requiring investigation:
`mobile programmatic delivery has been lower since Aug 4`.

Keep these entities separate.

[SRC-DDIA] [PRODUCT-SPEC]

# 79. Immutable event history

The operational memory should favor append-only facts.

Example:
- `script_added`;
- later `script_removed`.

Do not rewrite history to pretend the script never existed.

DDIA’s event-sourcing principles are useful conceptually:
events record facts that happened; read-optimized/materialized views can be recomputed from source events.

MVP architecture does **not** need a heavy event-stream platform to implement this principle.

PostgreSQL + object storage + deterministic derived tables are enough initially.

[SRC-DDIA]

# 80. System of record versus derived knowledge

Treat raw observations as systems of record:
- checkpoint artifacts;
- GA4 extracts;
- GSC extracts;
- GAM extracts;
- external event records;
- manual operator notes.

Derived:
- normalized diff;
- anomaly;
- event relationship;
- Last Known Good;
- incident hypothesis;
- weekly summary.

A derived result should retain links back to source evidence.

If reasoning rules improve, derived findings can be recomputed without altering raw history.

[SRC-DDIA]

# 81. Event normalization

Raw DOM/network diffs are too noisy.

Pipeline:

raw checkpoint
→ volatile-value removal
→ stable entity mapping
→ semantic diff
→ persistence check
→ domain relevance
→ event

## Normalize away by default
- cache busters;
- auction IDs;
- session IDs;
- creative URLs;
- recommendation ordering;
- article text;
- timestamps;
- random DOM identifiers.

## Preserve
- script dependency identity;
- ad slot identity;
- player identity/config;
- CMP behavior;
- SEO directives;
- network-domain changes;
- persistent JS errors;
- structural layout.

[PRODUCT-SPEC]

# 82. A/B tests and partial exposure

A/B experiments can mimic random site instability.

Clues:
- experiment vendor;
- variant cookie/query parameter;
- mutually exclusive DOM/script states;
- changes only on some synthetic sessions.

Rule:
Do not label a partial-exposure variant as a global deployment unless exposure is known.

If incident affects only the same variant, causal relevance rises.

[OPERATIONAL]

# 83. Event graph

A chronological list is necessary but insufficient.

Use typed edges such as:
- `precedes`;
- `coincides_with`;
- `same_segment_as`;
- `mechanistically_can_affect`;
- `metric_parent_of`;
- `metric_descendant_of`;
- `supports`;
- `contradicts`;
- `introduced_by`;
- `resolved_after`;
- `persisted_after_removal`;
- `external_context_for`;
- `unknown_relation`.

Reserve `causes` for confirmed evidence.

The graph supports explanations like:

`CMP behavior changed`
→ `TCF errors`
→ `GAM request drop`
→ `programmatic impressions drop`

instead of merely showing four timestamped rows.

[PRODUCT-SPEC] [DERIVED]

# 84. Change risk score versus cause score

A risky change is not necessarily the cause of an incident.

## Change risk factors
- blast radius;
- domain criticality;
- persistence;
- novelty;
- reversibility;
- proximity to critical systems.

Example:
a broad robots change is inherently high risk.

## Causal relevance factors
- timing;
- segment match;
- mechanism;
- intermediate evidence;
- control segment;
- intervention/rollback;
- contradictions.

Store these as separate scores/concepts.

[DERIVED]

# 85. Last Known Good

Last Known Good is the latest pre-incident checkpoint whose monitored structural/health state is within accepted baseline conditions.

Compare:
- scripts;
- slots;
- network dependencies;
- CMP behavior;
- player;
- SEO directives;
- synthetic performance;
- metric segments.

In MVP, Last Known Good is a **reference state**, not an automatic deployable rollback image.

Future automated rollback would require stronger write permissions, change ownership and safety controls.

[PRODUCT-SPEC]

# 86. Change accountability

Where possible, each intentional change can have:
- timestamp;
- actor;
- approver;
- system/source;
- reason;
- ticket/reference;
- expected scope.

Browser observation cannot identify who changed code.

If attribution is unknown:
`actor = unknown`.

Manual annotation is valuable and should coexist with automatic detection.

[PRODUCT-SPEC]

# 87. Alerting philosophy

Borrow SRE principles:
- page/alert on meaningful symptoms;
- alerts must be actionable;
- minimize fatigue/noise;
- cause-oriented signals help debugging more than paging.

For this product:

## Immediate alerts
Reserved for high severity, e.g.:
- site unavailable;
- broad robots/noindex error;
- widespread expected ad slots disappear;
- severe persistent ad-request/delivery collapse;
- CMP/runtime unavailable across key segment;
- explicit severe serving/policy issue;
- severe persistent performance/UX regression.

## Weekly brief
Most other changes:
3–7 ranked items.

## No immediate alert by default
- routine ads.txt diff;
- a single JS error;
- short eCPM variation;
- total raw revenue movement;
- normal content changes.

[SRC-SRE] [PRODUCT-SPEC]

# 88. Weekly report ranking

Rank observations using:
- severity;
- persistence;
- blast radius;
- confidence;
- actionability;
- novelty;
- business relevance.

Suppress:
- acknowledged intentional changes;
- transient noise;
- duplicate unresolved item with no new evidence;
- harmless content churn.

Weekly report language should separate:
- observed fact;
- risk;
- suggested verification.

Example:
**Observed:** article template now defines 3 GPT slots instead of 5 across 4 consecutive checkpoints.  
**Risk:** fewer ad opportunities.  
**Check:** confirm whether removal was intentional.

[PRODUCT-SPEC]

# 89. Incident intake

Minimum user input:
- approximate start date/time;
- symptom family;
- short description.

Optional:
- affected device/category;
- Google/vendor notice;
- known deploy/change;
- screenshot/message.

The user should not be required to diagnose.

The engine asks:
**What changed around the time this symptom began?**

[PRODUCT-SPEC]

# 90. Incident window selection

Lookback depends on mechanism.

## Sudden ad-serving problem
hours to days.

## Browser/performance
checkpoints around regression.

## Analytics measurement
hours/days around tagging/consent/config change.

## Search/Discover
days to weeks because crawling/indexing/ranking effects can lag.

## Gradual trend
longer baseline plus change-point analysis.

Do not use one universal ±24h incident window.

[DERIVED]

# 91. Root-cause ranking model

For each candidate:

### Temporal relevance
Did it occur at a plausible causal delay?

### Segment match
Same device/template/geo/source/ad unit?

### Mechanism
Can it physically/logically cause the symptom?

### Intermediate evidence
Did expected intermediate signals move?

### Magnitude compatibility
Could this change plausibly explain the size?

### Persistence
Did candidate and symptom coexist?

### Intervention
Was there rollback/recovery?

### External context
Platform/cohort event?

### Contradictions
What argues against it?

The engine should return an evidence explanation, not only a score.

[DERIVED] [INCIDENT-CORPUS]

# 92. Confidence language

Use qualitative confidence unless scores are empirically calibrated.

## CONFIRMED
Direct technical proof or strong controlled intervention/recovery evidence.

## PROBABLE
Multiple independent evidence lines, plausible mechanism, limited contradictions.

## POSSIBLE CONTRIBUTOR
Relevant evidence exists but material uncertainty remains.

## UNRESOLVED
Evidence insufficient.

Do not display fake precision such as `87.4% cause` merely because an internal heuristic has numeric weights.

[OPERATIONAL]

# 93. Counterfactual investigation

Prefer tests that isolate one variable with minimal business damage.

Examples:
- affected vs unaffected template;
- mobile vs desktop;
- consent accept vs reject;
- one ad unit;
- one bidder;
- one small traffic cohort;
- staging versus production;
- limited rollback.

Avoid:
- turning off every external monetization source for two weeks;
- changing several stack components simultaneously;
- destructive production experiments before evidence.

The purpose of a test is to reduce uncertainty, not merely “try something.”

[INCIDENT-CORPUS] [OPERATIONAL]

# 94. Failure-mode library — traffic/analytics

### F-AN-001 Analytics tag missing/broken
Signature:
GA4 falls while independent site/GSC evidence does not.

### F-AN-002 Duplicate/suppressed page_view
Signature:
users stable, views change abruptly around measurement deploy.

### F-AN-003 SPA/history measurement changed
Signature:
page navigation behavior differs without matching acquisition shift.

### F-AN-004 Consent changes analytics collection
Signature:
geo/consent segment changes; real traffic controls stable.

### F-AN-005 Channel attribution changes
Signature:
source mix changes more than total traffic.

### F-TR-001 Site availability
Signature:
multiple channels/pages collapse; HTTP/network evidence.

### F-TR-002 Content-consumption change
Signature:
users stable, views/session or views/user changes.

[INCIDENT-CORPUS]

# 95. Failure-mode library — Search/Discover

### F-SEO-001 robots block
Direct technical crawlability risk.

### F-SEO-002 noindex
Direct indexability risk.

### F-SEO-003 canonical misconfiguration
Broad incorrect canonical target/pattern.

### F-SEO-004 status/redirect/availability regression
5xx, loops, bad migration.

### F-SEO-005 JS rendering regression
Important content/meta absent after render.

### F-SEO-006 migration/site architecture change
Potential delayed crawl/indexing effects.

### F-SEO-007 Google external update/incident
External candidate; never automatic cause.

### F-SEO-008 search-demand/seasonality
Clicks decline without equivalent ranking loss.

### F-SEO-009 SERP CTR shift
Impressions/position relatively stable, CTR/clicks decline.

### F-SEO-010 editorial/content factor
Often not fully observable; requires human context.

[INCIDENT-CORPUS] [SRC-SEARCH]

# 96. Failure-mode library — GPT/GAM

### F-GAM-001 Slot removed
Page/template inventory opportunity changes.

### F-GAM-002 Request/targeting/config mismatch
Request path or eligibility changes.

### F-GAM-003 Direct/guaranteed displacement
Programmatic falls while intentional direct delivery rises.

### F-GAM-004 Pricing/floor restriction
Request stable; eligible bids/delivery changes.

### F-GAM-005 External demand/platform outage
Partner/Google incident.

### F-GAM-006 Broad market demand weakness
Multiple demand sources decline with stable inventory.

### F-GAM-007 Reporting/freshness anomaly
Dashboard/API data wrong/delayed while serving evidence differs.

### F-GPT-001 slot absent
### F-GPT-002 defined but not requested
### F-GPT-003 response missing
### F-GPT-004 creative injected but resource/load failure
### F-GPT-005 viewability/visibility issue

[INCIDENT-CORPUS]

# 97. Failure-mode library — header bidding

### F-HB-001 bidder/adapter removed or broken
### F-HB-002 timeout spike
### F-HB-003 auction timeout too short
### F-HB-004 auction/RTD/user-ID delay too long
### F-HB-005 targeting/key-values stale or missing
### F-HB-006 currency/floor module issue
### F-HB-007 identity/user-sync degradation
### F-HB-008 concurrent auction/race condition
### F-HB-009 Prebid Server hidden failure/timeout
### F-HB-010 video cache/render integration

For each, the engine should seek:
- config diff;
- event evidence;
- bidder timing;
- GAM request timing;
- affected bidder/device/ad unit;
- control bidder.

[INCIDENT-CORPUS] [SRC-PREBID]

# 98. Failure-mode library — consent

### F-CMP-001 CMP unavailable
### F-CMP-002 CMP/readiness slow
### F-CMP-003 invalid/missing/outdated TCF signal
### F-CMP-004 vendor/GVL/config mapping issue
### F-CMP-005 accept/reject behavior changed
### F-CMP-006 geo-specific consent issue
### F-CMP-007 CMP visual/UI-only change
Low causal weight if runtime/network behavior unchanged.

Empirical high-value pattern from the incident corpus:
stable page traffic + stable upstream SSP context + falling GAM requests + TCF error/outdated string can indicate Google-side request eligibility loss caused by consent signaling.

[INCIDENT-CORPUS]

# 99. Failure-mode library — video

### F-VID-001 player initialization/runtime failure
### F-VID-002 VAST/cache/wrapper/render failure
### F-VID-003 autoplay/mute/controls/sticky behavior
### F-VID-004 video placement declaration mismatch
### F-VID-005 video resource/performance regression
### F-VID-006 video reporting/render-rate discrepancy
### F-VID-007 video policy restriction
### F-VID-008 GAM/Prebid creative-cache-key mismatch

[INCIDENT-CORPUS] [SRC-VAST] [SRC-GOOGLE-VIDEO-POLICY]

# 100. Failure-mode library — supply/policy

### F-SUP-001 ads.txt missing/unreachable
### F-SUP-002 empty-success response
### F-SUP-003 account ID incorrect/missing
### F-SUP-004 DIRECT/RESELLER relationship wrong
### F-SUP-005 seller/sellers.json mismatch
### F-SUP-006 legitimate reseller path removed
### F-POL-001 serving restriction
### F-POL-002 ad interferes with content
### F-POL-003 disruptive sticky/video/density behavior
### F-POL-004 explicit ad-serving limit/policy notice

[INCIDENT-CORPUS] [SRC-IAB-ADSTXT] [SRC-GOOGLE-PUBLISHER-RESTRICTIONS]

# 101. Failure-mode library — browser/infrastructure

### F-BR-001 third-party script unavailable
### F-BR-002 JS exception before critical initialization
### F-BR-003 CSS/layout regression
### F-BR-004 CSP/security block
### F-BR-005 browser/privacy/ad-block population effect
### F-BR-006 CDN/resource latency
### F-BR-007 external dependency outage
### F-BR-008 control-plane/reporting outage only

[INCIDENT-CORPUS] [SRC-HPBN]

# 102. Causal evidence ladder

From weak to strong:

1. coincidence;
2. temporal precedence;
3. plausible mechanism;
4. segment match;
5. intermediate metric chain;
6. repeated reproduction;
7. unaffected control group;
8. targeted intervention;
9. rollback + recovery;
10. direct technical proof.

The Incident Engine should prefer a mundane candidate with strong evidence over a dramatic candidate with only coincidence.

[INCIDENT-CORPUS] [DERIVED]

# 103. Common confounders

Always consider:
- hour/day/season;
- traffic mix;
- country/device mix;
- direct campaign delivery;
- user scroll/depth;
- content mix/breaking news;
- consent-state mix;
- reporting freshness;
- buyer/market demand;
- Google external event;
- A/B experiment;
- CDN/vendor incident;
- analytics implementation.

A confounder can create an apparent before/after relationship without being the target cause.

[OPERATIONAL]

# 104. Wrong shortcuts explicitly prohibited

Never encode these as automatic truths:

- Revenue down → SSP problem.
- eCPM down → integration broken.
- Traffic down after deploy → deploy caused it.
- Google update + traffic drop → Google caused it.
- ads.txt changed → revenue impact.
- CMP updated → consent broke.
- More bidders → more revenue.
- More ad slots → more revenue.
- Worse CWV → direct Google penalty.
- Stable total traffic → no traffic problem.
- Stable users → no behavioral change.
- Total GAM revenue → invoiced publisher revenue.
- Synthetic browser result → all-user production truth.
- Removing suspect X without immediate recovery → X is innocent for every symptom class.
- HTTP 200 ads.txt → valid ads.txt.
- Bid response → rendered impression.
- GAM response → viewable impression.
- Dashboard outage → serving outage.

These should become eval counterexamples.

[DOMAIN-RULE]

# 105. Empirical lessons imported from the public incident corpus

The public incident corpus currently provides broad evidence across:
- GAM/platform incidents;
- Search/Discover external events and publisher cases;
- Prebid bugs;
- CMP/TCF failures;
- video;
- browser/performance;
- supply/policy;
- infrastructure;
- measurement discrepancies.

Important lessons that qualify for INCIDENT_BACKED status:

1. **Consent can alter GAM request volume**, not only downstream bidder fill.
2. **Header-bidding observability can itself be wrong**; timeout telemetry may have bugs.
3. **Stale targeting/refresh state can imitate bidder-demand problems.**
4. **Platform reporting can be wrong while serving is not equivalently broken.**
5. **External Search/Ad Manager incidents need product/segment matching before attribution.**
6. **Lab and field performance can disagree materially.**
7. **One SSP declining while another publisher sees the same SSP rise is disconfirming evidence for a universal vendor outage.**
8. **Supply-file cleanup can remove valid unique demand paths.**
9. **Disabling many monetization components simultaneously destroys attribution quality.**
10. **Unresolved incidents are a valid and necessary training/evaluation class.**

Corpus counts must never be interpreted as real-world incidence rates because public-source availability is highly biased.

[INCIDENT-CORPUS]

# 106. Source freshness classes

## DURABLE
Review infrequently:
- causal logic;
- latency fundamentals;
- rate semantics;
- event-history concepts.

## VERSIONED_STANDARD
Track version:
- ads.txt;
- sellers.json;
- OpenRTB;
- VAST;
- TCF;
- OM SDK.

## PLATFORM_CURRENT
Recheck frequently:
- GAM;
- GPT;
- GA4;
- Search/Search Console;
- Google Publisher Policies;
- Prebid current docs.

## EMPIRICAL
Continuously expand:
- incidents;
- vendor outages;
- practitioner failure modes.

A rule derived from PLATFORM_CURRENT must keep source/version metadata.

[DOMAIN-MAINTENANCE]

# 107. Knowledge update workflow

When a standard/platform changes:

1. create an `external_ruleset_changed` event;
2. identify affected DOMAIN rules;
3. update canonical source;
4. mark previous version historical;
5. re-evaluate derived rules;
6. rerun relevant evals;
7. do not silently rewrite historical incident interpretation.

The product should ultimately monitor the same external documentation/status sources that DOMAIN depends on.

[DERIVED]

# 108. Security and privacy constraints

MVP observation should use controlled synthetic sessions.

Avoid:
- logged-in personal accounts;
- user-entered form data;
- unnecessary persistent identifiers.

Screenshots/DOM may accidentally contain:
- personalization;
- email/account UI;
- cookie identifiers;
- form values.

Mitigations:
- clean profile;
- masking/redaction where feasible;
- restricted access;
- retention policy;
- encryption;
- audit logs.

Connected Google access:
- least privilege;
- read-only scopes/roles where possible;
- encrypted tokens;
- per-publisher tenant isolation.

[SRC-GAM-API-QUOTA] [SRC-GA4-DATA] [SECURITY-PRACTICE]

# 109. Data retention and evidence preservation

Different evidence has different value/cost.

Possible policy:
- screenshots: medium-term compressed/object storage;
- raw DOM: medium-term;
- normalized DOM fingerprints/diffs: long-term;
- time series: long-term;
- events/incidents: long-term;
- secrets/tokens: separate secure storage;
- verbose browser traces: shorter retention unless incident-linked.

Incident-linked evidence should be protected from routine deletion until retention policy permits.

[DERIVED]

# 110. KISS architecture implications from DOMAIN

DOMAIN implies a simple MVP architecture.

Need:
- scheduler;
- Playwright workers;
- PostgreSQL;
- object storage;
- Google connectors;
- normalization/event engine;
- incident analysis service;
- web UI.

Do not add by default:
- Kafka;
- Kubernetes;
- Neo4j;
- separate time-series database;
- dozens of microservices.

DDIA explicitly supports the general principle of avoiding unnecessary complexity; a single-machine/database approach is often preferable at small/moderate scale.

The **event graph is a logical model** and can live in relational tables initially.

[SRC-DDIA]

# 111. Minimal connector philosophy

## GA4
Mandatory for traffic/behavior if publisher participates.

## Search Console
Strongly recommended for Search/Discover incidents.

## GAM
Read-only, minimum necessary reporting/config state.

## Browser
Mandatory independent evidence source.

## ads.txt/sellers
Public fetch; no credential required.

The platform should remain useful even if a publisher declines sensitive financial GAM metrics.

[PRODUCT-SPEC]

# 112. What the MVP can know strongly

Strongly observable:
- page availability;
- representative DOM/render;
- scripts/network dependencies;
- JS errors;
- GPT slot lifecycle;
- public SEO directives;
- ads.txt state;
- GA4 reported behavior;
- Search Console reported visibility;
- GAM report/config signals made available;
- confirmed external platform events.

Moderately observable:
- Prebid state;
- CMP behavior;
- player/video state;
- page performance.

Weak/hidden:
- SSP server-side logic;
- DSP bidding strategy;
- hidden Google ranking systems;
- commercial contracts;
- advertiser budget intent;
- all real-user variants.

Confidence must reflect observability.

[DOMAIN-LIMIT]

# 113. What the MVP must refuse to claim

Do not claim:
- exact hidden Google ranking cause;
- guaranteed Discover recovery;
- complete Google compliance;
- legal compliance certification;
- complete SSP/DSP observability;
- deterministic revenue uplift;
- universal root-cause certainty;
- that every publisher visitor saw the synthetic checkpoint state;
- that a public external incident affected the publisher without local match.

[DOMAIN-LIMIT]

# 114. Incident output contract

A high-quality incident answer should contain:

## Symptom localization
What actually changed and where.

## Timeline
Relevant events before/after onset.

## Top hypotheses
Ranked.

For each:
- mechanism;
- supporting evidence;
- contradicting evidence;
- observability gaps;
- confidence.

## External context
Google/vendor/market events separately labeled.

## Suggested next checks
Prefer high-information, low-risk tests.

## Unknowns
What data is missing.

## Conclusion
May be:
`unresolved`.

The output should never hide uncertainty behind polished prose.

[PRODUCT-SPEC]

# 115. Example — traffic incident

User:
“Organic traffic started falling around 4 August.”

Engine:
1. verify GA4 measurement integrity;
2. isolate Organic Search/Discover vs other channels;
3. inspect Search Console impressions/clicks/CTR/position;
4. segment device/category/template;
5. compare robots/noindex/canonical/status;
6. inspect mobile rendered state;
7. inspect deploy/script/template changes;
8. check official Google events;
9. check incident-corpus analogues;
10. rank causes + contradictions.

A new video player that exists on only 20% of affected pages should not outrank a Search-wide visibility shift without mechanism evidence.

[DOMAIN-EXAMPLE]

# 116. Example — monetization incident

User:
“Programmatic monetization on mobile worsened yesterday.”

Engine:
1. do not start with total raw revenue;
2. check mobile traffic/views;
3. expected ad structure;
4. GAM requests;
5. served/impressions/fill semantics;
6. direct/programmatic composition;
7. demand/programmatic channel;
8. eCPM/value;
9. GPT lifecycle;
10. Prebid/consent;
11. serving restrictions/floors;
12. Google/vendor external events.

If:
traffic stable
+ SSP-side activity stable
+ GAM requests fall
+ TCF errors begin
then consent/request eligibility outranks “market demand.”

[DOMAIN-EXAMPLE] [INCIDENT-CORPUS]

# 117. Example — site performance incident

User:
“Mobile site became slower after Wednesday.”

Engine:
1. confirm field vs synthetic symptom;
2. localize templates;
3. compare Last Known Good;
4. diff scripts/network dependencies;
5. inspect LCP/INP/CLS components;
6. inspect ad/player/CMP timing;
7. check long tasks/request delays;
8. detect third-party outage/change;
9. verify business/engagement impact.

Do not attribute a field INP regression to one newly added script merely because both share a date.

[DOMAIN-EXAMPLE]

# 118. Expert-review questions before production use

The following require real publisher/operator validation:

1. Minimum GAM report cubes that work reliably across target publishers.
2. Which GAM financial metrics publishers will permit.
3. How to normalize “ad structure” across naming conventions.
4. Normal request/impression ratios by common template patterns.
5. Which header-bidding configurations are prevalent enough locally to prioritize.
6. Which CMP controlled checks produce acceptable false-positive rates.
7. How often refresh behavior is intentionally undocumented.
8. Video player/vendor patterns worth first-class detection.
9. Practical recovery lags after common ad-serving fixes.
10. Which changes operators know are critical but cannot be detected externally.
11. How direct campaign starts are normally represented in GAM.
12. Which deployment/ticket metadata publishers can realistically annotate.
13. What severity makes an immediate alert truly actionable.
14. Which browser/device/geo scenarios are worth the extra crawling cost.

These answers should refine OPERATIONAL rules, not overwrite canonical platform facts.

[EXPERT-REVIEW]

# 119. Required eval families

Before the Incident Engine is trusted, create evals for:

### Positive diagnosis
- accidental noindex;
- slot removed;
- JS blocks GPT initialization;
- TCF issue reduces GAM requests;
- bidder timeout spike;
- floor-driven fill change;
- direct displacement;
- GA4 measurement break;
- VAST/render failure.

### Counterexamples
- Google update occurs but decline started before update;
- CMP version changes but behavior unchanged;
- revenue falls because zero-valued direct campaign starts;
- eCPM falls while total monetization rises;
- ads.txt changes but affected seller unused;
- one JS error appears on unaffected widget;
- synthetic CWV worse but field stable;
- SSP revenue drops for one publisher while same vendor stable elsewhere.

### Unresolved
Multiple plausible candidates, insufficient evidence.

The model passes only if it can decline to overclaim.

[INCIDENT-CORPUS]

# 120. DOMAIN v1.0 completion criteria

DOMAIN v1.0 is fit to start MVP engineering when:

- Codex can identify the main publisher systems and boundaries;
- metric semantics are namespaced and denominator-aware;
- GAM/GPT/GA4/GSC/Prebid/TCF current behavior is versioned;
- browser observations map to meaningful stages;
- failure modes have exclusion tests;
- external Google events are context rather than automatic causes;
- total GAM revenue is not treated as universal business truth;
- every 6-hour checkpoint is preserved;
- raw evidence remains separate from derived conclusions;
- alerting is low-noise/actionable;
- incident outputs expose contradictions and unknowns;
- expert reviewers can identify remaining operational gaps rather than foundational misunderstandings.

The next DOMAIN revision should be driven primarily by:
1. expert review;
2. pilot implementation;
3. real publisher incidents;
4. changes in external standards/platforms;
5. incident-corpus expansion.

---

# 121. Source key registry

The main DOMAIN text uses compact source keys. Detailed URLs and freshness are in `DOMAIN_SOURCE_REGISTRY_v1.0.md`.

### Uploaded corpus
- `[PRODUCT-SPEC]` — New platform.docx, product/reviewer notes.
- `[SRC-ADTECH-BOOK]` — The AdTech Book, New 2026 Edition.
- `[SRC-KOSORIN]` — Dominik Kosorin, Introduction to Programmatic Advertising; durable concepts only.
- `[SRC-BUSCH]` — Oliver Busch (ed.), Programmatic Advertising; publisher strategy/economics/historical context.
- `[SRC-HPBN]` — Ilya Grigorik, High Performance Browser Networking; durable network fundamentals.
- `[SRC-DDIA]` — Kleppmann & Riccomini, Designing Data-Intensive Applications, 2nd ed., 2026.
- `[INCIDENT-CORPUS]` — Public Publisher Incident Corpus v0.5.

### Current official web corpus
- `[SRC-GAM]`
- `[SRC-GAM-SELECTION]`
- `[SRC-GAM-DYNAMIC]`
- `[SRC-GAM-REPORTS-2026]`
- `[SRC-GAM-REPORT-DIMS]`
- `[SRC-GAM-API-QUOTA]`
- `[SRC-GAM-UNFILLED]`
- `[SRC-GAM-VAST-ERRORS]`
- `[SRC-GPT-EVENTS]`
- `[SRC-GPT-LAZY]`
- `[SRC-GPT-REFRESH]`
- `[SRC-GA4]`
- `[SRC-GA4-DATA]`
- `[SRC-GA4-EXPECTATIONS]`
- `[SRC-SEARCH]`
- `[SRC-SEARCH-HOW]`
- `[SRC-SEARCH-ROBOTS]`
- `[SRC-SEARCH-NOINDEX]`
- `[SRC-SEARCH-CANONICAL]`
- `[SRC-SEARCH-SITEMAP]`
- `[SRC-SEARCH-JS]`
- `[SRC-SEARCH-MOBILE]`
- `[SRC-GSC-API]`
- `[SRC-GSC-LIMITS]`
- `[SRC-GA4-GSC]`
- `[SRC-DISCOVER]`
- `[SRC-SEARCH-STATUS]`
- `[SRC-IAB-ADSTXT]`
- `[SRC-IAB-SUPPLY]`
- `[SRC-IAB-VALIDATION]`
- `[SRC-PREBID]`
- `[SRC-PREBID-EVENTS]`
- `[SRC-PREBID-TIMEOUTS]`
- `[SRC-PREBID-CONFIG]`
- `[SRC-PREBID-FLOORS]`
- `[SRC-PREBID-CONSENT]`
- `[SRC-PREBID-USERID]`
- `[SRC-PREBID-SERVER]`
- `[SRC-PREBID-VIDEO]`
- `[SRC-TCF]`
- `[SRC-TCF-23]`
- `[SRC-VAST]`
- `[SRC-OMSDK]`
- `[SRC-GOOGLE-VIDEO-POLICY]`
- `[SRC-GOOGLE-PUBLISHER-RESTRICTIONS]`
- `[SRC-BETTER-ADS]`
- `[SRC-WEB-VITALS]`
- `[SRC-CWV-ADS]`
- `[SRC-SRE]`
- `[SRC-SRE-MONITORING]`
- `[SRC-SRE-TIMESERIES]`
- `[SRC-RTB-RESEARCH]`

---
