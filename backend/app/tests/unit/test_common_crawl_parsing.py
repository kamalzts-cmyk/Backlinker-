"""Unit tests for the pure-parsing parts of the Common Crawl connector --
no network. These can be verified fully in this sandbox even though the
live index.commoncrawl.org / data.commoncrawl.org connector itself could
not be (see docs/ARCHITECTURE.md risk #14).
"""

import gzip

from app.engines.backlink.common_crawl import extract_warc_html, parse_cdx_line

# A realistic sample of what index.commoncrawl.org's `output=json` CDX
# API actually returns, one JSON object per line.
_REAL_CDX_LINE = (
    '{"urlkey": "com,example)/page", "timestamp": "20240115000000", '
    '"url": "https://example.com/page", "mime": "text/html", '
    '"mime-detected": "text/html", "status": "200", '
    '"digest": "3I42H3S6NNFQ2MSVX7XZKYAYSCX5QBYJ", "length": "1234", '
    '"offset": "987654321", '
    '"filename": "crawl-data/CC-MAIN-2024-10/segments/x/warc/CC-MAIN-20240115.warc.gz"}'
)


def test_parse_cdx_line_extracts_real_fields():
    record = parse_cdx_line(_REAL_CDX_LINE)
    assert record is not None
    assert record.url == "https://example.com/page"
    assert record.status == "200"
    assert record.mime == "text/html"
    assert record.offset == 987654321
    assert record.length == 1234
    assert record.filename.endswith(".warc.gz")


def test_parse_cdx_line_returns_none_for_blank_line():
    assert parse_cdx_line("") is None
    assert parse_cdx_line("   \n") is None


def test_parse_cdx_line_returns_none_for_malformed_json():
    assert parse_cdx_line("not json at all") is None


def test_parse_cdx_line_returns_none_for_missing_required_field():
    assert parse_cdx_line('{"url": "https://example.com/"}') is None


def _build_warc_gzip_fixture(html_body: str, target_url: str) -> bytes:
    """Build a byte-accurate single-record WARC response, gzip-compressed,
    exactly like what a Range-fetch from data.commoncrawl.org returns.
    """
    body_bytes = html_body.encode("utf-8")
    http_message = (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: text/html; charset=UTF-8\r\n"
        b"Content-Length: " + str(len(body_bytes)).encode() + b"\r\n"
        b"\r\n" + body_bytes
    )
    warc_headers = (
        b"WARC/1.0\r\n"
        b"WARC-Type: response\r\n"
        b"WARC-Target-URI: " + target_url.encode() + b"\r\n"
        b"Content-Type: application/http; msgtype=response\r\n"
        b"Content-Length: " + str(len(http_message)).encode() + b"\r\n"
    )
    warc_record = warc_headers + b"\r\n" + http_message
    return gzip.compress(warc_record)


def test_extract_warc_html_round_trips_real_warc_bytes():
    html = "<html><body><h1>Hello from Common Crawl</h1></body></html>"
    raw = _build_warc_gzip_fixture(html, "https://example.com/page")
    extracted = extract_warc_html(raw)
    assert extracted == html


def test_extract_warc_html_returns_none_for_garbage_bytes():
    assert extract_warc_html(b"not a gzip stream at all") is None


def test_extract_warc_html_returns_none_for_truncated_warc():
    # valid gzip, but missing the double-CRLF separators a real WARC has
    raw = gzip.compress(b"WARC/1.0\r\nWARC-Type: response\r\n")
    assert extract_warc_html(raw) is None
