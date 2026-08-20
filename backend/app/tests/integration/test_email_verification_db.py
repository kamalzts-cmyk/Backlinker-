"""Real Postgres + real DNS: verify_contact_email() updates a real
Contact row and records a real EmailVerification history row.
"""

from sqlalchemy import select

from app.crawler.repository import get_or_create_domain
from app.db.base import session_scope
from app.db.models import Contact, ContactVerificationStatus, EmailVerification
from app.engines.contact.repository import get_or_create_contact
from app.engines.contact.verify_email import verify_contact_email


def test_verify_contact_email_updates_contact_and_records_history():
    with session_scope() as session:
        domain = get_or_create_domain(session, raw_host="verify-test.example")
        contact = get_or_create_contact(
            session, domain_id=domain.id, email="someone@gmail.com", phone=None
        )
        contact_id = contact.id

    with session_scope() as session:
        contact = session.get(Contact, contact_id)
        record = verify_contact_email(session, contact)

    assert record is not None
    assert record.result_status == ContactVerificationStatus.LIKELY

    with session_scope() as session:
        contact = session.get(Contact, contact_id)
        assert contact.verification_status == ContactVerificationStatus.LIKELY
        assert contact.confidence_score == 80

        history = session.scalars(
            select(EmailVerification).where(EmailVerification.contact_id == contact_id)
        ).all()
        assert len(history) == 1


def test_verify_contact_email_returns_none_for_phone_only_contact():
    with session_scope() as session:
        domain = get_or_create_domain(session, raw_host="phone-only.example")
        contact = get_or_create_contact(
            session, domain_id=domain.id, email=None, phone="+1 555 000 1111"
        )
        result = verify_contact_email(session, contact)

    assert result is None
