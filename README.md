# LinkIntel (working name)

An evidence-backed SEO backlink intelligence, link prospecting, contact
intelligence, and outreach platform — built on our own crawl and
discovery infrastructure instead of a paid backlink index.

This repository is currently at **Phase 0: architecture**. Start here:

1. [`PRODUCT_SPEC.md`](./PRODUCT_SPEC.md) — what we're building, why, and
   the non-negotiable engineering principles (no fake data, provenance on
   every fact, evidence on every recommendation).
2. [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) — system design, repo
   layout, service boundaries, development phases and exit criteria, and
   the technical risks flagged for review before Phase 1 begins.
3. [`docs/DATABASE.md`](./docs/DATABASE.md) — schema design.
4. [`docs/API.md`](./docs/API.md) — REST surface.
5. [`docs/CRAWLER.md`](./docs/CRAWLER.md) — crawl engine mechanics
   (HTTP-first with a Playwright fallback, politeness rules, backlink
   verification pipeline).

## Stack (free-first — see `ARCHITECTURE.md` for the full rationale)

Next.js · FastAPI · PostgreSQL (+ pgvector) · Redis · Crawlee
(HTTP + Playwright) · Common Crawl (public index) · Ollama (local AI,
default provider) · Docker.

## Status

**Phase 0 (architecture) through Phase 5 (competitor engine / link gap)
are done.** A working, tested, two-tier crawler (Crawlee HTTP-first with
a Playwright fallback) that extracts page metadata, schema.org/
OpenGraph/Twitter Cards, images, PDF/social links, embeds, and candidate
contact info; a direct backlink verification pipeline (crawl a claimed
source page for real, confirm the link is actually there, record anchor/
rel/context with first/last-seen history); a Common Crawl connector that
turns a seed domain's Common-Crawl-captured pages into verification
candidates; and a competitor/link-gap engine (which domains link to a
tracked competitor but not yet to you, with a transparent overlap-based
confidence tier) — see [`backend/README.md`](./backend/README.md) for
what's implemented, how to run it, and known follow-ups (including one
honest caveat: Common Crawl's own servers aren't reachable from this
particular build sandbox, so that one connector is tested against
realistic fixtures rather than the live service — needs a live smoke
test before production use). 64 tests pass, nearly all against real
infrastructure (a real fixture HTTP server that can simulate multiple
distinct domains, a real Postgres database, real live crawls and
backlink verification against a real public site, with rows inspected
directly in Postgres). Building this phase also surfaced and fixed a
genuine Crawlee bug (cross-run request-queue state leaking between
separate crawl jobs in the same process — see `docs/ARCHITECTURE.md`
risk #15). Everything past this (search-pattern discovery, prospect/
contact engines, API, frontend) is still empty pending its own phase,
per the build order in `PRODUCT_SPEC.md` §9 — no premature scaffolding
ahead of working code underneath it.

```
docker compose -f docker/docker-compose.yml up   # Postgres + Redis + Ollama
cd backend && pip install -e ".[dev]" && pytest app/tests -v
```
