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
│   │   │   ├── backlink/           # discovery + verification + observations
│   │   │   ├── common_crawl/       # CDX query client
│   │   │   ├── competitor/         # link gap
│   │   │   ├── prospect/           # discovery + scoring
│   │   │   ├── contact/            # extraction + verification
│   │   │   ├── author/
│   │   │   ├── guest_post/
│   │   │   ├── scoring/            # opportunity + sub-scores + evidence
│   │   │   ├── ai/                 # provider interface: Ollama / OpenAI / Anthropic
│   │   │   └── outreach/           # strategy, drafting, campaigns
│   │   ├── workers/                # Celery/RQ task definitions per queue
│   │   └── tests/
│   │       ├── fixtures/html/      # local fixture pages (see CRAWLER.md §Testing)
│   │       ├── unit/
│   │       └── integration/
│   ├── alembic/
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   ├── app/                       # Next.js routes: dashboard, projects, backlinks,
│   │                               # competitors, link-gap, prospects, contacts,
│   │                               # authors, guest-posts, opportunities, outreach,
│   │                               # campaigns, reports, monitoring, data-quality, settings
│   ├── components/
│   ├── lib/api-client/            # typed client generated from the API schema
│   └── Dockerfile
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

Next.js, API-first — the frontend is purely a client of the FastAPI
backend (no server-side data mutation logic duplicated in the frontend).
One route per module listed in the repo structure above. Every list view
needs: table, filters, search, sort, evidence/source drill-down, and an
explicit empty state (never a placeholder number). Avoid a generic SaaS
template feel — prioritize dense data tables, provenance/confidence
badges, and evidence panels over marketing-style cards.

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
| 1 | Real crawler (robots, sitemap, HTTP+Playwright, frontier, politeness) | Crawl a real public site end-to-end; pages/links/errors land in DB, verified by manual inspection |
| 2 | Full page/link extraction (metadata, schema, contacts, entities) | Extraction fields in `CRAWLER.md` §Page-level/Link-level all populated on a real crawl |
| 3 | Backlink verification pipeline | A known real backlink is discovered and reaches `VERIFIED` with correct anchor/rel/context |
| 4 | Common Crawl connector | CDX query returns candidate URLs for a real domain; candidates flow into verification |
| 5 | Competitor engine | Two real competitor domains crawled; shared/exclusive backlink sets computed correctly |
| 6 | Link gap engine + API/UI | `/link-gaps` returns real, evidenced opportunities for a test project |
| 7 | Prospect discovery | Independently discovered prospects (not just competitor-derived) with topical scores |
| 8 | Contact intelligence | All contact-relevant page types crawled; full extracted contact list (not capped) with confidence states |
| 9 | Email verification | Syntax/DNS/MX/catch-all layers implemented; no verification email ever sent |
| 10 | Guest-post intelligence | Probability computed from actual published contributor articles, not just page existence |
| 11 | Opportunity scoring | Configurable weighted composite + all named sub-scores rendered |
| 12 | Evidence engine | Every score/opportunity has a clickable, real evidence list |
| 13 | Ollama AI layer | Provider interface implemented; Ollama works with zero other API keys configured |
| 14 | Outreach intelligence | Strategy object generated before any email draft; no fabricated claims in output |
| 15 | Campaigns (human-approved send) | Full funnel tracked (sent→backlink); no automated bulk sending |
| 16 | Backlink monitoring | Scheduled re-crawl detects a real attribute/status change with before/after evidence |
| 17 | Reports/exports | CSV/XLSX/JSON/PDF export for each report type |
| 18 | AI-search/GEO intelligence | Every citation claim backed by a logged `{query, engine, timestamp, source_url}` observation |

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
3. **Search discovery depends on a search backend** (a scraping-friendly
   engine or a paid Search API) that isn't named in the "free-first"
   stack. This is a real gap: query-pattern discovery (§4.2 layer 2) needs
   *something* to execute searches against. Needs an explicit decision
   (self-hosted SearX instance vs. a rate-limited scrape vs. a small paid
   API budget) before Phase 4/7 — flagging rather than silently assuming.
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
