"""DB write helpers shared by the HTTP and Playwright crawl passes.

Kept separate from run.py so the orchestration logic isn't tangled with
SQLAlchemy session/query details.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.crawler.extractors.links import LinkData
from app.crawler.extractors.page import PageData
from app.crawler.normalize import normalize_host
from app.db.models import (
    CrawlError,
    CrawlErrorReason,
    CrawlMethod,
    CrawlRequest,
    Domain,
    LinkPosition,
    Page,
    PageLink,
)


def get_or_create_domain(session: Session, raw_host: str) -> Domain:
    normalized = normalize_host(raw_host)
    domain = session.scalar(select(Domain).where(Domain.normalized_host == normalized))
    if domain is not None:
        return domain
    domain = Domain(raw_host=raw_host, normalized_host=normalized)
    session.add(domain)
    session.flush()
    return domain


def record_crawl_request(
    session: Session,
    *,
    crawl_job_id: uuid.UUID,
    url: str,
    method: CrawlMethod,
    http_status: int | None,
    content_type: str | None,
    content_hash: str | None,
    html_hash: str | None,
    text_hash: str | None,
    structure_hash: str | None,
    timing_ms: int | None,
    redirect_chain: list[str] | None = None,
) -> CrawlRequest:
    request = CrawlRequest(
        crawl_job_id=crawl_job_id,
        url=url,
        method=method,
        http_status=http_status,
        content_type=content_type,
        content_hash=content_hash,
        html_hash=html_hash,
        text_hash=text_hash,
        structure_hash=structure_hash,
        timing_ms=timing_ms,
        redirect_chain=redirect_chain,
    )
    session.add(request)
    session.flush()
    return request


def record_crawl_error(
    session: Session, *, crawl_job_id: uuid.UUID, url: str, reason: CrawlErrorReason, detail: str | None
) -> CrawlError:
    error = CrawlError(crawl_job_id=crawl_job_id, url=url, reason=reason, detail=detail)
    session.add(error)
    session.flush()
    return error


def record_page(
    session: Session,
    *,
    domain: Domain,
    crawl_request_id: uuid.UUID,
    url: str,
    http_status: int | None,
    page_data: PageData,
    content_hash: str | None,
    html_hash: str | None,
    text_hash: str | None,
    structure_hash: str | None,
) -> Page:
    page = Page(
        domain_id=domain.id,
        crawl_request_id=crawl_request_id,
        url=url,
        canonical_url=page_data.canonical_url,
        http_status=http_status,
        title=page_data.title,
        meta_description=page_data.meta_description,
        h1=page_data.h1,
        headings=page_data.headings,
        word_count=page_data.word_count,
        language=page_data.language,
        robots_meta_noindex=page_data.robots_meta_noindex,
        robots_meta_nofollow=page_data.robots_meta_nofollow,
        is_indexable=not page_data.robots_meta_noindex,
        content_hash=content_hash,
        html_hash=html_hash,
        text_hash=text_hash,
        structure_hash=structure_hash,
    )
    session.add(page)
    session.flush()
    return page


def record_links(session: Session, *, page: Page, links: list[LinkData]) -> list[PageLink]:
    now = datetime.now(UTC)
    saved: list[PageLink] = []
    for link in links:
        target_domain = None
        if not link.is_internal:
            target_domain = get_or_create_domain(
                session, raw_host=_host_from_url(link.target_url)
            )
        page_link = PageLink(
            source_page_id=page.id,
            source_url=page.url,
            target_url=link.target_url,
            target_domain_id=target_domain.id if target_domain else None,
            anchor_text=link.anchor_text,
            surrounding_text=link.surrounding_text,
            rel_nofollow=link.rel_nofollow,
            rel_sponsored=link.rel_sponsored,
            rel_ugc=link.rel_ugc,
            target_blank=link.target_blank,
            link_position=LinkPosition(link.link_position),
            is_internal=link.is_internal,
            first_seen_at=now,
            last_seen_at=now,
        )
        session.add(page_link)
        saved.append(page_link)
    session.flush()
    return saved


def _host_from_url(url: str) -> str:
    from urllib.parse import urlsplit

    return urlsplit(url).hostname or ""
