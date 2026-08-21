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

**All backend phases (0-18) are done, and the Next.js frontend is now
a real client of that API.** What exists and is tested, end to end, against real
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
  `/competitors`, `/link-gaps`, `/prospects`, `/contacts`, `/guest-posts`,
  `/geo`) — no `projects`/auth layer exists yet.
- Search-pattern backlink discovery and independent prospect discovery:
  both run named query patterns against Claude's own web-search tool
  (`AnthropicSearchProvider`) — one produces URL-level backlink
  candidates from a brand query that feed straight into the existing
  verification pipeline, the other produces domain-level prospects from
  a bare topic (resource pages, roundups, guest-post blogs, industry
  publications) with a crude, clearly-labeled keyword-overlap fit score.
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

- Opportunity scoring: a composite score built only from components this
  project actually measured (indexability, content depth,
  contactability, link probability, crude keyword-overlap topical
  relevance), each one labeled `measured` or `unavailable` — organic
  traffic is always `unavailable` rather than a guessed number.
- An AI provider layer (`AIProvider` interface + `OllamaProvider`), built
  against Ollama's real documented structured-output API — schema
  validated, raises rather than returns a fabricated/partial result on
  any failure.
- Outreach strategy generation: for a given contact, deterministically
  picks an opportunity type (guest-post opportunity, link-gap
  opportunity, or generic direct outreach) and computes its reason,
  evidence, expected link probability, and difficulty from data this
  project already verified — the AI only synthesizes a short "angle"
  from that evidence, explicitly barred from inventing facts, and is
  left blank rather than fabricated when unavailable. No copy drafting
  or automated sending is built — the product spec is explicit that v1
  stops at a human-reviewed strategy.
- Campaign funnel tracking: a human records that they've pitched a
  contact (through their own email client — there is no send-email
  function anywhere in this codebase) and logs each real funnel-stage
  transition as it happens (sent, delivered, bounced, opened, clicked,
  replied, positive/negative reply, unsubscribed, published). The one
  automatic step checks the real verified-backlinks table for a match
  and advances the funnel only when it finds one — never fabricated
  progress.
- Backlink monitoring: re-verifies a tracked backlink for real and diffs
  the result against its last known state, producing explicit
  before/after alerts for exactly what changed (link attributes, anchor
  text, source status, canonical URL) — never a bare "something
  changed." A link that's gone is marked lost rather than silently kept.
- Reports/exports: CSV, JSON, XLSX, and PDF exports for backlinks,
  link-gap opportunities, contacts, guest-post opportunities, and
  opportunity scores — every value traces back to a row an earlier
  engine already collected and verified; the export layer adds no new
  computation, and each file format is a real one its own
  library/reader can open, not a stub with the right extension.
- AI-search/GEO intelligence: an append-only log of
  `{query, engine, timestamp, observed_result, source_url}`
  observations behind every citation claim, never asserted bare. A
  human can log what they saw checking a real answer engine themselves
  (no API needed), and the automated path's citation matching is
  deterministic (does a returned URL resolve to the domain being
  checked?) — now backed by a real, concrete `AnthropicSearchProvider`
  (the same one powering search-pattern/prospect discovery above),
  which resolves that gap by using Claude's own web-search tool instead
  of guessing at a paid third-party API's wire format.
- A Next.js frontend (App Router, Server Components + Server Actions,
  no client-side API calls, so the backend needs no CORS config) covers
  the full flow through the browser: register a domain, run a crawl,
  discover contacts and verify email, check for a guest-post program,
  view the opportunity score, track competitors and see link gaps,
  generate an outreach strategy and start a campaign, log GEO citation
  observations, recheck a backlink, and download a real report. Verified
  against a live backend via Playwright, not just a build check — see
  `frontend/README.md`.

175 tests pass, almost all against real infrastructure (a real fixture
HTTP server that can simulate multiple distinct domains, a real Postgres
database, real live crawls/verification/contact-discovery/DNS lookups
against real public sites/domains). Three honest caveats, not glossed
over: Common Crawl's own servers and Ollama itself aren't reachable
from this particular build sandbox, so those two integrations are tested
against realistic fixtures / mocked HTTP shaped exactly like the real
documented APIs rather than the live services (both need a live smoke
test before production use — see `docs/ARCHITECTURE.md` risks #14 and
#17); and `AnthropicSearchProvider` (search-pattern discovery, prospect
discovery, and automated GEO citation checking) is likewise tested
against the real Anthropic SDK's HTTP calls intercepted by `respx`,
proven correct against a request/response shape independently
confirmed via a live fetch of the current API reference — not against a
live API key, since this sandbox can't reach the internet directly
either. Run a live smoke test with a real `ANTHROPIC_API_KEY` before
depending on it in production — see `docs/ARCHITECTURE.md` risk #19.
Building this also surfaced and fixed a genuine Crawlee bug
(cross-run request-queue state leaking between separate crawl jobs in
the same process — see `docs/ARCHITECTURE.md` risk #15).

See [`backend/README.md`](./backend/README.md) and
[`frontend/README.md`](./frontend/README.md) for exactly what's
implemented, how to run each half, and the full list of known
follow-ups. Every phase in the build order in `PRODUCT_SPEC.md` §9 is
now built — no premature scaffolding ahead of working code underneath
it.

```
docker compose -f docker/docker-compose.yml up   # Postgres + Redis + Ollama
cd backend && pip install -e ".[dev]" && pytest app/tests -v
```
