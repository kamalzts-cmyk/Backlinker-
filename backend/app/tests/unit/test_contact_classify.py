from app.db.models import ContactPageType
from app.engines.contact.classify import classify_page_type, is_role_address


def test_classify_home():
    assert classify_page_type("https://example.com/") == ContactPageType.HOME
    assert classify_page_type("https://example.com") == ContactPageType.HOME


def test_classify_contact():
    assert classify_page_type("https://example.com/contact") == ContactPageType.CONTACT
    assert classify_page_type("https://example.com/contact.html") == ContactPageType.CONTACT


def test_classify_team():
    assert classify_page_type("https://example.com/team") == ContactPageType.TEAM
    assert classify_page_type("https://example.com/editorial-team") == ContactPageType.TEAM


def test_classify_author():
    assert classify_page_type("https://example.com/authors/jane-doe") == ContactPageType.AUTHOR


def test_classify_guest_post():
    assert classify_page_type("https://example.com/write-for-us") == ContactPageType.GUEST_POST
    assert classify_page_type("https://example.com/contribute") == ContactPageType.GUEST_POST


def test_classify_press():
    assert classify_page_type("https://example.com/press") == ContactPageType.PRESS


def test_classify_returns_none_for_unrelated_page():
    assert classify_page_type("https://example.com/blog/some-article") is None
    assert classify_page_type("https://example.com/pricing") is None


def test_is_role_address():
    assert is_role_address("info@example.com") is True
    assert is_role_address("press@example.com") is True
    assert is_role_address("jane.doe@example.com") is False
