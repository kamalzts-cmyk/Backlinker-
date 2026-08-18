"""Real end-to-end test of the Phase 3 backlink verification pipeline:
crawls a real page via the actual crawler and checks whether a claimed
link is really there, writing real rows to Postgres. See
docs/CRAWLER.md §6 and app/engines/backlink/verify.py.
"""

import pytest
from sqlalchemy import select

from app.crawler.repository import get_or_create_domain
from app.db.base import session_scope
from app.db.models import (
    Backlink,
    BacklinkCandidate,
    BacklinkCandidateStatus,
    BacklinkLinkType,
    BacklinkRejectionReason,
    BacklinkSourceType,
)
from app.engines.backlink.repository import create_candidate
from app.engines.backlink.verify import verify_candidate
from app.tests.fixtures.server import FixtureServer


def _make_candidate(session, *, source_url: str, target_url: str, target_host: str) -> BacklinkCandidate:
    target_domain = get_or_create_domain(session, raw_host=target_host)
    return create_candidate(
        session,
        source_url=source_url,
        target_url=target_url,
        target_domain_id=target_domain.id,
        source_type=BacklinkSourceType.USER_PROVIDED,
        discovery_method="test",
    )


@pytest.mark.asyncio
async def test_verify_candidate_confirms_a_real_followed_link():
    with FixtureServer() as base_url:
        with session_scope() as session:
            candidate = _make_candidate(
                session,
                source_url=f"{base_url}/index.html",
                target_url="https://example.com/follow-target",
                target_host="example.com",
            )
            candidate_id = candidate.id

        observation = await verify_candidate(candidate_id)

    assert observation is not None
    assert observation.rel_nofollow is False
    assert observation.anchor_text == "Example Corp"
    assert "small businesses" in observation.surrounding_text

    with session_scope() as session:
        refreshed = session.get(BacklinkCandidate, candidate_id)
        assert refreshed.status == BacklinkCandidateStatus.VERIFIED
        assert refreshed.verified_at is not None

        backlink = session.scalar(
            select(Backlink).where(Backlink.target_url == "https://example.com/follow-target")
        )
        assert backlink is not None
        assert backlink.first_seen_at is not None
        assert backlink.latest_observation_id == observation.id


@pytest.mark.asyncio
async def test_verify_candidate_detects_nofollow_and_sponsored_correctly():
    with FixtureServer() as base_url:
        with session_scope() as session:
            nofollow_candidate = _make_candidate(
                session,
                source_url=f"{base_url}/index.html",
                target_url="https://example.com/nofollow-target",
                target_host="example.com",
            )
            sponsored_candidate = _make_candidate(
                session,
                source_url=f"{base_url}/index.html",
                target_url="https://example.com/sponsored-target",
                target_host="example.com",
            )
            nofollow_id, sponsored_id = nofollow_candidate.id, sponsored_candidate.id

        nofollow_obs = await verify_candidate(nofollow_id)
        sponsored_obs = await verify_candidate(sponsored_id)

    assert nofollow_obs.rel_nofollow is True
    assert sponsored_obs.rel_sponsored is True
    assert sponsored_obs.link_type == BacklinkLinkType.SPONSORED


@pytest.mark.asyncio
async def test_verify_candidate_rejects_when_target_link_not_present():
    with FixtureServer() as base_url:
        with session_scope() as session:
            candidate = _make_candidate(
                session,
                source_url=f"{base_url}/index.html",
                target_url="https://not-actually-linked.example/nope",
                target_host="not-actually-linked.example",
            )
            candidate_id = candidate.id

        observation = await verify_candidate(candidate_id)

    assert observation is None
    with session_scope() as session:
        refreshed = session.get(BacklinkCandidate, candidate_id)
        assert refreshed.status == BacklinkCandidateStatus.REJECTED
        assert refreshed.rejection_reason == BacklinkRejectionReason.TARGET_NOT_FOUND


@pytest.mark.asyncio
async def test_verify_candidate_rejects_when_source_is_unreachable():
    with FixtureServer() as base_url:
        with session_scope() as session:
            candidate = _make_candidate(
                session,
                source_url=f"{base_url}/does-not-exist.html",
                target_url="https://example.com/follow-target",
                target_host="example.com",
            )
            candidate_id = candidate.id

        observation = await verify_candidate(candidate_id)

    assert observation is None
    with session_scope() as session:
        refreshed = session.get(BacklinkCandidate, candidate_id)
        assert refreshed.status == BacklinkCandidateStatus.REJECTED
        assert refreshed.rejection_reason == BacklinkRejectionReason.SOURCE_UNREACHABLE
