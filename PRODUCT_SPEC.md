# Product Specification — LinkIntel

> Working name. Rename freely — nothing below depends on the name.

## 1. What we are building

An evidence-backed **SEO backlink intelligence, link prospecting, contact
intelligence and outreach platform**, built on our own crawl and discovery
infrastructure instead of a paid third-party backlink index (Ahrefs, Semrush,
Moz).

The platform must use **real web data**. It is not a mockup, a prototype with
seeded/fake data, a static dashboard, a simulated crawler, or a demo-only
system.

Every displayed data point must either:

1. Come from a real crawl we performed, or
2. Come from a real public data source (e.g. Common Crawl), or
3. Be a deterministic computation over data we collected, or
4. Be explicitly labeled as **estimated** or **inferred**, with a confidence
   score.

We never fabricate metrics, backlinks, emails, traffic, authority scores,
contacts, or opportunities. If a number can't be produced honestly, the UI
shows `UNKNOWN` or `ESTIMATED (confidence: N%)` — never a plausible-looking
guess.

### Positioning

Competing tools (e.g. Backlinker.ai) emphasize journalist pitches, DFY
outreach, and an AI writer on top of a licensed backlink index. Our moat is
different and deliberately harder to copy:

> We know who can link to you, why they might, who controls that
> publication, how to reach them, what evidence supports the opportunity,
> how valuable the link would be, and whether the link actually appeared
> and survived.

The AI layer is an *interface to proprietary data* (crawl history, backlink
observations, contact graph, author graph, publisher graph, topic graph) —
not the product itself. That graph compounds over time; an AI pitch-writer
does not.

## 2. The six engines

```
                         ┌─────────────────────────┐
                         │       USER WEBSITE       │
                         └────────────┬─────────────┘
                                      │
                                      ▼
                    ┌───────────────────────────────┐
                    │  1. WEBSITE INTELLIGENCE       │
                    │  Crawl + understand the site    │
                    │  Topics / entities / pages       │
                    │  Products / services / people    │
                    └──────────────┬────────────────┘
                                   │
                ┌──────────────────┼──────────────────┐
                ▼                  ▼                  ▼
      ┌────────────────┐ ┌─────────────────┐ ┌─────────────────┐
      │ 2. BACKLINK    │ │ 3. PROSPECT     │ │ 4. COMPETITOR   │
      │ DISCOVERY      │ │ DISCOVERY       │ │ LINK GAP        │
      │ Common Crawl   │ │ Websites        │ │ Competitor links│
      │ Own crawling   │ │ Publications    │ │ Missing links   │
      │ Search indexes │ │ Blogs, resource │ │ Opportunities   │
      │ Direct checks  │ │ pages           │ │                 │
      └───────┬────────┘ └────────┬────────┘ └────────┬────────┘
              └───────────────────┼───────────────────┘
                                  ▼
                    ┌───────────────────────────────┐
                    │ 5. AUTHORITY + QUALITY ENGINE  │
                    │ Relevance · Authority · Traffic│
                    │ Editorial quality · Spam risk  │
                    │ Link type · Indexability       │
                    │ Outbound-link behavior         │
                    │ Contactability                 │
                    └───────────────┬───────────────┘
                                    ▼
                    ┌───────────────────────────────┐
                    │       OPPORTUNITY SCORE        │
                    │   "Should we pursue this?"     │
                    └───────────────┬───────────────┘
                   ┌────────────────┼─────────────────┐
                   ▼                ▼                 ▼
          ┌────────────────┐ ┌──────────────┐ ┌───────────────┐
          │ 6A. CONTACT    │ │ 6B. OUTREACH │ │ 6C. CAMPAIGN  │
          │ INTELLIGENCE   │ │ AI           │ │ MANAGEMENT    │
          │ Emails/Authors │ │ Pitch/angle  │ │ Sent/Opened   │
          │ Editors        │ │ Personalize  │ │ Replied       │
          │ Contact pages  │ │ Follow-up    │ │ Published     │
          │ Socials        │ │              │ │ Backlink      │
          └────────────────┘ └──────────────┘ └───────────────┘
                                    ▼
                         ┌────────────────────┐
                         │   USER DASHBOARD    │
                         │ Opportunities · Gap │
                         │ Prospects · Contacts│
                         │ Campaigns · Backlinks│
                         │ Reports              │
                         └────────────────────┘
```

## 3. The two mandatory cross-cutting systems

These are not optional "nice to have" layers. Every engine above must feed
them, and nothing may bypass them.

### 3.1 Data Provenance Engine

Every important data point (backlink, contact, score, opportunity, AI
claim) must carry:

| Field | Meaning |
|---|---|
| `value` | the data itself |
| `source_url` | where it was observed |
| `source_type` | `DIRECT_CRAWL` / `COMMON_CRAWL` / `SEARCH_DISCOVERED` / `INFERRED` / `AI_CLASSIFIED` / `USER_PROVIDED` |
| `discovery_method` | e.g. "HTML extraction", "pattern inference", "SMTP probe" |
| `discovered_at` | first observed |
| `last_verified_at` | most recent re-check |
| `verification_status` | see per-domain status enums below |
| `confidence_score` | 0–100 |

The UI must never present an inferred value with the same visual weight as
a directly verified one.

### 3.2 Evidence Engine

Every recommendation (an opportunity score, "pursue this," a suggested
outreach angle) must be explainable on click:

```
Why? → sub-scores (relevance, authority, editorial quality, ...)
Evidence → ✓ Competitor A links here
           ✓ Publisher covers this topic
           ✓ Guest-contribution page found
           ✓ Relevant editor identified
```

No black-box scores. If we can't produce evidence for a claim, we don't
make the claim.

## 4. Engine specifications

### 4.1 Website Intelligence (crawl + understand)

Crawls the user's own site (and later, prospects/competitors) and builds a
structured profile: topics, entities (people/orgs/products/services/
locations), content assets, and an author/editorial fingerprint if the site
is a publisher. Feeds every other engine. See `docs/CRAWLER.md` for
extraction fields and crawler mechanics.

### 4.2 Backlink Discovery

Three discovery layers, each tagged with its own confidence:

1. **Common Crawl** — query the public CDX index for pages under
   `target-domain.com/*` and for pages that reference the target domain.
   High confidence for *existence*, not yet "verified."
2. **Search discovery** — generated query patterns (`"brand"`,
   `"brand" -site:brand.com`, `"brand" resources`, `"brand"
   "according to"`, `filetype:pdf "brand"`, etc.) against a search backend,
   producing *candidate* URLs to crawl.
3. **Direct verification (own crawl)** — the only layer allowed to set
   `verification_status = VERIFIED`. Pipeline:

   ```
   page exists? → target URL present in HTML? → real <a href> (not text)? →
   page canonical? → page indexable? → link followed/nofollow/sponsored/ugc? →
   anchor text? → surrounding context? → VERIFIED BACKLINK
   ```

Backlinks are never stored as a boolean. Every crawl produces a **backlink
observation** (see `docs/DATABASE.md`), so we can show history: link
attribute changed from follow → nofollow on 2026-08-18, lost/restored dates,
etc. This "truth layer" — first seen / last seen / lost / restored /
attribute-changed — is a first-class feature (`Backlink Monitoring`, §4.9).

Backlink type classification: editorial, guest post, author bio, directory,
citation, resource page, forum, comment, profile, press release,
sponsorship, partner, affiliate, UGC, sponsored, sitewide, footer,
navigation, image, PDF/document, social.

### 4.3 Competitor Link Gap

User supplies their domain + up to N competitor domains. We compute:

```
domains linking to competitors − domains linking to target = link gap
```

with intersection logic: a domain linking to 3 of 4 competitors but not the
target is a stronger signal than one linking to a single competitor. This
"competitor overlap count" feeds the Opportunity Score.

### 4.4 Prospect Discovery

Independent discovery of relevant websites (not just competitor-derived):
resource pages, industry publications, blogs accepting contributions,
"best of" / "top tools" roundups, etc., filtered and ranked by topical fit
to the user's entity/topic profile from §4.1.

### 4.5 Authority + Quality / Opportunity Scoring

We deliberately do **not** use a single opaque Domain Rating as the primary
metric. Instead we compute several **named, inspectable** sub-scores and a
configurable weighted composite:

- Domain Quality Score
- Topical Relevance Score
- Editorial Quality Score
- Link Probability Score
- Contactability Score
- Spam Risk Score
- (later) AI Citation Score

```
Opportunity Score =
    Relevance          25%
  + Authority          20%
  + Organic Traffic    15%
  + Editorial Quality  15%
  + Link Probability   10%
  + Topical Fit         5%
  + Contactability      5%
  + Indexability        5%
  − Spam Risk
```

Weights must be configurable, not hardcoded. Every score renders with its
Evidence Engine breakdown (§3.2). Spam/quality signals are computed from
observable structure (content quality, outbound link density, commercial
anchor ratio, sitewide links, thin content, AI-generated-content signals,
link neighborhood, redirect patterns, suspicious TLDs) — never a blunt "low
DR = toxic" heuristic.

### 4.6 Contact Intelligence (6A)

For every prospect, crawl (in priority order) home, about, contact, team,
editorial-team, authors, contributors, write-for-us, guest-post,
contributor-guidelines, advertise, press, media, newsroom, and per-author
pages. Extract **every** publicly discoverable contact — not a capped
top-5 — with: name, job title, department, email, phone, contact form URL,
author URL, socials, source URL, source text, first discovered, last
verified.

**Email confidence states** (mandatory enum, never collapse these):

`DIRECTLY_PUBLISHED` · `VERIFIED` · `LIKELY` · `CATCH_ALL` ·
`ROLE_ADDRESS` · `PATTERN_INFERRED` · `UNKNOWN` · `INVALID`

Verification layers: syntax → DNS → MX → SMTP-level signal where reliable →
catch-all detection → disposable-domain detection → role-address detection.
We never send probe/test emails to "verify" an address, and pattern-guessed
addresses (`firstname.lastname@domain`) are always `PATTERN_INFERRED`,
never presented as verified.

**Author Intelligence**: per-author profile (role, publication, articles,
topics, publishing frequency, socials) with a computed topic-relevance
score against the user's expertise, so outreach targets the right person,
not just "the contact form."

### 4.7 Outreach AI (6B) and Campaign Management (6C)

AI does not write a pitch cold. It first produces an **outreach strategy**
(opportunity type, target contact, reason, evidence, recommended content
asset, angle, difficulty, expected link probability) and only then drafts
personalized copy from that strategy. The model must never invent
relationships, readership claims, statistics, credentials, or prior
contact. Unknown facts are omitted, not fabricated.

Campaigns track the full funnel and its conversion at each step: sent →
delivered → bounced → opened → clicked → replied → positive/negative reply
→ unsubscribed → published → backlink detected → backlink verified. This
lets us report real conversion rates (e.g. 3.2% link conversion) and,
later, cost-per-backlink / ROI.

**We do not build automated sending in v1.** Sequence: Discovery →
Verification → Ranking → Outreach *generation* → human-approved send. If
the discovery data is wrong, automated sending turns a data-quality bug
into a domain-reputation problem, and the actual moat is the intelligence
layer, not send volume.

### 4.8 Additional intelligence modules (differentiators beyond a pitch tool)

- **Unlinked brand mention detection** — mention found, no link → ask for
  a link.
- **Broken link opportunities** — external link on a relevant page returns
  404; if we have a replacement asset, that's an opportunity.
- **Link reclamation** — former backlink now 404/redirected/removed;
  recommend reclaiming it.
- **Resource-page opportunities** — pages like "useful links" /
  "recommended tools" that link out externally.
- **Guest-post intelligence** — don't trust a "Write for us" page alone;
  verify against *actually published* third-party-authored articles (do
  they exist, how recent, do they contain followed external links, are
  commercial anchors present) to produce a **Guest Post Probability**,
  separate from "page exists."
- **Content asset matching** — match the user's own assets (guides,
  studies, tools, data) to gaps in a prospect's published content.
- **Website relationship graph** — domain→domain link graph, enabling
  topic/publisher clusters and authority-hub discovery over time.
- **AI Search / GEO intelligence** — track whether/which publishers get
  cited by answer engines for relevant queries. Every such claim requires
  a logged `{query, engine, timestamp, observed_result, source_url}`
  observation — never asserted without one.

### 4.9 Backlink Monitoring

Verified backlinks are periodically re-crawled. Detect and alert on: new,
lost, attribute changed (follow→nofollow, sponsored added), target/anchor
changed, source page 404/redirected/deindexed, canonical changed. Alerts
show explicit before/after state, not just "something changed."

## 5. Non-negotiable engineering principles

1. **No fake data, ever.** Dev fixtures are clearly separated from the
   app; production shows empty states, not placeholder numbers.
2. **No fabricated metrics.** DR/DA/traffic/authority/rankings/AI-visibility
   that we can't produce honestly are `UNKNOWN` or `ESTIMATED` with a
   confidence value — never invented.
3. **Crawl legally and politely.** Respect `robots.txt`, rate limits, and
   server responses. Never bypass auth, CAPTCHA, paywalls, or access
   controls. Never collect non-public information. A block is
   `STATUS = BLOCKED`, not treated as data.
4. **Determinism where possible.** HTTP status, DNS/MX, canonical,
   nofollow, link existence, word/page counts are computed, not modeled by
   an LLM. AI is reserved for genuinely ambiguous judgment calls (topic
   classification, entity extraction, relevance matching, content
   summarization, pitch drafting) — see `docs/ARCHITECTURE.md` §AI.
5. **AI provider is swappable, and Ollama (local) is the default**, so the
   system runs at zero marginal API cost during development. OpenAI/
   Anthropic are optional, pluggable providers behind the same interface.
6. **History over mutation.** We store observations over time
   (`*_observations`, `*_history` tables), not just current state.
7. **A feature is "done" only when frontend + backend + database + real
   collected data + tests all work together against a real crawl.** A
   rendered UI with no real data behind it is not done.

## 6. What we deliberately do not build in v1

Billing/Stripe, team permissions/RBAC beyond basics, white-label reports,
mobile app, browser extension, 20 third-party integrations, automated
cold-email blasting, paid backlink-index APIs (Ahrefs/Semrush/Moz/Hunter),
paid scraping APIs, paid proxy networks, mandatory paid-AI-API dependency.

## 7. V1 success test

Given one target website and up to three competitor domains, the system
must produce, with every row traceable to a real source: pages crawled,
real external links, verified backlinks (+ lost backlinks), competitor
backlinks, link gap, relevant prospects, authors/editors, public contacts
with confidence states, guest-post opportunities, unlinked mentions,
broken-link opportunities, reclamation opportunities, and opportunity
scores with evidence.

## 8. Free-first technology stack

See `docs/ARCHITECTURE.md` for the full breakdown. Summary: Next.js +
FastAPI + PostgreSQL (+ pgvector, + full-text search — no OpenSearch until
justified) + Redis + Crawlee (HTTP crawler by default, Playwright only when
JS rendering is required) + Common Crawl (free public index) + Ollama
(local AI, default) + Docker for local dev. No paid data source or paid AI
API is required to build and run a real version of this product.

## 9. Build order (do not build everything at once)

Phase 0 architecture (this doc + `docs/ARCHITECTURE.md`, `DATABASE.md`,
`API.md`, `CRAWLER.md`) → Phase 1 real crawler → Phase 2 page/link
extraction → Phase 3 backlink verification → Phase 4 Common Crawl
connector → Phase 5 competitor engine → Phase 6 link gap → Phase 7
prospect discovery → Phase 8 contact intelligence → Phase 9 email
verification → Phase 10 guest-post intelligence → Phase 11 opportunity
scoring → Phase 12 evidence engine wiring → Phase 13 Ollama AI layer →
Phase 14 outreach intelligence → Phase 15 email campaigns (human-approved
send) → Phase 16 backlink monitoring → Phase 17 reports/exports → Phase 18
AI-search/GEO intelligence.

After each phase: run tests, run a real crawl, inspect actual database
records, fix issues, document what works — only then move on. See
`docs/ARCHITECTURE.md` §Development Phases for exit criteria per phase.
