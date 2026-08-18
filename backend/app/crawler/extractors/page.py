"""Page-level extraction. See docs/CRAWLER.md §4 Page-level.

Implements the deterministic subset for Phase 1 (title, meta description,
headings, word count, language, canonical, robots, indexability).
schema.org/OpenGraph/Twitter-card/entity extraction lands in Phase 2.
"""

from dataclasses import dataclass, field
from urllib.parse import urljoin

from bs4 import BeautifulSoup


@dataclass
class PageData:
    title: str | None
    meta_description: str | None
    canonical_url: str | None
    h1: list[str] = field(default_factory=list)
    headings: list[dict] = field(default_factory=list)
    word_count: int = 0
    language: str | None = None
    robots_meta_noindex: bool = False
    robots_meta_nofollow: bool = False


def extract_page_data(soup: BeautifulSoup, page_url: str) -> PageData:
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else None

    meta_desc_tag = soup.find("meta", attrs={"name": "description"})
    meta_description = meta_desc_tag.get("content", "").strip() if meta_desc_tag else None

    canonical_tag = soup.find("link", rel="canonical")
    canonical_url = urljoin(page_url, canonical_tag["href"]) if canonical_tag and canonical_tag.get("href") else None

    h1 = [h.get_text(strip=True) for h in soup.find_all("h1")]
    headings = [
        {"tag": tag.name, "text": tag.get_text(strip=True)}
        for tag in soup.find_all(["h2", "h3", "h4", "h5", "h6"])
    ]

    body_text = soup.get_text(separator=" ")
    word_count = len(body_text.split())

    html_tag = soup.find("html")
    language = html_tag.get("lang") if html_tag and html_tag.get("lang") else None

    robots_tag = soup.find("meta", attrs={"name": "robots"})
    robots_content = robots_tag.get("content", "").lower() if robots_tag else ""
    robots_meta_noindex = "noindex" in robots_content
    robots_meta_nofollow = "nofollow" in robots_content

    return PageData(
        title=title,
        meta_description=meta_description,
        canonical_url=canonical_url,
        h1=h1,
        headings=headings,
        word_count=word_count,
        language=language,
        robots_meta_noindex=robots_meta_noindex,
        robots_meta_nofollow=robots_meta_nofollow,
    )
