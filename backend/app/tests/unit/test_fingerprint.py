from bs4 import BeautifulSoup

from app.crawler.fingerprint import content_hash, html_hash, structure_hash, text_hash


def test_content_hash_changes_on_byte_change():
    assert content_hash("<p>a</p>") != content_hash("<p>b</p>")


def test_content_hash_stable_for_identical_input():
    assert content_hash("<p>a</p>") == content_hash("<p>a</p>")


def test_text_hash_ignores_markup_only_changes():
    soup_a = BeautifulSoup("<p class='x'>hello world</p>", "lxml")
    soup_b = BeautifulSoup("<p class='y'>hello   world</p>", "lxml")
    assert text_hash(soup_a) == text_hash(soup_b)


def test_structure_hash_ignores_text_changes():
    soup_a = BeautifulSoup("<div><p>hello</p></div>", "lxml")
    soup_b = BeautifulSoup("<div><p>goodbye</p></div>", "lxml")
    assert structure_hash(soup_a) == structure_hash(soup_b)


def test_structure_hash_changes_on_tag_change():
    soup_a = BeautifulSoup("<div><p>hello</p></div>", "lxml")
    soup_b = BeautifulSoup("<div><span>hello</span></div>", "lxml")
    assert structure_hash(soup_a) != structure_hash(soup_b)


def test_html_hash_ignores_whitespace_only_diffs():
    soup_a = BeautifulSoup("<p>hello</p>", "lxml")
    soup_b = BeautifulSoup("<p>hello</p>\n\n", "lxml")
    assert html_hash(soup_a) == html_hash(soup_b)
