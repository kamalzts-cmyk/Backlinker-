"""Real end-to-end test of Phase 8: crawls a real fixture site (reusing
the Phase 1/2 crawler -- no separate contact-crawling mechanism) and
confirms contacts are extracted with correct provenance, correct
role-address vs. directly-published classification, correct schema.org
Person handling, and -- importantly -- correct *refusal* to guess a
name/email pairing on an ambiguous multi-person page.
"""

import pytest
from sqlalchemy import select

from app.db.base import session_scope
from app.db.models import Contact, ContactVerificationStatus
from app.engines.contact.discover import discover_contacts_for_domain
from app.tests.fixtures.server import FixtureServer


@pytest.mark.asyncio
async def test_discover_contacts_from_a_real_multi_page_site():
    with FixtureServer() as base_url:
        # index.html links to /author.html; contact.html, team.html, and
        # write-for-us.html aren't linked from anywhere in the fixture
        # site, so crawl each directly to make sure they're all reached.
        contacts = []
        for path in ("/index.html", "/contact.html", "/team.html", "/write-for-us.html", "/author-schema.html"):
            contacts.extend(await discover_contacts_for_domain(f"{base_url}{path}", max_pages=5))

    with session_scope() as session:
        all_contacts = session.scalars(select(Contact)).all()
        by_email = {c.email: c for c in all_contacts if c.email}

        # role addresses correctly classified
        assert by_email["info@example.com"].verification_status == ContactVerificationStatus.ROLE_ADDRESS
        assert by_email["press@example.com"].verification_status == ContactVerificationStatus.ROLE_ADDRESS
        assert by_email["editor@example.com"].verification_status == ContactVerificationStatus.ROLE_ADDRESS

        # single-person page (author.html): name paired from the h1
        jane = by_email["jane.doe@example.com"]
        assert jane.name == "Jane Doe"
        assert jane.verification_status == ContactVerificationStatus.DIRECTLY_PUBLISHED

        # schema.org Person: structured name + job title, no guessing needed
        john = by_email["john.smith@example.com"]
        assert john.name == "John Smith"
        assert john.job_title == "Senior Editor"

        # ambiguous multi-person page (team.html): emails found, but NOT
        # paired with a name -- pairing "Our Team" to either would be a
        # fabrication
        sarah = by_email["sarah@example.com"]
        mike = by_email["mike@example.com"]
        assert sarah.name is None
        assert mike.name is None

        # every contact has at least one recorded source with the right
        # page-type classification
        assert any(s.page_type.value == "team" for s in sarah.sources)
        assert any(s.page_type.value == "contact" for s in by_email["info@example.com"].sources)
        assert any(s.page_type.value == "guest_post" for s in by_email["editor@example.com"].sources)


@pytest.mark.asyncio
async def test_discover_contacts_skips_non_contact_pages():
    with FixtureServer() as base_url:
        # index.html itself isn't a contact-relevant page type (not
        # home-page-only content -- it's classified HOME, which we do
        # extract from, but a generic /blog-style page should not be).
        contacts = await discover_contacts_for_domain(f"{base_url}/canonical.html", max_pages=1)
    assert contacts == []


@pytest.mark.asyncio
async def test_discover_contacts_dedupes_same_email_across_pages():
    with FixtureServer() as base_url:
        first = await discover_contacts_for_domain(f"{base_url}/contact.html", max_pages=1)
        second = await discover_contacts_for_domain(f"{base_url}/contact.html", max_pages=1)

    assert len(first) == len(second) == 2  # info@ and press@
    with session_scope() as session:
        info_contacts = session.scalars(
            select(Contact).where(Contact.email == "info@example.com")
        ).all()
        assert len(info_contacts) == 1  # not duplicated across two crawls
        assert len(info_contacts[0].sources) == 1  # same source_url deduped too
