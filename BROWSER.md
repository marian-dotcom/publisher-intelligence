# BROWSER.md
## Synthetic Browser & 6-Hour Black Box Specification
### Publisher Incident Intelligence Platform — v1.0

**Audience:** Codex, engineering, technical reviewers  
**Status:** MVP implementation contract  
**Owner:** Product / Engineering  
**Depends on:** `DOMAIN.md`, `PRODUCT.md`, `MVP.md`  
**Feeds:** `DATA_MODEL.md`, `EVENTS.md`, `INCIDENT.md`, `EVALS.md`

---

# 0. Purpose

The browser subsystem is the platform's **independent runtime observer**.

Its job is not to generate traffic, test conversion funnels, scrape article content, or replace real-user monitoring.

Its job is to answer:

> **What did this publisher page actually look like and how did it actually behave in a controlled browser at a specific point in time?**

It creates the platform's recurring **black-box evidence**:
- screenshots;
- structural page state;
- scripts and dependencies;
- network behavior;
- JavaScript errors;
- advertising lifecycle observations;
- consent behavior;
- video/player behavior;
- SEO/runtime state;
- synthetic performance signals.

This evidence is collected **before an incident exists** so that, when a publisher reports a problem later, the platform can reconstruct the state before and after the incident.

---

# 1. Non-negotiable invariants

Codex MUST preserve these rules unless `DECISIONS.md` explicitly changes them.

## BROWSER-INV-001 — Six-hour checkpoint cadence

Every monitored representative URL MUST receive a scheduled browser checkpoint every **6 hours**.

The checkpoint is created even when:
- no diff is expected;
- no anomaly is known;
- the previous checkpoint was healthy;
- no incident is open.

A checkpoint is evidence of state, not only a response to change.

## BROWSER-INV-002 — Immutable evidence

A completed checkpoint MUST NOT be edited in place.

If:
- normalization improves;
- classification changes;
- an event rule changes;

derive new output from the original checkpoint.

Never rewrite historical raw evidence.

## BROWSER-INV-003 — Real browser execution

MVP browser observations MUST use **Playwright controlling Chromium**.

HTML-only fetching is insufficient for the main checkpoint because publisher pages depend on:
- JavaScript;
- lazy loading;
- asynchronous network activity;
- CMP decisions;
- GPT;
- header bidding;
- iframes;
- video players;
- viewport and scroll position.

## BROWSER-INV-004 — Controlled synthetic visits

Browser runs are **small controlled synthetic observations**.

They MUST NOT be designed to:
- simulate large user traffic volumes;
- load test the publisher;
- inflate pageviews/ad requests;
- create artificial monetization activity.

## BROWSER-INV-005 — Environment provenance

Every observation MUST record the environment that produced it.

A browser result without environment metadata is incomplete evidence.

## BROWSER-INV-006 — Synthetic is not production truth

A synthetic run MUST NEVER be represented as proof that all real users saw the same state.

It is one controlled observation under a known environment.

## BROWSER-INV-007 — Evidence before interpretation

The browser subsystem collects facts.

It MUST NOT decide:
- root cause;
- publisher business impact;
- causal confidence;
- whether Google penalized a page.

Those belong to downstream systems.

## BROWSER-INV-008 — KISS

Do not add:
- browser farms;
- dozens of device profiles;
- residential proxy meshes;
- proprietary RUM SDKs;
- full session replay;
- multi-browser matrices;

until a validated pilot need exists.

---

# 2. Why Playwright + Chromium

The MVP backend is Python-based, so browser automation SHOULD use the Playwright Python async API.

Playwright is suitable because it can:
- operate isolated browser contexts;
- emulate desktop/mobile device properties;
- control geolocation, locale, timezone and permissions;
- monitor requests and responses;
- observe page/console errors;
- capture screenshots;
- execute page interactions;
- use Chromium DevTools Protocol where the standard Playwright API is insufficient.

Official Playwright documentation states that BrowserContexts provide independent sessions and that non-persistent contexts do not write browsing data to disk.

MVP default:

```text
one long-lived Chromium browser process per worker
    ↓
fresh isolated BrowserContext per scenario
    ↓
one Page per URL run
    ↓
close context after evidence persistence
```

Do not run all observations inside one shared user session.

---

# 3. Browser process architecture

Logical structure:

```text
Scheduler
   │
   ▼
Browser Job
   │
   ▼
Browser Worker
   │
   ├── Chromium process
   │
   ├── BrowserContext: scenario A
   │      └── Page
   │
   ├── BrowserContext: scenario B
   │      └── Page
   │
   └── Artifact collector
           │
           ├── screenshots
           ├── normalized observations
           ├── raw evidence
           └── checkpoint manifest
```

MVP SHOULD reuse the Chromium process across jobs for efficiency.

MVP MUST create clean contexts per scenario to prevent contamination between:
- cookies;
- localStorage;
- sessionStorage;
- permissions;
- cache/session state.

A worker crash MUST NOT corrupt already persisted checkpoints.

---

# 4. Monitored site model

The browser subsystem monitors **representative URLs grouped by template**, not every page on a publisher.

Typical templates:

- homepage;
- category/section;
- standard article;
- video article;
- gallery;
- live blog;
- tag/topic;
- special page.

A monitored URL record SHOULD contain:

```yaml
url:
template_id:
publisher_id:
priority:
is_canary:
expected_features:
  gpt: true
  prebid: optional
  cmp: true
  video: false
interaction_profile:
active: true
```

The URL list is configuration/state.  
The browser runtime MUST NOT invent new templates silently.

Automatic discovery MAY suggest template candidates, but promotion into the monitored set requires deterministic rules or user/operator approval.

---

# 5. Representative URL strategy

For an initial publisher, target approximately **20–40 representative URLs total**, depending on site complexity.

Do not interpret this as:
20–40 URLs × every possible browser state × every device × every geography.

The unit to control is:

```text
representative URL × scenario × cadence
```

Cost and site impact must remain bounded.

For dynamic article URLs, the system MAY rotate the concrete URL while preserving the same `template_id`.

If a URL is replaced, retain history of which concrete URL represented the template at each checkpoint.

---

# 6. Scenario model

A **scenario** is a reproducible browser state + interaction plan.

A scenario contains:

```yaml
scenario_id:
device_profile:
viewport:
user_agent:
locale:
timezone:
geo_profile:
storage_profile:
consent_path:
interaction_profile:
cache_mode:
network_profile:
```

Do not mix scenario identity with publisher/template identity.

---

# 7. MVP scenario matrix

DOMAIN lists useful scenarios:
- clean first visit;
- consent accepted;
- consent rejected;
- desktop;
- mobile.

MVP MUST avoid the naïve Cartesian product.

We do **not** run every combination for every URL every six hours.

## 7.1 Core 6-hour scenarios

For each representative URL, the default 6-hour cadence SHOULD run:

### CORE-DESKTOP
- clean non-persistent context;
- desktop profile;
- first-visit state;
- observe pre-consent state;
- follow configured primary consent path, normally Accept where ethically/legally appropriate for synthetic testing;
- execute template interaction script;
- collect post-consent ad/runtime evidence.

### CORE-MOBILE
Same logic using the canonical mobile profile.

This gives us:
- pre-consent evidence;
- post-consent runtime;
- desktop/mobile comparison;
without requiring separate browser contexts for every phase.

## 7.2 Reject scenario

`CONSENT-REJECT` SHOULD NOT automatically run for every URL every six hours.

Default MVP strategy:

- one canary URL per major template;
- daily cadence;
- mobile first;
- expand only if the publisher/incident demonstrates diagnostic value.

## 7.3 Additional geography

Geo scenarios MUST be opt-in/configured.

Do not create a proxy/geo system in MVP merely because geo-specific behavior is theoretically possible.

## 7.4 Incident-triggered scenarios

`INCIDENT.md` MAY request temporary additional runs such as:
- Accept vs Reject;
- mobile vs desktop;
- a specific viewport;
- specific template;
- repeated run for intermittent behavior.

These are investigation jobs, not permanent monitoring expansion.

Per ADR-130, such runs (and operator/tooling-initiated diagnostic runs) carry an explicit
observation kind and persistent trigger provenance. They remain immutable evidence but never
silently enter scheduled cadence, comparison lineage, event confirmation cohorts, or future
Last Known Good eligibility unless a versioned rule explicitly allows it.

---

# 8. Canonical device profiles

MVP should begin with only two canonical profiles.

## DESKTOP
A stable Chromium desktop profile.

Example target class:
- viewport around 1440 × 900;
- device scale factor 1;
- desktop user agent;
- pointer/mouse behavior.

## MOBILE
A stable modern smartphone profile.

Prefer a Playwright-supported device descriptor or an explicit frozen profile.

The exact device configuration MUST be versioned.

Do not silently change the mobile device profile when Playwright updates.

Store:

```text
device_profile_name
device_profile_version
viewport
device_scale_factor
user_agent
is_mobile
has_touch
```

Changing canonical device profile is an operational change because it can alter page behavior.

---

# 9. Browser version reproducibility

Every checkpoint MUST record:

- Playwright package version;
- Chromium build/version;
- browser launch arguments relevant to behavior.

Do not auto-upgrade Playwright/Chromium in production without recording it as a platform change.

A browser upgrade can change:
- rendering;
- cookie behavior;
- privacy behavior;
- performance;
- JavaScript execution;
- screenshots.

Browser upgrades SHOULD be staged and validated against known pages.

---

# 10. Browser launch policy

Default:

- Chromium;
- headless production mode;
- no user extensions;
- no personal profile;
- no logged-in accounts;
- no ad blocker;
- no custom privacy extension;
- no persistent profile.

Do not disable standard browser security mechanisms merely to make a page easier to inspect.

If a CSP, mixed-content, cross-origin or browser restriction blocks something, that can be meaningful evidence.

---

# 11. Browser context isolation

Each scenario MUST use a new isolated BrowserContext.

Default:
- non-persistent;
- no pre-existing storage;
- no authentication;
- only configured permissions;
- controlled locale/timezone.

Do not share:
- cookies;
- storage;
- service-worker state;
- cache;
between scenarios unless the scenario explicitly models a returning visitor.

A returning-user scenario is out of the initial core matrix unless validated as necessary.

---

# 12. Navigation protocol

A standard navigation run SHOULD follow this high-level sequence:

```text
1. create isolated context
2. register listeners BEFORE navigation
3. create page
4. navigate
5. wait for initial document readiness
6. observe pre-consent state
7. capture pre-consent viewport evidence if applicable
8. execute consent action if configured
9. wait for controlled post-consent stabilization
10. execute interaction profile
11. collect final runtime state
12. capture screenshots
13. persist artifacts + manifest
14. close context
```

Listeners MUST be attached before `page.goto()` so early requests/errors are not missed.

---

# 13. Navigation completion

Do not define success solely as `networkidle`.

Publisher pages may maintain:
- analytics connections;
- ad refresh;
- long polling;
- async widgets;
- late third-party calls.

MVP SHOULD use a bounded stabilization strategy such as:

```text
document navigation completed
+ DOMContentLoaded/load evidence
+ configurable quiet/stabilization window
+ absolute max time
```

A page that never becomes “network idle” MUST still produce a checkpoint with:
- partial evidence;
- timeout status;
- observed outstanding/failing dependencies.

Do not discard the run simply because a late vendor never becomes quiet.

---

# 14. Time budgets

All waits MUST be bounded.

No browser job may wait indefinitely.

Suggested conceptual budgets:

```text
navigation timeout
consent discovery timeout
consent action timeout
post-consent stabilization timeout
interaction step timeout
overall scenario timeout
```

Exact numbers belong in config and are calibrated in pilot.

Do not hard-code random sleeps throughout the code.

Use:
- observable state;
- bounded waits;
- one shared timing configuration.

---

# 15. Retry policy

Retry distinguishes:
- observation failure;
- page failure.

Example:

If Playwright crashes:
→ retry may be appropriate.

If the page returns 503:
→ that is evidence and should not be “retried away” until the checkpoint looks healthy.

Default:

- one technical retry for browser/runtime failure;
- preserve both attempt metadata;
- do not replace a real site error with a successful retry.

If first run shows 503 and second run works:
record:
`intermittent availability`.

Do not persist only the healthy retry.

---

# 16. Screenshot policy

Screenshots are first-class artifacts.

## 16.1 Required screenshots

Core checkpoint SHOULD capture:

### A. Initial viewport
Before interaction/consent action where meaningful.

### B. Post-consent / primary runtime viewport
After configured consent path has stabilized.

### C. Interaction milestone screenshots
Only at selected meaningful steps, not every 5% of scroll.

### D. Full-page screenshot
At the **end** of the run.

## 16.2 Why full-page screenshot is last

Evidence collection must avoid changing the state before the important runtime observations have completed.

Full-page capture MAY interact with rendering/lazy-loading behavior depending on implementation/browser behavior.

Therefore:
- collect lifecycle/network/interaction evidence first;
- capture full-page visual artifact last.

## 16.3 Screenshot format

MVP may store high-quality PNG or JPEG.

Storage strategy should be simple:
- object storage;
- content hash;
- artifact metadata;
- lifecycle/retention policy.

Do not build computer-vision screenshot diffing in the first browser milestone unless needed.

Initial screenshot comparison can use:
- side-by-side UI;
- basic perceptual hash/structural comparison later.

---

# 17. Screenshot privacy

Screenshots may contain:
- personalized modules;
- user/account UI;
- emails;
- form values;
- cookie IDs.

Synthetic sessions reduce this risk but do not eliminate it.

MVP MUST:
- never log into real user accounts;
- avoid filling personal forms;
- mask known sensitive selectors if configured;
- restrict artifact access by tenant;
- follow retention rules.

Do not store screenshots in public buckets.

---

# 18. DOM capture strategy

Do not treat the raw HTML string as the final site representation.

Capture two layers:

## RAW DOM SNAPSHOT
Useful for forensic evidence.

Retention may be shorter.

## NORMALIZED STRUCTURAL DOM
Used for comparison and long-term memory.

Normalization SHOULD remove or reduce volatile values.

---

# 19. DOM normalization

Default noise candidates:

- article text;
- headlines;
- timestamps;
- recommendation ordering;
- cache-busting values;
- random IDs;
- session IDs;
- auction IDs;
- creative URLs;
- tracking parameters;
- personalized content where recognizable.

Meaningful candidates:

- element hierarchy;
- major containers;
- ad-slot containers;
- player containers;
- sticky/fixed/overlay classes/styles;
- script tags;
- iframe structure;
- SEO meta;
- canonical;
- content visibility state.

Normalization MUST be deterministic and versioned.

Store:

```text
normalizer_version
```

A new normalizer does not rewrite the old checkpoint.

It creates a new derived representation.

---

# 20. Layout/visual structure

The browser SHOULD observe properties useful for publisher incidents:

- bounding boxes of important components;
- computed `position` for sticky/fixed elements;
- z-index where relevant;
- ad-slot dimensions;
- player dimensions;
- visible/hidden state;
- reserved ad space;
- overlay/fullscreen-like coverage.

Do not persist every computed CSS property.

Only capture properties tied to known DOMAIN failure modes.

---

# 21. Network collection

Playwright provides request/response monitoring for page traffic.

The browser collector SHOULD observe:

- request URL;
- method;
- resource type;
- initiator context where available;
- response status;
- failure reason;
- request timing;
- selected headers where safe;
- redirect chain;
- transfer/size information where available;
- first-party/third-party classification.

Network collection MUST include requests initiated by:
- XHR;
- fetch;
- scripts;
- images;
- media;
- iframes;
- ad tech.

Do not store sensitive request bodies by default.

---

# 22. Network normalization

Full request URLs are noisy.

Normalize dependencies into stable identities.

Example:

```text
https://bidder.example.com/openrtb2?auctionId=abc123
https://bidder.example.com/openrtb2?auctionId=def456
```

should normally map to the same dependency/path family.

Suggested identity:

```yaml
registrable_domain:
host:
path_family:
resource_type:
functional_category:
```

Functional categories:

- publisher/API;
- CDN;
- analytics;
- Google ad serving;
- header bidding/SSP;
- CMP/privacy;
- video/player;
- recommendation;
- social;
- verification;
- unknown.

---

# 23. Network event candidates

Browser layer may later feed event candidates such as:

- persistent dependency added;
- dependency removed;
- repeated 4xx/5xx;
- repeated timeout;
- redirect chain appeared;
- latency materially changed;
- CSP/browser block;
- critical script unavailable.

A single failed tracking pixel MUST NOT automatically become an event.

`EVENTS.md` owns the final promotion logic.

---

# 24. Console and JavaScript errors

Register listeners before navigation.

Collect:
- console errors;
- uncaught page errors;
- browser/page crashes where exposed.

Preserve:
- message;
- source URL;
- line/column where available;
- stack where available;
- timestamp relative to navigation.

Normalize fingerprints so the same repeated error can be grouped.

Example fingerprint inputs:
- error type;
- normalized message;
- source script/path;
- top stack frame.

---

# 25. JS error relevance is downstream

The browser collector records errors.

It MUST NOT decide:
“this error caused revenue loss.”

Downstream relevance can consider:
- new vs historical;
- persistence;
- affected template;
- timing before GPT/Prebid/CMP/player initialization;
- missing expected requests.

---

# 26. GPT detection

If Google Publisher Tag exists, the browser collector SHOULD detect and record:

- GPT presence;
- GPT version/build signal if safely available;
- defined slots;
- slot ad-unit path/code;
- slot sizes where available;
- slot DOM element;
- lifecycle events.

Core lifecycle:

```text
expected slot
→ defined
→ slotRequested
→ slotResponseReceived
→ slotRenderEnded
→ slotOnload
→ impressionViewable
```

Important:

`slotRenderEnded` means creative code has been injected.

It does NOT prove all creative resources completed loading.

The collector MUST preserve stage distinctions.

---

# 27. GPT expected-slot model

“Expected slot” is not purely discovered from current DOM.

It should come from:
- template baseline;
- previous healthy checkpoints;
- configured template expectation.

Otherwise a deleted slot would simply disappear from observation and the system would not know it was missing.

The browser collector should emit observations that allow downstream logic to say:

```text
expected slot: article_mid_2
current state: absent
```

The expected-state model will ultimately belong to publisher/template data in `DATA_MODEL.md`.

---

# 28. GPT request/render evidence

Per slot, collect where possible:

```yaml
slot_id:
ad_unit_path:
dom_element_id:
sizes:
defined_at:
requested_at:
response_received_at:
render_ended_at:
onload_at:
viewable_at:
is_empty:
creative_id_if_exposed:
line_item_id_if_exposed:
```

Do not require every field.

Missing data is valid and must remain explicit.

Do not invent an event timestamp if an event was not observed.

---

# 29. Lazy-loading observations

A slot not requested at page load may be correct.

The interaction script MUST allow downstream logic to distinguish:

```text
slot absent
```

from:

```text
slot exists but is below viewport and intentionally lazy
```

Useful evidence:
- DOM presence;
- bounding box;
- distance from viewport;
- request occurrence after scroll;
- request milestone.

A request decline after a lazy-load change is not automatically a defect.

---

# 30. Refresh observations

Where visible, collect:

- multiple request lifecycles for same slot;
- approximate interval;
- whether refresh occurs only when visible;
- whether a new Prebid auction occurs before refreshed GAM targeting where applicable.

Do not classify refresh as good/bad.

Record behavior.

---

# 31. Prebid detection

If `pbjs` or another recognizable Prebid surface is available, collect observable state.

Potential observations:

- Prebid present;
- version;
- configured ad units;
- bidders;
- modules where detectable;
- auction timeout;
- auction start/end;
- bidder request;
- bid response;
- no-bid;
- timeout;
- bid won;
- ad-server request;
- targeting values where safely observable.

Do not assume every publisher exposes Prebid in the same global shape.

Feature-detect.

---

# 32. Prebid Server limitation

If bidding is server-side:

The browser may observe only:
- the server endpoint;
- high-level request;
- final response;
- client-side integration events.

It may not see:
- every hidden bidder;
- server-side bid timing;
- rejection logic;
- server logs.

The checkpoint MUST carry observability limitation metadata when appropriate.

Never fabricate bidder-level evidence from a single server endpoint.

---

# 33. Header-bidding timing

Capture enough timing to later compare:

```text
auction start
bidder request
bid response / timeout
auction end
targeting set
GAM request start
```

This supports failure patterns such as:
- timeout too short;
- timeout too long;
- RTD/user-ID delay;
- targeting propagation failure.

The browser collector does not decide the optimal timeout.

---

# 34. CMP detection

CMP observability is behavior-first.

Potential evidence:

- CMP API/stub exists;
- TCF API exists;
- consent UI found;
- UI appeared at time T;
- TC String readable where allowed;
- `gdprApplies`/related state where exposed;
- consent event/status;
- time to usable consent state.

CMP brand/version may be recorded if reliable, but is secondary.

---

# 35. Consent action system

Do not implement one giant hard-coded selector list inside the browser runner.

Use a consent action abstraction.

Example:

```yaml
consent_adapter:
  type: known_cmp | generic | manual_config
  vendor:
  accept_selector:
  reject_selector:
  ready_condition:
```

Order of resolution:

1. publisher-specific configured adapter;
2. known CMP adapter;
3. conservative generic detection;
4. `action_unavailable`.

If the system cannot safely identify Accept/Reject:
do not click random buttons.

Record:
`consent_action_status = unavailable`.

---

# 36. Consent phases

For a fresh-visit scenario:

## PRE_CONSENT
Capture:
- screenshot viewport;
- CMP presence;
- initial network behavior;
- GPT/Prebid state if any;
- analytics calls;
- TC state if available.

## ACTION
Attempt configured Accept or Reject.

## POST_CONSENT
Capture:
- consent state;
- network changes;
- ad-tech requests;
- analytics behavior;
- GPT/Prebid activity;
- visual state.

This allows comparison inside the same run.

---

# 37. Consent timing

Store timing such as:

```text
navigation_start
cmp_detected
cmp_ready
consent_action_started
consent_action_completed
tc_state_available
first_prebid_auction
first_gpt_request
```

Do not assume CMP timing is the cause of an ad issue.

Timing is evidence for downstream investigation.

---

# 38. Video/player detection

Detect high-value player state:

- player present;
- player library/vendor if reliably fingerprinted;
- player container;
- dimensions;
- visibility;
- sticky/fixed state;
- controls state where observable;
- autoplay state;
- muted/audible state;
- media/video ad network calls;
- VAST-related requests/errors where visible.

Do not attempt to reverse-engineer every proprietary player implementation in MVP.

Use adapters only when repeated pilot value exists.

---

# 39. Video interaction

For video templates, the interaction profile MAY include:

- scroll until player enters viewport;
- observe whether autoplay starts;
- scroll past player;
- observe whether it becomes sticky;
- verify dismiss/controls presence;
- collect screenshots.

Do not intentionally play long content for minutes.

Bound observation time.

---

# 40. VAST evidence

Where observable, record:
- video ad request;
- VAST response status;
- wrapper-related requests;
- media resource request;
- common VAST error signals;
- player/render outcome.

A VAST response is not proof of a played impression.

Preserve stage distinctions.

---

# 41. SEO runtime evidence

For each checkpoint, browser/runtime layer SHOULD record:

- final URL;
- HTTP status;
- redirect chain;
- title;
- meta robots;
- canonical;
- rendered key directives;
- viewport/mobile state;
- presence of important content container;
- relevant JS failure that may affect rendering.

robots.txt and sitemap fetching may be done by a lightweight public/config collector rather than the page browser itself, but browser checkpoint manifest may reference their latest known state.

---

# 42. Synthetic performance collection

MVP browser observation should collect a bounded set of synthetic performance signals.

At minimum consider:
- navigation timing;
- LCP;
- CLS;
- INP proxy / interaction observations where feasible;
- long tasks;
- resource timing;
- DOM/node counts where useful.

Do not overbuild a Lighthouse clone.

The goal is incident evidence, not a complete performance-audit product.

---

# 43. Field vs synthetic provenance

Every performance value MUST carry provenance.

Example:

```yaml
metric: cls
value: 0.19
source: synthetic_browser
scenario: core_mobile
```

This MUST NOT be directly presented as the site's real-user p75 CLS.

If CrUX/Search Console field data exists, downstream systems can compare it separately.

---

# 44. Long tasks and runtime performance

Where feasible, observe:
- main-thread long tasks;
- timing around interaction;
- layout shifts;
- resource competition.

Use Chrome/Performance APIs or CDP only where needed.

Do not make raw CDP usage the default if Playwright/page APIs provide sufficient information.

CDP is an escape hatch, not the architecture.

---

# 45. Interaction profiles

Interaction profiles belong to template configuration.

Example:

```yaml
article_default:
  - wait: initial_stabilization
  - consent: primary
  - scroll_to: 25%
  - wait: short
  - scroll_to: 50%
  - wait: short
  - scroll_to: 75%
  - inspect: sticky_and_video
```

Video template may have a different profile.

Homepage may need less scroll.

Do not hard-code one interaction sequence for the entire internet.

---

# 46. Scroll implementation

Scroll MUST be deterministic enough for comparison.

Prefer:
- percentage of document height;
- or meaningful configured anchor.

Avoid:
- random scrolling;
- human-like noise;
- variable acceleration.

Store:
- target position;
- actual scroll position;
- timestamp;
- page height.

If document height changes dramatically, percentage-based comparison has limitations; record actual pixels too.

---

# 47. Interaction side effects

Interactions can change the page.

Therefore record them as part of evidence.

Example:
- clicking consent;
- opening/closing popup;
- scrolling;
- interacting with video.

The checkpoint manifest MUST allow a reviewer to know **what the browser did** before a screenshot or observation.

---

# 48. A/B and variant detection

Attempt to detect clues such as:
- experiment cookies;
- known experimentation scripts;
- variant query parameters;
- mutually exclusive component signatures.

Do not claim full experiment attribution.

If different clean contexts repeatedly receive different variants:
record:
`variant_instability_detected`.

Downstream logic decides relevance.

---

# 49. Service workers and caches

Service workers/cache can alter runtime behavior.

MVP policy:
- each core scenario starts from a fresh non-persistent context;
- this intentionally models a clean synthetic visit;
- it does not model every returning-user cache state.

If a future incident requires returning-user behavior, add an explicit scenario rather than contaminating the core baseline.

---

# 50. Popups and secondary pages

A page may open:
- login;
- consent;
- ad landing;
- popup.

Do not follow arbitrary external popups.

Record:
- popup opened;
- URL/domain;
- source action.

Close or ignore unless the interaction profile explicitly requires it.

Never click advertising creatives.

---

# 51. Ads and ethical interaction policy

Synthetic monitoring MUST NOT:
- intentionally click ads;
- generate conversion events;
- interact with advertiser landing pages;
- repeatedly refresh for the purpose of producing billable impressions.

The system observes publisher behavior.

It is not an ad-fraud generator.

---

# 52. Authentication

MVP browser monitoring targets public publisher pages.

Do not implement authenticated user monitoring in the first version.

If a publisher has a paywall:
- observe the public/non-authenticated state;
- record paywall presence;
- do not bypass it.

---

# 53. Bot detection

Some publishers/vendors may behave differently for automated/headless browsers.

The platform MUST NOT disguise itself to evade anti-bot systems.

If the site blocks or changes behavior for the synthetic monitor:
record that limitation.

Future publisher-authorized allowlisting is preferable to stealth/evasion.

---

# 54. Geolocation

Playwright can emulate geolocation, but IP-based geo behavior may depend on egress location.

Do not confuse:
- browser geolocation API emulation;
with
- IP geography.

If geo-specific monetization/consent matters, the infrastructure location/proxy must be a separate explicit capability.

MVP does not require a global proxy network.

---

# 55. Network throttling

Default six-hour black-box runs SHOULD use the normal controlled infrastructure network without artificial throttling.

Performance test profiles MAY use explicit network/CPU conditions later.

Do not mix throttled and unthrottled results under the same scenario ID.

---

# 56. Artifact manifest

Every scenario run MUST produce one manifest that links all evidence.

Conceptual shape:

```yaml
checkpoint_id:
publisher_id:
site_id:
template_id:
url:
scenario_id:
scheduled_for:
started_at:
completed_at:
status:
browser:
  playwright_version:
  chromium_version:
  headless:
environment:
  viewport:
  user_agent:
  locale:
  timezone:
  region:
  cache_mode:
consent:
  path:
  status:
interaction_profile:
artifacts:
  screenshots: []
  raw_dom:
  normalized_dom:
observations:
  network_summary:
  js_errors:
  gpt:
  prebid:
  cmp:
  video:
  seo:
  performance:
limitations: []
attempts: []
collector_versions: {}
```

`DATA_MODEL.md` will define final persistence schema.

BROWSER.md defines the semantic contract.

---

# 57. Collector versioning

Each major collector/normalizer SHOULD expose a version.

Examples:

```text
dom_collector_version
dom_normalizer_version
network_normalizer_version
gpt_collector_version
prebid_collector_version
cmp_collector_version
video_collector_version
performance_collector_version
```

Why:
a collector change can make before/after data look different.

The Incident Engine needs to know whether a diff reflects:
- publisher change;
or
- our collector change.

---

# 58. Checkpoint status

A checkpoint is not only `success/fail`.

Suggested statuses:

```text
COMPLETE
PARTIAL
SITE_ERROR
BROWSER_ERROR
TIMEOUT
BLOCKED
```

Examples:

`SITE_ERROR`
- site returned 503.

`BROWSER_ERROR`
- Chromium process crashed.

`PARTIAL`
- page loaded, but CMP action could not be completed.

Do not classify a publisher 503 as browser failure.

---

# 59. Partial evidence

A partial run still matters.

If:
- screenshot exists;
- DOM exists;
- network shows 503 dependencies;
- GPT never initializes;

persist it.

Do not discard useful evidence because one collector failed.

Each collector can have:

```text
OK
NOT_PRESENT
NOT_OBSERVABLE
ERROR
TIMEOUT
```

This is better than null with unknown meaning.

---

# 60. Failure isolation

Collectors SHOULD fail independently where practical.

Example:
Prebid collector throws an internal parser error.

The checkpoint should still preserve:
- screenshot;
- DOM;
- network;
- JS errors;
- GPT;
- SEO.

Avoid one optional integration crashing the whole checkpoint.

---

# 61. Raw versus normalized evidence

Store enough raw evidence to audit important conclusions.

But do not store everything forever.

Conceptual retention:

### Longer
- checkpoint manifest;
- screenshots;
- normalized DOM;
- important network summary;
- normalized errors;
- GPT/Prebid/CMP/video observations.

### Shorter/conditional
- full raw HTML/DOM;
- detailed raw network log;
- Playwright trace.

Retention belongs to `SECURITY.md` / data policy.

---

# 62. Playwright tracing

Playwright tracing is valuable but can be expensive in storage.

MVP SHOULD NOT permanently retain a full trace for every successful six-hour checkpoint.

Suggested policy:
- enable/retain trace on browser failure;
- retain for critical anomaly reproduction;
- retain for incident-triggered diagnostic jobs;
- optionally sample healthy runs.

Do not make Trace Viewer the core product data model.

---

# 63. Browser logs

Structured logs SHOULD include:

- job/checkpoint ID;
- publisher;
- template;
- scenario;
- stage;
- duration;
- failure class.

Do not log:
- OAuth secrets;
- raw cookies;
- full TC Strings if policy decides they are sensitive;
- arbitrary request bodies;
- personal data.

---

# 64. Concurrency and politeness

The monitor must behave politely toward publisher infrastructure.

MVP default:
- low concurrency per publisher;
- stagger URL runs;
- bounded retries;
- no burst of 40 pages at the same millisecond.

Scheduler SHOULD spread work within the checkpoint window.

For a 6-hour checkpoint:
“scheduled at 12:00” does not require every URL to start at exactly 12:00:00.

The manifest stores actual run time.

---

# 65. Cadence semantics

`6-hour checkpoint` means the platform aims to observe each configured core URL/scenario once in each six-hour monitoring window.

It does not mean exact synchronized atomic capture of the whole site.

If cross-page timing becomes important for an incident:
run an incident-triggered synchronized sample.

---

# 66. Site discovery before steady-state monitoring

On onboarding, run a discovery phase.

Goal:
- identify template candidates;
- scripts;
- ad stack;
- CMP;
- Prebid;
- video;
- important page types.

Discovery MAY use more URLs temporarily.

Steady-state monitoring then reduces to the representative set.

Discovery output is not automatically a permanent monitor configuration.

---

# 67. Browser-generated observations vs events

Browser collector may output:

```text
slot_count = 4
script_domain = x.example
cmp_detected = true
```

`EVENTS.md` decides whether this becomes:

```text
ad_slot_removed
third_party_dependency_added
consent_behavior_changed
```

Do not duplicate event logic inside browser collectors.

---

# 68. Browser-generated observations vs incidents

A browser observation can suggest risk.

It does not open an incident automatically unless alert/event policy says so.

Example:
new script appears.

That is not:
`Incident: traffic decline caused by script`.

The Incident Engine combines browser evidence with:
- GA4;
- GSC;
- GAM;
- external events;
- operational changes;
- incident corpus.

---

# 69. Expected-noise examples

Usually noise:

- new article title;
- article body changes;
- changing recommendations;
- creative image/URL;
- auction ID;
- cachebuster;
- random DOM ID;
- timestamp;
- rotating “most read” content.

Potentially meaningful:

- script dependency added/removed;
- expected GPT slot added/removed;
- player added/removed;
- sticky state changed;
- CMP runtime changed;
- canonical/noindex changed;
- persistent JS error;
- dependency starts timing out;
- layout structure changed.

---

# 70. Screenshot diffing — MVP stance

Do not begin by building an advanced computer-vision model.

MVP needs:
- stored screenshots;
- timeline;
- side-by-side comparison;
- selected basic metadata.

Later:
- perceptual hash;
- region-level diffs;
- visual element detection.

Only add if browser checkpoints prove valuable.

---

# 71. Ad-density observation

MVP MAY estimate ad density using:
- visible ad-slot geometry;
- viewport/content area;
- sticky/fixed ad surfaces.

This is an approximation.

Do not claim precise compliance unless the relevant standard can be measured correctly.

Store:
- method/version;
- evidence screenshot;
- calculated approximation.

---

# 72. Sticky/overlay detection

Potential signals:
- `position: fixed`;
- `position: sticky`;
- viewport overlap;
- z-index;
- bounding-box intersection;
- persistent element during scroll.

Classification can include:
- ad;
- player;
- CMP;
- unknown.

Do not label an unknown fixed element “aggressive ad” solely from CSS.

---

# 73. Performance contamination by the monitor

Instrumentation itself can affect timing.

The collector SHOULD minimize injected JavaScript.

Where possible:
- use browser/platform observer APIs;
- avoid large injected frameworks;
- avoid repeated heavy DOM serialization during critical performance windows.

Record collector version so performance shifts after instrumentation changes can be identified.

---

# 74. Browser upgrade test suite

Before upgrading Playwright/Chromium in production, run a small reference suite.

Reference pages should test:
- simple article;
- CMP;
- GPT;
- Prebid;
- lazy load;
- video;
- sticky;
- redirects;
- JS error collection.

Compare expected observation contracts, not pixel-perfect browser rendering.

---

# 75. Testability

All collectors SHOULD be testable against local fixtures.

We need fixture pages for:

- GPT lifecycle mock/stub;
- lazy slot;
- slot removed;
- JS error before initialization;
- CMP accept/reject;
- consent timeout;
- Prebid-style auction timing mock;
- sticky player;
- VAST/video mock;
- noindex/canonical;
- 503/timeout;
- network dependency failure.

Do not rely entirely on live third-party websites for tests.

---

# 76. Browser unit/integration test boundaries

## Unit tests
For:
- normalization;
- fingerprints;
- classification helpers;
- timing transformations;
- manifest creation.

## Browser integration tests
For:
- navigation;
- screenshots;
- request listeners;
- JS errors;
- consent adapters;
- scrolling;
- GPT/Prebid hooks;
- video state;
- failure statuses.

## End-to-end pilot tests
For:
- a real configured publisher domain;
- full checkpoint persistence;
- repeated six-hour-compatible runs;
- diff compatibility.

---

# 77. Required browser eval cases

At minimum, browser subsystem must correctly observe:

### EVAL-BR-001
Expected GPT slot present and requested.

### EVAL-BR-002
Expected slot removed.

### EVAL-BR-003
JS error prevents GPT request.

### EVAL-BR-004
Lazy slot requests only after scroll.

### EVAL-BR-005
CMP appears, Accept succeeds, ad requests appear post-consent.

### EVAL-BR-006
Reject path produces a different request pattern without being labeled a failure.

### EVAL-BR-007
Third-party script returns 5xx.

### EVAL-BR-008
Page itself returns 503; checkpoint becomes SITE_ERROR not BROWSER_ERROR.

### EVAL-BR-009
Sticky player appears after scroll.

### EVAL-BR-010
Synthetic CLS changes but engine does not claim field-CWV regression.

### EVAL-BR-011
Prebid bidder timeout is observed.

### EVAL-BR-012
Prebid Server endpoint exists but hidden bidder details remain NOT_OBSERVABLE.

### EVAL-BR-013
Full-page screenshot is captured after core interaction evidence.

### EVAL-BR-014
Browser technical retry does not erase first real page failure evidence.

---

# 78. Security requirements

Before pilot:

- browser artifacts tenant-isolated;
- object storage private;
- no public URLs by default;
- logs redact sensitive data;
- browser uses clean contexts;
- no personal authentication;
- no form submission except configured CMP action;
- request bodies not stored by default;
- retention configurable.

Further detail belongs in `SECURITY.md`.

---

# 79. Operational metrics for the browser subsystem

We need observability for our observer.

Track:

- checkpoint jobs scheduled;
- checkpoint completion rate;
- complete/partial/site-error/browser-error rates;
- median run duration;
- artifact persistence failures;
- Chromium crashes;
- consent-action success rate;
- URLs repeatedly blocked;
- collector errors by collector version.

Do not confuse monitor health with publisher health.

---

# 80. Browser subsystem SLIs

Initial internal SLIs MAY include:

```text
scheduled_checkpoint_execution_rate
complete_or_partial_evidence_rate
artifact_persistence_success_rate
browser_worker_crash_rate
```

A `SITE_ERROR` can still be a successful browser observation.

Therefore:
browser subsystem success should mean:
**we reliably observed and preserved what happened**, not:
**the publisher page was healthy**.

---

# 81. MVP implementation milestones

Implement in this order.

## Milestone B1 — Minimal real-browser checkpoint
One URL, Chromium:
- navigate;
- timestamp;
- viewport screenshot;
- full-page screenshot;
- HTML/DOM;
- scripts;
- network domains;
- request failures;
- JS errors;
- HTTP/final URL;
- artifact manifest.

No AI.

## Milestone B2 — Repeatable 6-hour-compatible run
- isolated contexts;
- scenario identity;
- device profiles;
- deterministic interaction;
- object storage;
- checkpoint persistence.

## Milestone B3 — Template-aware collection
- representative URL config;
- template ID;
- stable DOM normalization;
- script/network fingerprints;
- expected-state references.

## Milestone B4 — GPT
- slot discovery;
- lifecycle events;
- lazy loading observations.

## Milestone B5 — CMP
- pre-consent;
- configurable Accept;
- post-consent;
- Reject canary path.

## Milestone B6 — Prebid
- presence/version;
- auctions;
- bidder requests/responses/timeouts;
- ad-server timing.

## Milestone B7 — Video/player
- player state;
- sticky behavior;
- basic VAST/network evidence.

## Milestone B8 — Synthetic performance
- bounded Core Web Vital/runtime signals.

Do not implement B8 before B1–B4 are reliable.

---

# 82. MVP acceptance criteria

BROWSER v1 is acceptable when, for one pilot domain:

1. the scheduler can produce four monitoring windows/day;
2. representative URLs run in isolated desktop/mobile contexts;
3. every run has environment provenance;
4. screenshots are persisted and retrievable;
5. raw + normalized DOM evidence exists;
6. scripts and network dependencies are observable;
7. JS/page errors are captured;
8. site error vs browser error is distinguished;
9. core GPT slot lifecycle is observable on supported pages;
10. consent pre/post behavior is observable on configured CMP;
11. interaction scripts can trigger lazy-loaded inventory;
12. optional Prebid observation does not crash non-Prebid pages;
13. optional video observation does not crash non-video pages;
14. collector version changes are recorded;
15. partial checkpoints are retained;
16. a browser retry never deletes the original evidence;
17. the subsystem does not click ads;
18. the subsystem does not generate uncontrolled traffic;
19. synthetic observations are clearly labeled synthetic;
20. downstream systems can compare two checkpoints deterministically.

---

# 83. Explicit non-goals for BROWSER v1

Do NOT build now:

- real-user monitoring SDK;
- session replay;
- residential proxy network;
- stealth anti-bot evasion;
- automated ad clicking;
- full cross-browser Safari/Firefox matrix;
- every mobile phone profile;
- automatic visual AI diagnosis;
- browser-based revenue attribution;
- publisher login/paywall bypass;
- full Chrome DevTools clone;
- permanent Playwright tracing for every successful run;
- automatic production remediation.

---

# 84. Open pilot questions

These must be answered empirically.

1. Is desktop + mobile every six hours necessary for every URL, or can some templates use one primary device?
2. How many representative URLs per template are needed for stable signal?
3. Which CMP vendors require dedicated adapters?
4. How often does Reject-path monitoring produce unique value?
5. Which Prebid signals are reliably accessible across target publishers?
6. Which video/player vendors deserve adapters?
7. How much screenshot/raw-DOM retention is economically useful?
8. How much full-page screenshot variation is normal due to editorial content?
9. Which interaction steps are enough to exercise lazy inventory without creating excessive requests?
10. Which performance signals are stable enough to compare at 6-hour cadence?
11. Do publisher anti-bot/CDN systems require allowlisting?
12. Which geographies are commercially important enough for separate infrastructure?

Do not resolve these by speculation.  
Use pilot evidence and record decisions in `DECISIONS.md`.

---

# 85. Codex rules specific to browser work

Codex MUST:

- prefer simple explicit collectors over a giant generic abstraction;
- add tests for every normalization rule;
- preserve raw evidence when a parser fails;
- never swallow exceptions silently;
- use typed/structured output contracts;
- distinguish `NOT_PRESENT` from `NOT_OBSERVABLE`;
- distinguish site failure from monitor failure;
- record collector/browser versions;
- keep waits bounded;
- avoid arbitrary sleep-heavy logic;
- avoid selectors that assume one publisher globally;
- never click an ad;
- never add stealth/evasion without an explicit decision;
- never turn a collector observation directly into root cause;
- preserve checkpoint immutability;
- update this file or `DECISIONS.md` when semantics materially change.

---

# 86. Official implementation references

Codex should consult the current official documentation before using a Playwright API whose behavior may have changed.

Primary references:

- Playwright Python documentation — general-purpose browser automation.
- Playwright BrowserContext documentation — isolated/non-persistent contexts.
- Playwright Network documentation — request/response monitoring.
- Playwright Page API — page events and errors.
- Playwright Request API — request timing.
- Playwright Emulation documentation — devices, geolocation, locale/timezone.
- Playwright CDPSession documentation — raw Chromium DevTools Protocol when necessary.
- Chrome DevTools Performance documentation — runtime performance, layout shifts and long tasks.

Current platform/standard semantics for GPT, Prebid, CMP/TCF, VAST and Search live in `DOMAIN.md` and its source registry.

---

# 87. Final browser principle

The browser subsystem should make it possible to answer this question months later:

> **“Show me how this page actually behaved before the incident, how it behaved after, and exactly what our synthetic observer did to produce that evidence.”**

If we cannot answer that reliably, the black-box concept has failed.

If we can, `EVENTS.md` and `INCIDENT.md` have trustworthy raw material to reason over.
