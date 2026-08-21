# frontend

Next.js (App Router) application, done — a real client of the backend
API described in `../backend/README.md`, adapted to that API's *actual*
domain-centric route surface rather than the aspirational per-module
route list `../docs/ARCHITECTURE.md` originally sketched (no
`projects`/auth layer exists on the backend yet).

## Architecture

Every backend call runs **server-side**:

- Reads happen in `async` Server Components via `fetch` (`lib/api.ts`),
  always `cache: "no-store"` — every resource here can change from
  someone else's action, so nothing here is ever served stale.
- Writes happen in Server Actions (`app/actions.ts`, `'use server'`),
  which call the backend then `revalidatePath()` the page that called
  them. Plain `<form action={...}>` submissions, no client-side state
  management.
- The one exception is report downloads: `app/reports/download/route.ts`
  is a Route Handler that proxies bytes/headers straight through from
  `GET /reports/{type}` on the backend, since a Server Action can't hand
  the browser a file to save.

Because the browser never talks to the backend directly, the backend
needs **no CORS configuration** and `API_URL` (`.env.local` /
`.env.local.example`) never reaches the client bundle. The trade-off:
every mutation is a full server round-trip, not an optimistic client
update — acceptable for a single-operator internal tool with no
realtime requirement.

`lib/types.ts` mirrors `../backend/app/api/schemas.py` field-for-field.
When the backend's response shape changes, this file changes with it;
it isn't an independent contract that can drift.

## What's here

- `/` — register a domain, search/list every domain this project has
  ever touched (`GET /domains`, added specifically for this page —
  no list endpoint existed before the frontend needed one).
- `/domains/[id]` — the hub. Run a crawl; see backlinks pointing at this
  domain; run search-pattern backlink discovery and verify the resulting
  candidates inline; discover contacts and verify their email; check for a
  guest-post program; the opportunity score (recomputed on every view,
  matching the backend's own "cheap to recompute" design); track
  competitors and see link-gap opportunities; generate an outreach
  strategy per contact and start a campaign from it; log AI-search/GEO
  citation observations manually, or check one automatically via
  `POST /geo/check`. Backend endpoints
  (`POST /contacts/discover`, `POST /guest-posts/discover`,
  `POST /backlinks/discover-search`, `GET /backlinks/candidates`,
  `POST /backlinks/candidates/{id}/verify`, `POST /geo/check`) were
  added alongside this page for the same reason as `GET /domains` — the
  engines existed, nothing exposed them over the API yet.
- `/prospects` — independent, topic-keyed prospect discovery (Phase 7):
  a search form (`POST /prospects/discover`) and a results list
  (`GET /prospects?topic=`) showing each discovered domain's category,
  crude keyword-overlap fit score, source URL, and evidence. Not
  domain-scoped like the rest of the app — it doesn't need an existing
  tracked domain to run.
- `/crawl/[jobId]` — a crawl job's status, page/error counts.
- `/backlinks/[id]` — observation history plus the Phase 16 monitor: a
  "Recheck now" button that re-verifies the link for real and shows
  whatever changed (or didn't).
- `/campaigns/[id]` — funnel history and a form to record a real-world
  event (sent/opened/replied/...). No send button exists anywhere in
  this app, on the frontend or the backend — recording an event only
  ever logs what a human says already happened. `GET /campaigns` grew a
  `?contact_id=` filter for this page's use on `/domains/[id]`.
- `/reports` — pick a report type, format, and filter IDs; downloads a
  real CSV/JSON/XLSX/PDF via the backend's Phase 17 export layer.
- `/login` — a single shared-password gate for public deployments
  (`proxy.ts` redirects every other route here when `APP_SHARED_SECRET`
  is set and no valid session cookie is present; a no-op in local dev,
  where it's unset). Not a real multi-user auth system -- see
  `../docs/DEPLOYMENT.md`. The header's "Log out" button only appears
  once actually authenticated.

## Running it

```bash
npm install
cp .env.local.example .env.local   # API_URL, defaults to http://localhost:8000
npm run dev
```

Needs the backend running (`cd ../backend && uvicorn app.main:app --reload`)
against a migrated Postgres database. `APP_SHARED_SECRET` is unset by
default (no login gate, matching the backend's own default) -- see
`../docs/DEPLOYMENT.md` to put this behind a shared password for a
public deployment.

Verified with a real backend and a real Postgres database (not just a
build check): registered a domain, ran a live crawl against pypi.org,
discovered real contacts and a guest-post opportunity against this
project's own test fixtures served over a local HTTP server, watched a
real opportunity score compute from that crawl's actual page data,
generated a real outreach strategy, started a campaign and recorded a
funnel event, rechecked a real backlink and watched its observation
history grow, and downloaded a real CSV report — all through the
browser, via Playwright, screenshotted at each step. `npm run build`,
`npx tsc --noEmit`, and `npx eslint .` are all clean.

## Known follow-ups

- No test suite of its own yet (no Playwright/Vitest config committed) —
  correctness was verified manually against a live backend for this
  pass rather than with an automated frontend test suite (the
  shared-password login gate was verified end-to-end with a scripted
  Playwright run: wrong password rejected, correct password sets the
  session cookie and unlocks every route, logout revokes it). The
  backend's 178 tests are what actually prove the data this UI displays
  is real.
- Report downloads accept raw domain-ID text inputs on `/reports`
  rather than a domain picker — there's no cross-engine domain search
  UI yet, just the dashboard's list/search.
- No pagination on `GET /domains` — fine at the scale a single-operator
  tool accumulates; would need one before this scales past a few
  hundred domains.
