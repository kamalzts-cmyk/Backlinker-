# Database Design

PostgreSQL, SQLAlchemy models, Alembic migrations. Companion to
`ARCHITECTURE.md`. This document defines table groups, key columns, and
conventions — not full DDL (that's written against real model code in
Phase 0's implementation step, informed by this design).

## Conventions

- Primary keys: UUID (`gen_random_uuid()`), never auto-increment integers
  (avoids enumeration, safe to merge across environments).
- Every table has `created_at`, `updated_at` (`timestamptz`).
- **History over mutation**: tables that represent something observed over
  time (backlinks, contacts, prospect scores) are never updated in place
  for their core facts — a new `*_observations` row is inserted, and a
  denormalized "current state" view/column is maintained for fast reads.
- Every fact table that can be `INFERRED` vs `VERIFIED` carries the full
  provenance column set from `PRODUCT_SPEC.md` §3.1:
  `source_url, source_type, discovery_method, discovered_at,
  last_verified_at, verification_status, confidence_score`.
- Domains are always normalized (scheme stripped, `www` stripped, lowercase
  host, punycode-normalized, trailing slash stripped) before being stored
  or matched — see `ARCHITECTURE.md` risk #8. `domains.normalized_host` is
  unique and is the join key everywhere; raw/original host is kept
  separately for display.
- No unstructured catch-all JSON columns for core facts. `jsonb` is
  allowed only for genuinely variable, non-queried payloads (e.g. raw
  schema.org blob, raw AI response for audit).

## Table groups

### Identity & projects

- `users` — auth identity, RBAC role.
- `projects` — one per tracked website (belongs to a user); holds the
  project's own domain, competitor list, and configured score weights.
- `audit_logs` — who did what, when (auth events, sends, exports, config
  changes).

### Crawl layer

- `domains` — normalized host, first_seen, last_crawled, robots.txt cache,
  crawl politeness settings observed (crawl-delay, disallow rules).
- `crawl_jobs` — one per crawl run (project or ad hoc), status, phase
  (discovery/crawl/verify), started/finished, priority tier.
- `crawl_requests` — one per URL fetch attempt: URL, method (HTTP vs
  Playwright), status code, redirect chain, content type, content hash,
  html hash, text hash, structure hash, timing, `crawl_job_id`.
- `crawl_errors` — failed/blocked requests, reason (`BLOCKED_ROBOTS`,
  `BLOCKED_CAPTCHA`, `TIMEOUT`, `DNS_FAIL`, `HTTP_5XX`, ...), tied to
  `crawl_requests`.
- `pages` — current-state snapshot of a crawled URL: canonical, title,
  meta description, H1/H2-6 (as array or child table if we need per-tag
  querying), word count, language, content type, published/modified date,
  author, robots directives, indexability, OpenGraph/Twitter card data,
  schema.org types found, hashes (for change detection), `domain_id`,
  latest `crawl_request_id`.
- `page_changes` — history of hash changes per page (for the change-
  detection feature in `CRAWLER.md` §Fingerprinting).

### Links (internal graph + raw extraction)

- `page_links` — every extracted link, internal or external: `source_page_id`,
  `target_url`, `target_domain_id` (nullable until resolved), `anchor_text`,
  `surrounding_text`, `rel_nofollow`, `rel_sponsored`, `rel_ugc`,
  `target_blank`, `link_position` (nav/footer/body/sidebar), `first_seen`,
  `last_seen`, `http_status` (of target, if checked), `is_internal`.
  This is the raw material both the internal site graph and the backlink
  engine are built from.

### Backlink engine

- `backlinks` — current-state denormalized view of a source→target link
  pair (`source_domain_id`, `target_domain_id`, `source_url`, `target_url`,
  latest anchor/rel/type/status), for fast dashboard reads. Always derived
  from `backlink_observations`, never hand-edited.
- `backlink_observations` — append-only: every time we (re)verify a
  source→target pair, one row: anchor, rel flags, link type
  classification, context snippet + AI classification of *why* the link
  exists, source/target canonical + indexability at observation time,
  http status, `observed_at`, plus the full provenance column set. This is
  what powers "follow → nofollow on 2026-08-18" history.
- `backlink_candidates` — pre-verification queue: URL + why it's a
  candidate (`COMMON_CRAWL` / `SEARCH_DISCOVERED`), not yet crawled/
  verified. Promoted to `backlink_observations` on successful direct
  verification; candidates that fail verification are kept (status
  `REJECTED`, with reason) rather than deleted, for auditability.

### Competitor intelligence

- `competitors` — `project_id`, competitor `domain_id`, added_at.
- `competitor_backlinks` — materialized per-competitor backlink set
  (references `backlinks`), refreshed on competitor crawl.
- `link_gap_opportunities` — computed rows: `project_id`, `candidate_domain_id`,
  `competitor_overlap_count`, list of which competitors link there
  (child table or array of competitor ids), opportunity confidence,
  links into `link_opportunities` (below) once scored.

### Prospect & scoring

- `prospects` — a domain being evaluated as a link target for a project
  (`project_id`, `domain_id`, discovery source: competitor-gap /
  independent-discovery / resource-page / etc).
- `prospect_scores` — one row per scoring run per prospect: each named
  sub-score (domain quality, topical relevance, editorial quality, link
  probability, contactability, spam risk), the weighted composite, weight
  configuration used, `scored_at`.
- `link_opportunities` — the user-facing unit: joins a prospect (or
  competitor-gap row) to its latest score, recommended contact, and
  recommended content asset. This is what `/opportunities` serves.
- `evidence` — polymorphic evidence records: `subject_type` (`prospect_score`
  / `link_opportunity` / `guest_post_opportunity` / ...), `subject_id`,
  `claim` (e.g. "Competitor A links here"), `source_url`, `evidence_type`.
  Every scoring function must write these at score-time (see
  `ARCHITECTURE.md` risk #9).
- `content_assets` — the user's own linkable assets (guide/study/tool/
  data), used by content-asset matching.

### Contact intelligence

- `contacts` — person or role-address discovered on a domain: name
  (nullable for role addresses), job title, department, email, phone,
  contact-form URL, LinkedIn/X/other socials, `domain_id`, current
  `verification_status` (the 8-state enum from the spec), confidence.
- `contact_sources` — provenance detail per contact: `contact_id`,
  `source_url`, `source_text` (surrounding snippet), `page_type`
  (about/contact/team/author/...), `discovered_at`. A contact can have
  multiple sources (e.g. found on both the team page and an author bio).
- `email_verifications` — one row per verification attempt: `contact_id`,
  layer reached (syntax/DNS/MX/SMTP/catch-all), result, `checked_at`. Kept
  historical (an address can go from valid to bouncing over time).
- `authors` — extends `contacts` with publication-specific profile: author
  URL, topics (array or link to a topics table), publishing frequency,
  recent-article list (via `author_articles`), computed relevance score
  per project (in a join table, since relevance is project-specific).
- `author_articles` — articles attributed to an author (`author_id`,
  `page_id`, published_at), used to compute publishing frequency/topics
  and to verify guest-post activity.

### Guest post intelligence

- `guest_post_opportunities` — `domain_id`, guideline page URL (if found),
  computed `guest_post_probability`, accepts-external-links, dofollow/
  nofollow, author-bio-allowed, commercial-link-restrictions, submission
  method, editor contact, evidence pointer.
- `editorial_guidelines` — extracted structured guideline fields (word
  count range, topic restrictions, max links) tied to a
  `guest_post_opportunities` row, kept versioned (guidelines change).

### Outreach & campaigns

- `outreach_campaigns` — `project_id`, name, sequence config (initial +
  follow-up timing), status.
- `outreach_contacts` — join of campaign → `link_opportunities`/`contacts`,
  per-recipient status.
- `outreach_messages` — generated strategy object (opportunity type,
  reason, evidence refs, recommended asset, angle) *and* the drafted copy,
  kept separate so strategy can be audited independently of wording;
  send status (`DRAFT` → `APPROVED` → `SENT`).
- `outreach_events` — funnel events per message: delivered/opened/
  clicked/replied/positive/negative/unsubscribed/published/backlink-
  detected/backlink-verified, `occurred_at`. This is what powers
  conversion-rate and (later) ROI reporting.

### Monitoring

- Backlink monitoring reuses `backlink_observations` (a scheduled re-crawl
  simply inserts a new observation); "lost/changed" alerts are computed by
  diffing the two most recent observations for a pair, not a separate
  table.
- `crawl_jobs` with `schedule` (`ONE_TIME`/`DAILY`/`WEEKLY`/`MONTHLY`) drives
  recurring re-checks of prospects, contacts, and guest-post pages the same
  way.

### AI & data quality

- `ai_analysis` — every AI call: `subject_type/id`, provider used, prompt
  template id, raw response (jsonb, for audit), validated structured
  result, `succeeded`, `created_at`. Enables the Data Quality Center to
  report AI failure rates.
- Data Quality Center is a **read model over existing provenance columns**
  (percent verified vs. inferred, stale data older than N days, blocked
  pages, crawl error rates) — it does not need its own source-of-truth
  tables beyond maybe a materialized view refreshed periodically.

## Indexing strategy

- `normalized_host` unique index on `domains`.
- Composite index on `backlink_observations (source_domain_id,
  target_domain_id, observed_at desc)` — the hot path for "get current
  state" and "get history."
- Composite index on `page_links (target_domain_id)` for backlink
  candidate discovery from our own crawl graph.
- Partial index on `contacts (verification_status)` where status in
  (`VERIFIED`, `DIRECTLY_PUBLISHED`) — the common "show me real contacts"
  filter.
- Full-text (`tsvector`) index on `pages.title || pages.meta_description ||
  body_text` for prospect/content search without standing up a separate
  search cluster (see `ARCHITECTURE.md` §6 — no OpenSearch until
  justified).
- `pgvector` index (ivfflat/hnsw) on a `page_embeddings` table for topical
  similarity matching (content-asset matching, prospect relevance),
  populated by the AI engine.

## What we explicitly avoid

- No single giant `jsonb` "data" column standing in for structured
  columns — kills indexing and makes provenance per-field impossible.
- No boolean `is_backlink` flag anywhere — everything is derived from
  `backlink_observations`.
- No storing an inferred/guessed email in the same column/state as a
  verified one; the `verification_status` enum is mandatory on every read
  path, not just in the API layer.
