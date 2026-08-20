"""Phase 14: outreach strategy generation. See PRODUCT_SPEC.md §4.7:

    AI does not write a pitch cold. It first produces an outreach
    strategy (opportunity type, target contact, reason, evidence,
    recommended content asset, angle, difficulty, expected link
    probability) and only then drafts personalized copy from that
    strategy. The model must never invent relationships, readership
    claims, statistics, credentials, or prior contact. Unknown facts are
    omitted, not fabricated.

This module builds the strategy step only. Copy drafting and sending are
out of scope here -- PRODUCT_SPEC.md §4.7/§26 is explicit that v1 has no
automated sending, and copy drafting from a strategy is a distinct,
later step this project hasn't built.

opportunity_type, reason, evidence, expected_link_probability, and
difficulty are all computed *deterministically* from rows this project
already verified: Phase 10's GuestPostOpportunity, Phase 5's
LinkGapOpportunity, and Phase 8/9's Contact. None of that comes from the
AI. The AI (an `AIProvider`, Phase 13) is used for exactly one thing:
synthesizing `angle`, a short suggested framing for outreach, and it is
explicitly instructed to use only the evidence it's handed and never
invent facts. If no `AIProvider` is passed, or generation fails, `angle`
is left `None` -- this project would rather publish no angle than a
plausible-sounding fabricated one.

`recommended_content_asset` is always `None`: content-asset matching
(PRODUCT_SPEC.md §4.8) needs a table of the user's own content assets,
which doesn't exist yet in this project -- not guessed here.
"""

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Contact,
    ContactVerificationStatus,
    Domain,
    GuestPostOpportunity,
    LinkGapConfidence,
    LinkGapOpportunity,
    OutreachDifficulty,
    OutreachOpportunityType,
    OutreachStrategy,
)
from app.engines.ai.errors import AIGenerationError
from app.engines.ai.provider import AIProvider

# Deterministic tier -> expected-probability mapping, consistent with the
# same LOW/MEDIUM/HIGH tiers compute_link_gap already assigns from
# competitor_overlap_count alone (app/engines/competitor/gap.py). This is
# a transparent heuristic derived from an existing deterministic signal,
# not a measured probability -- callers see it labeled as "derived from
# link-gap confidence tier" in the reason/evidence text, never presented
# as an observed conversion rate.
_LINK_GAP_PROBABILITY_BY_CONFIDENCE = {
    LinkGapConfidence.HIGH: 65,
    LinkGapConfidence.MEDIUM: 40,
    LinkGapConfidence.LOW: 20,
}

_ANGLE_SYSTEM_PROMPT = (
    "You are an SEO outreach strategist. Using ONLY the evidence provided "
    "below, write a single sentence suggesting a specific, concrete angle "
    "for outreach to this contact. Never invent facts, statistics, "
    "readership numbers, credentials, or any prior relationship not "
    "explicitly stated in the evidence. If the evidence does not support "
    "a concrete angle, say so plainly instead of inventing one."
)


class _AngleResponse(BaseModel):
    angle: str


async def generate_outreach_strategy(
    session: Session,
    *,
    contact_id: uuid.UUID,
    primary_domain_id: uuid.UUID | None = None,
    ai_provider: AIProvider | None = None,
) -> OutreachStrategy:
    """Builds (upserts) the outreach strategy for one contact.

    `primary_domain_id` is optional and only affects whether a
    link-gap-derived strategy can be considered -- a link gap is scoped
    to a specific primary domain (see LinkGapOpportunity), so without one
    this function can only find a guest-post-derived or generic strategy.
    """
    contact = session.get(Contact, contact_id)
    if contact is None:
        raise ValueError(f"no contact with id {contact_id}")
    domain_id = contact.domain_id

    guest_post = session.scalar(
        select(GuestPostOpportunity).where(GuestPostOpportunity.domain_id == domain_id)
    )
    link_gap = None
    if primary_domain_id is not None:
        link_gap = session.scalar(
            select(LinkGapOpportunity).where(
                LinkGapOpportunity.primary_domain_id == primary_domain_id,
                LinkGapOpportunity.candidate_domain_id == domain_id,
            )
        )

    if guest_post is not None:
        opportunity_type = OutreachOpportunityType.GUEST_POST
        reason, evidence, expected_link_probability = _guest_post_strategy(guest_post)
    elif link_gap is not None:
        opportunity_type = OutreachOpportunityType.LINK_GAP
        reason, evidence, expected_link_probability = _link_gap_strategy(session, link_gap)
    else:
        opportunity_type = OutreachOpportunityType.GENERIC
        reason, evidence, expected_link_probability = _generic_strategy(session, contact)

    difficulty = _difficulty(expected_link_probability, contact)

    angle: str | None = None
    ai_generated = False
    if ai_provider is not None:
        try:
            result = await ai_provider.generate_structured(
                prompt=f"Reason: {reason}\nEvidence:\n" + "\n".join(f"- {e}" for e in evidence),
                response_model=_AngleResponse,
                system=_ANGLE_SYSTEM_PROMPT,
            )
        except AIGenerationError:
            angle = None
            ai_generated = False
        else:
            angle = result.angle
            ai_generated = True

    return _upsert(
        session,
        domain_id=domain_id,
        contact_id=contact_id,
        opportunity_type=opportunity_type,
        guest_post_opportunity_id=guest_post.id if guest_post is not None else None,
        link_gap_opportunity_id=link_gap.id if link_gap is not None else None,
        reason=reason,
        evidence=evidence,
        angle=angle,
        ai_generated=ai_generated,
        expected_link_probability=expected_link_probability,
        difficulty=difficulty,
    )


def _guest_post_strategy(
    guest_post: GuestPostOpportunity,
) -> tuple[str, list[str], int]:
    probability = guest_post.guest_post_probability
    reason = (
        f"This domain has an active guest-post opportunity "
        f"(probability {probability}/100)."
    )
    evidence = list(guest_post.evidence)
    if guest_post.editor_email and not any(guest_post.editor_email in e for e in evidence):
        evidence.append(f"Editor contact available: {guest_post.editor_email}")
    return reason, evidence, probability


def _link_gap_strategy(
    session: Session, link_gap: LinkGapOpportunity
) -> tuple[str, list[str], int]:
    probability = _LINK_GAP_PROBABILITY_BY_CONFIDENCE[link_gap.confidence]
    reason = (
        f"This domain already links to {link_gap.competitor_overlap_count} tracked "
        f"competitor(s) but not yet to the primary domain -- a link-gap opportunity "
        f"({link_gap.confidence.value} confidence)."
    )
    evidence = list(link_gap.evidence)
    evidence.append(
        f"Expected link probability {probability}/100 is derived from the "
        f"{link_gap.confidence.value} link-gap confidence tier, not an observed rate."
    )
    return reason, evidence, probability


def _generic_strategy(session: Session, contact: Contact) -> tuple[str, list[str], None]:
    domain = session.get(Domain, contact.domain_id)
    host = domain.normalized_host if domain is not None else str(contact.domain_id)
    reason = (
        "No guest-post program or competitor link-gap signal has been detected for "
        f"{host} yet -- this is direct outreach based on contact availability alone."
    )
    evidence = [f"Contact discovered on {host}: {contact.email or contact.phone}"]
    if contact.name:
        evidence.append(f"Named contact: {contact.name}" + (f" ({contact.job_title})" if contact.job_title else ""))
    return reason, evidence, None


def _difficulty(expected_link_probability: int | None, contact: Contact) -> OutreachDifficulty:
    if contact.verification_status in (
        ContactVerificationStatus.UNKNOWN,
        ContactVerificationStatus.INVALID,
    ):
        return OutreachDifficulty.HIGH
    if expected_link_probability is None:
        return OutreachDifficulty.MEDIUM
    if expected_link_probability >= 70:
        return OutreachDifficulty.LOW
    if expected_link_probability >= 40:
        return OutreachDifficulty.MEDIUM
    return OutreachDifficulty.HIGH


def _upsert(
    session: Session,
    *,
    domain_id: uuid.UUID,
    contact_id: uuid.UUID,
    opportunity_type: OutreachOpportunityType,
    guest_post_opportunity_id: uuid.UUID | None,
    link_gap_opportunity_id: uuid.UUID | None,
    reason: str,
    evidence: list[str],
    angle: str | None,
    ai_generated: bool,
    expected_link_probability: int | None,
    difficulty: OutreachDifficulty,
) -> OutreachStrategy:
    existing = session.scalar(
        select(OutreachStrategy).where(OutreachStrategy.contact_id == contact_id)
    )
    now = datetime.now(UTC)

    if existing is not None:
        existing.domain_id = domain_id
        existing.opportunity_type = opportunity_type
        existing.guest_post_opportunity_id = guest_post_opportunity_id
        existing.link_gap_opportunity_id = link_gap_opportunity_id
        existing.reason = reason
        existing.evidence = evidence
        existing.angle = angle
        existing.ai_generated = ai_generated
        existing.expected_link_probability = expected_link_probability
        existing.difficulty = difficulty
        existing.computed_at = now
        session.flush()
        return existing

    strategy = OutreachStrategy(
        domain_id=domain_id,
        contact_id=contact_id,
        opportunity_type=opportunity_type,
        guest_post_opportunity_id=guest_post_opportunity_id,
        link_gap_opportunity_id=link_gap_opportunity_id,
        reason=reason,
        evidence=evidence,
        angle=angle,
        ai_generated=ai_generated,
        expected_link_probability=expected_link_probability,
        difficulty=difficulty,
        computed_at=now,
    )
    session.add(strategy)
    session.flush()
    return strategy
