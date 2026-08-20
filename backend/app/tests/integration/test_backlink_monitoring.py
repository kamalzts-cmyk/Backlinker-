"""Real integration tests for Phase 16: backlink monitoring. Reuses the
real Phase 3 verification pipeline against the real fixture HTTP server
and a real Postgres test database -- no mocking. To exercise an actual
attribute/anchor change between two rechecks (the fixture server serves
static files off disk), this test temporarily writes a fixture file with
different content between the "before" and "after" crawl, then removes
it -- the crawls themselves, the parsing, and the diff are all real.
"""

import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from app.crawler.repository import get_or_create_domain
from app.db.base import session_scope
from app.db.models import (
    Backlink,
    BacklinkChangeType,
    BacklinkMonitoringEvent,
    BacklinkSourceType,
)
from app.engines.backlink.repository import create_candidate
from app.engines.backlink.verify import verify_candidate
from app.engines.monitoring.recheck import recheck_backlink
from app.tests.fixtures.server import FixtureServer

_FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "html" / "monitoring_source.html"

_INITIAL_HTML = (
    "<html><body><p>See our "
    '<a href="https://example.com/monitored-target">Example Target</a> for details.</p>'
    "</body></html>"
)
_CHANGED_HTML = (
    "<html><body><p>See our "
    '<a href="https://example.com/monitored-target" rel="nofollow sponsored">'
    "New Anchor Text</a> for details.</p>"
    "</body></html>"
)


async def _create_and_verify_backlink(base_url: str) -> uuid.UUID:
    with session_scope() as session:
        target_domain = get_or_create_domain(session, raw_host="example.com")
        candidate = create_candidate(
            session,
            source_url=f"{base_url}/monitoring_source.html",
            target_url="https://example.com/monitored-target",
            target_domain_id=target_domain.id,
            source_type=BacklinkSourceType.USER_PROVIDED,
        )
        candidate_id = candidate.id

    observation = await verify_candidate(candidate_id)
    assert observation is not None

    with session_scope() as session:
        backlink = session.scalar(
            select(Backlink).where(
                Backlink.source_url == f"{base_url}/monitoring_source.html",
                Backlink.target_url == "https://example.com/monitored-target",
            )
        )
        assert backlink is not None
        return backlink.id


@pytest.mark.asyncio
async def test_recheck_detects_attribute_and_anchor_changes():
    _FIXTURE_PATH.write_text(_INITIAL_HTML)
    try:
        with FixtureServer() as base_url:
            backlink_id = await _create_and_verify_backlink(base_url)

            _FIXTURE_PATH.write_text(_CHANGED_HTML)
            events = await recheck_backlink(backlink_id)

        change_types = {e["change_type"] for e in events}
        assert BacklinkChangeType.ATTRIBUTE_CHANGED in change_types
        assert BacklinkChangeType.ANCHOR_CHANGED in change_types

        attr_event = next(e for e in events if e["change_type"] == BacklinkChangeType.ATTRIBUTE_CHANGED)
        assert attr_event["before_state"] == {
            "rel_nofollow": False,
            "rel_sponsored": False,
            "rel_ugc": False,
        }
        assert attr_event["after_state"] == {
            "rel_nofollow": True,
            "rel_sponsored": True,
            "rel_ugc": False,
        }

        anchor_event = next(e for e in events if e["change_type"] == BacklinkChangeType.ANCHOR_CHANGED)
        assert anchor_event["before_state"] == {"anchor_text": "Example Target"}
        assert anchor_event["after_state"] == {"anchor_text": "New Anchor Text"}

        with session_scope() as session:
            backlink = session.get(Backlink, backlink_id)
            assert backlink.lost_at is None
            persisted = session.scalars(
                select(BacklinkMonitoringEvent).where(
                    BacklinkMonitoringEvent.backlink_id == backlink_id
                )
            ).all()
            assert len(persisted) == 2
    finally:
        _FIXTURE_PATH.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_recheck_with_no_changes_records_no_events():
    _FIXTURE_PATH.write_text(_INITIAL_HTML)
    try:
        with FixtureServer() as base_url:
            backlink_id = await _create_and_verify_backlink(base_url)
            events = await recheck_backlink(backlink_id)
        assert events == []
    finally:
        _FIXTURE_PATH.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_recheck_detects_a_lost_backlink_when_source_is_unreachable():
    _FIXTURE_PATH.write_text(_INITIAL_HTML)
    try:
        with FixtureServer() as base_url:
            backlink_id = await _create_and_verify_backlink(base_url)
        # FixtureServer has shut down -- the source is now genuinely unreachable.
        events = await recheck_backlink(backlink_id)
    finally:
        _FIXTURE_PATH.unlink(missing_ok=True)

    assert len(events) == 1
    assert events[0]["change_type"] == BacklinkChangeType.LOST

    with session_scope() as session:
        backlink = session.get(Backlink, backlink_id)
        assert backlink.lost_at is not None


@pytest.mark.asyncio
async def test_recheck_raises_for_unknown_backlink():
    with pytest.raises(ValueError):
        await recheck_backlink(uuid.uuid4())
