from pathlib import Path

from bs4 import BeautifulSoup

from app.crawler.extractors.schema import extract_structured_metadata

FIXTURES = Path(__file__).parent.parent / "fixtures" / "html"


def _soup(name: str) -> BeautifulSoup:
    return BeautifulSoup((FIXTURES / name).read_text(), "lxml")


def test_extract_open_graph():
    meta = extract_structured_metadata(_soup("rich_metadata.html"), "https://fixtures.local/rich_metadata.html")
    assert meta.open_graph["og:title"] == "Rich Metadata Fixture"
    assert meta.open_graph["og:type"] == "article"


def test_extract_twitter_card():
    meta = extract_structured_metadata(_soup("rich_metadata.html"), "https://fixtures.local/rich_metadata.html")
    assert meta.twitter_card["twitter:card"] == "summary_large_image"


def test_extract_json_ld_schema_org():
    meta = extract_structured_metadata(_soup("rich_metadata.html"), "https://fixtures.local/rich_metadata.html")
    assert len(meta.schema_org) == 1
    assert meta.schema_org[0]["@type"] == "Article"
    assert meta.schema_org[0]["author"]["name"] == "Jane Doe"


def test_extract_images_with_and_without_alt():
    meta = extract_structured_metadata(_soup("rich_metadata.html"), "https://fixtures.local/rich_metadata.html")
    by_src = {img["src"]: img["alt"] for img in meta.images}
    assert by_src["https://fixtures.local/images/hero.jpg"] == "A hero banner"
    assert by_src["https://fixtures.local/images/no-alt.jpg"] == ""


def test_extract_pdf_links():
    meta = extract_structured_metadata(_soup("rich_metadata.html"), "https://fixtures.local/rich_metadata.html")
    assert meta.pdf_links == ["https://fixtures.local/reports/annual-report.pdf"]


def test_extract_social_links():
    meta = extract_structured_metadata(_soup("rich_metadata.html"), "https://fixtures.local/rich_metadata.html")
    assert "https://twitter.com/example" in meta.social_links
    assert "https://www.linkedin.com/company/example" in meta.social_links


def test_extract_embeds():
    meta = extract_structured_metadata(_soup("rich_metadata.html"), "https://fixtures.local/rich_metadata.html")
    assert meta.embeds == ["https://www.youtube.com/embed/dQw4w9WgXcQ"]


def test_extract_structured_metadata_empty_on_plain_page():
    meta = extract_structured_metadata(_soup("index.html"), "https://fixtures.local/index.html")
    assert meta.schema_org == []
    assert meta.open_graph == {}
    assert meta.twitter_card == {}
    assert meta.pdf_links == []
