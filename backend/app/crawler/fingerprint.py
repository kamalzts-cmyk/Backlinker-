"""Page fingerprinting for change detection. See docs/CRAWLER.md §5."""

import hashlib
import re

from bs4 import BeautifulSoup

_WHITESPACE_RE = re.compile(r"\s+")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def content_hash(raw_html: str) -> str:
    """Hash of the raw response body -- changes on any byte-level change."""
    return _sha256(raw_html)


_BETWEEN_TAGS_RE = re.compile(r">\s+<")


def html_hash(soup: BeautifulSoup) -> str:
    """Hash of the parsed HTML with whitespace *between tags* removed and
    all other whitespace runs collapsed -- ignores insignificant
    formatting differences (e.g. a CMS re-indenting its templates) that
    content_hash would catch.
    """
    raw = str(soup)
    without_inter_tag_whitespace = _BETWEEN_TAGS_RE.sub("><", raw)
    normalized = _WHITESPACE_RE.sub(" ", without_inter_tag_whitespace).strip()
    return _sha256(normalized)


def text_hash(soup: BeautifulSoup) -> str:
    """Hash of visible text only -- flags content changes independent of
    markup/attribute changes (e.g. a rel=nofollow flip won't trip this).
    """
    text = _WHITESPACE_RE.sub(" ", soup.get_text(separator=" ")).strip()
    return _sha256(text)


def structure_hash(soup: BeautifulSoup) -> str:
    """Hash of the tag skeleton only (no text/attributes) -- flags
    structural/template changes independent of copy edits.
    """
    skeleton = "".join(tag.name for tag in soup.find_all(True))
    return _sha256(skeleton)
