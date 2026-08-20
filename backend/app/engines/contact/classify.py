"""Deterministic page-type and role-address classification. See
PRODUCT_SPEC.md §4.6's list of contact-relevant page types.
"""

from urllib.parse import urlsplit

from app.db.models import ContactPageType

_PAGE_TYPE_PATTERNS: dict[ContactPageType, tuple[str, ...]] = {
    ContactPageType.CONTACT: ("/contact",),
    ContactPageType.ABOUT: ("/about",),
    ContactPageType.TEAM: ("/team", "/editorial-team", "/our-team", "/staff"),
    ContactPageType.AUTHOR: ("/author", "/authors", "/contributor", "/contributors", "/writers"),
    ContactPageType.GUEST_POST: (
        "/write-for-us",
        "/guest-post",
        "/guest-author",
        "/contribute",
        "/contributor-guidelines",
        "/submit",
        "/pitch",
    ),
    ContactPageType.PRESS: ("/press", "/media", "/newsroom", "/advertise"),
}

_ROLE_ADDRESS_LOCAL_PARTS = frozenset(
    {
        "info",
        "contact",
        "press",
        "media",
        "editor",
        "editorial",
        "editors",
        "admin",
        "support",
        "hello",
        "team",
        "help",
        "sales",
        "pr",
        "newsroom",
        "office",
        "general",
        "enquiries",
        "inquiries",
        "webmaster",
        "advertise",
        "advertising",
        "marketing",
        "hr",
        "careers",
        "jobs",
        "noreply",
        "no-reply",
    }
)


def classify_page_type(url: str) -> ContactPageType | None:
    """Returns None for a page that isn't contact-relevant at all (so
    callers can skip it) -- HOME and OTHER are only ever assigned
    explicitly by the caller, never guessed from the path alone.
    """
    path = urlsplit(url).path.lower().rstrip("/")
    if path in ("", "/"):
        return ContactPageType.HOME
    for page_type, patterns in _PAGE_TYPE_PATTERNS.items():
        if any(pattern in path for pattern in patterns):
            return page_type
    return None


def is_role_address(email: str) -> bool:
    local_part = email.split("@", 1)[0].lower()
    return local_part in _ROLE_ADDRESS_LOCAL_PARTS
