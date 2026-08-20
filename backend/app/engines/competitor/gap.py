"""Link gap computation. See PRODUCT_SPEC.md §4.3 and §13-14:

    domains linking to competitors
    - domains linking to target
    = potential opportunities

Purely a query over existing `backlinks` rows -- discovering those rows
in the first place is Phase 3/4's job (direct verification, optionally
seeded by Common Crawl), run once with the primary domain as target and
again with each competitor as target. This module does not crawl
anything.
"""

import uuid
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Backlink, LinkGapConfidence, LinkGapOpportunity
from app.engines.competitor.repository import list_competitor_domain_ids


def _confidence_for_overlap(overlap_count: int) -> LinkGapConfidence:
    if overlap_count >= 3:
        return LinkGapConfidence.HIGH
    if overlap_count == 2:
        return LinkGapConfidence.MEDIUM
    return LinkGapConfidence.LOW


def compute_link_gap(session: Session, *, primary_domain_id: uuid.UUID) -> list[LinkGapOpportunity]:
    """Recompute (upsert) link-gap opportunities for primary_domain_id
    against all its tracked competitors. A candidate domain that already
    links to the primary domain is excluded -- it's not a gap.
    """
    competitor_domain_ids = list_competitor_domain_ids(session, primary_domain_id)
    if not competitor_domain_ids:
        return []

    already_linking_to_primary = set(
        session.scalars(
            select(Backlink.source_domain_id).where(Backlink.target_domain_id == primary_domain_id)
        )
    )

    overlap: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    rows = session.execute(
        select(Backlink.source_domain_id, Backlink.target_domain_id).where(
            Backlink.target_domain_id.in_(competitor_domain_ids)
        )
    ).all()
    for source_domain_id, competitor_id in rows:
        if source_domain_id == primary_domain_id or source_domain_id in already_linking_to_primary:
            continue
        overlap[source_domain_id].add(competitor_id)

    results = []
    for candidate_domain_id, competitors_linked in overlap.items():
        results.append(
            _upsert_gap_opportunity(
                session,
                primary_domain_id=primary_domain_id,
                candidate_domain_id=candidate_domain_id,
                competitor_domain_ids=competitors_linked,
            )
        )
    return results


def _upsert_gap_opportunity(
    session: Session,
    *,
    primary_domain_id: uuid.UUID,
    candidate_domain_id: uuid.UUID,
    competitor_domain_ids: set[uuid.UUID],
) -> LinkGapOpportunity:
    overlap_count = len(competitor_domain_ids)
    confidence = _confidence_for_overlap(overlap_count)
    domain_id_strings = sorted(str(d) for d in competitor_domain_ids)
    now = datetime.now(UTC)

    existing = session.scalar(
        select(LinkGapOpportunity).where(
            LinkGapOpportunity.primary_domain_id == primary_domain_id,
            LinkGapOpportunity.candidate_domain_id == candidate_domain_id,
        )
    )
    if existing is not None:
        existing.competitor_overlap_count = overlap_count
        existing.competitor_domain_ids = domain_id_strings
        existing.confidence = confidence
        existing.computed_at = now
        return existing

    opportunity = LinkGapOpportunity(
        primary_domain_id=primary_domain_id,
        candidate_domain_id=candidate_domain_id,
        competitor_overlap_count=overlap_count,
        competitor_domain_ids=domain_id_strings,
        confidence=confidence,
        computed_at=now,
    )
    session.add(opportunity)
    session.flush()
    return opportunity
