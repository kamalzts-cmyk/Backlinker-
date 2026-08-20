"""Real end-to-end test of Phase 10: crawls a real fixture guideline page
(reusing the Phase 1/2 crawler) and confirms structured extraction plus
the distinct-authors proxy signal (reusing real Contact rows from Phase 8)
-- no mocking, real Postgres.
"""

import pytest

from app.engines.contact.discover import discover_contacts_for_domain
from app.engines.guest_post.detect import discover_guest_post_opportunity
from app.tests.fixtures.server import FixtureServer


@pytest.mark.asyncio
async def test_discover_guest_post_opportunity_extracts_real_guidelines():
    with FixtureServer() as base_url:
        # seed two distinct named authors on this domain first, so the
        # guest-post score's author-count signal has something real to
        # find (see app/engines/guest_post/detect.py's docstring on why
        # this is a proxy signal, not confirmed guest authorship).
        await discover_contacts_for_domain(f"{base_url}/author.html", max_pages=1)
        await discover_contacts_for_domain(f"{base_url}/author-schema.html", max_pages=1)

        opportunity = await discover_guest_post_opportunity(
            f"{base_url}/write-for-us-detailed.html", max_pages=1
        )

    assert opportunity is not None
    assert opportunity.guideline_page_url.endswith("/write-for-us-detailed.html")
    assert opportunity.word_count_min == 1200
    assert opportunity.word_count_max == 2000
    assert opportunity.mentions_dofollow is True
    assert opportunity.mentions_author_bio is True
    assert opportunity.mentions_sponsored is True  # "sponsored ... content will be rejected"
    assert opportunity.editor_email == "editor@example.com"
    assert opportunity.appears_closed is False
    assert opportunity.distinct_authors_observed == 2
    assert opportunity.guest_post_probability > 0
    assert any("distinct author" in e for e in opportunity.evidence)
    assert any("Editor contact" in e for e in opportunity.evidence)


@pytest.mark.asyncio
async def test_discover_guest_post_opportunity_detects_closed_submissions():
    with FixtureServer() as base_url:
        opportunity = await discover_guest_post_opportunity(
            f"{base_url}/contribute-closed.html", max_pages=1
        )

    assert opportunity is not None
    assert opportunity.appears_closed is True
    # penalty applied -- score should be lower than the base "page exists" points
    assert opportunity.guest_post_probability < 40


@pytest.mark.asyncio
async def test_discover_guest_post_opportunity_returns_none_when_no_guideline_page_found():
    with FixtureServer() as base_url:
        opportunity = await discover_guest_post_opportunity(f"{base_url}/canonical.html", max_pages=1)
    assert opportunity is None


@pytest.mark.asyncio
async def test_discover_guest_post_opportunity_upserts_on_recompute():
    with FixtureServer() as base_url:
        first = await discover_guest_post_opportunity(f"{base_url}/write-for-us-detailed.html", max_pages=1)
        second = await discover_guest_post_opportunity(f"{base_url}/write-for-us-detailed.html", max_pages=1)

    assert first.id == second.id  # same row updated, not duplicated
