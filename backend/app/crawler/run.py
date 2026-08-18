"""Crawl orchestration: robots/sitemap discovery, the HTTP-first pass,
JS-detection escalation to a Playwright pass, and DB persistence.

See docs/CRAWLER.md for the full design this implements.
"""

import logging
import uuid
from datetime import UTC, datetime
from urllib.parse import urlsplit

from crawlee import Request
from crawlee.crawlers import BeautifulSoupCrawlingContext, PlaywrightCrawlingContext

from app.core.config import settings
from app.crawler.extractors.contact import extract_contact_emails, extract_contact_phones
from app.crawler.extractors.links import extract_links
from app.crawler.extractors.page import extract_page_data
from app.crawler.extractors.schema import extract_structured_metadata
from app.crawler.fingerprint import content_hash, html_hash, structure_hash, text_hash
from app.crawler.http_crawler import build_http_crawler
from app.crawler.js_detection import looks_js_rendered
from app.crawler.normalize import normalize_url, registrable_domain_for_url
from app.crawler.playwright_crawler import build_playwright_crawler
from app.crawler.repository import (
    get_or_create_domain,
    record_crawl_error,
    record_crawl_request,
    record_links,
    record_page,
)
from app.crawler.robots import fetch_robots_txt, sitemap_urls_from_robots
from app.crawler.sitemap import default_sitemap_locations, discover_sitemap_urls
from app.db.base import session_scope
from app.db.models import CrawlErrorReason, CrawlJob, CrawlJobStatus, CrawlMethod, Domain

logger = logging.getLogger(__name__)


async def run_crawl(start_url: str, *, max_pages: int | None = None) -> uuid.UUID:
    """Crawl one site starting from start_url. Returns the CrawlJob id.

    Real network I/O throughout -- no simulated responses. Intended for
    both the integration test suite (pointed at a local fixture server)
    and real ad hoc crawls (pointed at a live site).
    """
    max_pages = max_pages or settings.crawler_max_pages_per_job
    start_url = normalize_url(start_url)
    host = registrable_domain_for_url(start_url)

    with session_scope() as session:
        domain = get_or_create_domain(session, raw_host=host)
        job = CrawlJob(
            domain_id=domain.id,
            start_url=start_url,
            status=CrawlJobStatus.RUNNING,
            max_pages=max_pages,
            started_at=datetime.now(UTC),
        )
        session.add(job)
        session.flush()
        job_id = job.id
        domain_id = domain.id

    sitemap_seed_urls = await _discover_seed_urls(start_url, domain_id)

    js_escalation_urls: list[str] = []
    pages_crawled = 0

    async def handle_http(context: BeautifulSoupCrawlingContext) -> None:
        nonlocal pages_crawled
        url = context.request.loaded_url or context.request.url
        status = context.http_response.status_code

        try:
            raw_bytes = await context.http_response.read()
            raw_html = raw_bytes.decode("utf-8", errors="ignore")
        except RuntimeError:  # body already consumed upstream by the parser
            raw_html = str(context.soup)

        if status >= 400:
            reason = CrawlErrorReason.HTTP_4XX if status < 500 else CrawlErrorReason.HTTP_5XX
            with session_scope() as session:
                record_crawl_error(
                    session, crawl_job_id=job_id, url=url, reason=reason, detail=f"HTTP {status}"
                )
            return

        if looks_js_rendered(raw_html):
            js_escalation_urls.append(url)
            return

        _persist_page(
            job_id=job_id,
            host=host,
            url=url,
            status=status,
            content_type=context.http_response.headers.get("content-type"),
            soup=context.soup,
            raw_html=raw_html,
            method=CrawlMethod.HTTP,
        )
        pages_crawled += 1
        await context.enqueue_links(strategy="same-domain")

    async def handle_failed(context, error: Exception) -> None:
        detail = str(error)
        reason = CrawlErrorReason.OTHER
        lowered = detail.lower()
        if "timeout" in lowered:
            reason = CrawlErrorReason.TIMEOUT
        elif "name or service not known" in lowered or "dns" in lowered:
            reason = CrawlErrorReason.DNS_FAIL
        with session_scope() as session:
            record_crawl_error(
                session,
                crawl_job_id=job_id,
                url=context.request.url,
                reason=reason,
                detail=detail[:2000],
            )

    http_crawler = build_http_crawler(
        max_pages=max_pages, request_handler=handle_http, failed_request_handler=handle_failed
    )
    seed_urls = [start_url, *sitemap_seed_urls[: max(max_pages - 1, 0)]]
    await http_crawler.run(seed_urls)

    if js_escalation_urls:
        await _run_playwright_pass(
            job_id=job_id,
            host=host,
            urls=js_escalation_urls[:max_pages],
            on_page_crawled=lambda: None,
        )

    with session_scope() as session:
        job = session.get(CrawlJob, job_id)
        job.status = CrawlJobStatus.COMPLETED
        job.finished_at = datetime.now(UTC)
        job.pages_crawled = pages_crawled

        domain = session.get(Domain, domain_id)
        domain.last_crawled_at = datetime.now(UTC)

    return job_id


async def _discover_seed_urls(start_url: str, domain_id: uuid.UUID) -> list[str]:
    origin = _origin(start_url)
    robots_txt = await fetch_robots_txt(origin)
    if robots_txt:
        with session_scope() as session:
            domain = session.get(Domain, domain_id)
            domain.robots_txt_raw = robots_txt
            domain.robots_txt_fetched_at = datetime.now(UTC)
        sitemap_locations = sitemap_urls_from_robots(robots_txt) or default_sitemap_locations(origin)
    else:
        sitemap_locations = default_sitemap_locations(origin)

    try:
        return await discover_sitemap_urls(sitemap_locations)
    except Exception:
        logger.warning("Sitemap discovery failed for %s", start_url, exc_info=True)
        return []


async def _run_playwright_pass(
    *, job_id: uuid.UUID, host: str, urls: list[str], on_page_crawled
) -> None:
    async def handle_playwright(context: PlaywrightCrawlingContext) -> None:
        url = context.request.loaded_url or context.request.url
        status = context.response.status if context.response else None
        html = await context.page.content()

        if status is not None and status >= 400:
            reason = CrawlErrorReason.HTTP_4XX if status < 500 else CrawlErrorReason.HTTP_5XX
            with session_scope() as session:
                record_crawl_error(
                    session, crawl_job_id=job_id, url=url, reason=reason, detail=f"HTTP {status}"
                )
            return

        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        _persist_page(
            job_id=job_id,
            host=host,
            url=url,
            status=status,
            content_type="text/html",
            soup=soup,
            raw_html=html,
            method=CrawlMethod.PLAYWRIGHT,
        )
        on_page_crawled()

    playwright_crawler = build_playwright_crawler(
        max_pages=len(urls), request_handler=handle_playwright
    )
    # These URLs were already visited (and marked handled) by the HTTP
    # pass before being escalated -- always_enqueue bypasses Crawlee's
    # dedup-by-unique-key so the escalation actually gets a Playwright
    # request instead of being silently skipped as "already handled".
    escalated_requests = [Request.from_url(url, always_enqueue=True) for url in urls]
    await playwright_crawler.run(escalated_requests)


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def _persist_page(*, job_id, host, url, status, content_type, soup, raw_html, method) -> None:
    page_data = extract_page_data(soup, url)
    links = extract_links(soup, url)
    structured_metadata = extract_structured_metadata(soup, url)
    contact_emails = extract_contact_emails(soup)
    contact_phones = extract_contact_phones(soup)

    c_hash = content_hash(raw_html)
    h_hash = html_hash(soup)
    t_hash = text_hash(soup)
    s_hash = structure_hash(soup)

    with session_scope() as session:
        domain = get_or_create_domain(session, raw_host=host)
        crawl_request = record_crawl_request(
            session,
            crawl_job_id=job_id,
            url=url,
            method=method,
            http_status=status,
            content_type=content_type,
            content_hash=c_hash,
            html_hash=h_hash,
            text_hash=t_hash,
            structure_hash=s_hash,
            timing_ms=None,
        )
        page = record_page(
            session,
            domain=domain,
            crawl_request_id=crawl_request.id,
            url=url,
            http_status=status,
            page_data=page_data,
            structured_metadata=structured_metadata,
            contact_emails=contact_emails,
            contact_phones=contact_phones,
            content_hash=c_hash,
            html_hash=h_hash,
            text_hash=t_hash,
            structure_hash=s_hash,
        )
        record_links(session, page=page, links=links)
