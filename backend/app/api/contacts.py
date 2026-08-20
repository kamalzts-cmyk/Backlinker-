import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.errors import NotFoundError
from app.api.schemas import ContactOut
from app.db.models import Contact
from app.engines.contact.verify_email import verify_contact_email

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.get("", response_model=list[ContactOut])
def list_contacts(
    domain_id: uuid.UUID = Query(...),
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
) -> list[Contact]:
    return list(
        db.scalars(select(Contact).where(Contact.domain_id == domain_id).limit(limit))
    )


@router.post("/{contact_id}/verify-email", response_model=ContactOut)
def verify_email(contact_id: uuid.UUID, db: Session = Depends(get_db)) -> Contact:
    contact = db.get(Contact, contact_id)
    if contact is None:
        raise NotFoundError(f"no such contact: {contact_id}")
    verify_contact_email(db, contact)
    return contact
