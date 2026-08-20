"""Real end-to-end test of Phase 11: composite scores computed from
actual crawled/verified/discovered data (Phases 1-2, 5, 8, 10) against a
real Postgres database. No fabricated components -- confirms
unmeasurable ones (organic traffic, and topical relevance/link
probability without a reference domain) report as unavailable rather
than a guessed number.
"""

import pytest

from app.crawler.run import run_crawl
from app.db.base import session_scope
from app.db.models import BacklinkSourceType
from app.engines.backlink.repository import create_candidate
from app.engines.backlink.verify import verify_candidate
from app.engines.competitor.repository import add_competitor
from app.engines.contact.discover import discover_contacts_for_domain
from app.engines.guest_post.detect import discover_guest_post_opportunity
from app.engines.scoring.opportunity import compute_opportunity_score
from app.tests.fixtures.server import FixtureServer


@pytest.mark.asyncio
async def test_opportunity_score_standalone_no_reference_domain():
    with FixtureServer() as base_url:
        await run_crawl(f"{base_url}/index.html", max_pages=5)
        contacts = await discover_contacts_for_domain(f"{base_url}/contact.html", max_pages=1)
        domain_id = contacts[0].domain_id

    with session_scope() as session:
        score = compute_opportunity_score(session, domain_id=domain_id)

    by_name = {c["name"]: c for c in score.components}
    # measured, because we crawled real pages
    assert by_name["indexability"]["confidence"] == "measured"
    assert by_name["content_depth"]["confidence"] == "measured"
    assert by_name["contactability"]["confidence"] == "measured"
    # never fabricated
    assert by_name["organic_traffic"]["confidence"] == "unavailable"
    assert by_name["organic_traffic"]["value"] is None
    # no reference domain given -> these are honestly unavailable, not guessed
    assert by_name["topical_relevance"]["confidence"] == "unavailable"

    assert score.composite_score is not None
    assert 0 <= score.composite_score <= 100
    assert any("indexability" in e for e in score.evidence)


@pytest.mark.asyncio
async def test_opportunity_score_with_reference_domain_uses_link_gap_and_topical_overlap():
    with FixtureServer() as base_url:
        with session_scope() as session:
            from app.crawler.repository import get_or_create_domain

            primary = get_or_create_domain(session, raw_host="scoring-primary.example")
            # matches the target links_competitor_a_only.html actually
            # contains -- see its fixture source
            competitor = get_or_create_domain(session, raw_host="competitor-a.example")
            add_competitor(session, primary_domain_id=primary.id, competitor_domain_id=competitor.id)
            primary_id, competitor_id = primary.id, competitor.id

        # crawl the "reference" (primary) site for real, and the
        # candidate source page that links to the tracked competitor
        await run_crawl(f"{base_url}/index.html", max_pages=5)
        with session_scope() as session:
            candidate = create_candidate(
                session,
                source_url=f"{base_url}/links_competitor_a_only.html",
                target_url="https://competitor-a.example/product",
                target_domain_id=competitor_id,
                source_type=BacklinkSourceType.USER_PROVIDED,
            )
            candidate_id = candidate.id

        observation = await verify_candidate(candidate_id)
        assert observation is not None

        from app.engines.competitor.gap import compute_link_gap

        with session_scope() as session:
            compute_link_gap(session, primary_domain_id=primary_id)

        candidate_domain_id = None
        with session_scope() as session:
            from app.crawler.normalize import registrable_domain_for_url

            candidate_host = registrable_domain_for_url(base_url)
            from app.crawler.repository import get_or_create_domain

            candidate_domain_id = get_or_create_domain(session, raw_host=candidate_host).id

        with session_scope() as session:
            score = compute_opportunity_score(
                session, domain_id=candidate_domain_id, reference_domain_id=primary_id
            )

    by_name = {c["name"]: c for c in score.components}
    assert by_name["link_probability"]["confidence"] == "measured"
    assert by_name["link_probability"]["value"] > 0
    assert score.composite_score is not None


@pytest.mark.asyncio
async def test_opportunity_score_incorporates_guest_post_probability():
    with FixtureServer() as base_url:
        opportunity = await discover_guest_post_opportunity(
            f"{base_url}/write-for-us-detailed.html", max_pages=1
        )
        assert opportunity is not None

        with session_scope() as session:
            score = compute_opportunity_score(session, domain_id=opportunity.domain_id)

    by_name = {c["name"]: c for c in score.components}
    assert by_name["link_probability"]["confidence"] == "measured"
    assert "guest-post probability" in by_name["link_probability"]["detail"]


def test_opportunity_score_upserts_on_recompute():
    with session_scope() as session:
        from app.crawler.repository import get_or_create_domain

        domain = get_or_create_domain(session, raw_host="rescore-test.example")
        domain_id = domain.id

    with session_scope() as session:
        first = compute_opportunity_score(session, domain_id=domain_id)
        first_id = first.id

    with session_scope() as session:
        second = compute_opportunity_score(session, domain_id=domain_id)

    assert first_id == second.id
