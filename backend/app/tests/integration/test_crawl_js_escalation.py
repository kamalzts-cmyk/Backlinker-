"""Real end-to-end test of the JS-detection escalation path: a page whose
HTTP-fetched HTML looks like an empty SPA shell must be re-crawled with a
real (headless) Playwright browser, per docs/CRAWLER.md §1.
"""

import pytest
from sqlalchemy import select

from app.crawler.run import run_crawl
from app.db.base import session_scope
from app.db.models import CrawlMethod, CrawlRequest, Page
from app.tests.fixtures.server import FixtureServer


@pytest.mark.asyncio
async def test_js_rendered_page_is_recrawled_with_playwright():
    with FixtureServer() as base_url:
        job_id = await run_crawl(f"{base_url}/js_rendered.html", max_pages=1)

    with session_scope() as session:
        pages = session.scalars(select(Page)).all()
        js_page = next((p for p in pages if p.url.endswith("/js_rendered.html")), None)
        assert js_page is not None, "JS-rendered fixture should have been crawled via the Playwright pass"

        request = session.scalar(
            select(CrawlRequest).where(
                CrawlRequest.crawl_job_id == job_id,
                CrawlRequest.url == js_page.url,
            )
        )
        assert request is not None
        assert request.method == CrawlMethod.PLAYWRIGHT
        assert js_page.title == "App"
