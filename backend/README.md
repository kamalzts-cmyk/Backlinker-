# backend

FastAPI project. **Phase 1 (real crawler) and Phase 2 (full page/link
extraction) are implemented and tested** — see `app/crawler/`. The API
layer (`app/api/`), the intelligence engines (`app/engines/`), and
everything past the crawl layer are still empty pending their own phases
(`../PRODUCT_SPEC.md` §9, `../docs/ARCHITECTURE.md` §9) — no premature
scaffolding ahead of working code underneath it.

## What's here

- `app/crawler/` — the two-tier crawler (Crawlee `BeautifulSoupCrawler` by
  default, `PlaywrightCrawler` only when `app/crawler/js_detection.py`'s
  heuristic says the HTML needs JS rendering), robots.txt + sitemap
  discovery, URL/domain normalization, page fingerprinting, and
  extractors (`app/crawler/extractors/`) for page metadata, links,
  structured metadata (schema.org/OpenGraph/Twitter Cards/images/PDF and
  social links/embeds), and candidate contact emails/phones. See
  `../docs/CRAWLER.md` for the design.
- `app/db/models.py` — the crawl-layer schema (domains, crawl_jobs,
  crawl_requests, crawl_errors, pages, page_links). See
  `../docs/DATABASE.md`.
- `alembic/` — migrations; `alembic upgrade head` against a real Postgres
  database (matching `docker/.env.example` / `.env.example`).
- `app/tests/` — 42 tests, all real: unit tests for normalization/
  fingerprinting/JS-detection/extraction against local HTML fixtures
  (`app/tests/fixtures/html/`), and integration tests that run the actual
  crawler against a local fixture HTTP server (`app/tests/fixtures/server.py`)
  and a real Postgres test database — no mocked HTTP, no mocked DB.

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
