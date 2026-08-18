from pathlib import Path

from bs4 import BeautifulSoup

from app.crawler.extractors.contact import extract_contact_emails, extract_contact_phones

FIXTURES = Path(__file__).parent.parent / "fixtures" / "html"


def _soup(name: str) -> BeautifulSoup:
    return BeautifulSoup((FIXTURES / name).read_text(), "lxml")


def test_extract_contact_emails_from_plain_text():
    emails = extract_contact_emails(_soup("contact_page.html"))
    assert emails == ["press@example.com"]


def test_extract_contact_phones_from_plain_text():
    phones = extract_contact_phones(_soup("contact_page.html"))
    assert "+1 555 987 6543" in phones
    assert "(555) 234-5678" in phones


def test_extract_contact_phones_excludes_bare_reference_numbers():
    phones = extract_contact_phones(_soup("contact_page.html"))
    assert not any("2026081812345" in p for p in phones)


def test_extract_contact_emails_ignores_obfuscated_addresses():
    # obfuscated_email.html deliberately writes "editor [at] example dot com"
    # -- Phase 2 is not meant to de-obfuscate this (see contact.py docstring).
    emails = extract_contact_emails(_soup("obfuscated_email.html"))
    assert emails == []


def test_extract_contact_emails_from_mailto_page_text():
    # mailto.html has the address both in href and as visible text;
    # extraction works off visible text so it's found regardless of the link.
    emails = extract_contact_emails(_soup("mailto.html"))
    assert "editorial-team@example.com" in emails
