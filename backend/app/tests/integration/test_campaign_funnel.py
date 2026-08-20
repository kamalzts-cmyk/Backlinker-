"""Real integration tests for Phase 15: campaign funnel tracking. No
mocking anywhere -- creating a campaign, recording events, and detecting
a real backlink all run against the real fixture HTTP server, the real
Phase 3 verification pipeline, and a real Postgres test database. See
app/engines/campaigns/funnel.py's module docstring for why this project
never sends anything itself.
"""

import uuid

import pytest

from app.db.base import session_scope
from app.db.models import BacklinkSourceType, CampaignFunnelStage
from app.engines.backlink.repository import create_candidate
from app.engines.backlink.verify import verify_candidate
from app.engines.campaigns.funnel import check_backlink_detected, create_campaign, record_event
from app.engines.contact.discover import discover_contacts_for_domain
from app.engines.outreach.strategy import generate_outreach_strategy
from app.tests.fixtures.server import FixtureServer


@pytest.mark.asyncio
async def test_full_funnel_records_events_and_detects_a_real_verified_backlink():
    with FixtureServer() as base_url:
        contacts = await discover_contacts_for_domain(f"{base_url}/contact.html", max_pages=1)
        contact_id = contacts[0].id

        with session_scope() as session:
            strategy = await generate_outreach_strategy(session, contact_id=contact_id)
            strategy_id = strategy.id

        with session_scope() as session:
            campaign = create_campaign(
                session,
                outreach_strategy_id=strategy_id,
                target_url="https://example.com/follow-target",
            )
            campaign_id = campaign.id
            assert campaign.current_stage is None

        with session_scope() as session:
            record_event(session, campaign_id=campaign_id, stage=CampaignFunnelStage.SENT)
            record_event(session, campaign_id=campaign_id, stage=CampaignFunnelStage.OPENED)
            event = record_event(
                session,
                campaign_id=campaign_id,
                stage=CampaignFunnelStage.REPLIED,
                detail="Asked for more detail on the asset",
            )
            assert event.detail == "Asked for more detail on the asset"

        with session_scope() as session:
            from app.db.models import Campaign

            campaign = session.get(Campaign, campaign_id)
            assert campaign.current_stage == CampaignFunnelStage.REPLIED
            assert len(campaign.events) == 3

        # No matching backlink exists yet -- checking must not fabricate progress.
        with session_scope() as session:
            campaign = check_backlink_detected(session, campaign_id=campaign_id)
            assert campaign.current_stage == CampaignFunnelStage.REPLIED

        # Now create and verify a real backlink matching target_url, via
        # the real Phase 3 pipeline against the fixture server.
        with session_scope() as session:
            from app.crawler.repository import get_or_create_domain

            target_domain = get_or_create_domain(session, raw_host="example.com")
            candidate = create_candidate(
                session,
                source_url=f"{base_url}/index.html",
                target_url="https://example.com/follow-target",
                target_domain_id=target_domain.id,
                source_type=BacklinkSourceType.USER_PROVIDED,
            )
            candidate_id = candidate.id

        observation = await verify_candidate(candidate_id)
        assert observation is not None

        with session_scope() as session:
            campaign = check_backlink_detected(session, campaign_id=campaign_id)
            assert campaign.current_stage == CampaignFunnelStage.BACKLINK_VERIFIED

        with session_scope() as session:
            from app.db.models import Campaign

            campaign = session.get(Campaign, campaign_id)
            stages = [e.stage for e in campaign.events]
            assert CampaignFunnelStage.BACKLINK_DETECTED in stages
            assert CampaignFunnelStage.BACKLINK_VERIFIED in stages


@pytest.mark.asyncio
async def test_create_campaign_rejects_unknown_strategy():
    with session_scope() as session, pytest.raises(ValueError):
        create_campaign(
            session,
            outreach_strategy_id=uuid.uuid4(),
            target_url="https://example.com/whatever",
        )
