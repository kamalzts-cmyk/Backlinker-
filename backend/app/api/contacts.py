import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.errors import NotFoundError
from app.api.schemas import ContactOut
from app.core.config import settings
from app.db.models import Contact
from app.engines.contact.discover import discover_contacts_for_domain
from app.engines.contact.verify_email import verify_contact_email

router = APIRouter(prefix="/contacts", tags=["contacts"])


class DiscoverContactsIn(BaseModel):
    start_url: str
    max_pages: int | None = None


@router.get("", response_model=list[ContactOut])
def list_contacts(
    domain_id: uuid.UUID = Query(...),
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
) -> list[Contact]:
    return list(
        db.scalars(select(Contact).where(Contact.domain_id == domain_id).limit(limit))
    )


@router.post("/discover", response_model=list[ContactOut], status_code=201)
async def discover_contacts(body: DiscoverContactsIn) -> list[Contact]:
    """Crawls `start_url` for real (Phase 1/2 pipeline, reused) and
    returns whatever contacts Phase 8's classifier finds -- an empty
    list is an honest negative result, not an error, if the crawl-
    reachable pages don't include an about/contact/team page.
    """
    return await discover_contacts_for_domain(
        body.start_url, max_pages=body.max_pages or settings.crawler_max_pages_per_job
    )


@router.post("/{contact_id}/verify-email", response_model=ContactOut)
def verify_email(contact_id: uuid.UUID, db: Session = Depends(get_db)) -> Contact:
    contact = db.get(Contact, contact_id)
    if contact is None:
        raise NotFoundError(f"no such contact: {contact_id}")
    verify_contact_email(db, contact)
    return contact
