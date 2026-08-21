# Architecture

Companion to `PRODUCT_SPEC.md`. Read that first — this document is *how*,
not *what/why*. See also `DATABASE.md`, `API.md`, `CRAWLER.md`.

## 1. System diagram

```
                         ┌───────────────────┐
                         │       USER        │
                         └─────────┬─────────┘
                                   ▼
                         ┌───────────────────┐
                         │    Next.js UI     │
                         └─────────┬─────────┘
                                   ▼
                         ┌───────────────────┐
                         │      FastAPI      │  (API-first: UI is just a client)
                         └─────────┬─────────┘
          ┌────────────────────────┼────────────────────────┐
          ▼                        ▼                        ▼
   ┌──────────────┐       ┌───────────────┐       ┌──────────────┐
   │ Crawl Engine │       │ Intelligence  │       │ Outreach     │
   │ (Crawlee:    │       │ Engine        │       │ Engine       │
   │  HTTP first, │       │ (scoring,     │       │ (campaigns,  │
   │  Playwright  │       │  evidence,    │       │  tracking,   │
   │  fallback)   │       │  entities)    │       │  sending)    │
   └──────┬───────┘       └───────┬───────┘       └──────┬───────┘
          └──────────────┬────────┴──────────────────────┘
                         ▼
                 ┌──────────────────┐
                 │   PostgreSQL     │  pages, links, backlinks, contacts,
                 │  (+ pgvector,    │  authors, prospects, evidence,
                 │   full-text)     │  observations/history
                 └────────┬─────────┘
                ┌─────────┴──────────┐
                ▼                    ▼
          ┌────────────┐       ┌──────────────┐
          │  Redis     │       │   Ollama     │
          │ queues +   │       │ local AI     │
          │ cache      │       │ (default)    │
          └────────────┘       └──────────────┘

External free data:  Common Crawl (CDX index) ──▶ Backlink Discovery ──▶ Direct verification (own crawl)
```

## 2. Repository structure

Monorepo. One deployable backend, one frontend, crawler code lives inside
the backend as a service module (it shares models/DB access, no need to
split it into a separate deployable in v1).

```
/
├── PRODUCT_SPEC.md
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DATABASE.md
│   ├── API.md
│   └── CRAWLER.md
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI app factory
│   │   ├── api/                   # routers, one module per resource (see API.md)
│   │   │   ├── projects.py
│   │   │   ├── crawl.py
│   │   │   ├── backlinks.py
│   │   │   ├── competitors.py
│   │   │   ├── link_gaps.py
│   │   │   ├── prospects.py
│   │   │   ├── contacts.py
│   │   │   ├── authors.py
│   │   │   ├── guest_posts.py
│   │   │   ├── opportunities.py
│   │   │   ├── campaigns.py
│   │   │   ├── reports.py
│   │   │   └── data_quality.py
│   │   ├── core/                  # config, security, logging, rate limiting
│   │   ├── db/                    # SQLAlchemy models, session, migrations (Alembic)
│   │   ├── crawler/                # Crawlee-based crawl engine (see CRAWLER.md)
│   │   │   ├── frontier.py
│   │   │   ├── http_crawler.py
│   │   │   ├── playwright_crawler.py
│   │   │   ├── js_detection.py
│   │   │   ├── extractors/         # page, link, contact, schema extractors
│   │   │   └── fingerprint.py
│   │   ├── engines/
│   │   │   ├── backlink/           # discovery + verification + observations,
│   │   │   │                       # incl. search_discovery.py (Phase 7 candidates)
│   │   │   ├── common_crawl/       # CDX query client
│   │   │   ├── competitor/         # link gap
│   │   │   ├── prospects/          # Phase 7 independent prospect discovery + scoring
│   │   │   ├── contact/            # extraction + verification
│   │   │   ├── author/
│   │   │   ├── guest_post/
│   │   │   ├── scoring/            # opportunity + sub-scores + evidence
│   │   │   ├── ai/                 # provider interface: Ollama / OpenAI / Anthropic
│   │   │   ├── search/             # AISearchProvider interface + AnthropicSearchProvider,
│   │   │   │                       # shared by Phase 7 discovery and Phase 18 GEO citations
│   │   │   ├── geo/                # GEOObservation + check_citation (Phase 18)
│   │   │   └── outreach/           # strategy, drafting, campaigns
│   │   ├── workers/                # Celery/RQ task definitions per queue
│   │   └── tests/
│   │       ├── fixtures/html/      # local fixture pages (see CRAWLER.md §Testing)
│   │       ├── unit/
│   │       └── integration/
│   ├── alembic/
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/                      # Next.js (App Router) -- see §4 and frontend/README.md
│   ├── app/                       # domain-centric routes: dashboard (/), /domains/[id],
│   │                               # /crawl/[jobId], /backlinks/[id], /campaigns/[id], /reports
│   │   └── actions.ts             # every Server Action (mutation) in one place
│   ├── components/                # Section, Badge, EvidenceList, EmptyState, SubmitButton
│   ├── lib/api.ts                 # typed server-side fetch wrapper (no client-side calls)
│   ├── lib/types.ts               # TS types mirroring backend/app/api/schemas.py exactly
│   └── package.json
├── docker/
│   ├── docker-compose.yml         # postgres, redis, ollama, backend, frontend, worker
│   └── .env.example
└── .gitignore
```

## 3. Backend architecture

FastAPI, organized as **engines** (one Python package per engine from the
product spec), each exposing:

- a **service** layer (business logic, pure functions where possible),
- a **repository** layer (SQLAlchemy queries — no raw SQL scattered in
  services),
- an API router that only orchestrates service calls and shapes
  responses.

Rules: no giant files; no business logic in route handlers; Pydantic
models validate every request/response and every AI JSON response (AI
output that fails schema validation is a hard failure, not a best-effort
parse). Type hints throughout; `ruff` + `pytest` enforced in CI.

## 4. Frontend architecture

**Done** — see `frontend/README.md` for the full account. Next.js
(App Router), API-first: the frontend is purely a client of the FastAPI
backend, no server-side data mutation logic duplicated in the frontend.
Adapted to the backend's *real* domain-centric route surface (no
`projects`/auth layer exists — see §9) rather than the aspirational
per-module route list this section originally sketched: pages are
organized around a domain detail hub (`/domains/[id]`) plus focused
detail pages for a crawl job, a backlink, and a campaign, instead of one
flat route per engine. The one exception is `/prospects` (Phase 7):
since prospect discovery is topic-keyed rather than domain-keyed, it
gets its own top-level route (topic search form + results list) rather
than living under a domain hub. `/domains/[id]` also gained two Phase
7/18 sections: pending search-pattern-discovered `BacklinkCandidate`s
(with an inline verify action) and an automated "check citation now"
form (`POST /geo/check`) alongside the pre-existing manual GEO-log form.

Every backend call runs server-side — reads in `async` Server
Components (`fetch`, `cache: "no-store"`), writes via Server Actions
(`'use server'`, `revalidatePath`) — so the browser never talks to the
backend directly. That means zero CORS configuration on the backend and
`API_URL` never reaching the client bundle, at the cost of every
mutation being a full-page server round-trip rather than an optimistic
client update; acceptable for a single-operator tool with no realtime
requirement. The one exception is report downloads (`GET
/reports/download`), a Next.js Route Handler that proxies bytes/headers
straight through from the backend, since a Server Action can't hand the
browser a file to save.

List views use dense HTML tables, provenance/confidence badges, and
inline evidence lists rather than marketing-style cards, per this
section's original intent — no separate component library was added
for that; a handful of shared primitives in `frontend/components/`
(`Section`, `Badge`, `EvidenceList`, `EmptyState`) do the job. Every
list renders an explicit empty state, never a placeholder number.

## 5. Crawler architecture (summary — full detail in `CRAWLER.md`)

Crawlee, HTTP crawler as the default path, Playwright only when a
JS-detection heuristic says the HTML doesn't already contain the content.
Crawl Manager assigns priority (backlink candidate > competitor backlink >
contact/author/guest-post page > high-value/recently-changed page > general)
via Redis-backed priority queues, not a single FIFO queue.

## 6. Queue architecture

Redis + Celery (or RQ — pick one at implementation time; Celery if we need
multiple queues/priorities and scheduled/periodic tasks, which we do for
monitoring). Separate queues: `crawl.priority_a` (backlinks),
`crawl.priority_b` (contacts), `crawl.priority_c` (general), `verify.email`,
`ai.jobs`, `monitor.recheck`, plus a dead-letter queue for permanently
failed crawl/verification jobs. Redis also backs response caching and
robots.txt caching.

## 7. AI architecture

```
                 AIProvider (interface)
                        │
        ┌───────────────┼───────────────┐
        ▼                ▼               ▼
     Ollama           OpenAI         Anthropic
   (default, local)  (optional)     (optional)
```

Single interface (`generate_structured(prompt, json_schema) -> validated
result | raises`). Ollama's local HTTP API (`localhost:11434`) is the
default so the system runs at zero API cost during development; OpenAI/
Anthropic are opt-in via config, never required. AI is used only for
genuinely ambiguous judgment (topic/entity classification, author-topic
matching, link-context classification, opportunity explanation prose,
content-asset matching, outreach strategy/drafting). AI is explicitly
**not** used for anything deterministic (HTTP status, URL/canonical
handling, DNS/MX, nofollow detection, link existence, word/page counts) —
see `PRODUCT_SPEC.md` §5.4. A failed or schema-invalid AI call must not
silently fabricate a result; it fails the job and is retried/logged.

## 8. Docker architecture

`docker/docker-compose.yml` services: `postgres` (with `pgvector`
extension), `redis`, `ollama`, `backend` (FastAPI), `worker` (Celery,
same image as backend, different entrypoint), `frontend` (Next.js). No
OpenSearch, no paid services. Local dev should come up with a single
`docker compose up`.

## 9. Development phases and exit criteria

Each phase below must satisfy: tests pass, the app runs, a **real** crawl
was executed, database records were manually inspected against the real
source pages, and results are documented — before moving to the next
phase. "Frontend renders" is never sufficient on its own.

| Phase | Deliverable | Exit criteria |
|---|---|---|
| 0 | This architecture package + repo/Docker/DB skeleton | `docker compose up` brings up Postgres/Redis/Ollama; Alembic runs against an empty DB |
| 1 ✅ | Real crawler (robots, sitemap, HTTP+Playwright, frontier, politeness) | **Done.** Crawled a live public site (pypi.org) end-to-end with real Postgres rows manually inspected; 27 passing tests including 4 real integration tests (local fixture server + real Postgres, no mocks) covering the fixture site, a broken-link 404, robots.txt caching, and HTTP→Playwright JS escalation. See `backend/app/crawler/`. |
| 2 ✅ | Full page/link extraction (metadata, schema, contacts, entities) | **Done** for the deterministic subset: schema.org (JSON-LD), OpenGraph, Twitter Cards, images+alt, PDF links, social profile links, embeds, and candidate contact emails/phones from page text — all verified against a real crawl (pypi.org) with rows inspected in Postgres, plus 15 new tests (6 integration, real HTTP + real DB). AI-assisted entity extraction (Organization/Person/Product/Service/Location per `PRODUCT_SPEC.md` §4.1) is deliberately deferred to Phase 13 (AI layer) rather than faked here — see `backend/README.md`. |
| 3 ✅ | Backlink verification pipeline | **Done.** `BacklinkCandidate` → direct crawl (reuses the Phase 1/2 crawler) → `BacklinkObservation` (`VERIFIED`/`REJECTED` with reason) → derived `backlinks` current-state row with first/last-seen. Verified against a real live backlink (pypi.org homepage → `/help/`, correct anchor/rel/nav-classification) plus 9 tests covering VERIFIED, nofollow/sponsored detection, target-not-found rejection, and source-unreachable rejection — all against a real fixture server and real Postgres. See `backend/app/engines/backlink/`. |
| 4 ✅ | Common Crawl connector | **Done, with a caveat.** CDX index query + WARC-record Range-fetch (reusing the Phase 2 link extractor on the fetched HTML) produces real `BacklinkCandidate` rows that flow straight into Phase 3 verification — proven end-to-end against a real Postgres database and a real live verification pass. The one piece not independently proven is the raw HTTP calls to Common Crawl's own servers: `index.commoncrawl.org`/`data.commoncrawl.org` are policy-denied by *this build sandbox's* egress proxy (confirmed via the proxy's diagnostic log — a real, persistent policy denial, not a flake), so those two endpoints are tested against fixtures shaped exactly like their documented real response formats (CDX JSON, gzip WARC records) rather than the live service. Needs one live smoke test in an environment with normal internet access before fully trusting it in production — see risk #14. |
| 5 ✅ | Competitor engine | **Done.** `CompetitorRelationship` (domain-keyed, no `projects` table needed yet) + `compute_link_gap()`, a pure query over existing `backlinks` rows — "crawling a competitor" is just Phase 3/4 discovery/verification run with the competitor's domain as the target, no new crawl mechanism needed. Proven with a fully real multi-domain scenario (distinct loopback addresses as genuinely separate source domains, real crawls, real Postgres), confirming correct overlap counting/tiering and correct exclusion of domains that already link to the primary. Surfaced and fixed a real Crawlee bug in the process — see risk #15. |
| 6 ✅ | Link gap engine + API | **Done** (API only at the time — the frontend consuming it was built later, see §4). Introduces `app/api/` (FastAPI, domain-centric since no `projects`/auth layer exists yet): `/domains`, `/crawl`, `/backlinks`, `/competitors`, `/link-gaps`. `/link-gaps` recomputes on every call (cheap query over `backlinks`) and returns real, evidenced opportunities — proven via `TestClient` driving the real route handlers against a real Postgres test database, including a real crawl through `/crawl` and a real verified backlink through `/backlinks`. |
| 7 ✅ | Prospect discovery | **Done.** Two distinct engines, both driven by `AnthropicSearchProvider` (Claude's web-search tool, see risk #3/#18/#19) rather than a scrape-based search backend. `app/engines/backlink/search_discovery.py`'s `discover_candidates_from_search()` covers PRODUCT_SPEC §4.2 Layer 2: named query patterns (`intitle:`, `"brand" "resources"`, etc.) against `brand_query`, producing URL-level `BacklinkCandidate` rows (`source_type=SEARCH_DISCOVERED`) that flow into the existing Phase 3 verify pipeline via `POST /backlinks/discover-search` + `POST /backlinks/candidates/{id}/verify`. `app/engines/prospects/discover.py`'s `discover_prospects()` is the independent, PRODUCT_SPEC §4.4 module this row's exit criteria actually names: given only a topic (no competitor, no existing domain), it searches category-specific templates (resource pages, roundups, guest-post blogs, industry publications) and produces domain-level `Prospect` rows with a `topical_fit_score` -- explicitly documented as a crude keyword-overlap proxy (topic words vs. host + search-answer text), not a duplicate of Phase 11's real, crawl-based `topical_relevance` scoring, which remains the source of truth once a domain has been crawled. `POST /prospects/discover`, `GET /prospects`. 6 new integration tests (`FakeAISearchProvider` + real Postgres) plus API-level tests in `test_api.py`. |
| 8 ✅ | Contact intelligence | **Done.** Reuses the Phase 1/2 crawler (no separate contact-crawling mechanism); classifies contact-relevant pages by URL path (about/contact/team/author/guest-post/press) and turns Phase 2's page-level `contact_emails`/`contact_phones`/`schema_org` into full, uncapped `Contact` rows with provenance. Deliberately refuses to guess a name/email pairing beyond schema.org `Person` markup or an unambiguous single-person page (exactly one heading + one email) — proven by a test asserting a multi-person team page leaves names unattributed rather than mis-paired. 11 new tests, all real (fixture server + real Postgres). Live-checked against pypi.org: correctly returned zero contacts, since its crawl-reachable pages don't include an about/contact/team page — an honest negative result, not a bug. |
| 9 ✅ | Email verification | **Done for the deterministic layers.** Syntax, domain DNS/MX (with RFC 5321 A-record fallback), and a disposable-domain list — genuinely proven with real, live DNS lookups (no mocking needed; unlike HTTPS, DNS resolution isn't restricted in this sandbox). SMTP-level mailbox/catch-all probing is out of scope, not silently skipped: outbound port 25 is blocked here (confirmed with a direct TCP connect test) and PRODUCT_SPEC.md is independently skeptical of it — we never send a verification email. Ceiling is `LIKELY`, never `VERIFIED`/`CATCH_ALL`. `EmailVerification` keeps a full history per contact; `POST /contacts/{id}/verify-email` exposes it. |
| 10 ✅ | Guest-post intelligence | **Done.** Reuses Phase 1/2 crawl + Phase 8 page classification to find and analyze the guideline page (word-count range, dofollow/nofollow/sponsored/author-bio mentions, editor email, closed-submissions detection — all via named, explicit regex patterns, not general NLP). The probability score factors in distinct authors already observed on the domain's author pages as a proxy for "does this site publish more than one person" — explicitly labeled a proxy, not confirmed third-party authorship, since we can't yet distinguish staff writers from guest contributors. Also retroactively completes a Phase 2 gap: added the `pages.body_text` column (already documented in `docs/DATABASE.md`'s indexing strategy but never actually added) plus the full-text GIN index it was meant to back. 7 new tests, all real. |
| 11 ✅ | Opportunity scoring | **Done, with an intentionally smaller component set than PRODUCT_SPEC.md §8's named list** (see `OpportunityScore`'s model docstring) — every component is computed only from data this project actually collected (indexability, content depth, contactability, link probability from Phase 5/10, crude keyword-overlap topical relevance) or explicitly reported `unavailable` (organic traffic — no data source; topical relevance/link probability without a reference domain). Composite is a weighted average over only the *available* components, then spam risk (crawl-error-rate + thin-content-ratio) dampens it. `POST /opportunities/score`. 4 new tests confirming real signals feed real scores and unmeasurable ones never get a fabricated number. |
| 12 ✅ | Evidence engine | **Done — as a design discipline applied from Phase 5 onward, not a separate module.** Per risk #9's original warning, every opportunity-shaped table (`LinkGapOpportunity`, `GuestPostOpportunity`, `OpportunityScore`) got an `evidence: list[str]` field the moment it was created, populated at write-time by the same function that computes the score — never backfilled later. `BacklinkObservation`/`Contact` carry their evidence structurally (anchor_text, surrounding_text, source_url, source_text) rather than as prose, which is more precise, not less. No separate polymorphic `evidence` table was built: colocating evidence with what it explains avoids a join and can't drift out of sync the way a backfilled side-table could. Closed the one gap found on audit (`LinkGapOpportunity` lacked the field the other two had) and added real assertions proving the evidence content, not just its presence. |
| 13 ✅ | Ollama AI layer | **Done, with a caveat.** `AIProvider` abstract interface (`app/engines/ai/provider.py`) plus `OllamaProvider` (`app/engines/ai/ollama_provider.py`), built against Ollama's real, documented `/api/generate` structured-output API — requests a JSON Schema via `format`, validates the response against the caller's Pydantic `response_model`, raises `AIGenerationError` on any transport/parse/schema failure rather than returning a partial result. No business use case wired to it yet (deferred to Phase 14, so the interface isn't shaped around one assumed caller). Same caveat as Phase 4: Ollama itself is unreachable from this build sandbox (policy-denied, see risk #17), so `OllamaProvider` is tested with `respx`-mocked HTTP proving request/response correctness, not live connectivity — needs a live smoke test before production use. `FakeAIProvider` test double added for later phases to depend on the `AIProvider` contract without needing Ollama at all. 8 new tests. |
| 14 ✅ | Outreach intelligence | **Done, strategy generation only (no copy drafting or sending, per spec).** `app/engines/outreach/strategy.py`'s `generate_outreach_strategy()` picks an opportunity type by priority (guest-post opportunity > link-gap opportunity > generic direct-outreach) and computes `reason`/`evidence`/`expected_link_probability`/`difficulty` **deterministically** from Phase 5/10 rows this project already verified -- never from the AI. The AI (`AIProvider`, Phase 13) is used for exactly one thing, synthesizing `angle`, explicitly instructed to use only the evidence it's given and never invent facts/statistics/readership/credentials/prior contact per PRODUCT_SPEC.md §4.7; `angle` stays `None` (not a canned fallback string) when no provider is configured or generation fails -- proven with both a real `FakeAIProvider` success case and a real failure case. `recommended_content_asset` is always `None` (content-asset matching needs a user-asset table that doesn't exist -- Phase 4.8, not built). `POST /outreach/strategy`, `GET /outreach/strategy/{contact_id}`. 8 new tests, all against real crawled/verified data except the AI step (`FakeAIProvider`, same reasoning as risk #17). |
| 15 ✅ | Campaigns (human-approved send) | **Done.** `app/engines/campaigns/funnel.py`: a `Campaign` is a record a human creates from an `OutreachStrategy` *after* pitching a contact through their own email client -- there is no `send_email` function anywhere in this codebase, confirmed by grep, not just by claim. `record_event` logs each real-world funnel-stage transition (sent/delivered/bounced/opened/clicked/replied/positive_reply/negative_reply/unsubscribed/published/backlink_detected/backlink_verified) as the human reports it; no ordering is enforced since real outreach doesn't move through these linearly. `check_backlink_detected` is the one non-manual transition: it queries the real Phase 3 `backlinks` table for a link matching the human-supplied `target_url`, and because that table only ever holds already-verified links by construction, BACKLINK_DETECTED and BACKLINK_VERIFIED are recorded together with a note explaining why, rather than faking a gap between them. Proven end-to-end: real contact discovery → real strategy generation → campaign creation → recorded events → a real crawl+verify (Phase 3) producing a real backlink → `check_backlink_detected` correctly finding it and advancing the funnel, with a prior check correctly finding nothing before the backlink existed. `POST /campaigns`, `GET /campaigns/{id}`, `POST /campaigns/{id}/events`, `POST /campaigns/{id}/check-backlink`. 4 new tests, all real, no mocking. |
| 16 ✅ | Backlink monitoring | **Done** (on-demand re-check; no scheduler wired up -- see the note below). `app/engines/monitoring/recheck.py`'s `recheck_backlink()` re-runs Phase 3's real candidate verification for a tracked backlink's exact (source_url, target_url) pair and diffs the new observation against the previous one, producing explicit before/after `BacklinkMonitoringEvent` rows for exactly what changed (link attributes, anchor text, source HTTP status, canonical URL) -- never a bare "something changed." A rejected re-verification (the link is gone) sets a new `lost_at` timestamp on the `backlinks` row, since a lost link produces no new `BacklinkObservation` to derive state from -- the one intentional, documented exception to that table's "never hand-edited" rule (see `Backlink`'s docstring). "Target changed" from the spec's list isn't attempted: re-verification checks whether *this* target_url is still linked, so a retargeted source page surfaces as LOST, not as a distinguishable "retargeted" event -- not guessed. Proven with 4 real tests: an actual attribute+anchor change detected across two real crawls of the same URL (fixture content temporarily swapped on disk between crawls), a stable link producing zero false-positive events, a genuinely unreachable source correctly producing LOST and setting `lost_at`, and an unknown-backlink error path. `POST /backlinks/{id}/recheck`, `GET /backlinks/{id}/monitoring-events`. Periodic scheduling (a cron/worker calling `recheck_backlink` on a cadence) is not built -- there's no task-queue/scheduler infrastructure in this project yet, and adding one just to call an already-correct function would be exactly the premature scaffolding `PRODUCT_SPEC.md` warns against; the on-demand endpoint is the real, tested primitive a scheduler would call. |
| 17 ✅ | Reports/exports | **Done.** `app/reports/`: `rows.py` builds real row data for five report types (backlinks, link_gaps, contacts, guest_posts, opportunity_scores) by querying the tables Phases 3/5/8/10/11 already populated -- no new computation, only formatting. `export.py` writes the same row/column shape to CSV and JSON (stdlib), XLSX (`openpyxl`), and PDF (`reportlab`) -- real files each format's own library can read back, not a text file wearing an extension (proven by round-tripping every format through its real parser/reader in tests, and asserting the PDF bytes start with the real `%PDF-` magic number). `GET /reports/{report_type}?format=csv\|json\|xlsx\|pdf&...filters`. 17 new tests (5 unit on the writers, 5 integration proving a backlinks-CSV and contacts-JSON report reflect an actual verified backlink/discovered contact byte-for-value, plus error-path tests, plus 2 API-level). |
| 18 ✅ | AI-search/GEO intelligence | **Done, including a live provider (see risk #18/#19).** `GEOObservation` is the append-only `{query, engine, timestamp, observed_result, source_url}` log `PRODUCT_SPEC.md` §4.8 requires -- every citation claim is backed by one, never asserted bare. Two ways to produce one: `record_manual_observation()` (a human checked a real answer engine themselves and logs what they saw -- no API needed, fully legitimate) and `check_citation()` (automated, via an `AISearchProvider`; the citation match itself is deterministic registrable-domain comparison against whatever URLs the provider returns, never a fuzzy judgment call). `AnthropicSearchProvider` (`app/engines/search/anthropic_provider.py`) is the concrete provider that resolved the earlier gap: it uses Claude's own `web_search` server tool, whose request/response shape was confirmed via a live fetch of the current API reference rather than guessed -- the same tool also backs Phase 7's discovery engines. `check_citation`'s matching logic is proven correct against both a `FakeAISearchProvider` and `respx`-mocked `AnthropicSearchProvider` requests. `POST /geo/observations`, `GET /geo/observations`, `POST /geo/check` (automated, wired to `AnthropicSearchProvider`). 7 Phase-18 tests plus new provider/API tests (see risk #19 for what remains unverified against a live key). |

## 10. Technical risks and contradictions (flagged for review before Phase 1)

1. **Crawler scalability vs. politeness.** Per-domain concurrency/delay
   limits (required, §Crawler) directly cap throughput. Decide the
   acceptable pages/minute target *before* sizing the queue/worker count —
   otherwise Phase 1 will look "slow" against an implicit unstated
   expectation.
2. **Common Crawl freshness.** CDX index lag can be weeks; a link that
   Common Crawl hasn't captured yet is a false negative, not proof a
   backlink doesn't exist. The product must never say "no backlinks found"
   from Common Crawl alone — direct verification and search discovery are
   required to raise confidence, and the UI must show coverage confidence,
   not false completeness (see spec §"don't promise all backlinks").
3. **(Resolved in Phase 7 build) Search discovery depends on a search
   backend** (a scraping-friendly engine or a paid Search API) that isn't
   named in the "free-first" stack. This is a real gap: query-pattern
   discovery (§4.2 layer 2) needs *something* to execute searches
   against. **Decision made:** reuse Claude's own web search tool
   (`app/engines/search/anthropic_provider.py`) as the search backend for
   both Phase 7 (this risk) and Phase 18 (risk #18/#19) rather than a
   self-hosted SearX instance, a rate-limited scrape, or a paid Search
   API budget. Not free the way Ollama or Common Crawl are, but its
   request/response shape was independently verified against the live
   API reference at implementation time — see risk #19 for the full
   rationale and its one remaining caveat.
4. **SMTP-level email verification is inherently unreliable** (catch-all
   domains, greylisting, many mail servers reject unknown-sender probes
   outright). The spec's own confidence-state model (§4.6) is the correct
   mitigation — but implementers must resist the temptation to treat a
   successful SMTP handshake as "VERIFIED"; catch-all detection must run
   first and downgrade accordingly.
5. **Playwright resource usage.** Even with JS-detection gating, Playwright
   crawls are 10-50x more expensive than HTTP. Per-domain and global
   concurrency limits for the Playwright pool must be *separate and lower*
   than the HTTP crawler's, or a handful of JS-heavy prospects will starve
   the whole crawl queue.
6. **Database growth from historical observations.** Storing every crawl
   as an observation (not mutating current state) is correct for the
   backlink-history feature, but on frequently-monitored large sites this
   grows unbounded. Needs a retention/rollup policy (e.g. collapse
   unchanged daily observations into a date range) — not required for
   Phase 1-3, but the schema should anticipate it (see `DATABASE.md`
   §Observation tables).
7. **AI provider abstraction vs. structured-output guarantees.** Ollama
   local models are weaker at strict JSON-schema adherence than hosted
   frontier models. The `AIProvider.generate_structured` contract must
   validate and reject-and-retry rather than assume any provider reliably
   returns valid JSON — this affects Phase 13 design, not just prompting.
8. **Duplicate URL / domain normalization is a prerequisite, not a detail.**
   Every engine (backlink, competitor, prospect, contact) keys off
   `domain_id`. If normalization (www/scheme/trailing-slash/punycode/
   redirect-resolution) isn't correct and centralized *before* Phase 1
   data starts accumulating, later phases will double-count domains and
   the fix becomes a data migration, not a code change. Build the
   normalization utility first and reuse it everywhere — never
   re-implement per engine.
9. **Evidence Engine coupling.** Every engine that produces a score must
   also write evidence records at the same time (not backfill later), or
   the Evidence Engine (Phase 12) becomes a giant retrofit across Phases
   3-11. Each scoring function's contract should require an evidence list
   as part of its return type from the start.
10. **"No automated sending in v1" vs. campaign/reply tracking.** Reply/
    bounce/open tracking (§4.7) generally requires inbox or webhook
    integration (Gmail API, SMTP headers) which is itself meaningful
    integration work even without *sending* automation. Scope Phase 15
    explicitly as "human clicks send, system tracks the rest" so it isn't
    quietly treated as full send automation.
11. **(Confirmed in Phase 1 build) Crawlee's default HTTP client does not
    reliably honor environment-based egress-proxy configuration** on
    every platform -- it silently fails the CONNECT tunnel where `httpx`
    succeeds using the same env vars. Any deployment sitting behind a
    corporate/CI egress proxy should default to Crawlee's `HttpxHttpClient`
    rather than its default (`app/crawler/http_crawler.py` already does
    this) instead of debugging this per-environment later.
12. **(Confirmed in Phase 1 build) The HTTP→Playwright escalation needs
    `always_enqueue=True` on the re-crawl request.** Crawlee dedups
    requests by URL-derived unique key within a run; a URL the HTTP pass
    already "handled" (even if our own handler chose to escalate rather
    than extract) is silently skipped by the Playwright pass's queue
    unless the escalated request is explicitly marked `always_enqueue`.
    Getting this wrong doesn't raise an error -- it just silently crawls
    zero pages, which is the kind of failure mode that's easy to miss
    without an integration test asserting on real DB rows (see
    `app/tests/integration/test_crawl_js_escalation.py`).
13. **(Confirmed in Phase 3 build) Reusing a named Postgres ENUM type
    across tables in different Alembic migrations needs an explicit
    `create_type=False`, and the generic `sa.Enum(...)`'s `create_type`
    kwarg doesn't reliably suppress the CREATE TYPE DDL in this
    SQLAlchemy version -- use the dialect-specific
    `sqlalchemy.dialects.postgresql.ENUM(..., create_type=False)` in the
    migration script for any column after the first that references an
    already-existing enum (e.g. `link_position`, reused by
    `backlink_observations` after `page_links` created it in an earlier
    migration -- see `alembic/versions/4d4f7236ee73_*.py`). Sharing the
    same Python `Enum(...)` object across model columns is still correct
    practice (it makes `Base.metadata.create_all()` -- what the test
    suite uses -- dedupe correctly), but autogenerated migration files
    are serialized as independent literals and need this fix by hand
    every time a new table reuses an existing named enum.
14. **(Confirmed in Phase 4 build) Common Crawl's public endpoints
    (`index.commoncrawl.org`, `data.commoncrawl.org`) are not reachable
    from every environment.** In this project's build sandbox they're
    policy-denied at the egress proxy (not a transient failure --
    confirmed via the proxy's own diagnostic log showing repeated,
    consistent `403` on the CONNECT tunnel). The connector
    (`app/engines/backlink/common_crawl.py`) is built against Common
    Crawl's real, documented API shapes (CDX server `output=json`
    NDJSON, gzip-compressed single-record WARC fetched via HTTP `Range`)
    and is unit/integration-tested against fixtures matching those
    shapes byte-for-byte, but has not been exercised against the live
    service. Before relying on it in any real deployment, run one live
    smoke test (`discover_candidates_from_common_crawl` against a real
    seed domain) from an environment with normal internet egress -- do
    not assume sandbox test-passing alone proves the live integration
    works, the way it was independently proven for Phases 1-3 against
    pypi.org.
16. **(Confirmed in Phase 11 build) A raw-SQL object created via
    `op.execute()` in one migration (e.g. `ix_pages_fulltext`, the
    functional GIN full-text index added in Phase 10 -- it isn't
    expressible as a plain SQLAlchemy `Index()` on the ORM model) gets
    proposed for deletion by the *next* `alembic revision --autogenerate`
    call.** The diff tool only knows about what's declared in ORM
    metadata; anything created out-of-band looks, from its point of
    view, like drift to correct. Always read a freshly autogenerated
    migration for unexpected `drop_index`/`drop_table`/`drop_column`
    lines referencing anything added via raw SQL in an earlier
    migration, and delete the spurious drop (and its downgrade-side
    recreate) by hand before applying.
15. **(Confirmed in Phase 5 build) A fresh `MemoryStorageClient()`
    instance per crawl run is not enough to prevent state leaking
    across separate crawler runs in the same process.** Crawlee resolves
    a request queue by *name* against a process-wide registry; two
    `BeautifulSoupCrawler`/`PlaywrightCrawler` instances that both rely
    on the implicit "default" queue name can pick up each other's
    pending/discovered requests even with distinct storage client
    objects. This surfaced concretely as: verifying two
    `BacklinkCandidate`s that share the same `source_url` (e.g. checking
    whether one page links to two different competitors) caused the
    second verification's crawl to also attempt fetching the first
    page's *external* links -- links that `enqueue_links(strategy=
    "same-domain")` had correctly filtered out of the first run, but
    which apparently still ended up in the shared "default"-named queue.
    Fixed by giving every crawl run (`app/crawler/http_crawler.py` and
    `playwright_crawler.py`) its own uniquely-named `RequestQueue.open(
    name=f"...-{uuid4()}", storage_client=...)` instead of relying on
    the crawler's implicit default queue. Any future code that builds a
    Crawlee crawler directly (bypassing these two factories) needs the
    same treatment.
17. **(Confirmed in Phase 13 build) Ollama itself cannot be installed or
    reached from this build sandbox.** Both `ollama.com/install.sh` and
    the GitHub releases used to install Ollama are policy-denied by the
    outbound proxy here — same egress-allowlist pattern already
    documented in risk #14 for Common Crawl, confirmed via the proxy's
    diagnostic log (persistent denial, not a flake). This is despite the
    sandbox otherwise having enough headroom to run a small local model
    (15GB RAM, 30GB disk, 4 cores). Following the same precedent as
    Common Crawl: `app/engines/ai/ollama_provider.py`'s `OllamaProvider`
    is built against Ollama's real, documented `/api/generate`
    structured-output API (JSON Schema in `format`, `stream: false`), and
    its request construction/response parsing is proven correct with
    `respx`-mocked HTTP — but live connectivity to a real `ollama serve`
    has not been exercised here. Run a live smoke test before depending
    on it in production. `app/tests/fixtures/fake_ai_provider.py`'s
    `FakeAIProvider` lets Phase 14 (the only consumer of `AIProvider` so
    far) be tested without depending on Ollama being reachable at all.
18. **(Confirmed in Phase 18 build, resolved in a later pass) No
    free/open-source, self-hostable "answer engine" API exists to build
    a verifiable `AISearchProvider` implementation against, unlike
    Ollama.** The real APIs that return AI-answer citations (Perplexity,
    etc.) are paid and key-gated, and this sandbox couldn't confirm
    their current documented request/response shape closely enough to
    implement a genuine integration without guessing at wire-format
    details -- a materially different situation from Ollama
    (self-hostable, well-established documented API, confirmed from
    training knowledge) or Common Crawl (public, unauthenticated,
    well-established documented API). Shipping a provider implementation
    built on an unverified guess would be exactly the fabrication
    `PRODUCT_SPEC.md` warns against, just moved into code instead of
    into a number, so none shipped at first. **Resolved:** see risk #19
    -- Claude's own web search tool's request/response shape was
    independently confirmed via a live fetch of the current API
    reference (not recalled from training data, and not guessed), which
    removed the actual blocker recorded here. `AnthropicSearchProvider`
    (`app/engines/search/anthropic_provider.py`) is now the concrete
    implementation both `check_citation()` (`app/engines/geo/
    citations.py`, wired to `POST /geo/check`) and Phase 7's discovery
    modules use. `GEOObservation`'s append-only `{query, engine,
    timestamp, observed_result, source_url}` log (`PRODUCT_SPEC.md`
    §4.8) and its deterministic registrable-domain citation matching are
    unchanged by this -- `record_manual_observation()` (no API needed)
    remains equally legitimate, and `FakeAISearchProvider` remains the
    test double for logic that doesn't need to exercise the real
    provider.
19. **(Confirmed in the Phase 7/18-resolution build) `AnthropicSearchProvider`
    is tested with the real Anthropic Python SDK's HTTP calls
    intercepted by `respx`, not against a live Anthropic API key.** This
    project has no Anthropic API key configured for its own deployment
    in this sandbox, so live reachability of `POST /v1/messages` with
    the `web_search_20250305` tool is unverified here -- same posture as
    risk #17's Ollama caveat, not risk #18's original "no viable
    integration exists" one. The response shapes the tests assert
    against (`web_search_tool_result` content lists, `web_search_result`
    fields, the `web_search_tool_result_error` error shape, citation
    blocks) were copied from a live fetch of
    `platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool`
    at implementation time, not recalled from training data. Also
    discovered empirically (not documented behavior): when no Anthropic
    credentials resolve anywhere (no `api_key`, no `ANTHROPIC_API_KEY`,
    no `ant auth login` profile), the SDK raises a plain `TypeError` at
    request-construction time rather than an `anthropic.APIError`
    subclass -- `AnthropicSearchProvider.search()` catches this
    specifically so a misconfigured deployment fails with a clear
    `AISearchError` → `502 upstream_error`, not an unhandled 500. Run a
    live smoke test with a real key before depending on this in
    production. **Separately, pinned `anthropic<1.0`:** the 1.x SDK line
    moves its transport onto a separate `httpx2` package that this
    project's respx-based HTTP mocking (used consistently for every
    other provider's tests) cannot intercept; the wire format this
    project depends on is unchanged between the two SDK major versions,
    only client-side ergonomics differ.
