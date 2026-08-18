"""Real end-to-end test that Phase 2 structured-metadata and contact-info
extraction actually lands in Postgres from a real crawl, not just that the
extractor functions work in isolation.
"""

import pytest
from sqlalchemy import select

from app.crawler.run import run_crawl
from app.db.base import session_scope
from app.db.models import Page
from app.tests.fixtures.server import FixtureServer


@pytest.mark.asyncio
async def test_crawl_persists_structured_metadata_and_contacts():
    with FixtureServer() as base_url:
        await run_crawl(f"{base_url}/rich_metadata.html", max_pages=1)

    with session_scope() as session:
        page = session.scalar(select(Page).where(Page.url.endswith("/rich_metadata.html")))
        assert page is not None

        assert page.open_graph["og:title"] == "Rich Metadata Fixture"
        assert page.twitter_card["twitter:card"] == "summary_large_image"
        assert len(page.schema_org) == 1
        assert page.schema_org[0]["@type"] == "Article"

        image_srcs = {img["src"] for img in page.images}
        assert any(src.endswith("/images/hero.jpg") for src in image_srcs)

        assert page.pdf_links == [f"{base_url}/reports/annual-report.pdf"]
        assert any("twitter.com/example" in link for link in page.social_links)
        assert page.embeds == ["https://www.youtube.com/embed/dQw4w9WgXcQ"]


@pytest.mark.asyncio
async def test_crawl_persists_contact_candidates():
    with FixtureServer() as base_url:
        await run_crawl(f"{base_url}/contact_page.html", max_pages=1)

    with session_scope() as session:
        page = session.scalar(select(Page).where(Page.url.endswith("/contact_page.html")))
        assert page is not None
        assert page.contact_emails == ["press@example.com"]
        assert "+1 555 987 6543" in page.contact_phones
