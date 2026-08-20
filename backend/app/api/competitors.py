import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.errors import NotFoundError
from app.api.schemas import CompetitorRelationshipOut, LinkGapOpportunityOut
from app.crawler.repository import get_or_create_domain
from app.db.models import Domain
from app.engines.competitor.gap import compute_link_gap
from app.engines.competitor.repository import add_competitor, list_competitor_domain_ids

router = APIRouter(tags=["competitors"])


class AddCompetitorIn(BaseModel):
    primary_domain_id: uuid.UUID
    competitor_host: str


@router.post("/competitors", response_model=CompetitorRelationshipOut, status_code=201)
def create_competitor(body: AddCompetitorIn, db: Session = Depends(get_db)) -> CompetitorRelationshipOut:
    primary = db.get(Domain, body.primary_domain_id)
    if primary is None:
        raise NotFoundError(f"no such domain: {body.primary_domain_id}")

    competitor_domain = get_or_create_domain(db, raw_host=body.competitor_host)
    relationship = add_competitor(
        db, primary_domain_id=primary.id, competitor_domain_id=competitor_domain.id
    )
    return CompetitorRelationshipOut(
        id=relationship.id,
        primary_domain_id=relationship.primary_domain_id,
        competitor_domain_id=relationship.competitor_domain_id,
        competitor_host=competitor_domain.normalized_host,
    )


@router.get("/competitors", response_model=list[CompetitorRelationshipOut])
def list_competitors(
    primary_domain_id: uuid.UUID = Query(...), db: Session = Depends(get_db)
) -> list[CompetitorRelationshipOut]:
    competitor_ids = list_competitor_domain_ids(db, primary_domain_id)
    if not competitor_ids:
        return []
    domains = {d.id: d for d in db.scalars(select(Domain).where(Domain.id.in_(competitor_ids)))}
    return [
        CompetitorRelationshipOut(
            id=uuid.uuid4(),  # relationship id not needed for this read view
            primary_domain_id=primary_domain_id,
            competitor_domain_id=cid,
            competitor_host=domains[cid].normalized_host,
        )
        for cid in competitor_ids
        if cid in domains
    ]


@router.get("/link-gaps", response_model=list[LinkGapOpportunityOut])
def get_link_gaps(
    primary_domain_id: uuid.UUID = Query(...), db: Session = Depends(get_db)
) -> list[LinkGapOpportunityOut]:
    """Recomputes on every call -- link gaps are cheap to derive from
    existing `backlinks` rows (see app/engines/competitor/gap.py), so
    there's no separate "stale until refreshed" state to manage yet.
    """
    opportunities = compute_link_gap(db, primary_domain_id=primary_domain_id)
    if not opportunities:
        return []

    domain_ids = {o.candidate_domain_id for o in opportunities}
    for o in opportunities:
        domain_ids.update(uuid.UUID(d) for d in o.competitor_domain_ids)
    domains = {d.id: d for d in db.scalars(select(Domain).where(Domain.id.in_(domain_ids)))}

    return [
        LinkGapOpportunityOut(
            id=o.id,
            candidate_domain_id=o.candidate_domain_id,
            candidate_host=domains[o.candidate_domain_id].normalized_host,
            competitor_overlap_count=o.competitor_overlap_count,
            competitor_hosts=sorted(
                domains[uuid.UUID(d)].normalized_host
                for d in o.competitor_domain_ids
                if uuid.UUID(d) in domains
            ),
            confidence=o.confidence,
            computed_at=o.computed_at,
        )
        for o in opportunities
    ]
