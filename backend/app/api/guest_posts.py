import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.errors import NotFoundError
from app.api.schemas import GuestPostOpportunityOut
from app.db.models import GuestPostOpportunity

router = APIRouter(prefix="/guest-posts", tags=["guest-posts"])


@router.get("", response_model=list[GuestPostOpportunityOut])
def list_guest_post_opportunities(
    domain_id: uuid.UUID | None = Query(default=None), db: Session = Depends(get_db)
) -> list[GuestPostOpportunity]:
    stmt = select(GuestPostOpportunity)
    if domain_id is not None:
        stmt = stmt.where(GuestPostOpportunity.domain_id == domain_id)
    return list(db.scalars(stmt))


@router.get("/{opportunity_id}", response_model=GuestPostOpportunityOut)
def get_guest_post_opportunity(
    opportunity_id: uuid.UUID, db: Session = Depends(get_db)
) -> GuestPostOpportunity:
    opportunity = db.get(GuestPostOpportunity, opportunity_id)
    if opportunity is None:
        raise NotFoundError(f"no such guest-post opportunity: {opportunity_id}")
    return opportunity
