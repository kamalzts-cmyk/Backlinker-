"""Direct backlink verification. See docs/CRAWLER.md §6 and
PRODUCT_SPEC.md §4.2/§6 ("Direct backlink verification... We don't simply
say 'Backlink found.' We crawl the page ourselves.").

Reuses the Phase 1/2 crawl pipeline rather than re-implementing a fetch:
verifying a candidate is exactly "crawl this one URL and see what its
extracted outbound links actually are," which app.crawler.run.run_crawl
already does (robots/politeness, HTTP-then-Playwright, full extraction).
A single-page crawl is just run_crawl(url, max_pages=1).
"""

import uuid

from sqlalchemy import select

from app.crawler.extractors.links import LinkData
from app.crawler.normalize import normalize_url
from app.crawler.run import run_crawl
from app.db.base import session_scope
from app.db.models import (
    BacklinkCandidate,
    BacklinkObservation,
    BacklinkRejectionReason,
    CrawlError,
    CrawlErrorReason,
    CrawlRequest,
    Page,
    PageLink,
)
from app.engines.backlink.repository import record_verified_observation, reject_candidate

# Direct crawl verification is the highest-confidence source in the
# provenance model (PRODUCT_SPEC.md §2's table: "Directly crawled page" =
# Very High). Kept as a named constant rather than a magic number so the
# rationale is visible at the call site.
_DIRECT_CRAWL_CONFIDENCE = 95


async def verify_candidate(candidate_id: uuid.UUID) -> BacklinkObservation | None:
    """Crawl the candidate's source_url and either record a VERIFIED
    observation (if the target link is really there) or reject the
    candidate with a reason. Returns the observation, or None if
    rejected.
    """
    with session_scope() as session:
        candidate = session.get(BacklinkCandidate, candidate_id)
        if candidate is None:
            raise ValueError(f"no such backlink candidate: {candidate_id}")
        source_url = candidate.source_url
        target_url = candidate.target_url

    job_id = await run_crawl(source_url, max_pages=1)

    with session_scope() as session:
        candidate = session.get(BacklinkCandidate, candidate_id)
        normalized_source = normalize_url(source_url)

        # Scoped to *this* crawl job, not just URL: the same source_url
        # can legitimately be verified more than once (e.g. checked
        # against two different competitor targets), which would create
        # multiple Page rows with the same url across separate jobs.
        page = session.scalar(
            select(Page)
            .join(CrawlRequest, Page.crawl_request_id == CrawlRequest.id)
            .where(CrawlRequest.crawl_job_id == job_id, Page.url == normalized_source)
        )
        if page is None:
            return _reject_for_crawl_failure(session, candidate, job_id)

        # target_url on PageLink is the raw resolved URL, not normalized,
        # so compare on normalized form rather than exact string match.
        normalized_target = normalize_url(target_url)
        matching_link = next(
            (
                link
                for link in session.scalars(select(PageLink).where(PageLink.source_page_id == page.id))
                if normalize_url(link.target_url) == normalized_target
            ),
            None,
        )
        if matching_link is None:
            reject_candidate(session, candidate=candidate, reason=BacklinkRejectionReason.TARGET_NOT_FOUND)
            return None

        link_data = LinkData(
            target_url=matching_link.target_url,
            anchor_text=matching_link.anchor_text or "",
            surrounding_text=matching_link.surrounding_text or "",
            rel_nofollow=matching_link.rel_nofollow,
            rel_sponsored=matching_link.rel_sponsored,
            rel_ugc=matching_link.rel_ugc,
            target_blank=matching_link.target_blank,
            link_position=matching_link.link_position.value,
            is_internal=matching_link.is_internal,
        )

        return record_verified_observation(
            session,
            candidate=candidate,
            source_url=page.url,
            source_domain_id=page.domain_id,
            target_url=matching_link.target_url,
            target_domain_id=candidate.target_domain_id,
            link=link_data,
            source_canonical_url=page.canonical_url,
            source_http_status=page.http_status,
            source_is_indexable=page.is_indexable,
            crawl_request_id=page.crawl_request_id,
            confidence_score=_DIRECT_CRAWL_CONFIDENCE,
        )


def _reject_for_crawl_failure(session, candidate: BacklinkCandidate, job_id: uuid.UUID) -> None:
    error = session.scalar(
        select(CrawlError).where(CrawlError.crawl_job_id == job_id).order_by(CrawlError.occurred_at.desc())
    )
    reason = BacklinkRejectionReason.SOURCE_UNREACHABLE
    if error is not None and error.reason in (
        CrawlErrorReason.BLOCKED_ROBOTS,
        CrawlErrorReason.BLOCKED_CAPTCHA,
    ):
        reason = BacklinkRejectionReason.BLOCKED
    reject_candidate(session, candidate=candidate, reason=reason)
