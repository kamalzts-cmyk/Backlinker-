"""Heuristic gate deciding HTTP-fetched HTML vs. a Playwright render.

docs/CRAWLER.md §1: escalate to Playwright only when this heuristic says
the content isn't already present in the plain HTTP response -- Playwright
is 10-50x more expensive and must not be the default path.
"""

import re

from bs4 import BeautifulSoup

_SPA_ROOT_IDS = {"root", "app", "__next", "___gatsby"}
_HYDRATION_MARKERS = ("__NEXT_DATA__", "ng-version", "data-reactroot", "__NUXT__")
_MIN_TEXT_CHARS = 200
_MIN_TEXT_TO_SCRIPT_RATIO = 0.15


def looks_js_rendered(html: str) -> bool:
    """Return True if the page likely needs JS rendering to show real
    content (i.e. we should escalate to Playwright).
    """
    soup = BeautifulSoup(html, "lxml")

    visible_text = re.sub(r"\s+", " ", soup.get_text(separator=" ")).strip()
    script_text_len = sum(len(s.get_text()) for s in soup.find_all("script"))
    total_len = max(len(html), 1)

    if len(visible_text) < _MIN_TEXT_CHARS:
        for marker in _HYDRATION_MARKERS:
            if marker in html:
                return True
        for root_id in _SPA_ROOT_IDS:
            el = soup.find(id=root_id)
            if el is not None and not el.get_text(strip=True):
                return True
        # Very little visible text and nothing else to go on: be
        # conservative and treat as JS-rendered rather than silently
        # extracting an empty page.
        if script_text_len / total_len > _MIN_TEXT_TO_SCRIPT_RATIO:
            return True

    return False
