"""Common Crawl connector. See PRODUCT_SPEC.md §4.2 Layer 1 and
docs/CRAWLER.md §6.

Common Crawl's public CDX index only indexes *by URL* -- it has no
"who links to this domain" reverse index (that requires the columnar/
Athena index, out of scope here). What it does give us, for free and
without auth, is: (a) which pages of a given domain it has captured, and
(b) via the `filename`/`offset`/`length` CDX fields, a direct HTTP Range
fetch of that exact page's raw captured content from data.commoncrawl.org
-- no live crawl needed just to inspect it.

So the real, honest use of Common Crawl here is: given a *seed domain* we
suspect might link to our target (e.g. a competitor, a known publisher),
pull its Common-Crawl-captured pages, check their captured HTML for a
link to the target using our existing extractor, and turn any hit into a
BacklinkCandidate for Phase 3 to directly verify. This does not claim to
discover "every site that links to X" -- see PRODUCT_SPEC.md §34 ("don't
promise all backlinks"); it's one candidate-generation source among
several (search discovery, prospect discovery, user-provided).
"""

import gzip
import json
import logging
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.core.config import settings
from app.crawler.extractors.links import extract_links
from app.crawler.normalize import normalize_url
from app.db.models import BacklinkCandidate, BacklinkSourceType, Domain
from app.engines.backlink.repository import create_candidate

logger = logging.getLogger(__name__)

CDX_INDEX_SERVER = "https://index.commoncrawl.org"
DATA_SERVER = "https://data.commoncrawl.org"
_REQUEST_TIMEOUT = 20


@dataclass
class CdxRecord:
    url: str
    timestamp: str
    status: str | None
    mime: str | None
    filename: str
    offset: int
    length: int


def parse_cdx_line(line: str) -> CdxRecord | None:
    """Parse one line of CDX server `output=json` NDJSON. Returns None
    for a line that doesn't look like a real capture record (blank
    lines, error payloads) rather than raising -- CDX responses are
    external input.
    """
    line = line.strip()
    if not line:
        return None
    try:
        data = json.loads(line)
        return CdxRecord(
            url=data["url"],
            timestamp=data["timestamp"],
            status=data.get("status"),
            mime=data.get("mime"),
            filename=data["filename"],
            offset=int(data["offset"]),
            length=int(data["length"]),
        )
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        return None


def extract_warc_html(raw_gzip_bytes: bytes) -> str | None:
    """A CDX record's Range-fetched bytes are a single gzip-compressed
    WARC record: WARC headers, blank line, then an embedded HTTP
    response (status line + headers, blank line, HTML body). Returns
    just the HTML body, or None if the payload doesn't parse as expected.
    """
    try:
        decompressed = gzip.decompress(raw_gzip_bytes)
    except OSError:
        return None

    parts = decompressed.split(b"\r\n\r\n", 1)
    if len(parts) != 2:
        return None
    _warc_headers, http_message = parts

    http_parts = http_message.split(b"\r\n\r\n", 1)
    if len(http_parts) != 2:
        return None
    _http_headers, body = http_parts

    return body.decode("utf-8", errors="ignore")


async def _latest_collection_cdx_api(client: httpx.AsyncClient) -> str | None:
    response = await client.get(f"{CDX_INDEX_SERVER}/collinfo.json")
    if response.status_code != 200:
        return None
    collections = response.json()
    if not collections:
        return None
    return collections[0].get("cdx-api")


async def query_cdx(
    client: httpx.AsyncClient, *, collection_cdx_api: str, url_pattern: str, limit: int = 50
) -> list[CdxRecord]:
    response = await client.get(
        collection_cdx_api,
        params={"url": url_pattern, "output": "json", "limit": limit},
    )
    if response.status_code != 200:
        return []
    records = [parse_cdx_line(line) for line in response.text.splitlines()]
    return [r for r in records if r is not None]


async def _fetch_warc_html(client: httpx.AsyncClient, record: CdxRecord) -> str | None:
    headers = {"Range": f"bytes={record.offset}-{record.offset + record.length - 1}"}
    try:
        response = await client.get(f"{DATA_SERVER}/{record.filename}", headers=headers)
    except httpx.HTTPError:
        return None
    if response.status_code not in (200, 206):
        return None
    return extract_warc_html(response.content)


async def discover_candidates_from_common_crawl(
    session: Session,
    *,
    seed_domain: str,
    target_domain: Domain,
    target_url: str,
    limit: int = 20,
) -> list[BacklinkCandidate]:
    """Check up to `limit` Common-Crawl-captured pages of seed_domain for
    a link to target_url, creating a BacklinkCandidate for each hit.
    Candidates still require Phase 3 direct verification -- this only
    establishes "worth checking," per the confidence table in
    PRODUCT_SPEC.md §2 (Common Crawl alone is High, not Very High).
    """
    normalized_target = normalize_url(target_url)
    headers = {"User-Agent": settings.crawler_user_agent}

    async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT, headers=headers) as client:
        collection_cdx_api = await _latest_collection_cdx_api(client)
        if collection_cdx_api is None:
            logger.warning("Common Crawl collinfo.json unavailable; no candidates discovered")
            return []

        records = await query_cdx(
            client, collection_cdx_api=collection_cdx_api, url_pattern=f"{seed_domain}/*", limit=limit
        )
        html_records = [r for r in records if r.status == "200" and (r.mime or "").startswith("text/html")]

        created: list[BacklinkCandidate] = []
        for record in html_records:
            html = await _fetch_warc_html(client, record)
            if html is None:
                continue

            soup = BeautifulSoup(html, "lxml")
            links = extract_links(soup, record.url)
            match = next(
                (link for link in links if normalize_url(link.target_url) == normalized_target), None
            )
            if match is None:
                continue

            candidate = create_candidate(
                session,
                source_url=record.url,
                target_url=match.target_url,
                target_domain_id=target_domain.id,
                source_type=BacklinkSourceType.COMMON_CRAWL,
                discovery_method=f"common_crawl_cdx:{collection_cdx_api}",
            )
            created.append(candidate)

        return created
