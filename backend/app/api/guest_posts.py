import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.errors import NotFoundError
from app.api.schemas import GuestPostOpportunityOut
from app.core.config import settings
from app.db.models import GuestPostOpportunity
from app.engines.guest_post.detect import discover_guest_post_opportunity

router = APIRouter(prefix="/guest-posts", tags=["guest-posts"])


class DiscoverGuestPostIn(BaseModel):
    start_url: str
    max_pages: int | None = None


@router.post("/discover", response_model=GuestPostOpportunityOut | None, status_code=200)
async def discover_guest_post(body: DiscoverGuestPostIn) -> GuestPostOpportunity | None:
    """Crawls `start_url` for real looking for a guest-post guideline
    page. Returns null (not an error) if none was found within the
    crawl budget -- an honest negative result, per
    app/engines/guest_post/detect.py's own docstring.
    """
    return await discover_guest_post_opportunity(
        body.start_url, max_pages=body.max_pages or settings.crawler_max_pages_per_job
    )


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
