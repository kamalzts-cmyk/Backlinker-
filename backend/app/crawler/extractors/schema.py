"""Structured-metadata extraction: schema.org (JSON-LD), OpenGraph,
Twitter Cards, images, PDF links, social profile links, and embeds. See
docs/CRAWLER.md §4 Page-level.

JSON-LD only, not microdata/RDFa -- JSON-LD is the dominant modern format
and covers the large majority of real-world schema.org usage; microdata
support is a documented follow-up, not silently promised.
"""

import json
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

_SOCIAL_DOMAINS = (
    "twitter.com",
    "x.com",
    "linkedin.com",
    "facebook.com",
    "instagram.com",
    "youtube.com",
    "tiktok.com",
    "github.com",
    "mastodon.social",
)
_EMBED_DOMAINS = ("youtube.com", "youtube-nocookie.com", "vimeo.com", "player.vimeo.com")


@dataclass
class StructuredMetadata:
    schema_org: list[dict] = field(default_factory=list)
    open_graph: dict[str, str] = field(default_factory=dict)
    twitter_card: dict[str, str] = field(default_factory=dict)
    images: list[dict] = field(default_factory=list)  # [{"src": ..., "alt": ...}]
    pdf_links: list[str] = field(default_factory=list)
    social_links: list[str] = field(default_factory=list)
    embeds: list[str] = field(default_factory=list)


def extract_structured_metadata(soup: BeautifulSoup, page_url: str) -> StructuredMetadata:
    return StructuredMetadata(
        schema_org=_extract_json_ld(soup),
        open_graph=_extract_meta_prefixed(soup, prefix="og:", attr="property"),
        twitter_card=_extract_meta_prefixed(soup, prefix="twitter:", attr="name"),
        images=_extract_images(soup, page_url),
        pdf_links=_extract_pdf_links(soup, page_url),
        social_links=_extract_social_links(soup, page_url),
        embeds=_extract_embeds(soup, page_url),
    )


def _extract_json_ld(soup: BeautifulSoup) -> list[dict]:
    blocks = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            parsed = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue  # malformed JSON-LD is common in the wild; skip, don't fail the crawl
        blocks.extend(parsed if isinstance(parsed, list) else [parsed])
    return blocks


def _extract_meta_prefixed(soup: BeautifulSoup, *, prefix: str, attr: str) -> dict[str, str]:
    result = {}
    for tag in soup.find_all("meta", attrs={attr: re.compile(rf"^{re.escape(prefix)}")}):
        key = tag.get(attr, "")
        content = tag.get("content")
        if key and content is not None:
            result[key] = content
    return result


def _extract_images(soup: BeautifulSoup, page_url: str) -> list[dict]:
    images = []
    for img in soup.find_all("img", src=True):
        src = img["src"].strip()
        if not src:
            continue
        images.append({"src": urljoin(page_url, src), "alt": img.get("alt", "").strip()})
    return images


def _extract_pdf_links(soup: BeautifulSoup, page_url: str) -> list[str]:
    links = set()
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()
        if href.lower().split("?")[0].endswith(".pdf"):
            links.add(urljoin(page_url, href))
    return sorted(links)


def _extract_social_links(soup: BeautifulSoup, page_url: str) -> list[str]:
    links = set()
    for a_tag in soup.find_all("a", href=True):
        href = urljoin(page_url, a_tag["href"].strip())
        host = urlsplit(href).hostname or ""
        host = host.lower().removeprefix("www.")
        if host in _SOCIAL_DOMAINS:
            links.add(href)
    return sorted(links)


def _extract_embeds(soup: BeautifulSoup, page_url: str) -> list[str]:
    embeds = set()
    for iframe in soup.find_all("iframe", src=True):
        src = urljoin(page_url, iframe["src"].strip())
        host = (urlsplit(src).hostname or "").lower().removeprefix("www.")
        if host in _EMBED_DOMAINS:
            embeds.add(src)
    for video in soup.find_all(["video", "source"], src=True):
        embeds.add(urljoin(page_url, video["src"].strip()))
    return sorted(embeds)
