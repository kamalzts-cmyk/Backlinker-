"""Guest-post intelligence. See PRODUCT_SPEC.md §16/§24.

Reuses the Phase 1/2 crawler and Phase 8's page-type classification --
detecting a guest-post opportunity is "crawl the domain, find the page
classified GUEST_POST, and analyze what it plainly says," not a new
crawl mechanism. Word-count ranges, dofollow/nofollow/sponsored
mentions, and author-bio mentions are matched via a small set of
explicit regexes -- deliberately narrow rather than general NLP, so
every field is traceable to a specific pattern rather than an opaque
guess.
"""

import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.crawler.run import run_crawl
from app.db.base import session_scope
from app.db.models import (
    Contact,
    ContactPageType,
    ContactSource,
    CrawlRequest,
    GuestPostOpportunity,
    Page,
)
from app.engines.contact.classify import classify_page_type

_WORD_COUNT_RE = re.compile(r"(\d{3,5})\s*(?:-|to|–)\s*(\d{3,5})\s*words", re.IGNORECASE)
_CLOSED_KEYWORDS = (
    "not currently accepting",
    "closed for submissions",
    "not accepting guest",
    "no longer accepting",
    "temporarily closed",
)

# Deterministic point values -- each one traceable to a specific,
# named piece of evidence. Not the full weighted Opportunity Score
# (Phase 11); this is guest-post-specific and much narrower.
_POINTS_GUIDELINE_PAGE_EXISTS = 40
_POINTS_PER_DISTINCT_AUTHOR = 5
_MAX_AUTHOR_POINTS = 30
_POINTS_AUTHOR_BIO_MENTIONED = 10
_POINTS_EDITOR_EMAIL_FOUND = 10
_POINTS_APPEARS_CLOSED_PENALTY = 40


def _extract_word_count_range(text: str) -> tuple[int | None, int | None]:
    match = _WORD_COUNT_RE.search(text)
    if match is None:
        return None, None
    low, high = int(match.group(1)), int(match.group(2))
    return (low, high) if low <= high else (high, low)


def _mentions_any(text: str, *phrases: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in phrases)


async def discover_guest_post_opportunity(
    start_url: str, *, max_pages: int = 20
) -> GuestPostOpportunity | None:
    """Crawls the domain and looks for a guest-post guideline page.
    Returns None if none was found within the crawl budget -- an honest
    "we didn't find one," not a fabricated low score.
    """
    job_id = await run_crawl(start_url, max_pages=max_pages)

    with session_scope() as session:
        pages = session.scalars(
            select(Page)
            .join(CrawlRequest, Page.crawl_request_id == CrawlRequest.id)
            .where(CrawlRequest.crawl_job_id == job_id)
        ).all()

        guideline_page = next(
            (p for p in pages if classify_page_type(p.url) == ContactPageType.GUEST_POST), None
        )
        if guideline_page is None:
            return None

        return _analyze_and_store(session, guideline_page)


def _analyze_and_store(session: Session, page: Page) -> GuestPostOpportunity:
    text = page.body_text or " ".join(
        filter(None, [page.title or "", page.meta_description or ""])
    )
    word_count_min, word_count_max = _extract_word_count_range(text)
    mentions_dofollow = _mentions_any(text, "dofollow", "do-follow", "do follow")
    mentions_nofollow = _mentions_any(text, "nofollow", "no-follow", "no follow")
    mentions_sponsored = _mentions_any(text, "sponsored")
    mentions_author_bio = _mentions_any(text, "author bio", "bio link", "about the author")
    appears_closed = _mentions_any(text, *_CLOSED_KEYWORDS)
    editor_email = (page.contact_emails or [None])[0]

    distinct_authors = _count_distinct_authors(session, page.domain_id)

    score = _POINTS_GUIDELINE_PAGE_EXISTS
    evidence = [f"Guideline page found at {page.url}"]

    author_points = min(distinct_authors * _POINTS_PER_DISTINCT_AUTHOR, _MAX_AUTHOR_POINTS)
    if distinct_authors:
        score += author_points
        evidence.append(
            f"{distinct_authors} distinct author(s) observed on this domain "
            "(proxy signal, not confirmed third-party authorship)"
        )
    if mentions_author_bio:
        score += _POINTS_AUTHOR_BIO_MENTIONED
        evidence.append("Guidelines mention an author bio")
    if editor_email:
        score += _POINTS_EDITOR_EMAIL_FOUND
        evidence.append(f"Editor contact found: {editor_email}")
    if appears_closed:
        score -= _POINTS_APPEARS_CLOSED_PENALTY
        evidence.append("Page language suggests submissions are currently closed")

    score = max(0, min(100, score))

    existing = session.scalar(
        select(GuestPostOpportunity).where(GuestPostOpportunity.domain_id == page.domain_id)
    )
    now = datetime.now(UTC)
    if existing is not None:
        opportunity = existing
    else:
        opportunity = GuestPostOpportunity(domain_id=page.domain_id)
        session.add(opportunity)

    opportunity.guideline_page_url = page.url
    opportunity.editor_email = editor_email
    opportunity.word_count_min = word_count_min
    opportunity.word_count_max = word_count_max
    opportunity.mentions_dofollow = mentions_dofollow
    opportunity.mentions_nofollow = mentions_nofollow
    opportunity.mentions_sponsored = mentions_sponsored
    opportunity.mentions_author_bio = mentions_author_bio
    opportunity.appears_closed = appears_closed
    opportunity.distinct_authors_observed = distinct_authors
    opportunity.guest_post_probability = score
    opportunity.evidence = evidence
    opportunity.computed_at = now

    session.flush()
    return opportunity


def _count_distinct_authors(session: Session, domain_id: uuid.UUID) -> int:
    return (
        session.query(Contact.id)
        .join(ContactSource, ContactSource.contact_id == Contact.id)
        .filter(
            Contact.domain_id == domain_id,
            Contact.name.isnot(None),
            ContactSource.page_type == ContactPageType.AUTHOR,
        )
        .distinct()
        .count()
    )
