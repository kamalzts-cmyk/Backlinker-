"""Real integration tests for Phase 7: search-pattern backlink
discovery. The search backend itself is a `FakeAISearchProvider` (same
reasoning as the GEO tests: this sandbox has no Anthropic API key
configured for this project's own deployment) returning realistic
result-URL lists; candidate creation and self-result filtering run for
real against a real Postgres test database.
"""

import pytest
from sqlalchemy import select

from app.crawler.repository import get_or_create_domain
from app.db.base import session_scope
from app.db.models import BacklinkCandidate, BacklinkSourceType
from app.engines.backlink.search_discovery import discover_candidates_from_search
from app.engines.search.provider import AISearchResult
from app.tests.fixtures.fake_ai_search_provider import FakeAISearchProvider


@pytest.mark.asyncio
async def test_discover_candidates_from_search_creates_one_per_distinct_result_url():
    with session_scope() as session:
        target_domain = get_or_create_domain(session, raw_host="search-target.example")
        target_domain_id = target_domain.id

    # 5 patterns are generated for a named-host query (base + -site: +
    # resources + according-to + filetype:pdf) -- queue one result set
    # per pattern, in the same order search_discovery.py generates them.
    provider = FakeAISearchProvider(
        [
            AISearchResult(
                answer_text="", citations=["https://publisher-a.example/post"]
            ),
            AISearchResult(
                answer_text="", citations=["https://publisher-b.example/resources"]
            ),
            AISearchResult(answer_text="", citations=[]),
            AISearchResult(
                answer_text="",
                citations=[
                    "https://publisher-a.example/post",  # duplicate across patterns
                    "https://search-target.example/self-page",  # self-result
                ],
            ),
            AISearchResult(answer_text="", citations=[]),
        ]
    )

    with session_scope() as session:
        target_domain = get_or_create_domain(session, raw_host="search-target.example")
        created = await discover_candidates_from_search(
            session,
            brand_query="Search Target Brand",
            target_domain=target_domain,
            target_url="https://search-target.example/guide",
            provider=provider,
        )

    assert len(provider.queries) == 5
    assert provider.queries[0] == '"Search Target Brand"'
    assert provider.queries[1] == '"Search Target Brand" -site:search-target.example'

    created_urls = {c.source_url for c in created}
    assert created_urls == {
        "https://publisher-a.example/post",
        "https://publisher-b.example/resources",
    }
    assert all(c.source_type == BacklinkSourceType.SEARCH_DISCOVERED for c in created)
    assert all(c.target_url == "https://search-target.example/guide" for c in created)

    with session_scope() as session:
        persisted = session.scalars(
            select(BacklinkCandidate).where(BacklinkCandidate.target_domain_id == target_domain_id)
        ).all()
        assert len(persisted) == 2  # no duplicate row for the repeated URL


@pytest.mark.asyncio
async def test_discover_candidates_from_search_respects_results_per_pattern():
    with session_scope() as session:
        target_domain = get_or_create_domain(session, raw_host="capped-target.example")

    provider = FakeAISearchProvider(
        [
            AISearchResult(
                answer_text="",
                citations=[f"https://publisher-{i}.example/post" for i in range(10)],
            )
        ]
        * 5
    )

    with session_scope() as session:
        target_domain = get_or_create_domain(session, raw_host="capped-target.example")
        created = await discover_candidates_from_search(
            session,
            brand_query="Capped Brand",
            target_domain=target_domain,
            target_url="https://capped-target.example/guide",
            provider=provider,
            results_per_pattern=2,
        )

    assert len(created) == 2


@pytest.mark.asyncio
async def test_discover_candidates_from_search_returns_empty_when_no_results():
    with session_scope() as session:
        target_domain = get_or_create_domain(session, raw_host="empty-target.example")

    provider = FakeAISearchProvider([AISearchResult(answer_text="", citations=[])] * 5)

    with session_scope() as session:
        target_domain = get_or_create_domain(session, raw_host="empty-target.example")
        created = await discover_candidates_from_search(
            session,
            brand_query="Empty Brand",
            target_domain=target_domain,
            target_url="https://empty-target.example/guide",
            provider=provider,
        )

    assert created == []
