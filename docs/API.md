# API Design

REST, API-first (the Next.js frontend is one client among possible future
clients). FastAPI generates OpenAPI automatically from the Pydantic models
described here — this document defines the resource surface and response
conventions, not exhaustive schemas.

## Conventions

- All list endpoints support pagination (`?page=`, `?page_size=`, capped
  max page size), filtering, and sorting. Standard filters available on
  every relevant resource: relevance/authority/traffic ranges, link type,
  follow/nofollow, contact availability, guest-post accepted, industry/
  topic, score range, spam-risk range, `first_seen`/`last_verified` date
  ranges, country/language.
- Every response object that carries a scored or discovered fact embeds
  its **provenance envelope** (`source_url, source_type, discovery_method,
  discovered_at, last_verified_at, verification_status, confidence_score`)
  inline — never as a separate round-trip the client has to make.
- Scored objects (`link_opportunities`, `prospect_scores`,
  `guest_post_opportunities`) embed an `evidence: []` array by default (or
  behind `?include=evidence` if payload size becomes a concern) rather
  than requiring a second call for the common case of "why?".
- Errors follow a single shape: `{ "error": { "code", "message", "detail" } }`.
- Auth: bearer token (JWT) issued at login; RBAC role checked per route.
- Rate limiting applied per user/token, not just per IP, since outreach-
  sending endpoints in particular must be throttled.

## Resource surface

### Auth / users
`POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`,
`GET /users/me`

### Projects
`POST /projects` · `GET /projects` · `GET /projects/{id}` ·
`PATCH /projects/{id}` (includes score-weight configuration) ·
`DELETE /projects/{id}`

### Crawl
`POST /projects/{id}/crawl` (body: scope — own site / a specific
prospect / competitor; schedule — one-time/daily/weekly/monthly) ·
`GET /crawl/{job_id}` (status, pages crawled, errors) ·
`GET /crawl/{job_id}/pages` · `GET /crawl/{job_id}/errors`

### Backlinks
`GET /backlinks` (filterable by project, link type, follow/nofollow,
first/last seen) · `GET /backlinks/{id}` (includes full
`backlink_observations` history) · `GET /backlinks/{id}/history` ·
`GET /backlinks/lost` · `GET /backlinks/changed`

### Competitors / link gap
`POST /competitors` · `GET /competitors?project_id=` ·
`DELETE /competitors/{id}` · `GET /link-gaps?project_id=` (returns
`link_gap_opportunities` with competitor-overlap evidence)

### Prospects
`GET /prospects?project_id=` · `GET /prospects/{id}` (full score
breakdown + evidence + contacts + guest-post status in one payload, since
this backs the prospect detail page) · `POST /prospects/{id}/rescore`

### Opportunities
`GET /opportunities?project_id=` (the primary ranked list —
`link_opportunities` joined to latest score) · `GET /opportunities/{id}`

### Contacts / authors
`GET /contacts?domain_id=` (full list, never capped — see spec §4.6) ·
`GET /contacts/{id}` (sources + verification history) ·
`POST /contacts/{id}/reverify` ·
`GET /authors?domain_id=` · `GET /authors/{id}` (articles, topics,
relevance score)

### Guest posts
`GET /guest-posts?project_id=` · `GET /guest-posts/{id}` (guidelines +
probability + evidence from actual published articles)

### Content assets
`POST /content-assets` · `GET /content-assets?project_id=`

### Outreach / campaigns
`POST /campaigns` · `GET /campaigns?project_id=` · `GET /campaigns/{id}`
(funnel stats) · `POST /campaigns/{id}/contacts` (add opportunities to a
campaign) · `POST /campaigns/{id}/messages/{message_id}/generate` (AI
strategy + draft — does not send) ·
`POST /campaigns/{id}/messages/{message_id}/approve` ·
`POST /campaigns/{id}/messages/{message_id}/send` (explicit
human-approved action, never triggered by a background job) ·
`GET /campaigns/{id}/events`

### Monitoring
`GET /monitoring/alerts?project_id=` (lost/changed backlinks, contact
changes, guest-post-page changes) · `POST /monitoring/schedules`

### Reports / export
`GET /reports/{type}?project_id=&format=csv|xlsx|json|pdf` where `type`
is one of: backlink, competitor-gap, prospect, contact, guest-post,
outreach, lost-link, link-reclamation

### Data quality
`GET /data-quality?project_id=` (verified vs. inferred percentages, stale
data, blocked pages, crawl error rates, source distribution, confidence
distribution — the read model described in `DATABASE.md` §AI & data
quality)

## Explicitly out of scope for v1 API surface

Billing/subscription endpoints, team/role-management beyond the basic
owner/member RBAC already covered by `users`, and any endpoint that
triggers bulk automated sending without a preceding `approve` call.
