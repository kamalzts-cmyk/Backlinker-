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

**Phase 0 (architecture) and Phase 1 (real crawler) are done.** Phase 1
is a working, tested, two-tier crawler (Crawlee HTTP-first with a
Playwright fallback) — see [`backend/README.md`](./backend/README.md) for
what's implemented, how to run it, and known follow-ups. 27 tests pass,
including real integration tests against a local fixture server and a
real Postgres database (no mocks), plus a manually-verified live crawl of
a real public site. Everything past the crawl layer (API, intelligence
engines, frontend) is still empty pending its own phase, per the build
order in `PRODUCT_SPEC.md` §9 — no premature scaffolding ahead of working
code underneath it.

```
docker compose -f docker/docker-compose.yml up   # Postgres + Redis + Ollama
cd backend && pip install -e ".[dev]" && pytest app/tests -v
```
