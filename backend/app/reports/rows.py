"""Phase 17: report row builders. Each function is a pure read over data
this project already collected and verified -- reports never compute a
new fact, they just format existing rows for export. See
app/reports/export.py for the format-agnostic CSV/JSON/XLSX/PDF writers
and app/reports/reports.py for how the two are tied together.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Backlink,
    Contact,
    Domain,
    GuestPostOpportunity,
    LinkGapOpportunity,
    OpportunityScore,
)


def _host(session: Session, domain_id: uuid.UUID | None) -> str | None:
    if domain_id is None:
        return None
    domain = session.get(Domain, domain_id)
    return domain.normalized_host if domain is not None else str(domain_id)


def backlinks_rows(
    session: Session,
    *,
    target_domain_id: uuid.UUID | None = None,
    source_domain_id: uuid.UUID | None = None,
) -> list[dict]:
    stmt = select(Backlink)
    if target_domain_id is not None:
        stmt = stmt.where(Backlink.target_domain_id == target_domain_id)
    if source_domain_id is not None:
        stmt = stmt.where(Backlink.source_domain_id == source_domain_id)

    rows = []
    for backlink in session.scalars(stmt.order_by(Backlink.last_seen_at.desc())):
        observation = backlink.latest_observation
        rows.append(
            {
                "id": str(backlink.id),
                "source_url": backlink.source_url,
                "target_url": backlink.target_url,
                "source_host": _host(session, backlink.source_domain_id),
                "target_host": _host(session, backlink.target_domain_id),
                "anchor_text": observation.anchor_text if observation else None,
                "link_type": observation.link_type.value if observation else None,
                "rel_nofollow": observation.rel_nofollow if observation else None,
                "rel_sponsored": observation.rel_sponsored if observation else None,
                "rel_ugc": observation.rel_ugc if observation else None,
                "first_seen_at": backlink.first_seen_at.isoformat(),
                "last_seen_at": backlink.last_seen_at.isoformat(),
                "lost_at": backlink.lost_at.isoformat() if backlink.lost_at else None,
            }
        )
    return rows


def link_gap_rows(session: Session, *, primary_domain_id: uuid.UUID) -> list[dict]:
    stmt = select(LinkGapOpportunity).where(
        LinkGapOpportunity.primary_domain_id == primary_domain_id
    )
    rows = []
    for opp in session.scalars(stmt.order_by(LinkGapOpportunity.competitor_overlap_count.desc())):
        rows.append(
            {
                "id": str(opp.id),
                "candidate_host": _host(session, opp.candidate_domain_id),
                "competitor_overlap_count": opp.competitor_overlap_count,
                "confidence": opp.confidence.value,
                "evidence": "; ".join(opp.evidence),
                "computed_at": opp.computed_at.isoformat(),
            }
        )
    return rows


def contacts_rows(session: Session, *, domain_id: uuid.UUID) -> list[dict]:
    stmt = select(Contact).where(Contact.domain_id == domain_id)
    rows = []
    for contact in session.scalars(stmt.order_by(Contact.confidence_score.desc())):
        rows.append(
            {
                "id": str(contact.id),
                "domain_host": _host(session, contact.domain_id),
                "name": contact.name,
                "job_title": contact.job_title,
                "email": contact.email,
                "phone": contact.phone,
                "verification_status": contact.verification_status.value,
                "confidence_score": contact.confidence_score,
            }
        )
    return rows


def guest_post_rows(session: Session, *, domain_id: uuid.UUID | None = None) -> list[dict]:
    stmt = select(GuestPostOpportunity)
    if domain_id is not None:
        stmt = stmt.where(GuestPostOpportunity.domain_id == domain_id)
    rows = []
    for opp in session.scalars(stmt.order_by(GuestPostOpportunity.guest_post_probability.desc())):
        rows.append(
            {
                "id": str(opp.id),
                "domain_host": _host(session, opp.domain_id),
                "guideline_page_url": opp.guideline_page_url,
                "editor_email": opp.editor_email,
                "word_count_min": opp.word_count_min,
                "word_count_max": opp.word_count_max,
                "appears_closed": opp.appears_closed,
                "distinct_authors_observed": opp.distinct_authors_observed,
                "guest_post_probability": opp.guest_post_probability,
                "evidence": "; ".join(opp.evidence),
                "computed_at": opp.computed_at.isoformat(),
            }
        )
    return rows


def opportunity_score_rows(
    session: Session,
    *,
    domain_id: uuid.UUID | None = None,
    reference_domain_id: uuid.UUID | None = None,
) -> list[dict]:
    stmt = select(OpportunityScore)
    if domain_id is not None:
        stmt = stmt.where(OpportunityScore.domain_id == domain_id)
    if reference_domain_id is not None:
        stmt = stmt.where(OpportunityScore.reference_domain_id == reference_domain_id)
    rows = []
    for score in session.scalars(stmt.order_by(OpportunityScore.composite_score.desc())):
        rows.append(
            {
                "id": str(score.id),
                "domain_host": _host(session, score.domain_id),
                "reference_host": _host(session, score.reference_domain_id),
                "composite_score": score.composite_score,
                "evidence": "; ".join(score.evidence),
                "computed_at": score.computed_at.isoformat(),
            }
        )
    return rows
