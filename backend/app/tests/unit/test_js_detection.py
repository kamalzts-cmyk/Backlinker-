from pathlib import Path

from app.crawler.js_detection import looks_js_rendered

FIXTURES = Path(__file__).parent.parent / "fixtures" / "html"


def test_js_rendered_shell_is_escalated():
    html = (FIXTURES / "js_rendered.html").read_text()
    assert looks_js_rendered(html) is True


def test_content_rich_page_is_not_escalated():
    html = (FIXTURES / "index.html").read_text()
    assert looks_js_rendered(html) is False


def test_author_page_is_not_escalated():
    html = (FIXTURES / "author.html").read_text()
    assert looks_js_rendered(html) is False
