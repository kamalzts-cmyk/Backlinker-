"""Real integration tests for Phase 7: prospect discovery. The search
backend is a `FakeAISearchProvider` (same reasoning as the GEO and
search-discovery tests: no Anthropic API key configured for this
project's own deployment) returning realistic result-URL lists;
domain creation, deduplication, scoring, and upsert-on-recompute all run
for real against a real Postgres test database.
"""

import pytest
from sqlalchemy import select

from app.db.base import session_scope
from app.db.models import Prospect, ProspectCategory
from app.engines.prospects.discover import discover_prospects
from app.engines.search.provider import AISearchResult
from app.tests.fixtures.fake_ai_search_provider import FakeAISearchProvider


@pytest.mark.asyncio
async def test_discover_prospects_creates_one_per_distinct_host_with_a_real_score():
    # 4 categories -> 4 patterns, in the dict-insertion order defined in
    # discover.py: roundup, resource_page, guest_post_blog, industry_publication.
    provider = FakeAISearchProvider(
        [
            AISearchResult(
                answer_text="Widget Weekly covers the best widget tools.",
                citations=["https://widget-weekly.example/best-tools"],
            ),
            AISearchResult(
                answer_text="A curated widget resources page.",
                citations=["https://widget-resources.example/list"],
            ),
            AISearchResult(answer_text="", citations=[]),
            AISearchResult(
                answer_text="",
                citations=["https://widget-weekly.example/best-tools"],  # duplicate host
            ),
        ]
    )

    with session_scope() as session:
        created = await discover_prospects(session, topic="widget", provider=provider)

    assert len(provider.queries) == 4
    assert provider.queries[0] == '"best widget" tools'
    assert provider.queries[1] == '"widget" resources'

    hosts = {p.domain_id for p in created}
    assert len(hosts) == 2  # duplicate host across patterns not double-created

    categories = {p.category for p in created}
    assert categories == {ProspectCategory.ROUNDUP, ProspectCategory.RESOURCE_PAGE}

    roundup = next(p for p in created if p.category == ProspectCategory.ROUNDUP)
    assert roundup.topical_fit_score > 0  # "widget" appears in host + answer text
    assert any("roundup query" in e for e in roundup.evidence)


@pytest.mark.asyncio
async def test_discover_prospects_upserts_on_recompute_rather_than_duplicating():
    provider_1 = FakeAISearchProvider(
        [AISearchResult(answer_text="widget content", citations=["https://widget-site.example/a"])]
        + [AISearchResult(answer_text="", citations=[])] * 3
    )
    with session_scope() as session:
        first = await discover_prospects(session, topic="widget", provider=provider_1)
    assert len(first) == 1
    first_id = first[0].id

    provider_2 = FakeAISearchProvider(
        [AISearchResult(answer_text="updated widget content", citations=["https://widget-site.example/b"])]
        + [AISearchResult(answer_text="", citations=[])] * 3
    )
    with session_scope() as session:
        second = await discover_prospects(session, topic="widget", provider=provider_2)
    assert len(second) == 1
    assert second[0].id == first_id
    assert second[0].source_url == "https://widget-site.example/b"

    with session_scope() as session:
        persisted = session.scalars(select(Prospect).where(Prospect.topic_query == "widget")).all()
        assert len(persisted) == 1


@pytest.mark.asyncio
async def test_discover_prospects_returns_empty_when_no_results():
    provider = FakeAISearchProvider([AISearchResult(answer_text="", citations=[])] * 4)
    with session_scope() as session:
        created = await discover_prospects(session, topic="nonexistent-topic-xyz", provider=provider)
    assert created == []
