"""Link-level extraction. See docs/CRAWLER.md §4 Link-level.

For every external link we store surrounding context, not just the bare
URL -- that's what turns a backlink observation into something we can
later classify ("why does this link exist?") instead of a boolean.
"""

import re
from dataclasses import dataclass
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from bs4.element import Tag

from app.crawler.normalize import registrable_domain_for_url

_NAV_HINTS = ("nav", "menu", "breadcrumb")
_FOOTER_HINTS = ("footer",)
_SIDEBAR_HINTS = ("sidebar", "aside", "widget")
_SURROUNDING_TEXT_MAX_CHARS = 300


@dataclass
class LinkData:
    target_url: str
    anchor_text: str
    surrounding_text: str
    rel_nofollow: bool
    rel_sponsored: bool
    rel_ugc: bool
    target_blank: bool
    link_position: str
    is_internal: bool


def _classify_position(a_tag: Tag) -> str:
    for ancestor in a_tag.parents:
        if not isinstance(ancestor, Tag):
            continue
        haystack = " ".join(
            [ancestor.name or "", " ".join(ancestor.get("class", [])), ancestor.get("id", "")]
        ).lower()
        if any(hint in haystack for hint in _NAV_HINTS) or ancestor.name == "nav":
            return "nav"
        if any(hint in haystack for hint in _FOOTER_HINTS) or ancestor.name == "footer":
            return "footer"
        if any(hint in haystack for hint in _SIDEBAR_HINTS) or ancestor.name == "aside":
            return "sidebar"
        if ancestor.name in ("article", "main") or "content" in haystack or "body" in haystack:
            return "body"
    return "unknown"


def _surrounding_text(a_tag: Tag) -> str:
    parent = a_tag.parent if isinstance(a_tag.parent, Tag) else None
    text = parent.get_text(separator=" ") if parent is not None else a_tag.get_text(separator=" ")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > _SURROUNDING_TEXT_MAX_CHARS:
        text = text[:_SURROUNDING_TEXT_MAX_CHARS]
    return text


def extract_links(soup: BeautifulSoup, page_url: str) -> list[LinkData]:
    page_domain = registrable_domain_for_url(page_url)
    links: list[LinkData] = []

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue

        target_url = urljoin(page_url, href)
        if not target_url.startswith(("http://", "https://")):
            continue

        rel_values = {r.lower() for r in a_tag.get("rel", [])}
        anchor_text = a_tag.get_text(strip=True)

        links.append(
            LinkData(
                target_url=target_url,
                anchor_text=anchor_text,
                surrounding_text=_surrounding_text(a_tag),
                rel_nofollow="nofollow" in rel_values,
                rel_sponsored="sponsored" in rel_values,
                rel_ugc="ugc" in rel_values,
                target_blank=(a_tag.get("target") == "_blank"),
                link_position=_classify_position(a_tag),
                is_internal=(registrable_domain_for_url(target_url) == page_domain),
            )
        )

    return links
