from pathlib import Path

from bs4 import BeautifulSoup

from app.crawler.extractors.links import extract_links
from app.crawler.extractors.page import extract_page_data

FIXTURES = Path(__file__).parent.parent / "fixtures" / "html"


def _soup(name: str) -> BeautifulSoup:
    return BeautifulSoup((FIXTURES / name).read_text(), "lxml")


def test_extract_page_data_index():
    page = extract_page_data(_soup("index.html"), "https://fixtures.local/index.html")
    assert page.title == "LinkIntel Fixture Site"
    assert page.meta_description == "Local fixture site for crawler extractor tests."
    assert page.canonical_url == "https://fixtures.local/index.html"
    assert page.h1 == ["LinkIntel Fixture Site"]
    assert any(h["tag"] == "h2" for h in page.headings)
    assert page.word_count > 0
    assert page.language == "en"
    assert page.robots_meta_noindex is False


def test_extract_page_data_canonical_mismatch():
    page = extract_page_data(_soup("canonical.html"), "https://fixtures.local/canonical.html")
    assert page.canonical_url == "https://fixtures.local/canonical-target.html"
    assert page.canonical_url != "https://fixtures.local/canonical.html"


def test_extract_links_flags_follow_nofollow_sponsored_ugc():
    links = extract_links(_soup("index.html"), "https://fixtures.local/index.html")
    by_target = {link.target_url: link for link in links}

    follow = by_target["https://example.com/follow-target"]
    assert follow.rel_nofollow is False
    assert follow.rel_sponsored is False
    assert "small businesses" in follow.surrounding_text

    nofollow = by_target["https://example.com/nofollow-target"]
    assert nofollow.rel_nofollow is True

    sponsored = by_target["https://example.com/sponsored-target"]
    assert sponsored.rel_sponsored is True

    ugc = by_target["https://example.com/ugc-target"]
    assert ugc.rel_ugc is True


def test_extract_links_skips_mailto_and_anchors():
    links = extract_links(_soup("index.html"), "https://fixtures.local/index.html")
    targets = {link.target_url for link in links}
    assert not any(t.startswith("mailto:") for t in targets)


def test_extract_links_classifies_position():
    links = extract_links(_soup("index.html"), "https://fixtures.local/index.html")
    by_target = {link.target_url: link for link in links}
    assert by_target["https://example.com/footer-target"].link_position == "footer"


def test_extract_links_internal_vs_external():
    links = extract_links(_soup("index.html"), "https://fixtures.local/index.html")
    internal = [link for link in links if link.target_url.startswith("https://fixtures.local")]
    assert all(link.is_internal for link in internal)
    external = [link for link in links if link.target_url.startswith("https://example.com")]
    assert all(not link.is_internal for link in external)


def test_extract_links_mailto_fixture_has_no_http_links():
    links = extract_links(_soup("mailto.html"), "https://fixtures.local/mailto.html")
    assert links == []
