"""Real integration tests for Phase 18: AI-search / GEO intelligence.
No live answer engine exists to test against (see app/db/models.py's
Phase 18 comment for why) -- `check_citation`'s deterministic
citation-matching logic is proven against a `FakeAISearchProvider`
returning realistic citation URL lists, and `record_manual_observation`
is proven for real against a real Postgres test database with no
mocking at all.
"""

import uuid

import pytest

from app.crawler.repository import get_or_create_domain
from app.db.base import session_scope
from app.db.models import GEOCitationResult, GEOObservation
from app.engines.geo.citations import check_citation, record_manual_observation
from app.engines.search.provider import AISearchResult
from app.tests.fixtures.fake_ai_search_provider import FakeAISearchProvider


def test_record_manual_observation_persists_a_cited_result():
    with session_scope() as session:
        domain = get_or_create_domain(session, raw_host="geo-example.com")
        observation = record_manual_observation(
            session,
            query="best backlink intelligence tools",
            engine="chatgpt_search",
            target_domain_id=domain.id,
            observed_result=GEOCitationResult.CITED,
            source_url="https://geo-example.com/guide",
            answer_excerpt="One option is Geo Example's guide...",
        )
        observation_id = observation.id

    with session_scope() as session:
        persisted = session.get(GEOObservation, observation_id)
        assert persisted.observed_result == GEOCitationResult.CITED
        assert persisted.source_url == "https://geo-example.com/guide"


def test_record_manual_observation_rejects_cited_without_source_url():
    with session_scope() as session:
        domain = get_or_create_domain(session, raw_host="geo-example-2.com")
        with pytest.raises(ValueError):
            record_manual_observation(
                session,
                query="anything",
                engine="perplexity",
                target_domain_id=domain.id,
                observed_result=GEOCitationResult.CITED,
            )


@pytest.mark.asyncio
async def test_check_citation_detects_a_real_matching_url_from_fake_provider():
    with session_scope() as session:
        domain = get_or_create_domain(session, raw_host="cited-example.com")
        domain_id = domain.id

    provider = FakeAISearchProvider(
        [
            AISearchResult(
                answer_text="According to Cited Example, backlinks matter.",
                citations=[
                    "https://cited-example.com/backlinks-guide",
                    "https://unrelated-site.example/post",
                ],
            )
        ]
    )

    with session_scope() as session:
        observation = await check_citation(
            session,
            query="do backlinks still matter",
            engine="fake_engine",
            target_domain_id=domain_id,
            provider=provider,
        )

    assert observation.observed_result == GEOCitationResult.CITED
    assert observation.source_url == "https://cited-example.com/backlinks-guide"
    assert provider.queries == ["do backlinks still matter"]


@pytest.mark.asyncio
async def test_check_citation_records_not_cited_when_no_url_matches():
    with session_scope() as session:
        domain = get_or_create_domain(session, raw_host="not-cited-example.com")
        domain_id = domain.id

    provider = FakeAISearchProvider(
        [
            AISearchResult(
                answer_text="Several other publishers cover this topic.",
                citations=["https://competitor-a.example/post", "https://competitor-b.example/post"],
            )
        ]
    )

    with session_scope() as session:
        observation = await check_citation(
            session,
            query="who covers this topic",
            engine="fake_engine",
            target_domain_id=domain_id,
            provider=provider,
        )

    assert observation.observed_result == GEOCitationResult.NOT_CITED
    assert observation.source_url is None


@pytest.mark.asyncio
async def test_check_citation_raises_for_unknown_domain():
    provider = FakeAISearchProvider([AISearchResult(answer_text="", citations=[])])
    with session_scope() as session, pytest.raises(ValueError):
        await check_citation(
            session,
            query="x",
            engine="fake_engine",
            target_domain_id=uuid.uuid4(),
            provider=provider,
        )
