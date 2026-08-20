"""Proves the full Phase 4 -> Phase 3 chain: a candidate discovered via
Common Crawl (network mocked, see test_common_crawl_discovery.py's
docstring for why) still goes through real, live direct verification
before being trusted -- Common Crawl discovery alone never marks
anything VERIFIED. This is the core promise of PRODUCT_SPEC.md §2/§6.
"""

import gzip

import httpx
import pytest
import respx

from app.crawler.repository import get_or_create_domain
from app.db.base import session_scope
from app.db.models import BacklinkCandidateStatus
from app.engines.backlink.common_crawl import (
    CDX_INDEX_SERVER,
    DATA_SERVER,
    discover_candidates_from_common_crawl,
)
from app.engines.backlink.verify import verify_candidate
from app.tests.fixtures.server import FixtureServer

_COLLINFO = [{"id": "CC-MAIN-2024-10", "cdx-api": f"{CDX_INDEX_SERVER}/CC-MAIN-2024-10-index"}]


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
async def test_common_crawl_candidate_still_requires_live_verification():
    with FixtureServer() as base_url:
        # A page Common Crawl captured a while ago claims to link to our
        # target -- but crawling it *live and for real* (via the fixture
        # server) is what index.html actually contains, per its fixture.
        warc = _warc_gzip(
            '<a href="https://example.com/follow-target">link</a>', f"{base_url}/index.html"
        )
        cdx_body = (
            f'{{"url": "{base_url}/index.html", "status": "200", "mime": "text/html", '
            '"timestamp": "20240115000000", "filename": "x.warc.gz", '
            f'"offset": "0", "length": "{len(warc)}"}}'
        )

        # respx only intercepts for this block -- verify_candidate's own
        # real HTTP calls to the fixture server below must go out for
        # real, not through a mock.
        with respx.mock:
            respx.get(f"{CDX_INDEX_SERVER}/collinfo.json").mock(
                return_value=httpx.Response(200, json=_COLLINFO)
            )
            respx.get(f"{CDX_INDEX_SERVER}/CC-MAIN-2024-10-index").mock(
                return_value=httpx.Response(200, text=cdx_body)
            )
            respx.get(f"{DATA_SERVER}/x.warc.gz").mock(return_value=httpx.Response(206, content=warc))

            with session_scope() as session:
                target_domain = get_or_create_domain(session, raw_host="example.com")
                candidates = await discover_candidates_from_common_crawl(
                    session,
                    seed_domain=base_url,
                    target_domain=target_domain,
                    target_url="https://example.com/follow-target",
                )
                assert len(candidates) == 1
                candidate_id = candidates[0].id
                assert candidates[0].status == BacklinkCandidateStatus.PENDING  # not yet verified

        # Now the real, live verification pass -- crawls the fixture
        # server for real, independent of anything Common Crawl claimed.
        observation = await verify_candidate(candidate_id)

    assert observation is not None
    assert observation.anchor_text == "Example Corp"  # the *actual* live anchor text
    assert observation.rel_nofollow is False
