"""Contact discovery. See PRODUCT_SPEC.md §4.6 and docs/CRAWLER.md.

Discovery reuses the Phase 1/2 crawl pipeline exactly like Phase 3's
backlink verification does: crawling a domain to find its contact pages
is just run_crawl(homepage, max_pages=N) -- same-domain link-following
naturally reaches /about, /contact, /team, etc. from nav/footer links on
a normally-structured site. This module's job starts once pages exist:
classify which ones are contact-relevant, and turn what they plainly
contain (Phase 2's page.contact_emails/contact_phones/schema_org) into
Contact rows with provenance.

Deliberately does NOT guess a name/role pairing beyond two safe cases:
schema.org Person markup (explicit, structured), and an unambiguous
single-person page (exactly one h1 and one email on the page -- the
common "author bio" shape). Anything else stays an unattributed
email/phone contact rather than a mis-attributed one.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.crawler.run import run_crawl
from app.db.base import session_scope
from app.db.models import Contact, ContactVerificationStatus, CrawlRequest, Page
from app.engines.contact.classify import classify_page_type, is_role_address
from app.engines.contact.repository import add_source, get_or_create_contact

# Deterministic confidence per status -- not a substitute for Phase 9
# email verification, just a starting point reflecting how the contact
# was found.
_CONFIDENCE_BY_STATUS = {
    ContactVerificationStatus.DIRECTLY_PUBLISHED: 90,
    ContactVerificationStatus.ROLE_ADDRESS: 70,
    ContactVerificationStatus.UNKNOWN: 40,
}


def _is_person_schema(obj: dict) -> bool:
    schema_type = obj.get("@type")
    if isinstance(schema_type, list):
        return "Person" in schema_type
    return schema_type == "Person"


def _clean_str(value) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


async def discover_contacts_for_domain(start_url: str, *, max_pages: int = 20) -> list[Contact]:
    job_id = await run_crawl(start_url, max_pages=max_pages)

    with session_scope() as session:
        pages = session.scalars(
            select(Page)
            .join(CrawlRequest, Page.crawl_request_id == CrawlRequest.id)
            .where(CrawlRequest.crawl_job_id == job_id)
        ).all()

        contacts: dict[uuid.UUID, Contact] = {}
        for page in pages:
            for contact in extract_contacts_from_page(session, page):
                contacts[contact.id] = contact
        return list(contacts.values())


def extract_contacts_from_page(session: Session, page: Page) -> list[Contact]:
    page_type = classify_page_type(page.url)
    if page_type is None:
        return []

    contacts: list[Contact] = []
    emails_from_schema: set[str] = set()

    for obj in page.schema_org or []:
        if not isinstance(obj, dict) or not _is_person_schema(obj):
            continue
        email = _clean_str(obj.get("email"))
        if email is None:
            continue
        email = email.removeprefix("mailto:")
        name = _clean_str(obj.get("name"))
        job_title = _clean_str(obj.get("jobTitle"))

        contact = get_or_create_contact(session, domain_id=page.domain_id, email=email, phone=None)
        contact.name = contact.name or name
        contact.job_title = contact.job_title or job_title
        contact.verification_status = ContactVerificationStatus.DIRECTLY_PUBLISHED
        contact.confidence_score = _CONFIDENCE_BY_STATUS[ContactVerificationStatus.DIRECTLY_PUBLISHED]
        add_source(
            session,
            contact=contact,
            source_url=page.url,
            page_type=page_type,
            source_text=f"schema.org Person: {name or email}",
        )
        contacts.append(contact)
        emails_from_schema.add(email)

    plain_emails = [e for e in (page.contact_emails or []) if e not in emails_from_schema]
    # Exactly one heading and one email is the "single-person bio page"
    # shape (see app/tests/fixtures/html/author.html) -- safe to pair.
    single_person_name = (
        page.h1[0] if page.h1 and len(page.h1) == 1 and len(plain_emails) == 1 else None
    )

    for email in plain_emails:
        contact = get_or_create_contact(session, domain_id=page.domain_id, email=email, phone=None)
        if contact.name is None and single_person_name:
            contact.name = single_person_name
        status = (
            ContactVerificationStatus.ROLE_ADDRESS
            if is_role_address(email)
            else ContactVerificationStatus.DIRECTLY_PUBLISHED
        )
        contact.verification_status = status
        contact.confidence_score = _CONFIDENCE_BY_STATUS[status]
        add_source(session, contact=contact, source_url=page.url, page_type=page_type, source_text=None)
        contacts.append(contact)

    # Attach the page's phone(s) to the single-person contact if there is
    # exactly one of each; otherwise record them as standalone
    # phone-only contacts rather than guessing whose number it is.
    phones = page.contact_phones or []
    if len(phones) == 1 and len(plain_emails) == 1:
        contacts[-1].phone = contacts[-1].phone or phones[0]
    else:
        for phone in phones:
            contact = get_or_create_contact(session, domain_id=page.domain_id, email=None, phone=phone)
            if contact.verification_status == ContactVerificationStatus.UNKNOWN:
                contact.verification_status = ContactVerificationStatus.DIRECTLY_PUBLISHED
                contact.confidence_score = _CONFIDENCE_BY_STATUS[
                    ContactVerificationStatus.DIRECTLY_PUBLISHED
                ]
            add_source(session, contact=contact, source_url=page.url, page_type=page_type, source_text=None)
            contacts.append(contact)

    return contacts
