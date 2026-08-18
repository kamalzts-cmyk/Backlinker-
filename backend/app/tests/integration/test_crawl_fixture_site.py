"""Real end-to-end crawl test: runs the actual Crawlee-based crawler
(app.crawler.run.run_crawl) against a real local HTTP server serving the
fixture site, writing to a real Postgres test database, then asserts on
the actual rows created -- per docs/ARCHITECTURE.md Phase 1 exit
criteria ("pages/links/errors land in DB, verified by manual inspection").

No mocked HTTP responses and no mocked database.
"""

import pytest
from sqlalchemy import select

from app.crawler.run import run_crawl
from app.db.base import session_scope
from app.db.models import CrawlError, CrawlJob, CrawlJobStatus, CrawlRequest, Page, PageLink
from app.tests.fixtures.server import FixtureServer


@pytest.mark.asyncio
async def test_crawl_fixture_site_end_to_end():
    with FixtureServer() as base_url:
        job_id = await run_crawl(f"{base_url}/index.html", max_pages=10)

    with session_scope() as session:
        job = session.get(CrawlJob, job_id)
        assert job is not None
        assert job.status == CrawlJobStatus.COMPLETED
        assert job.pages_crawled >= 1

        pages = session.scalars(select(Page)).all()
        assert len(pages) >= 1

        index_page = next(p for p in pages if p.url.endswith("/index.html"))
        assert index_page.title == "LinkIntel Fixture Site"
        assert index_page.word_count > 0
        assert index_page.http_status == 200
        assert index_page.content_hash is not None
        assert index_page.html_hash is not None

        requests = session.scalars(select(CrawlRequest).where(CrawlRequest.crawl_job_id == job_id)).all()
        assert any(r.http_status == 200 for r in requests)

        links = session.scalars(select(PageLink).where(PageLink.source_page_id == index_page.id)).all()
        by_target = {link.target_url: link for link in links}

        assert by_target["https://example.com/follow-target"].rel_nofollow is False
        assert by_target["https://example.com/nofollow-target"].rel_nofollow is True
        assert by_target["https://example.com/sponsored-target"].rel_sponsored is True
        assert by_target["https://example.com/ugc-target"].rel_ugc is True
        assert by_target["https://example.com/footer-target"].link_position.value == "footer"

        # the same-domain author page must have been discovered via
        # enqueue_links and crawled in the same job
        assert any(p.url.endswith("/author.html") for p in pages)


@pytest.mark.asyncio
async def test_crawl_records_broken_link_as_error_on_direct_visit():
    with FixtureServer() as base_url:
        job_id = await run_crawl(f"{base_url}/does-not-exist.html", max_pages=1)

    with session_scope() as session:
        errors = session.scalars(select(CrawlError).where(CrawlError.crawl_job_id == job_id)).all()
        assert len(errors) == 1
        assert errors[0].reason.value == "http_4xx"
        assert "404" in errors[0].detail


@pytest.mark.asyncio
async def test_crawl_robots_txt_is_cached_on_domain():
    from app.crawler.normalize import registrable_domain_for_url
    from app.db.models import Domain

    with FixtureServer() as base_url:
        crawled_host = registrable_domain_for_url(base_url)
        await run_crawl(f"{base_url}/index.html", max_pages=1)

    with session_scope() as session:
        # index.html also links out to example.com, which creates its own
        # (uncrawled) Domain row via record_links -- so look up the
        # crawled site's domain specifically rather than assuming there's
        # only one row.
        domain = session.scalar(select(Domain).where(Domain.normalized_host == crawled_host))
        assert domain is not None
        assert domain.robots_txt_raw is not None
        assert "User-agent" in domain.robots_txt_raw
        assert domain.robots_txt_fetched_at is not None
