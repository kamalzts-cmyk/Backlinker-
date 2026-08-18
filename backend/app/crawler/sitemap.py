"""Sitemap / sitemap-index discovery. See docs/CRAWLER.md §2."""

import httpx
from lxml import etree

from app.core.config import settings

_MAX_SITEMAP_RECURSION = 3
_XML_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


async def _fetch_xml(client: httpx.AsyncClient, url: str) -> etree._Element | None:
    try:
        response = await client.get(url)
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    try:
        return etree.fromstring(response.content)
    except etree.XMLSyntaxError:
        return None


async def discover_sitemap_urls(candidate_sitemap_urls: list[str], *, _depth: int = 0) -> list[str]:
    """Given one or more starting sitemap URLs (from robots.txt or the
    conventional /sitemap.xml / /sitemap_index.xml locations), return the
    flat list of page URLs found, recursing into sitemap indexes.
    """
    if _depth >= _MAX_SITEMAP_RECURSION or not candidate_sitemap_urls:
        return []

    page_urls: list[str] = []
    nested_sitemaps: list[str] = []
    headers = {"User-Agent": settings.crawler_user_agent}

    async with httpx.AsyncClient(timeout=10, headers=headers, follow_redirects=True) as client:
        for sitemap_url in candidate_sitemap_urls:
            root = await _fetch_xml(client, sitemap_url)
            if root is None:
                continue

            tag = etree.QName(root).localname
            if tag == "sitemapindex":
                nested_sitemaps.extend(
                    loc.text.strip()
                    for loc in root.findall(".//sm:sitemap/sm:loc", _XML_NS)
                    if loc.text
                )
            elif tag == "urlset":
                page_urls.extend(
                    loc.text.strip() for loc in root.findall(".//sm:url/sm:loc", _XML_NS) if loc.text
                )

    if nested_sitemaps:
        page_urls.extend(await discover_sitemap_urls(nested_sitemaps, _depth=_depth + 1))

    return page_urls


def default_sitemap_locations(base_url: str) -> list[str]:
    base = base_url.rstrip("/")
    return [f"{base}/sitemap.xml", f"{base}/sitemap_index.xml"]
