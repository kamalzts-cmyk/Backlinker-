"""Integration test for the Common Crawl connector's orchestration and DB
writes, against a real Postgres test database.

The network layer here is mocked (respx) with responses shaped exactly
like real Common Crawl API output (collinfo.json / CDX JSON / gzip WARC
bytes) -- unlike every other integration test in this suite, this one
could NOT be run against the live service from this sandbox:
index.commoncrawl.org and data.commoncrawl.org are both policy-denied by
the environment's egress proxy (confirmed via the proxy's own diagnostic
log, not a transient failure). See docs/ARCHITECTURE.md risk #14. This
test verifies our parsing/orchestration/DB-write logic is correct; it is
not a substitute for a live smoke test in an environment with real
internet access.
"""

import gzip

import httpx
import pytest
import respx
from sqlalchemy import select

from app.crawler.repository import get_or_create_domain
from app.db.base import session_scope
from app.db.models import BacklinkCandidate, BacklinkSourceType
from app.engines.backlink.common_crawl import (
    CDX_INDEX_SERVER,
    DATA_SERVER,
    discover_candidates_from_common_crawl,
)

_COLLINFO = [{"id": "CC-MAIN-2024-10", "cdx-api": f"{CDX_INDEX_SERVER}/CC-MAIN-2024-10-index"}]

_LINKING_HTML = (
    "<html><body><p>According to "
    '<a href="https://target-brand.example/guide">target-brand.example</a>, '
    "this works.</p></body></html>"
)
_NON_LINKING_HTML = "<html><body><p>No relevant links here.</p></body></html>"


def _warc_gzip(html: str, target_uri: str) -> bytes:
    body = html.encode("utf-8")
    http_message = (
        b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: "
        + str(len(body)).encode()
        + b"\r\n\r\n"
        + body
    )
    warc = (
        b"WARC/1.0\r\nWARC-Type: response\r\nWARC-Target-URI: "
        + target_uri.encode()
        + b"\r\nContent-Type: application/http; msgtype=response\r\n\r\n"
        + http_message
    )
    return gzip.compress(warc)


@pytest.mark.asyncio
@respx.mock
async def test_discover_candidates_creates_backlink_candidate_on_real_link_match():
    linking_warc = _warc_gzip(_LINKING_HTML, "https://seed-publisher.example/article-1")
    non_linking_warc = _warc_gzip(_NON_LINKING_HTML, "https://seed-publisher.example/article-2")

    cdx_body = "\n".join(
        [
            (
                '{"url": "https://seed-publisher.example/article-1", "status": "200", '
                '"mime": "text/html", "timestamp": "20240115000000", '
                '"filename": "crawl-data/CC-MAIN-2024-10/x.warc.gz", '
                f'"offset": "1000", "length": "{len(linking_warc)}"}}'
            ),
            (
                '{"url": "https://seed-publisher.example/article-2", "status": "200", '
                '"mime": "text/html", "timestamp": "20240115000100", '
                '"filename": "crawl-data/CC-MAIN-2024-10/x.warc.gz", '
                f'"offset": "2000", "length": "{len(non_linking_warc)}"}}'
            ),
        ]
    )

    respx.get(f"{CDX_INDEX_SERVER}/collinfo.json").mock(
        return_value=httpx.Response(200, json=_COLLINFO)
    )
    respx.get(f"{CDX_INDEX_SERVER}/CC-MAIN-2024-10-index").mock(
        return_value=httpx.Response(200, text=cdx_body)
    )
    respx.get(f"{DATA_SERVER}/crawl-data/CC-MAIN-2024-10/x.warc.gz").mock(
        side_effect=lambda request: httpx.Response(
            206, content=linking_warc if "1000" in request.headers["Range"] else non_linking_warc
        )
    )

    with session_scope() as session:
        target_domain = get_or_create_domain(session, raw_host="target-brand.example")
        created = await discover_candidates_from_common_crawl(
            session,
            seed_domain="seed-publisher.example",
            target_domain=target_domain,
            target_url="https://target-brand.example/guide",
            limit=10,
        )

    assert len(created) == 1
    assert created[0].source_url == "https://seed-publisher.example/article-1"
    assert created[0].target_url == "https://target-brand.example/guide"
    assert created[0].source_type == BacklinkSourceType.COMMON_CRAWL

    with session_scope() as session:
        rows = session.scalars(
            select(BacklinkCandidate).where(
                BacklinkCandidate.source_url == "https://seed-publisher.example/article-1"
            )
        ).all()
        assert len(rows) == 1
        assert rows[0].source_type == BacklinkSourceType.COMMON_CRAWL
        assert rows[0].discovery_method.startswith("common_crawl_cdx:")


@pytest.mark.asyncio
@respx.mock
async def test_discover_candidates_returns_empty_when_no_page_links_to_target():
    non_linking_warc = _warc_gzip(_NON_LINKING_HTML, "https://seed-publisher.example/article-2")
    cdx_body = (
        '{"url": "https://seed-publisher.example/article-2", "status": "200", '
        '"mime": "text/html", "timestamp": "20240115000100", '
        '"filename": "crawl-data/CC-MAIN-2024-10/x.warc.gz", '
        f'"offset": "2000", "length": "{len(non_linking_warc)}"}}'
    )

    respx.get(f"{CDX_INDEX_SERVER}/collinfo.json").mock(
        return_value=httpx.Response(200, json=_COLLINFO)
    )
    respx.get(f"{CDX_INDEX_SERVER}/CC-MAIN-2024-10-index").mock(
        return_value=httpx.Response(200, text=cdx_body)
    )
    respx.get(f"{DATA_SERVER}/crawl-data/CC-MAIN-2024-10/x.warc.gz").mock(
        return_value=httpx.Response(206, content=non_linking_warc)
    )

    with session_scope() as session:
        target_domain = get_or_create_domain(session, raw_host="target-brand.example")
        created = await discover_candidates_from_common_crawl(
            session,
            seed_domain="seed-publisher.example",
            target_domain=target_domain,
            target_url="https://target-brand.example/guide",
            limit=10,
        )

    assert created == []


@pytest.mark.asyncio
@respx.mock
async def test_discover_candidates_handles_unavailable_collinfo_gracefully():
    respx.get(f"{CDX_INDEX_SERVER}/collinfo.json").mock(return_value=httpx.Response(503))

    with session_scope() as session:
        target_domain = get_or_create_domain(session, raw_host="target-brand.example")
        created = await discover_candidates_from_common_crawl(
            session,
            seed_domain="seed-publisher.example",
            target_domain=target_domain,
            target_url="https://target-brand.example/guide",
        )

    assert created == []
