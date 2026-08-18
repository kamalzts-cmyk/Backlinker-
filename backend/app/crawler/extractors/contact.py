"""Deterministic contact-info extraction from visible page text.

Regex-based, on purpose -- see PRODUCT_SPEC.md §5.4: HTTP/DNS/link-shape
facts are deterministic, and a plain email/phone appearing in rendered
text is the same kind of fact. Full name/role/department attribution
(who does this email belong to) is Contact Intelligence (Phase 8), not
this module -- this only answers "what emails/phones are visible on this
page," each one still needing a provenance record upstream (source page,
discovered_at) before it becomes a `contacts` row.

Deliberately does NOT attempt to defeat obfuscation ("editor [at] x.com",
image-based addresses, JS-assembled strings) -- an address hidden well
enough to dodge this regex is exactly the case docs/CRAWLER.md fixtures
(obfuscated_email.html) exist to keep honest: we extract what's plainly
present, not what we can cleverly de-obfuscate.
"""

import re

from bs4 import BeautifulSoup

_EMAIL_RE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._%+-]*@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

# Loosely matches common phone formats (+1 555 123 4567, (555) 123-4567,
# 555-123-4567) while requiring enough digits to avoid catching dates,
# prices, or heading numbers. False positives are possible; this is a
# candidate signal, not a verified contact -- verification is Phase 9.
_PHONE_RE = re.compile(r"(?<!\d)(\+?\(?\d[\d\-.\(\)\s]{7,}\d)(?!\d)")
_MIN_PHONE_DIGITS = 9
_MAX_PHONE_DIGITS = 15


def extract_contact_emails(soup: BeautifulSoup) -> list[str]:
    text = soup.get_text(separator=" ")
    found = {m.group(0).rstrip(".,;:") for m in _EMAIL_RE.finditer(text)}
    return sorted(found)


def extract_contact_phones(soup: BeautifulSoup) -> list[str]:
    text = soup.get_text(separator=" ")
    candidates = set()
    for match in _PHONE_RE.finditer(text):
        raw = match.group(0).strip()
        digit_count = sum(c.isdigit() for c in raw)
        has_separator = any(c in raw for c in " -.()")
        # Bare digit runs (order numbers, IDs, long dates) are excluded --
        # a phone number written in prose almost always has a separator.
        if has_separator and _MIN_PHONE_DIGITS <= digit_count <= _MAX_PHONE_DIGITS:
            candidates.add(raw)
    return sorted(candidates)
