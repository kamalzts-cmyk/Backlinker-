"""Real end-to-end test of Phase 5: competitor tracking + link gap
computation. Uses distinct loopback addresses (127.0.0.2, .3, .4) as
genuinely separate "source domains" -- real HTTP servers, real crawls,
real Postgres rows, no mocking -- so the multi-domain gap logic is
exercised for real rather than against synthetic ORM objects.
"""

import pytest
from sqlalchemy import select

from app.crawler.normalize import registrable_domain_for_url
from app.crawler.repository import get_or_create_domain
from app.db.base import session_scope
from app.db.models import BacklinkSourceType, LinkGapConfidence, LinkGapOpportunity
from app.engines.backlink.repository import create_candidate
from app.engines.backlink.verify import verify_candidate
from app.engines.competitor.gap import compute_link_gap
from app.engines.competitor.repository import add_competitor
from app.tests.fixtures.server import FixtureServer


@pytest.mark.asyncio
async def test_link_gap_excludes_domains_already_linking_to_primary_and_tiers_by_overlap():
    with (
        FixtureServer(host="127.0.0.2") as both_url,
        FixtureServer(host="127.0.0.3") as a_only_url,
        FixtureServer(host="127.0.0.4") as a_and_primary_url,
    ):
        with session_scope() as session:
            primary = get_or_create_domain(session, raw_host="primary-brand.example")
            competitor_a = get_or_create_domain(session, raw_host="competitor-a.example")
            competitor_b = get_or_create_domain(session, raw_host="competitor-b.example")
            add_competitor(session, primary_domain_id=primary.id, competitor_domain_id=competitor_a.id)
            add_competitor(session, primary_domain_id=primary.id, competitor_domain_id=competitor_b.id)

            candidates = [
                create_candidate(
                    session,
                    source_url=f"{both_url}/links_both_competitors.html",
                    target_url="https://competitor-a.example/product",
                    target_domain_id=competitor_a.id,
                    source_type=BacklinkSourceType.USER_PROVIDED,
                ),
                create_candidate(
                    session,
                    source_url=f"{both_url}/links_both_competitors.html",
                    target_url="https://competitor-b.example/product",
                    target_domain_id=competitor_b.id,
                    source_type=BacklinkSourceType.USER_PROVIDED,
                ),
                create_candidate(
                    session,
                    source_url=f"{a_only_url}/links_competitor_a_only.html",
                    target_url="https://competitor-a.example/product",
                    target_domain_id=competitor_a.id,
                    source_type=BacklinkSourceType.USER_PROVIDED,
                ),
                create_candidate(
                    session,
                    source_url=f"{a_and_primary_url}/links_competitor_a_and_primary.html",
                    target_url="https://competitor-a.example/product",
                    target_domain_id=competitor_a.id,
                    source_type=BacklinkSourceType.USER_PROVIDED,
                ),
                create_candidate(
                    session,
                    source_url=f"{a_and_primary_url}/links_competitor_a_and_primary.html",
                    target_url="https://primary-brand.example/",
                    target_domain_id=primary.id,
                    source_type=BacklinkSourceType.USER_PROVIDED,
                ),
            ]
            candidate_ids = [c.id for c in candidates]
            primary_id = primary.id

        # Real, live-crawl direct verification for every candidate above
        # (Phase 3) -- this is what actually populates `backlinks`.
        for candidate_id in candidate_ids:
            observation = await verify_candidate(candidate_id)
            assert observation is not None, f"expected candidate {candidate_id} to verify"

        with session_scope() as session:
            opportunities = compute_link_gap(session, primary_domain_id=primary_id)

        both_host = registrable_domain_for_url(both_url)
        a_only_host = registrable_domain_for_url(a_only_url)
        a_and_primary_host = registrable_domain_for_url(a_and_primary_url)

        with session_scope() as session:
            both_domain = get_or_create_domain(session, raw_host=both_host)
            a_only_domain = get_or_create_domain(session, raw_host=a_only_host)
            a_and_primary_domain = get_or_create_domain(session, raw_host=a_and_primary_host)

            by_candidate = {o.candidate_domain_id: o for o in opportunities}

            assert both_domain.id in by_candidate
            assert by_candidate[both_domain.id].competitor_overlap_count == 2
            assert by_candidate[both_domain.id].confidence == LinkGapConfidence.MEDIUM

            assert a_only_domain.id in by_candidate
            assert by_candidate[a_only_domain.id].competitor_overlap_count == 1
            assert by_candidate[a_only_domain.id].confidence == LinkGapConfidence.LOW

            # already links to primary -- must NOT appear as a gap
            assert a_and_primary_domain.id not in by_candidate

            # and confirm it's really absent from the table, not just
            # from this call's return value
            persisted = session.scalars(
                select(LinkGapOpportunity).where(
                    LinkGapOpportunity.primary_domain_id == primary_id,
                    LinkGapOpportunity.candidate_domain_id == a_and_primary_domain.id,
                )
            ).all()
            assert persisted == []


@pytest.mark.asyncio
async def test_compute_link_gap_returns_empty_with_no_tracked_competitors():
    with session_scope() as session:
        primary = get_or_create_domain(session, raw_host="lonely-brand.example")
        primary_id = primary.id

    with session_scope() as session:
        assert compute_link_gap(session, primary_domain_id=primary_id) == []
