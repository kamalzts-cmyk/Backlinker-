"""Phase 15: campaign funnel tracking. See PRODUCT_SPEC.md §4.7:

    Campaigns track the full funnel and its conversion at each step:
    sent -> delivered -> bounced -> opened -> clicked -> replied ->
    positive/negative reply -> unsubscribed -> published -> backlink
    detected -> backlink verified ... We do not build automated sending
    in v1.

There is no `send_email` function anywhere in this codebase. A
`Campaign` is a record a human creates *after* they've pitched a contact
through their own email client, and `record_event` is how they log each
funnel-stage transition as it happens in the real world (a reply
arrives, a bounce notice comes back, etc.) -- this module never sends
anything and never infers a stage from anything but an explicit call.

The one stage this module *can* check for real rather than take on
faith is the last one: `check_backlink_detected` queries the real
`backlinks` table (Phase 3) for a link from the contact's domain to the
`target_url` the human said they pitched. Because that table, by
construction, only ever holds links that already passed direct
verification (see `Backlink`'s model docstring -- a row only exists
after `verify_candidate` confirms it), a match here means the link is
already both *detected* and *verified* -- there's no real gap between
those two funnel stages in this project's data model, unlike a passive
monitoring crawl (Phase 16) that might see a link before independently
confirming it. Both events are recorded together, with a note in the
event detail explaining why, rather than pretending there were two
separate moments.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Backlink,
    Campaign,
    CampaignEvent,
    CampaignFunnelStage,
    Contact,
    OutreachStrategy,
)


def create_campaign(
    session: Session, *, outreach_strategy_id: uuid.UUID, target_url: str
) -> Campaign:
    """Creates the campaign record. This is not a send -- it's the human
    saying "I'm about to pitch/have pitched this asset to this contact."
    `target_url` is the human's own asset URL; this project has no
    content-asset-matching data source to derive it from instead.
    """
    strategy = session.get(OutreachStrategy, outreach_strategy_id)
    if strategy is None:
        raise ValueError(f"no outreach strategy with id {outreach_strategy_id}")

    campaign = Campaign(
        outreach_strategy_id=outreach_strategy_id,
        contact_id=strategy.contact_id,
        target_url=target_url,
        current_stage=None,
    )
    session.add(campaign)
    session.flush()
    return campaign


def record_event(
    session: Session,
    *,
    campaign_id: uuid.UUID,
    stage: CampaignFunnelStage,
    detail: str | None = None,
) -> CampaignEvent:
    """Appends a funnel-stage transition the human is telling us about
    (or, for BACKLINK_DETECTED/BACKLINK_VERIFIED, that
    `check_backlink_detected` confirmed against real data). No ordering
    is enforced -- a reply can arrive after a bounce notice, an
    unsubscribe can follow a positive reply, real outreach doesn't move
    through these stages in a strict line, and this project isn't going
    to invent a validation rule the spec doesn't ask for.
    """
    campaign = session.get(Campaign, campaign_id)
    if campaign is None:
        raise ValueError(f"no campaign with id {campaign_id}")

    now = datetime.now(UTC)
    event = CampaignEvent(campaign_id=campaign_id, stage=stage, detail=detail, occurred_at=now)
    session.add(event)
    campaign.current_stage = stage
    session.flush()
    return event


def check_backlink_detected(session: Session, *, campaign_id: uuid.UUID) -> Campaign:
    """Checks the real `backlinks` table for a verified link from the
    contact's domain to `campaign.target_url`. If found, records
    BACKLINK_DETECTED and BACKLINK_VERIFIED together (see module
    docstring for why there's no real gap between them here) and
    advances `current_stage`. If not found, the campaign is returned
    unchanged -- no fabricated progress.
    """
    campaign = session.get(Campaign, campaign_id)
    if campaign is None:
        raise ValueError(f"no campaign with id {campaign_id}")

    contact = session.get(Contact, campaign.contact_id)
    if contact is None:
        raise ValueError(f"no contact with id {campaign.contact_id}")

    backlink = session.scalar(
        select(Backlink).where(
            Backlink.source_domain_id == contact.domain_id,
            Backlink.target_url == campaign.target_url,
        )
    )
    if backlink is None:
        return campaign

    detail = (
        f"Verified backlink found at {backlink.source_url} -> {backlink.target_url} "
        f"(first seen {backlink.first_seen_at.isoformat()})"
    )
    now = datetime.now(UTC)
    session.add(
        CampaignEvent(
            campaign_id=campaign_id,
            stage=CampaignFunnelStage.BACKLINK_DETECTED,
            detail=detail,
            occurred_at=now,
        )
    )
    session.add(
        CampaignEvent(
            campaign_id=campaign_id,
            stage=CampaignFunnelStage.BACKLINK_VERIFIED,
            detail=(
                "Recorded in the same instant as BACKLINK_DETECTED -- this project's "
                "backlinks table only ever holds already-verified links, see module docstring."
            ),
            occurred_at=now,
        )
    )
    campaign.current_stage = CampaignFunnelStage.BACKLINK_VERIFIED
    session.flush()
    return campaign
