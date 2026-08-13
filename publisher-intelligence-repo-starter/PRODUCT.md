# PRODUCT.md
## Publisher Incident Intelligence Platform
### Product Specification — v1.0

**Audience:** Product, Codex, engineering, design, sales, pilot reviewers  
**Status:** Canonical product definition  
**Purpose:** Define what the product is, who it is for, what problem it solves, how users experience it, and what product behavior must remain true regardless of implementation  
**Depends on:** `MVP.md`, `DOMAIN.md`, `INCIDENT.md`, `EVENTS.md`, `BROWSER.md`, `CONNECTORS.md`, `EVALS.md`  
**Implementation details live in:** `ARCHITECTURE.md`, `DATA_MODEL.md`, `SECURITY.md`, subsystem specifications

---

# 0. Product in one sentence

> **The operational memory and incident investigator for digital publishers.**

Alternative formulation:

> **A black-box recorder for publishers that continuously remembers what changed across the website, traffic, Search and monetization, then reconstructs the evidence when something goes wrong.**

Formal formulation:

> **A publisher observability and incident-intelligence platform that continuously records the technical and business state of a digital publisher, then reconstructs what changed and ranks the most plausible explanations when an incident occurs.**

---

# 1. The problem

Digital publishers depend on many interconnected systems:

```text
website templates
JavaScript
consent/CMP
Google Publisher Tag
Prebid/header bidding
video players
Google Ad Manager
analytics
Search
Discover
CDN/infrastructure
demand partners
third-party scripts
external platforms
```

A problem can surface as:

```text
traffic down
Search down
Discover down
ads not serving
programmatic revenue down
fill down
eCPM down
page slower
video not working
policy restriction
layout broken
```

But the symptom rarely reveals the cause.

Today, many incident investigations begin after the important evidence has already disappeared.

Teams ask:

```text
What changed?
When?
Who changed it?
Was this already happening?
Was it Google?
Was it the player?
Was it CMP?
Was it the ad stack?
Was traffic already declining?
Did removing the suspected component help?
```

Often nobody can answer confidently.

---

# 2. Existing workflow failure

A typical publisher incident today can look like:

```text
Symptom noticed
        ↓
Dashboard checked
        ↓
Teams/vendors asked
        ↓
Everyone proposes a theory
        ↓
Several changes made at once
        ↓
Components disabled
        ↓
Revenue / traffic opportunity lost
        ↓
No clean control group remains
        ↓
Root cause still uncertain
```

The problem is not merely lack of dashboards.

The deeper problem is:

> **Lack of synchronized historical context.**

Most tools show what exists now.

The publisher needs to know:

> **What was true immediately before the incident?**

---

# 3. Product thesis

The platform is built around one thesis:

> **Better operational memory produces better incident decisions.**

If the product continuously records:

- how important pages behaved;
- which scripts/dependencies existed;
- which ad slots existed;
- whether requests fired;
- how consent behaved;
- traffic/Search/GAM metrics;
- configuration changes;
- external events;

then an incident no longer begins from memory and speculation.

It begins from evidence.

---

# 4. Product category

The platform is closest to:

```text
Sentry / Datadog / black-box recorder
```

but designed for:

```text
digital publishing operations
```

instead of application backend engineering.

It combines:

```text
observability
+
operational memory
+
publisher-domain intelligence
+
incident investigation
```

It is not a traditional publisher analytics dashboard.

---

# 5. What the product is NOT

The product is not primarily:

- a revenue optimizer;
- an SSP;
- an ad server;
- a header-bidding wrapper;
- a Google ranking predictor;
- an SEO tool;
- a website crawler report;
- a policy certification product;
- a BI dashboard;
- a project-management platform;
- a logging platform for engineers.

Some of these domains supply evidence.

They are not the product category.

---

# 6. The core user need

The central question is:

> **"Something went wrong. What changed around the same time, what can actually explain the symptom, and what should we check next?"**

The product must make that question easy to ask.

The user should not need to understand:

- request waterfalls;
- TCF APIs;
- Prebid event hooks;
- GAM report semantics;
- event graphs;
- causal scoring.

The product translates that complexity into evidence-backed explanations.

---

# 7. Primary users

## Publisher commercial / monetization leadership

Questions:

- Why did monetization fall?
- Is this traffic, inventory, fill or price?
- Is a vendor actually responsible?
- Did direct campaigns displace programmatic?
- Is this temporary market behavior?

## Ad operations

Questions:

- Are slots still requesting?
- Is GAM receiving requests?
- Did Prebid change?
- Is consent affecting serving?
- Is one format/template broken?

## Audience / SEO

Questions:

- Is the Search decline real?
- Is it technical?
- Is it one template/device?
- Does it coincide with a Google update?
- Did it start before or after our change?

## Product / technical managers

Questions:

- What changed on the site?
- Which deploy/script/player/CMP event aligns with the symptom?
- Is this global or local?
- Can we reproduce it?

## Executives

Questions:

- Is there a serious issue?
- What do we know?
- What is still uncertain?
- What should the team do next?

---

# 8. User sophistication

The product assumes users understand industry language broadly.

They may know terms such as:

```text
GAM
fill
eCPM
CMP
Search Console
Discover
Prebid
video player
ad slots
direct campaigns
```

But they may not know:

```text
slotRenderEnded
TC String lifecycle
hb_* targeting
network request waterfall
collector versioning
source maturity
event graphs
causal inference
```

The interface must therefore be:

> **industry-native but not engineering-native.**

---

# 9. Product language

Prefer:

> Expected ad slot disappeared from mobile articles.

Instead of:

> The GPT slot entity transitioned from PRESENT to ABSENT.

Prefer:

> GAM requests fell while pageviews remained stable.

Instead of:

> Upstream request realization diverged from the pageview denominator.

Technical evidence can be available in drill-down.

The primary explanation must remain understandable.

---

# 10. Core product loop

The product has four core stages:

```text
OBSERVE
↓
REMEMBER
↓
UNDERSTAND
↓
INVESTIGATE
```

Future stages may include:

```text
ACT
↓
AUTOMATE
```

but not in the core MVP promise.

---

# 11. OBSERVE

The platform continuously observes a bounded set of high-value publisher signals.

These come from three primary evidence families:

## Synthetic Browser Observability

Controlled Chromium visits to representative pages.

## Business/API Telemetry

GA4, Search Console and GAM read-only data.

## Public / Operational / External Context

robots, ads.txt, external Google/platform events, manual changes.

The product does not claim to observe everything.

It must explicitly represent its blind spots.

---

# 12. REMEMBER

The platform stores historical evidence so the publisher can reconstruct the past.

This is central.

It remembers:

```text
what existed
what disappeared
what was added
what changed
when it was first/last observed
which source saw it
how certain the timing is
```

Operational memory is more important than any single alert.

---

# 13. UNDERSTAND

The platform turns raw observations into a small set of meaningful operational events.

Examples:

```text
Expected GPT slot missing on mobile articles
New third-party script added
Broad noindex appeared
GAM requests below baseline
TCF error appeared
Google Search update began
Direct campaign share increased
```

It does not surface every difference.

The product should remain quiet during normal operation.

---

# 14. INVESTIGATE

When a user reports a problem, the system reconstructs the relevant context.

It asks:

```text
What exactly changed?
Where?
When?
What was normal before?
What else changed at the same time?
Which changes can physically explain the symptom?
What evidence argues against each hypothesis?
What is hidden/unobservable?
What test would best reduce uncertainty?
```

The investigation is evidence-driven.

---

# 15. The product's strongest differentiation

The most important differentiator is not simply AI.

It is:

> **Longitudinal publisher-specific operational memory.**

A generic AI can explain what:
- GAM;
- CMP;
- Prebid;
- Search;
- GPT;

are.

But it does not automatically know:

```text
what this publisher looked like 18 hours ago
which script appeared
which slot disappeared
which metric moved first
which device was affected
what happened after a rollback
```

The product does.

---

# 16. Synthetic Browser & 6-Hour Black Box

This must be visible as a major product capability.

The system repeatedly visits representative pages using a controlled real browser.

Every core observation creates a historical checkpoint.

Typical user-facing concept:

> **Website Black Box**

or:

> **6-Hour Site Checkpoint**

The technical implementation uses Playwright/Chromium, but the primary product concept is:

> **We preserve how the site actually looked and behaved at that moment.**

---

# 17. What a browser checkpoint means to the user

A checkpoint can preserve:

- screenshots;
- page structure;
- scripts;
- third-party dependencies;
- JS errors;
- ad slots;
- ad-request lifecycle;
- consent behavior;
- video behavior;
- SEO state;
- synthetic performance.

The user does not need to see all of these by default.

The important product promise is:

> **We can compare the incident state with the last known healthy state.**

---

# 18. Last Known Good

One of the product's core explanatory concepts.

For an incident, the system identifies a relevant:

> **Last Known Good**

Then compares:

```text
Before
vs
Incident
```

Examples:

```text
5 expected ad slots → 3
no TCF errors → TCF error present
canonical self-reference → cross-domain canonical
player normal → sticky overlay behavior
```

Last Known Good is incident-specific.

---

# 19. Business telemetry

Browser evidence tells us what the page did.

Business telemetry tells us what the publisher experienced.

Examples:

## GA4

```text
users
sessions
views
channel
device
page/template
```

## Search Console

```text
Search clicks
impressions
CTR
position
Discover
```

## GAM

```text
requests
impressions
fill context
eCPM/value
direct/programmatic mix
inventory/demand segment
```

The product links page behavior to business outcomes.

---

# 20. Why multiple sources matter

No single source is enough.

Example:

```text
GA4 traffic down
```

could mean:
- real traffic decline;
- tracking issue;
- consent change.

Example:

```text
GAM revenue down
```

could mean:
- traffic down;
- fewer requests;
- lower fill;
- lower eCPM;
- more direct delivery;
- reporting/accounting differences.

The product cross-checks sources instead of trusting one dashboard blindly.

---

# 21. Home

Home answers:

> **"Do I need to care about anything right now?"**

It should remain compact.

Primary state:

```text
HEALTHY
ATTENTION
INCIDENT
```

Home includes only:

- current meaningful attention items;
- latest important change;
- active incident if any;
- Weekly Brief;
- Investigate CTA.

---

# 22. HEALTHY

Meaning:

> No currently observed issue crosses the threshold for meaningful attention.

Healthy does not mean:

```text
everything is perfect
```

It means:

```text
nothing important currently requires action based on available evidence
```

---

# 23. ATTENTION

Meaning:

> Something meaningful changed or degraded and should be reviewed, but it is not necessarily an active critical incident.

Examples:

- important script dependency changed;
- one monetization segment is persistently weaker;
- unusual consent behavior;
- Search visibility decline;
- persistent performance regression.

---

# 24. INCIDENT

Meaning:

> A material issue is actively affecting or plausibly affecting publisher operation, or the publisher has opened an active investigation.

Examples:

- site unavailable;
- broad noindex;
- severe ad-request collapse;
- active user-reported incident.

---

# 25. Home should NOT become a dashboard wall

Avoid:

- 25 charts;
- every eCPM metric;
- every technical status;
- network logs;
- every event.

The user should understand Home in seconds.

---

# 26. Timeline

Timeline is the publisher's operational history.

It answers:

> **What changed around this period?**

It includes:

```text
technical change
business anomaly
external event
manual change
recovery
```

on one synchronized time axis.

---

# 27. Timeline event examples

```text
12:00–18:00
Expected mid-article GPT slot disappeared on mobile articles.

14:00
Direct campaign share increased materially.

15:00
GAM requests per view began falling on mobile articles.

16:00
TCF error first observed.

Aug 12
Google began a Core Update rollout.
```

Timeline does not imply causality.

---

# 28. Timeline filters

Simple filters:

```text
Site
Traffic
Search
Monetization
Google
CMP
Video
Performance
External
```

Advanced technical subfilters may exist later.

---

# 29. Timeline evidence detail

Clicking an event may show:

```text
Observed
Before / After
Scope
Evidence
Timestamp / occurrence window
Source
Risk
Related events
```

For browser events:

```text
screenshot
structural diff
network evidence
```

where useful.

---

# 30. Investigate

Investigate is the signature user workflow.

The input should feel almost conversational.

Primary fields:

```text
What happened?
When did it start?
Optional context
```

Example:

> "Search traffic looks down since Monday."

or:

> "Programmatic monetization on mobile dropped yesterday."

The user should not need to choose the suspected technical cause.

---

# 31. Investigation UX principle

The product should begin with:

> **symptom**

not:

> **hypothesis**

Bad intake:

```text
Which component do you think caused the problem?
```

Good:

```text
What changed from your point of view?
```

This reduces anchoring bias.

---

# 32. Investigation output hierarchy

The report should first answer:

```text
What we confirmed
```

Then:

```text
Where it is happening
```

Then:

```text
What changed
```

Then:

```text
What can explain it
```

Then:

```text
What evidence argues against those explanations
```

Then:

```text
What to do next
```

---

# 33. Investigation report — top summary

Example:

> **Observed:** Mobile programmatic delivery began deteriorating on Aug 12. GA4 pageviews remained within baseline, while GAM requests on mobile article inventory fell materially.

> **Leading explanation:** A request-generation issue is more likely than a broad demand decline.

> **Confidence:** PROBABLE.

> **Why:** The first broken stage is GAM request volume, the affected scope matches mobile article browser behavior, and demand-side indicators occur downstream.

This is the type of explanation the user needs.

---

# 34. Supporting evidence

For each hypothesis:

```text
What supports it?
```

Examples:

- exact timing;
- same affected template;
- expected intermediate signal;
- direct error;
- unaffected control;
- rollback recovery.

Evidence should be clickable where possible.

---

# 35. Contradicting evidence

For each top hypothesis:

```text
What argues against it?
```

This must be visible.

Example:

> The suspected player was introduced six days after the measurable Search decline began.

This single fact may matter more than five weak correlations.

---

# 36. Unknowns

The product must clearly state what it cannot know.

Examples:

```text
Bidder-side server logic is not observable.
Search ranking-system internals are not exposed by Google.
GAM source data for the latest two hours remains preliminary.
No pre-incident browser checkpoint exists for this template.
```

Unknown is a legitimate answer.

---

# 37. Confidence

User-facing confidence labels:

```text
CONFIRMED
PROBABLE
POSSIBLE CONTRIBUTOR
UNRESOLVED
```

No fake precision.

Do not show:

```text
87.3% probability
```

until product evidence supports actual calibration.

---

# 38. CONFIRMED

Use sparingly.

Typical supporting situations:

- direct technical proof;
- controlled reproduction;
- rollback + recovery;
- explicit official/vendor confirmation plus matching local evidence.

The product's credibility depends on not overusing this label.

---

# 39. PROBABLE

Use when:

- timing matches;
- mechanism matches;
- scope matches;
- intermediate evidence exists;
- no major contradiction remains.

This should be a strong operational recommendation, not certainty.

---

# 40. POSSIBLE CONTRIBUTOR

Use when:

- mechanism is plausible;
- some evidence matches;
- evidence is incomplete;
- another explanation may coexist.

Multi-causal incidents can contain multiple contributors.

---

# 41. UNRESOLVED

Use when:

- evidence does not discriminate;
- important sources are missing;
- causes remain observationally hidden;
- top hypotheses conflict.

UNRESOLVED is not a product failure.

A useful unresolved report can still eliminate:
- wrong vendors;
- wrong technical theories;
- risky shutdowns.

---

# 42. No Strong Local Cause

A particularly valuable unresolved result:

> **No strong local cause was identified.**

Example:

- Search decline is real;
- site technical state is stable;
- no relevant deploy;
- suspected local changes pre/post timing does not fit;
- Google/external/content factors remain possible.

This prevents false local blame.

---

# 43. Next test

When the report cannot confidently discriminate causes, it should recommend the next best test.

The product should prefer:

```text
smallest change
highest information gain
lowest business risk
```

Example:

> Compare the affected mobile article template with desktop using the same page and consent path.

Not:

> Disable all monetization vendors for two weeks.

---

# 44. Test prediction

Every recommended test should explain:

```text
If hypothesis is correct → expect X
If hypothesis is wrong → expect Y
```

This makes the recommendation scientific rather than procedural.

---

# 45. Safe diagnostics

The product can automatically perform safe read-only diagnostics such as:

- extra synthetic browser run;
- second representative page;
- Accept/Reject comparison;
- screenshot;
- validated API drill-down.

The product should clearly distinguish:

```text
Automatic diagnostic
```

from:

```text
Production change
```

---

# 46. Production changes

MVP recommendations may include:

- inspect;
- verify;
- rollback;
- isolate;
- change config.

But the product does not execute production changes automatically.

The user/team remains in control.

---

# 47. Weekly Brief

Weekly Brief answers:

> **What changed this week that is actually worth my attention?**

It should feel curated.

Target:

```text
3–7 findings
```

not dozens.

---

# 48. Weekly Brief format

Each finding should follow:

```text
Observed
Risk
Check
```

Example:

> **Observed:** GAM requests per view on mobile articles were persistently lower from Wednesday onward.

> **Risk:** Fewer monetizable opportunities per pageview.

> **Check:** Verify whether the article template changed lazy-load or slot-definition behavior.

This communicates relevance without pretending causality.

---

# 49. Weekly Brief tone

The brief should be:

- concise;
- factual;
- calm;
- operational;
- non-alarmist.

Avoid:

- "critical disaster";
- "Google punished your site";
- "your revenue is leaking";
- speculative vendor blame.

---

# 50. Weekly Brief noise standard

A publisher should prefer:

```text
3 excellent findings
```

over:

```text
7 mediocre findings.
```

The 3–7 target is a ceiling/range, not a quota.

Do not invent findings to fill the report.

---

# 51. Alerts

Alerts should be rare.

The user should believe:

> **If this product interrupts me, I should look at it.**

Examples:

- site unavailable;
- broad noindex;
- critical request/delivery collapse;
- CMP runtime unavailable;
- widespread inventory disappearance.

---

# 52. Non-alert examples

Usually not immediate alerts:

- eCPM down for one hour;
- ads.txt line changed;
- one JS error;
- external Google update started;
- one synthetic CLS outlier;
- new harmless third-party script.

These can appear in Timeline/Weekly.

---

# 53. Alert UX

An alert should answer:

```text
What happened?
Where?
How sure are we?
Why does it matter?
What should I check?
```

Example:

> **Critical:** `noindex` was detected on multiple article pages and confirmed in a second check. Search visibility may be affected. Check the article-template SEO configuration.

This is actionable.

---

# 54. External context

The product tracks official ecosystem events.

Examples:

```text
Google Core Update
Google Search incident
GAM platform issue
major CDN outage
standards/policy change
```

They appear in Timeline because timing matters.

But the product must say:

> **Context**

unless publisher-specific evidence supports causality.

---

# 55. Operational changes

The product should preserve important human/business changes.

Examples:

- deployment;
- player integration;
- CMP change;
- GAM configuration;
- vendor integration;
- rollback;
- direct campaign start.

These can be entered manually initially.

---

# 56. Why manual changes matter

A browser sees:

```text
a script appeared
```

but it may not know:

```text
who deployed it
why
whether intentional
```

Operational context closes that gap.

The product should preserve both:

```text
detected change
+
known human change
```

without conflating them.

---

# 57. Product evidence model

Every important claim should be explainable through:

```text
Source
↓
Observation
↓
Event/Metric
↓
Evidence
↓
Hypothesis
↓
Conclusion
```

This chain is the foundation of trust.

---

# 58. Evidence detail for non-technical users

Do not force users to read JSON/network logs.

Translate:

```text
request stage absent
```

into:

> The ad slot existed on the page but no GAM request was generated.

Then offer:

> View technical evidence

for advanced users.

---

# 59. Evidence-first AI

AI can help explain:

```text
what the evidence means
```

AI must not create:

```text
the evidence itself.
```

This distinction should remain visible in product behavior.

---

# 60. AI role

AI is useful for:

- synthesizing evidence;
- explaining mechanism;
- comparing hypotheses;
- generating readable incident reports;
- rewriting weekly findings;
- explaining unknowns;
- recommending bounded tests from approved patterns.

AI is not authoritative for:

- raw data;
- event existence;
- timestamp;
- confidence source;
- production changes.

---

# 61. Product personality

The product should behave like:

> **A calm senior publisher operator who keeps excellent notes and refuses to guess when evidence is missing.**

It should not behave like:

> **An AI oracle.**

---

# 62. Product trust model

Trust comes from:

1. preserved evidence;
2. visible before/after comparisons;
3. source attribution;
4. contradicting evidence;
5. explicit unknowns;
6. restrained confidence;
7. reproducible chronology.

Not from:
- more AI text;
- more charts;
- more alerts.

---

# 63. Explainability

Every top hypothesis should answer:

```text
Why is this ranked here?
```

Example:

> It occurred in the same window, affects the same mobile article scope, and the expected downstream GAM request signal changed at the same time.

And:

```text
What weakens it?
```

Example:

> Desktop is also affected, which does not fit a mobile-only implementation failure.

---

# 64. Product principle: first broken link

For monetization/technical incidents, the user should be shown:

> **Where does the chain first break?**

Example:

```text
Pageviews stable
Slots stable
GAM requests ↓
Impressions ↓
Revenue ↓
```

The first meaningful break is:

```text
requests
```

This dramatically narrows investigation.

---

# 65. Product principle: baseline first

The product should not compare only:

```text
today vs yesterday
```

without context.

It should understand:

- weekday;
- hour;
- normal variation;
- pre-existing decline;
- affected segment.

---

# 66. Product principle: pre-existing decline

If data shows the symptom began before the user thought:

the product should say so.

Example:

> The decline appears to have started approximately 10 days earlier than the reported incident date.

This may invalidate a suspected cause.

---

# 67. Product principle: controls

Unaffected segments are part of the explanation.

Example:

> The issue appears limited to mobile article pages. Desktop article and homepage behavior remained within baseline.

This is highly useful even before root cause is known.

---

# 68. Product principle: intervention evidence

If a component was removed:

the product should compare what happened after.

Example:

> The suspected integration was removed on Aug 3, but the traffic decline continued without material recovery over the following period.

This should reduce causal confidence where recovery should have been rapid.

---

# 69. Product principle: avoid destructive debugging

The product should explicitly prefer:

```text
one-variable tests
```

over:

```text
disable everything
```

This is not merely a technical preference.

It protects:
- revenue;
- user experience;
- attribution quality.

---

# 70. Product principle: no vendor blame without evidence

The product may rank:

> Vendor integration is a possible contributor.

It should not say:

> Vendor X caused the incident

unless evidence justifies it.

This is particularly important commercially.

---

# 71. Product principle: no Google blame without evidence

Similarly:

```text
Google update overlaps incident
```

does not equal:

```text
Google update caused incident
```

The product must remain neutral and evidence-based.

---

# 72. Product principle: no raw metric absolutism

Examples:

```text
fill down
```

is not enough.

Need:

```text
requests
impressions
numerator
denominator
segment
baseline
```

Likewise:

```text
revenue down
```

is not an explanation.

---

# 73. Product principle: measurement is fallible

GA4, GSC and GAM are sources.

They can be:
- delayed;
- incomplete;
- differently defined;
- misconfigured.

The product should never make one source invisible behind a generic label.

Source provenance matters.

---

# 74. Product principle: synthetic is synthetic

Browser measurements are controlled observations.

They are not:

```text
all real users
```

For example:

> Synthetic CLS worsened.

Not:

> All users experienced worse CLS.

---

# 75. Product principle: quiet system

A core UX success measure:

> **Normal days should feel quiet.**

If the product creates anxiety during healthy operation, it fails.

Observability should create confidence, not alert fatigue.

---

# 76. Pilot onboarding experience

A pilot onboarding should feel like:

```text
1. Add site
2. Identify major page types
3. Choose representative URLs
4. Connect GA4
5. Connect Search Console
6. Connect GAM
7. Confirm monitoring
```

The publisher should not configure dozens of low-level rules.

---

# 77. Technical discovery during onboarding

The product can automatically identify:

- page templates;
- scripts;
- CMP;
- GPT;
- Prebid;
- players;
- key dependencies;
- robots/ads.txt.

Then operator confirms/corrects.

This reduces onboarding burden.

---

# 78. Onboarding confidence

Before declaring setup complete, the product should show:

```text
Browser monitoring: Ready
GA4: Connected
Search Console: Connected
GAM: Connected / Limited
```

If a source is missing:

```text
GAM not connected
```

not:

```text
Everything healthy
```

---

# 79. Source limitations UX

Example:

> GAM demand-channel detail is unavailable for this network/report configuration. Monetization investigations will have reduced demand-side observability.

This is better than silently omitting the source.

---

# 80. Site health versus source health

The product must distinguish:

```text
Publisher site issue
```

from:

```text
Our monitoring source unavailable
```

Example:

> Search Console data is delayed.

should not become:

> Search traffic dropped.

---

# 81. Historical exploration

Timeline allows users to go back and answer:

```text
What changed on this date?
```

This has value even without an active incident.

Example:

> "What was different on the site before the player migration?"

---

# 82. Incident reopening

A closed incident can be reopened if:

- symptom returns;
- new evidence appears;
- same mechanism recurs.

The product should preserve prior investigation.

Do not start from zero.

---

# 83. Recurring incidents

If a similar incident happened before:

the product may say:

> This resembles a previous incident on this publisher in which the same mobile template lost expected GPT requests after a script change.

This is publisher-specific memory.

It should still be treated as precedent, not proof.

---

# 84. Shared knowledge

The product may use generalized public incident knowledge.

Example:

> Similar consent/TCF request-eligibility failures have occurred in other publisher environments.

This improves hypothesis generation.

It must not expose private client data.

---

# 85. Private publisher memory

Private observations/incidents belong to the publisher.

The product should not silently train/share them across tenants.

Cross-publisher intelligence requires future explicit policy.

---

# 86. Product moat

The moat can develop from four layers:

```text
1. longitudinal publisher evidence
2. publisher-specific operational memory
3. curated domain reasoning
4. validated incident patterns/evals
```

Generic AI is not the moat.

---

# 87. Future cohort intelligence

Long-term:

> Several publishers using different local stacks experience the same Search pattern in the same period.

This can help distinguish:

```text
local issue
vs
ecosystem issue
```

But this requires enough publisher coverage and careful privacy.

Not core MVP.

---

# 88. Future remediation

Long-term progression:

```text
Observe
→ Understand
→ Act
→ Autonomous remediation
```

But automatic changes should come only after:

- high diagnostic confidence;
- strong safety boundaries;
- human trust;
- auditability;
- rollback.

Not MVP.

---

# 89. Product success scenario

A publisher says:

> "Programmatic revenue dropped yesterday."

The product should ideally respond:

```text
Traffic: stable
Views: stable
Expected slots: stable
GAM requests: -24%
Impressions: -22%
eCPM: roughly stable
Affected: mobile article only
Desktop: healthy
New event: TCF errors appeared in same observation window
```

Leading interpretation:

> Request generation/eligibility is more likely than broad demand weakness.

Next test:

> Re-run the mobile Accept scenario and compare GAM request generation against the unaffected desktop control.

That is the product.

---

# 90. Search success scenario

Publisher:

> "Google traffic dropped after we launched the new video player."

Product:

```text
GSC decline began 5 days before player launch.
Pages without the player declined similarly.
Player was later removed.
Search did not materially recover.
```

Conclusion:

> The player is unlikely to explain the onset of the Search decline.

The actual cause may remain unresolved.

This is a successful investigation because it prevents a false cause.

---

# 91. Weekly success scenario

Publisher opens Monday Brief.

It contains:

1. mobile article GAM requests/view persistently lower;
2. broad robots file changed but was restored;
3. new player dependency appeared on video templates;
4. Search visibility remained within baseline.

Nothing else.

User thinks:

> These are the things I would actually want to know.

Success.

---

# 92. Alert success scenario

Publisher receives:

> **Critical:** Multiple article pages are now returning `noindex`. The change was confirmed in a second check. This can affect Search indexability. Investigate the article-template SEO configuration.

They act.

No false panic.

Success.

---

# 93. Product failure scenario: noisy monitoring

User receives:

```text
37 JS errors
18 ads.txt changes
12 eCPM alerts
9 script changes
```

every day.

They ignore the product.

Failure.

---

# 94. Product failure scenario: AI certainty

Report:

> "Google Core Update caused your traffic loss."

Evidence:

```text
only date overlap
```

Failure.

---

# 95. Product failure scenario: dashboard clone

Product becomes:

```text
GA4 charts
GSC charts
GAM charts
```

with no historical technical memory or incident reasoning.

Failure.

The publisher already has dashboards.

---

# 96. Product failure scenario: crawler report

Product produces:

```text
your ads.txt has 82 lines
your page has 57 scripts
your CLS is 0.11
```

with no temporal context.

Failure.

The product must answer:

> What changed and why does it matter?

---

# 97. Product failure scenario: opaque AI

Report says:

> "Likely CMP issue."

No evidence.

No mechanism.

No contradiction.

No source.

Failure.

---

# 98. Product failure scenario: overbuilding

Engineering builds:

- Kafka;
- graph DB;
- browser fleet;
- custom analytics SDK;
- autonomous agents;

before one reliable checkpoint + incident reconstruction works.

Failure.

---

# 99. UX principle: progressive disclosure

Primary interface:

```text
simple
```

Evidence detail:

```text
available on demand
```

Example:

Home:
> Mobile monetization needs attention.

Click:

> GAM requests/view are 21% below baseline.

Click technical evidence:

> GPT lifecycle, network, screenshots, source metrics.

---

# 100. UX principle: evidence before charts

Charts are useful when they clarify:

- onset;
- baseline;
- affected segment;
- recovery.

Do not add charts merely because telemetry exists.

---

# 101. UX principle: one time axis

Where possible, incident UI should align:

```text
site changes
business metrics
external events
manual changes
```

on one timeline.

This is one of the highest-value visualizations.

---

# 102. UX principle: show before/after

For technical changes, prefer:

```text
Before
After
```

Examples:

- screenshot;
- slot list;
- script list;
- CMP state;
- canonical.

This is easier to understand than raw logs.

---

# 103. UX principle: explain causality carefully

Visually distinguish:

```text
Observed
Related
Possible Cause
Confirmed Cause
```

Do not render all connected nodes as if causal.

---

# 104. UX principle: confidence is qualitative

Use clear labels and explanation.

Example:

> **PROBABLE** — timing, scope and request-chain evidence match; no major contradicting evidence was found.

This is better than:

> 82%.

---

# 105. UX principle: uncertainty is visible

Example:

> We cannot determine whether bidder-side server behavior changed because this part of the auction is not observable from the connected sources.

Never bury this in technical footnotes.

---

# 106. UX principle: actionability

Every important finding should help answer:

> What do I do with this?

Possible actions:

- Investigate;
- Compare Last Known Good;
- Verify intentional change;
- Run additional diagnostic;
- Mark intentional;
- Add note;
- Resolve.

---

# 107. Mark intentional

Users should be able to mark:

> This change was intentional.

The event remains historical evidence.

But:
- alert can close;
- weekly priority can drop.

Do not delete it.

---

# 108. Add context

User can attach:

- note;
- deployment reference;
- vendor explanation;
- screenshot/document;
- rollback timestamp.

This enriches future RCA.

Keep interaction lightweight.

---

# 109. Resolve incident

Resolving means:

> operational symptom is no longer active or investigation is closed.

It does not require confirmed root cause.

Possible:

```text
Resolved — root cause unresolved
```

This is valid.

---

# 110. Post-incident value

After closure, the product should preserve:

- timeline;
- conclusion;
- ruled-out causes;
- recovery;
- intervention;
- evidence.

Future incidents benefit.

This creates compounding value over time.

---

# 111. Product metrics

Core product metrics:

```text
Mean Time To Investigate
False-cause rate
Time to symptom localization
Time to useful hypothesis
User-rated investigation usefulness
Weekly Brief usefulness
Critical alert precision
Incidents with usable Last Known Good
```

---

# 112. What not to optimize

Do not optimize for:

```text
number of events
number of alerts
number of AI messages
number of charts
number of monitored signals
```

More is not inherently better.

---

# 113. North Star behavior

A strong North Star qualitative question:

> **When an incident occurs, does the publisher consult this product before blaming a vendor or disabling infrastructure?**

If yes, the product has become operationally trusted.

---

# 114. Pilot validation questions

Ask pilot users:

- Would this have shortened your last incident?
- Did it show evidence you otherwise would not have had?
- Did it eliminate any wrong hypothesis?
- Was the Timeline understandable?
- Were any alerts noisy?
- Was the Weekly Brief worth reading?
- Did Investigate recommend a useful next test?
- Did you trust the conclusion?
- What evidence did you still need outside the product?

---

# 115. Product-market fit signal

Strong signal:

Publisher says:

> "We need this running before the next incident."

Even stronger:

> "I don't want to investigate without it."

The value is risk reduction and operational certainty, not dashboard engagement alone.

---

# 116. Pricing logic

The product's economic value comes from:

- investigation time saved;
- avoided monetization shutdowns;
- avoided false vendor blame;
- faster recovery;
- preserved commercial relationships;
- reduced reliance on scarce technical experts;
- better incident documentation.

Pricing should reflect operational value, not pageview volume alone.

---

# 117. Sales positioning

Avoid:

> AI analytics platform.

Prefer:

> **The black-box recorder and incident investigator for publishers.**

or:

> **When traffic or monetization changes, we show you what actually changed around it.**

This is concrete.

---

# 118. Competitive positioning

Traditional tools often cover one slice:

```text
analytics
SEO
ad reporting
uptime
performance
logs
```

The product's category advantage is:

> **Cross-layer historical incident reconstruction.**

It connects:
site reality
to
business reality
to
operational history
to
external context.

---

# 119. Why publisher-specific matters

A generic monitoring product may detect:

> script changed.

A publisher-specific product understands:

> that script participates in consent, which can affect GPT request generation, which can affect GAM requests and programmatic delivery.

This domain model is essential.

---

# 120. Why incident-specific matters

A generic anomaly detector says:

> eCPM down 18%.

The product asks:

```text
traffic?
requests?
fill?
device?
geo?
direct mix?
price?
viewability?
market?
```

It should help find the first broken stage.

---

# 121. Product roadmap principle

Future development should follow evidence from pilot use.

Do not expand because a feature sounds impressive.

Ask:

> Did real publisher investigations repeatedly need this?

Examples that may justify later:
- additional SSP connectors;
- direct deploy integrations;
- Slack;
- field RUM;
- cohort intelligence;
- automated remediation.

---

# 122. Product boundary with support/consulting

The product may surface:

> We cannot observe enough evidence to distinguish these two causes.

This may create a need for human expert investigation.

That is acceptable.

The product should not hide its limitations to appear complete.

---

# 123. Product boundary with Google

The platform should never imply privileged access to:
- Search ranking algorithm;
- Discover distribution logic;
- advertiser auction intent.

It interprets observable evidence only.

---

# 124. Product boundary with policy

The platform can say:

> We observed autoplay + audible behavior under this scenario, which intersects with the current policy/ruleset.

It should not claim:

> This website is legally compliant/non-compliant

unless a relevant platform gives an explicit enforcement signal.

---

# 125. Product boundary with finance

The platform can say:

> GAM programmatic revenue is below its comparable baseline.

It should not automatically say:

> Publisher lost €40,000

unless source data and business assumptions support the calculation.

---

# 126. MVP user journey

A complete MVP user journey:

```text
Sign in
↓
Select publisher/site
↓
Home
↓
See HEALTHY / ATTENTION / INCIDENT
↓
Open Timeline
↓
Inspect meaningful events
↓
Receive Weekly Brief
↓
Notice/report issue
↓
Open Investigate
↓
Describe symptom + onset
↓
System confirms/localizes
↓
System reconstructs LKG/timeline
↓
Hypotheses ranked
↓
Evidence for/against shown
↓
Next test suggested
↓
User adds context / runs diagnostic
↓
Report updates
↓
Incident resolved / closed unresolved
```

---

# 127. MVP outcome

The MVP is successful when a publisher can say:

> **"Instead of spending two days asking five vendors what might have happened, I had a timeline of what changed, saw which layer actually broke first, ruled out the wrong suspects, and knew what to test next."**

That is the product outcome.

---

# 128. Canonical product principles

All product/design/engineering work should preserve:

```text
Evidence before explanation
Baseline before attribution
Scope before cause
Mechanism before confidence
Contradictions before conclusion
Quiet by default
Unknown is allowed
Historical memory is sacred
User remains in control
```

---

# 129. Product rule for Codex

When implementing a feature, Codex must ask:

> **Which user question does this help answer?**

If no clear user question exists:
the feature probably does not belong in the product yet.

If the user question exists but implementation is outside `MVP.md`:
create a proposal, not code.

---

# 130. Final product principle

The product should never compete with publishers by being louder than their existing dashboards.

It should be the tool they open when the dashboards stop explaining the problem.

# **Observe broadly. Remember faithfully. Alert rarely. Investigate deeply.**
