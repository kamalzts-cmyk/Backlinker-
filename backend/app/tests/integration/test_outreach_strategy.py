"""Real integration tests for Phase 14: outreach strategy generation.
Reuses the Phase 5 (link gap), Phase 8 (contacts), and Phase 10
(guest-post) engines against the real fixture HTTP server and a real
Postgres test database -- no mocked HTTP for any of the deterministic
data collection. Only the AI angle-synthesis step is exercised with
`FakeAIProvider` (see its docstring): this project cannot reach a real
Ollama server from this sandbox (Phase 13 caveat, docs/ARCHITECTURE.md
risk #17), and `FakeAIProvider` exists precisely so phases like this one
don't need to depend on that.
"""

import pytest

from app.crawler.repository import get_or_create_domain
from app.db.base import session_scope
from app.db.models import BacklinkSourceType, OutreachDifficulty, OutreachOpportunityType
from app.engines.backlink.repository import create_candidate
from app.engines.backlink.verify import verify_candidate
from app.engines.competitor.gap import compute_link_gap
from app.engines.competitor.repository import add_competitor
from app.engines.contact.discover import discover_contacts_for_domain
from app.engines.guest_post.detect import discover_guest_post_opportunity
from app.engines.outreach.strategy import _AngleResponse, generate_outreach_strategy
from app.tests.fixtures.fake_ai_provider import FakeAIProvider
from app.tests.fixtures.server import FixtureServer


@pytest.mark.asyncio
async def test_prefers_guest_post_strategy_when_available():
    with FixtureServer() as base_url:
        contacts = await discover_contacts_for_domain(f"{base_url}/contact.html", max_pages=1)
        guest_post = await discover_guest_post_opportunity(
            f"{base_url}/write-for-us-detailed.html", max_pages=1
        )
        assert guest_post is not None
        contact_id = contacts[0].id

        with session_scope() as session:
            strategy = await generate_outreach_strategy(session, contact_id=contact_id)

        assert strategy.opportunity_type == OutreachOpportunityType.GUEST_POST
        assert strategy.expected_link_probability == guest_post.guest_post_probability
        assert strategy.guest_post_opportunity_id == guest_post.id
        assert strategy.link_gap_opportunity_id is None
        assert strategy.angle is None
        assert strategy.ai_generated is False
        assert strategy.recommended_content_asset is None
        assert any("editor@example.com" in e for e in strategy.evidence)


@pytest.mark.asyncio
async def test_uses_link_gap_strategy_when_no_guest_post_opportunity():
    with FixtureServer(host="127.0.0.6") as source_url:
        with session_scope() as session:
            primary = get_or_create_domain(session, raw_host="outreach-primary.example")
            competitor = get_or_create_domain(session, raw_host="competitor-a.example")
            add_competitor(session, primary_domain_id=primary.id, competitor_domain_id=competitor.id)
            candidate = create_candidate(
                session,
                source_url=f"{source_url}/links_competitor_a_only.html",
                target_url="https://competitor-a.example/product",
                target_domain_id=competitor.id,
                source_type=BacklinkSourceType.USER_PROVIDED,
            )
            candidate_id, primary_id = candidate.id, primary.id

        observation = await verify_candidate(candidate_id)
        assert observation is not None

        contacts = await discover_contacts_for_domain(f"{source_url}/contact.html", max_pages=1)
        contact_id = contacts[0].id

        with session_scope() as session:
            opportunities = compute_link_gap(session, primary_domain_id=primary_id)
        assert len(opportunities) == 1

        with session_scope() as session:
            strategy = await generate_outreach_strategy(
                session, contact_id=contact_id, primary_domain_id=primary_id
            )

        assert strategy.opportunity_type == OutreachOpportunityType.LINK_GAP
        assert strategy.expected_link_probability == 20  # LOW confidence tier -> 20
        assert strategy.link_gap_opportunity_id is not None
        assert strategy.guest_post_opportunity_id is None
        assert any("competitor-a.example" in e for e in strategy.evidence)


@pytest.mark.asyncio
async def test_falls_back_to_generic_strategy_with_no_signal():
    with FixtureServer() as base_url:
        contacts = await discover_contacts_for_domain(f"{base_url}/contact.html", max_pages=1)
        contact_id = contacts[0].id

        with session_scope() as session:
            strategy = await generate_outreach_strategy(session, contact_id=contact_id)

        assert strategy.opportunity_type == OutreachOpportunityType.GENERIC
        assert strategy.expected_link_probability is None
        assert strategy.difficulty == OutreachDifficulty.MEDIUM  # role_address, no probability signal


@pytest.mark.asyncio
async def test_ai_angle_is_populated_from_a_fake_provider():
    with FixtureServer() as base_url:
        contacts = await discover_contacts_for_domain(f"{base_url}/contact.html", max_pages=1)
        contact_id = contacts[0].id

        provider = FakeAIProvider([_AngleResponse(angle="Mention the shared industry focus.")])
        with session_scope() as session:
            strategy = await generate_outreach_strategy(
                session, contact_id=contact_id, ai_provider=provider
            )

        assert strategy.angle == "Mention the shared industry focus."
        assert strategy.ai_generated is True
        assert len(provider.calls) == 1
        assert "never invent" in provider.calls[0]["system"].lower()


@pytest.mark.asyncio
async def test_ai_failure_leaves_angle_none_rather_than_fabricated():
    with FixtureServer() as base_url:
        contacts = await discover_contacts_for_domain(f"{base_url}/contact.html", max_pages=1)
        contact_id = contacts[0].id

        provider = FakeAIProvider([])  # no queued response -> raises AIGenerationError
        with session_scope() as session:
            strategy = await generate_outreach_strategy(
                session, contact_id=contact_id, ai_provider=provider
            )

        assert strategy.angle is None
        assert strategy.ai_generated is False


@pytest.mark.asyncio
async def test_regenerating_a_strategy_upserts_rather_than_duplicating():
    with FixtureServer() as base_url:
        contacts = await discover_contacts_for_domain(f"{base_url}/contact.html", max_pages=1)
        contact_id = contacts[0].id

        with session_scope() as session:
            first = await generate_outreach_strategy(session, contact_id=contact_id)
            first_id = first.id

        with session_scope() as session:
            second = await generate_outreach_strategy(session, contact_id=contact_id)

        assert second.id == first_id
