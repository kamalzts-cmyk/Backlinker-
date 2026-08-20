"""DB write helpers for the contact engine."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Contact, ContactPageType, ContactSource


def get_or_create_contact(
    session: Session, *, domain_id: uuid.UUID, email: str | None, phone: str | None
) -> Contact:
    if email is None and phone is None:
        raise ValueError("a contact needs at least an email or a phone")

    if email is not None:
        existing = session.scalar(
            select(Contact).where(Contact.domain_id == domain_id, Contact.email == email)
        )
    else:
        existing = session.scalar(
            select(Contact).where(Contact.domain_id == domain_id, Contact.phone == phone)
        )
    if existing is not None:
        if phone is not None and existing.phone is None:
            existing.phone = phone
        return existing

    contact = Contact(domain_id=domain_id, email=email, phone=phone)
    session.add(contact)
    session.flush()
    return contact


def add_source(
    session: Session,
    *,
    contact: Contact,
    source_url: str,
    page_type: ContactPageType,
    source_text: str | None,
) -> ContactSource | None:
    existing = session.scalar(
        select(ContactSource).where(
            ContactSource.contact_id == contact.id, ContactSource.source_url == source_url
        )
    )
    if existing is not None:
        return None

    source = ContactSource(
        contact_id=contact.id, source_url=source_url, page_type=page_type, source_text=source_text
    )
    session.add(source)
    session.flush()
    return source
