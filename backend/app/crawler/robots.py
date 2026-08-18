"""robots.txt fetch + cache.

Actual crawl-time enforcement is delegated to Crawlee's built-in
`respect_robots_txt_file` support on the crawler (see
app/crawler/http_crawler.py) rather than re-implemented here -- per
docs/ARCHITECTURE.md §5, we use Crawlee's primitives instead of
reinventing them. This module is the piece Crawlee doesn't cover: caching
the raw robots.txt onto the Domain record (docs/DATABASE.md §Crawl layer)
so it's inspectable, and parsing `Sitemap:` directives for sitemap
discovery.
"""

import httpx

from app.core.config import settings


async def fetch_robots_txt(base_url: str) -> str | None:
    robots_url = base_url.rstrip("/") + "/robots.txt"
    headers = {"User-Agent": settings.crawler_user_agent}
    try:
        async with httpx.AsyncClient(timeout=10, headers=headers, follow_redirects=True) as client:
            response = await client.get(robots_url)
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    return response.text


def sitemap_urls_from_robots(robots_txt: str) -> list[str]:
    urls = []
    for line in robots_txt.splitlines():
        line = line.strip()
        if line.lower().startswith("sitemap:"):
            urls.append(line.split(":", 1)[1].strip())
    return urls
