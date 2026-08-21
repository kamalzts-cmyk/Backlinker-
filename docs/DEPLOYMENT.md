# Deployment (free-tier)

How to put LinkIntel on the public internet for $0/month, so anyone with
the shared password can use it from a browser -- no local setup needed.

This is optional. Everything in `backend/README.md` and
`frontend/README.md` about running it locally still applies; this doc is
only for making that a public URL instead of `localhost`.

## What actually needs hosting

Only three things:

- **Postgres** -- the one real dependency. [Neon](https://neon.tech) has a
  free tier with no expiry (unlike some providers' 90-day-then-deleted
  free databases).
- **The FastAPI backend** -- [Render](https://render.com)'s free web
  service tier.
- **The Next.js frontend** -- [Vercel](https://vercel.com)'s free Hobby
  tier (it's what Next.js's own App Router/Server Actions are built
  around, so it's the path of least friction).

**Not needed:** Redis (config exists but nothing in this codebase
actually uses it yet -- no queue infrastructure is built, see
`docs/ARCHITECTURE.md` §9) and Ollama (an *optional* AI provider for one
outreach-angle-synthesis step; unset, `angle` just stays `None` instead
of AI-generated -- nothing breaks). Skip both.

**Free-tier tradeoffs, stated up front:** Render's free web service spins
down after ~15 minutes idle, so the first request after a quiet period
takes 30-60s to wake back up -- normal, not broken. Neon's free tier caps
storage (generous for a single-operator tool). Vercel's free tier is
built for exactly this kind of app.

## Before you start: the security gate

**This app has no login/multi-user system by design** (see
`docs/ARCHITECTURE.md` §9 -- there's no `projects`/auth layer). Deployed
as-is, anyone who finds the URL could run the crawler against arbitrary
sites, harvest the contacts it finds, and (if you set an Anthropic key)
spend against it. `SharedSecretMiddleware`
(`backend/app/api/auth_gate.py`) and the frontend's `proxy.ts` close
that gap with one shared password -- not real per-user auth, just a
lock on the front door. **Set `APP_SHARED_SECRET` in both places below
before sharing the URL with anyone.**

## Step 1 -- Neon (Postgres)

1. Sign up at [neon.tech](https://neon.tech) (free, no card required).
2. Create a project. Note the connection string it gives you --
   it looks like:
   ```
   postgresql://<user>:<password>@<host>.neon.tech/<dbname>?sslmode=require
   ```
3. That's it for now -- migrations run automatically as part of the
   Render deploy in Step 2.

`app/core/config.py`'s `database_url` property accepts this directly via
a `DATABASE_URL` env var (added specifically for this): it normalizes
the `postgresql://` scheme to the `postgresql+psycopg://` driver this
project's SQLAlchemy setup needs, `sslmode=require` and all. You don't
need to split it into the individual `POSTGRES_*` vars.

## Step 2 -- Render (backend)

1. Sign up at [render.com](https://render.com) (free, connects to
   GitHub).
2. **New > Web Service**, connect the `kamalzts-cmyk/Backlinker-` repo,
   branch `claude/six-engine-architecture-i1wnok` (or wherever this
   landed after merge).
3. Root directory: `backend`. Environment: **Python 3**.
4. Build command:
   ```
   pip install -e ".[dev]"
   ```
   (Playwright's Chromium browser is *not* installed by this build
   command on purpose -- see the caveat below. The HTTP-first crawler,
   which is most of what this app does, doesn't need it.)
5. Start command:
   ```
   alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```
   (Running migrations before the server starts means every deploy
   self-migrates -- no separate manual step.)
6. Environment variables:
   | Key | Value |
   |---|---|
   | `DATABASE_URL` | the Neon connection string from Step 1 |
   | `APP_SHARED_SECRET` | a random string, e.g. `openssl rand -hex 24` |
   | `ANTHROPIC_API_KEY` | *(optional)* enables search-pattern discovery, prospect discovery, GEO citation checks |
   | `CRAWLER_USER_AGENT` | *(optional, recommended)* identify your deployment, e.g. `LinkIntelBot/0.1 (+https://yoursite.example)` |
7. Deploy. Note the public URL Render gives you
   (`https://<something>.onrender.com`) -- the frontend needs it next.

**Playwright caveat:** without `playwright install --with-deps chromium`
in the build step, JS-escalation crawls (pages the HTTP-first crawler's
`js_detection.py` heuristic flags as needing real rendering) fail for
just that one page, not the whole app -- `build_playwright_crawler` is
only invoked when a crawl actually needs it (see `app/crawler/`). Add
that install command to the build step if you need JS-rendered crawling
and your Render plan has the disk/build-minutes budget for a
~300MB browser download; the free tier may not.

## Step 3 -- Vercel (frontend)

1. Sign up at [vercel.com](https://vercel.com) (free Hobby tier,
   connects to GitHub).
2. **Add New > Project**, import the same repo.
3. Root directory: `frontend`. Framework preset: Next.js (auto-detected).
4. Environment variables:
   | Key | Value |
   |---|---|
   | `API_URL` | the Render URL from Step 2 |
   | `APP_SHARED_SECRET` | the **same** value as the backend's |
5. Deploy. Vercel gives you the public URL -- this is the one you share.

Both `API_URL` and `APP_SHARED_SECRET` are server-only (no `NEXT_PUBLIC_`
prefix, see `frontend/lib/api.ts`), so neither the backend's location
nor the password ever reaches the browser bundle.

## After deploying

Visit the Vercel URL, enter the shared password, and use the app exactly
as described in `frontend/README.md`. Log out via the header button
whenever you want to require the password again on that browser.

To rotate the password: change `APP_SHARED_SECRET` in both Render and
Vercel to a new value and redeploy both -- old sessions (cookie holds a
hash of the old secret) stop working immediately.

## Doing this without touching either dashboard

If you'd rather hand Claude API tokens for Render/Vercel/Neon (each
platform's dashboard has a place to generate one) than click through
the UI yourself, paste them into the conversation and Claude can drive
the actual service creation and deploys via each platform's CLI/API
directly from the terminal -- you'd still need to create the free
accounts yourself first (that step can't be automated), but everything
after that can be.
