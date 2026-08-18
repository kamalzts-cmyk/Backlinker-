# Crawler

Companion to `ARCHITECTURE.md` §5. This is the detailed spec for
`backend/app/crawler/`. Built on **Crawlee** (open source; provides
request-queue, retry, and both HTTP and Playwright crawler primitives out
of the box — we use its primitives rather than reinventing basic
queueing).

## 1. Why two crawl paths

Playwright (real browser rendering) is 10-50x more expensive than a plain
HTTP fetch + HTML parse. Using it for every page is wasteful and would
dominate resource usage. Most pages we care about (articles, contact
pages, about pages, guideline pages) are server-rendered and don't need
it.

```
URL
 │
 ├── robots.txt
 ├── sitemap.xml / sitemap_index.xml
 ▼
HTTP crawler (fast path)
 │
 ├── HTML already contains the content? ──YES──▶ fast parser (BeautifulSoup/Parsel)
 │
 └── JS rendering required? ──YES──▶ Playwright (slow path, separate pool/concurrency limit)
```

### JS-detection heuristic (run before ever launching Chromium)

Score the raw HTTP-fetched HTML on:

- text-to-script ratio (very low → likely JS-rendered shell)
- known SPA framework markers (`__NEXT_DATA__`, `ng-version`, empty
  `#root`/`#app` div with a bundle script, etc.)
- presence of hydration markers with an otherwise-empty body
- whether the specific content we need (e.g. contact info, article body)
  is actually present in the fetched HTML

Escalate to Playwright only if this heuristic says the content isn't
already there. This is what "massively reduces resource consumption"
means in practice — it must be a real gate, not a manual per-domain flag.

## 2. Crawl frontier & scheduling

Not a single FIFO queue. A **priority-aware frontier**:

| Priority | Examples |
|---|---|
| A — immediate | known backlink candidate URL, competitor backlink candidate |
| B — high | contact page, author page, editorial page, guest-post/guideline page |
| C — normal | general site pages, recrawl of a page whose fingerprint may have changed |

Frontier responsibilities: URL normalization (see `DATABASE.md`
§Conventions — same normalization function reused everywhere), duplicate
detection, canonical normalization, per-domain/per-path/depth limits,
crawl budgets, retry queue with exponential backoff, and a dead-letter
queue for permanently failed requests (never silently dropped — they must
be inspectable).

## 3. Politeness (mandatory, not configurable per crawl)

- Respect `robots.txt` (cached per domain, TTL-bound).
- Per-domain concurrency and per-domain delay, independent of global
  concurrency.
- Backoff on `429`/`503`, honoring `Retry-After` when present.
- Identify our crawler with a real, honest User-Agent string.
- Never attempt to bypass CAPTCHA, login walls, paywalls, or any access
  control. A block is recorded as `crawl_errors.reason = BLOCKED_*` — it
  is a status, not a failed extraction to retry harder against.
- Never collect information that isn't publicly accessible without
  authentication.

## 4. What we extract

### Page-level

URL, canonical, HTTP status, title, meta description, H1, H2–H6, word
count, language, content type, published date, modified date, author,
schema.org data, OpenGraph, Twitter card, robots directives,
indexability, internal links, external links, images (+ alt text),
videos/embeds, PDF links, social links, and contact info found on the page
(emails, phone numbers) plus entities (organization/person/product/
service/location — extracted deterministically where possible, AI-assisted
for ambiguous cases per `ARCHITECTURE.md` §7).

### Link-level (for every external link)

`source_url, target_url, target_domain, anchor_text, surrounding_text,
rel_nofollow, rel_sponsored, rel_ugc, target_blank, link_position,
first_seen, last_seen, http_status (of target), target_indexability,
context`.

**Context, not just existence.** Instead of storing "backlink from
example.com," we store the actual surrounding sentence (e.g. *"According
to [brand], small businesses can reduce..."*) and classify why the link
exists (editorial reference, citation, directory listing, etc. — see
`PRODUCT_SPEC.md` §4.2 backlink types). This is what makes a backlink
observation useful instead of a bare boolean.

## 5. Fingerprinting & change detection

Every crawled page gets `content_hash`, `html_hash`, `text_hash`,
`structure_hash`. Comparing hashes across crawls (stored in
`page_changes`, see `DATABASE.md`) drives change detection: content
changed, backlink removed, anchor changed, rel changed, page deleted,
redirected, canonical changed — without needing to re-diff full HTML on
every check.

## 6. Backlink discovery → verification pipeline

Three discovery layers feed one verification pipeline (full detail in
`PRODUCT_SPEC.md` §4.2); the crawler's job is:

1. **Common Crawl connector** queries the public CDX index for
   `target-domain.com/*` and for pages plausibly referencing the target,
   producing `backlink_candidates` (source_type = `COMMON_CRAWL`).
2. **Search discovery** runs generated query patterns and adds
   `backlink_candidates` (source_type = `SEARCH_DISCOVERED`). This layer's
   backing search mechanism is an open decision — see
   `ARCHITECTURE.md` risk #3.
3. **Direct verification** (this module) crawls every candidate itself
   (HTTP first, Playwright if the JS-detection heuristic requires it) and
   runs the check sequence: page exists → target URL present in raw HTML
   → is an actual `<a href>` (not just text) → page canonical → page
   indexable → follow/nofollow/sponsored/ugc → anchor text → surrounding
   context. Only this path can set `verification_status = VERIFIED`; a
   candidate that fails any step is marked `REJECTED` with a reason, kept
   for audit, not deleted.

## 7. Testing

Crawler/extractor code must be tested against **local HTML fixtures**
(`backend/app/tests/fixtures/html/`) covering: follow link, nofollow,
sponsored, UGC, redirect, canonical, broken link (404), JS-rendered
content, obfuscated email, `mailto:` link, a simulated block page
(Cloudflare-style challenge), a guest-post guideline page, and an author
page. Fixture-based tests must pass before any test is run against a real
live site; live-site tests are integration tests, not the primary
correctness check (the internet changes — fixtures don't).

## 8. Crawl replay

Store request/response headers, status, and an HTML snapshot per
`crawl_requests` row (subject to retention/rollup — see
`ARCHITECTURE.md` risk #6) so extraction bugs can be reproduced from a
stored snapshot without re-crawling the live site.
