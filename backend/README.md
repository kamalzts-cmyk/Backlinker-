# backend

FastAPI project. **Phases 1-6 and 8-12 (real crawler, full page/link
extraction, backlink verification, Common Crawl connector,
competitor/link-gap engine, a real API layer, contact intelligence,
email verification, guest-post intelligence, opportunity scoring, and
evidence-on-every-opportunity) are implemented and tested** — see `app/crawler/`,
`app/engines/backlink/`, `app/engines/competitor/`,
`app/engines/contact/`, `app/engines/guest_post/`,
`app/engines/scoring/`, and `app/api/`. Run it with `uvicorn
app.main:app --reload`. Phase 7 (search-pattern prospect discovery) is skipped for
now — it needs a search-backend decision (paid API vs. self-hosted vs.
scraping) that hasn't been made; see the note in `../docs/ARCHITECTURE.md`
risk #3. The rest of the intelligence engines and the frontend are still
empty pending their own phases (`../PRODUCT_SPEC.md` §9,
`../docs/ARCHITECTURE.md` §9) — no premature scaffolding ahead of working
code underneath it.

**Phase 4 caveat:** Common Crawl's own servers are unreachable from this
build sandbox (policy-denied at the network layer, not a bug — see
`../docs/ARCHITECTURE.md` risk #14) so that one connector is tested
against realistic fixtures rather than the live service. Run a live smoke
test before depending on it in production.

## What's here

- `app/crawler/` — the two-tier crawler (Crawlee `BeautifulSoupCrawler` by
  default, `PlaywrightCrawler` only when `app/crawler/js_detection.py`'s
  heuristic says the HTML needs JS rendering), robots.txt + sitemap
  discovery, URL/domain normalization, page fingerprinting, and
  extractors (`app/crawler/extractors/`) for page metadata, links,
  structured metadata (schema.org/OpenGraph/Twitter Cards/images/PDF and
  social links/embeds), and candidate contact emails/phones. See
  `../docs/CRAWLER.md` for the design.
- `app/engines/backlink/` — the direct backlink verification pipeline:
  given a `BacklinkCandidate` (source_url claiming to link to target_url),
  crawl source_url for real (reusing the Phase 1/2 crawler -- verifying a
  candidate is just a single-page crawl) and check whether the target
  link is actually there, producing a `VERIFIED` or `REJECTED`
  `BacklinkObservation` plus a derived current-state `backlinks` row with
  first/last-seen. See `../docs/CRAWLER.md` §6.
- `app/engines/backlink/common_crawl.py` — the Common Crawl connector:
  queries the CDX index for a seed domain's captured pages, Range-fetches
  each one's raw WARC content directly from Common Crawl's data server
  (no live crawl needed just to check it), and reuses the Phase 2 link
  extractor to check for a link to the target, producing
  `BacklinkCandidate` rows for Phase 3 to verify. See its module
  docstring for exactly what Common Crawl's public CDX API can and can't
  answer.
- `app/engines/competitor/` — competitor relationship tracking and link
  gap computation. No `projects` concept exists yet, so a competitor
  relationship is just "domain A treats domain B as a competitor" keyed
  directly on `domains`. `compute_link_gap()` is a pure query over
  existing `backlinks` rows — "crawling a competitor" is just Phase 3/4
  discovery/verification run with the competitor's domain as the
  verification target; no new crawl mechanism here. See
  `PRODUCT_SPEC.md` §4.3/§13-14.
- `app/engines/contact/` — contact discovery. Reuses the Phase 1/2
  crawler; classifies contact-relevant pages by URL path and turns
  page-level `contact_emails`/`contact_phones`/`schema_org` into `Contact`
  rows with full provenance (`ContactSource`). Never guesses a name/email
  pairing beyond schema.org `Person` markup or an unambiguous
  single-person page. See `PRODUCT_SPEC.md` §4.6.
- `app/engines/contact/verify_email.py` — email verification: syntax,
  DNS/MX (with the RFC 5321 A-record fallback), and a disposable-domain
  list. Deliberately does not attempt SMTP-level mailbox/catch-all
  probing (would need outbound port 25, blocked here) or send any
  verification email, per `PRODUCT_SPEC.md` §13. Ceiling is `LIKELY`,
  never `VERIFIED`/`CATCH_ALL` — see the module docstring.
- `app/engines/guest_post/detect.py` — guest-post guideline analysis
  (word-count range, dofollow/nofollow/sponsored/author-bio mentions,
  editor email, closed-submissions detection) plus a transparent
  probability score that factors in distinct authors already observed on
  the domain (a proxy signal, explicitly labeled as such — see the
  module docstring). Also where `pages.body_text` earns its keep: full
  visible page text, added in this phase after noticing `../docs/DATABASE.md`
  had documented it for full-text search but Phase 2 never actually added
  the column.
- `app/engines/scoring/opportunity.py` — opportunity scoring. Smaller,
  honestly-scoped component set than `PRODUCT_SPEC.md` §8's named list
  (see `OpportunityScore`'s model docstring) — every component is either
  `measured` from real data or explicitly `unavailable`, never guessed.
  Organic traffic is *always* unavailable (no data source integrated).
- `app/api/` + `app/main.py` — the FastAPI layer. Domain-centric routes
  (`/domains`, `/crawl`, `/backlinks`, `/competitors`, `/link-gaps`) since
  there's no `projects`/auth layer yet; sync SQLAlchemy sessions via
  `app/api/deps.py` (FastAPI runs sync route functions in a threadpool).
  Errors follow `../docs/API.md`'s `{"error": {"code","message","detail"}}`
  shape (`app/api/errors.py`).
- `app/db/models.py` — the crawl-layer schema (domains, crawl_jobs,
  crawl_requests, crawl_errors, pages, page_links), the backlink engine
  schema (backlink_candidates, backlink_observations, backlinks), the
  competitor/link-gap schema (competitor_relationships,
  link_gap_opportunities), and the contact schema (contacts,
  contact_sources). See `../docs/DATABASE.md`.
- `alembic/` — migrations; `alembic upgrade head` against a real Postgres
  database (matching `docker/.env.example` / `.env.example`).
- `app/tests/` — 105 tests, all real except the Common Crawl HTTP layer
  (see the Phase 4 caveat above): unit tests for normalization/
  fingerprinting/JS-detection/extraction/classification/CDX-parsing
  against local HTML fixtures (`app/tests/fixtures/html/`), and
  integration tests that run the actual crawler, backlink verification,
  competitor/link-gap, and API pipelines against a local fixture HTTP
  server (`app/tests/fixtures/server.py`, which can bind multiple
  loopback addresses to simulate genuinely distinct source domains) and a
  real Postgres test database — no mocked HTTP, no mocked DB, anywhere
  except the Common Crawl connector's own external calls.

## Running it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env   # point at your local Postgres/Redis

# Create both databases first (see .env.example) then:
alembic upgrade head

pytest app/tests -v
ruff check app
```

Ad hoc live crawl:

```python
import asyncio
from app.crawler.run import run_crawl

asyncio.run(run_crawl("https://example.com", max_pages=10))
```

## Known follow-ups (intentionally out of Phase 1 scope)

- `app/crawler/normalize.py` only strips a leading `www.` — full
  public-suffix-list registrable-domain resolution is deferred (see the
  docstring and `../docs/ARCHITECTURE.md` risk #8), fine for crawling
  one's own site, revisit before Phase 5 (competitors).
- Page-level extraction now covers title, meta description, canonical,
  headings, word count, language, robots meta, schema.org (JSON-LD only
  — no microdata/RDFa yet), OpenGraph, Twitter Cards, images+alt, PDF
  links, social profile links, embeds, and candidate contact emails/
  phones (regex-based; deliberately does not attempt to de-obfuscate
  addresses — see `app/crawler/extractors/contact.py`). Structured
  entity extraction (Organization/Person/Product/Service/Location as
  first-class records, not just raw schema.org JSON) is AI-assisted per
  `PRODUCT_SPEC.md` §4.1 and belongs to Phase 13.
- `CrawlErrorReason.BLOCKED_ROBOTS` / `BLOCKED_CAPTCHA` are modeled but
  not yet populated by a real detector — Crawlee's `respect_robots_txt_file`
  currently skips disallowed URLs without surfacing a classified error
  back to us; a `blocked_page.html` fixture exists for when that detector
  is built.
- Crawlee's default HTTP client (`impit`) does not reliably honor
  environment-based egress-proxy configuration; `app/crawler/http_crawler.py`
  uses Crawlee's `HttpxHttpClient` instead. Keep that if you touch this
  file — see `../docs/ARCHITECTURE.md` risk #11.
- Backlink discovery (Common Crawl + search-pattern candidates feeding
  `BacklinkCandidate` rows) is Phase 4/7, not built yet — Phase 3 only
  implements verification given a candidate. `classify_link_type`
  (`app/engines/backlink/classify.py`) only labels NAVIGATION/FOOTER/
  SPONSORED/UGC deterministically; the fuller taxonomy (guest_post,
  directory, citation, ...) needs content judgment and is Phase 12 AI
  work, not guessed here.
- If you add a new table that reuses an existing named Postgres enum
  type (e.g. another `link_position` column), autogenerate's migration
  needs a hand-edit — see `../docs/ARCHITECTURE.md` risk #13 and
  `alembic/versions/4d4f7236ee73_*.py` for the pattern.
- The Common Crawl connector needs a *seed domain* to check (a
  competitor, a known publisher, etc.) — it does not discover "every
  site on the web that might link to X" by itself (that reverse-index
  query isn't available through the free CDX API; see the module
  docstring). It's one candidate source among several; search-pattern
  discovery (Phase 7) is the other free one from `PRODUCT_SPEC.md` §4.2
  Layer 2, not built yet. Run a live smoke test against the real Common
  Crawl service before depending on this in production — see
  `../docs/ARCHITECTURE.md` risk #14.
- If you build a Crawlee crawler directly instead of going through
  `build_http_crawler`/`build_playwright_crawler`, give it its own
  uniquely-named `RequestQueue` — see `../docs/ARCHITECTURE.md` risk
  #15 for why a fresh `MemoryStorageClient()` alone isn't sufficient.
- No `/opportunities` or `/prospects` API endpoints yet (`/contacts`
  exists as of Phase 9: `GET /contacts?domain_id=`, `POST
  /contacts/{id}/verify-email`). `/link-gaps` is the only
  "opportunity"-shaped view so far, and it's the raw competitor-overlap
  signal, not a scored opportunity.
- Contact name/role pairing only handles two safe, unambiguous cases
  (schema.org `Person`, single-person pages) by design — a page with
  multiple people and no structured markup yields correctly-unattributed
  email/phone contacts rather than a guessed pairing. Real name
  extraction for multi-person pages (e.g. via NLP or an AI pass) is
  future work, not something to bolt on as a fragile heuristic.
- Email *verification* (syntax/DNS/MX/catch-all/SMTP -- Phase 9) doesn't
  exist yet. Every contact's `verification_status` here is only ever
  `DIRECTLY_PUBLISHED`, `ROLE_ADDRESS`, or `UNKNOWN` -- `VERIFIED`/
  `CATCH_ALL`/`INVALID`/`LIKELY`/`PATTERN_INFERRED` are modeled but
  unused until then.
- Link-gap opportunities are keyed on `competitor_overlap_count` and a
  simple deterministic confidence tier (1→LOW, 2→MEDIUM, 3+→HIGH) — this
  is not the full weighted Opportunity Score from `PRODUCT_SPEC.md` §4.5
  (relevance/authority/traffic/editorial-quality/etc.), which is Phase
  11. Don't present these tiers to a user as if they were the final
  score.
