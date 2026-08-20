# LinkIntel (working name)

An evidence-backed SEO backlink intelligence, link prospecting, contact
intelligence, and outreach platform — built on our own crawl and
discovery infrastructure instead of a paid backlink index.

Read the architecture first, then the code — start here:

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

**Phases 0-6 and 8-10 are done** (Phase 7 is intentionally skipped —
see below). What exists and is tested, end to end, against real
infrastructure:

- A two-tier crawler (Crawlee HTTP-first, Playwright fallback) extracting
  page metadata, schema.org/OpenGraph/Twitter Cards, images, PDF/social
  links, embeds, and candidate contact info.
- Direct backlink verification: crawl a claimed source page for real,
  confirm the link is actually there, record anchor/rel/context with
  first/last-seen history.
- A Common Crawl connector turning a seed domain's captured pages into
  verification candidates.
- A competitor/link-gap engine: which domains link to a tracked
  competitor but not yet to you, with a transparent overlap-based
  confidence tier.
- Contact intelligence: crawl a domain's about/contact/team/author/
  guest-post pages and turn what they plainly contain into full,
  uncapped contact records with provenance — never guessing a name/email
  pairing beyond schema.org markup or an unambiguous single-person page.
- A domain-centric FastAPI layer (`/domains`, `/crawl`, `/backlinks`,
  `/competitors`, `/link-gaps`, `/contacts`, `/guest-posts`) — no
  `projects`/auth layer exists yet.
- Email verification: syntax, DNS/MX, and disposable-domain checks,
  genuinely proven against live DNS (no mocking needed — unlike HTTPS,
  DNS resolution isn't restricted here). SMTP-level mailbox/catch-all
  probing is explicitly out of scope: outbound port 25 is blocked in
  this sandbox, and the product spec is independently skeptical of it —
  we never send a verification email.
- Guest-post intelligence: finds and analyzes a domain's guideline page
  (word-count range, dofollow/nofollow/sponsored/author-bio mentions,
  editor contact, closed-submissions detection) and produces a
  transparent probability score that factors in how many distinct
  authors have already been observed on the domain — labeled a proxy
  signal, not confirmed guest authorship.

100 tests pass, almost all against real infrastructure (a real fixture
HTTP server that can simulate multiple distinct domains, a real Postgres
database, real live crawls/verification/contact-discovery/DNS lookups
against real public sites/domains). Two honest caveats, not glossed
over: Common Crawl's own
servers aren't reachable from this particular build sandbox, so that one
connector is tested against realistic fixtures rather than the live
service (needs a live smoke test before production use); and **Phase 7
(search-pattern prospect discovery) is skipped** because it needs a
search-backend decision — paid API, self-hosted SearX, or scraping —
that hasn't been made. Building this also surfaced and fixed a genuine
Crawlee bug (cross-run request-queue state leaking between separate
crawl jobs in the same process — see `docs/ARCHITECTURE.md` risk #15).

See [`backend/README.md`](./backend/README.md) for exactly what's
implemented, how to run it, and the full list of known follow-ups.
Everything past this (prospect discovery, email verification, guest-post
intelligence, scoring, AI layer, outreach, campaigns, monitoring,
reports, GEO intelligence, frontend) is still empty pending its own
phase, per the build order in `PRODUCT_SPEC.md` §9 — no premature
scaffolding ahead of working code underneath it.

```
docker compose -f docker/docker-compose.yml up   # Postgres + Redis + Ollama
cd backend && pip install -e ".[dev]" && pytest app/tests -v
```
