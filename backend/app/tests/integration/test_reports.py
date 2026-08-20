"""Real integration tests for Phase 17: reports/exports. Every report is
generated from data produced by the real engines earlier in this
project (a real crawl + Phase 3 verification, real contact discovery)
against a real Postgres test database -- reports.py adds no new
computation, only formatting, so these tests confirm the export
faithfully reflects what's really in the database.
"""

import csv
import io
import json

import pytest

from app.crawler.repository import get_or_create_domain
from app.db.base import session_scope
from app.db.models import BacklinkSourceType
from app.engines.backlink.repository import create_candidate
from app.engines.backlink.verify import verify_candidate
from app.engines.contact.discover import discover_contacts_for_domain
from app.reports.reports import generate_report
from app.tests.fixtures.server import FixtureServer


@pytest.mark.asyncio
async def test_backlinks_report_csv_reflects_a_real_verified_backlink():
    with FixtureServer() as base_url:
        with session_scope() as session:
            target_domain = get_or_create_domain(session, raw_host="example.com")
            candidate = create_candidate(
                session,
                source_url=f"{base_url}/index.html",
                target_url="https://example.com/follow-target",
                target_domain_id=target_domain.id,
                source_type=BacklinkSourceType.USER_PROVIDED,
            )
            candidate_id, target_domain_id = candidate.id, target_domain.id

        observation = await verify_candidate(candidate_id)
        assert observation is not None

        with session_scope() as session:
            body = generate_report(
                session,
                report_type="backlinks",
                export_format="csv",
                target_domain_id=target_domain_id,
            )

    rows = list(csv.DictReader(io.StringIO(body.decode("utf-8"))))
    assert len(rows) == 1
    assert rows[0]["target_url"] == "https://example.com/follow-target"
    assert rows[0]["anchor_text"] == "Example Corp"


@pytest.mark.asyncio
async def test_contacts_report_json_reflects_real_discovered_contacts():
    with FixtureServer() as base_url:
        contacts = await discover_contacts_for_domain(f"{base_url}/contact.html", max_pages=1)
        domain_id = contacts[0].domain_id

        with session_scope() as session:
            body = generate_report(
                session, report_type="contacts", export_format="json", domain_id=domain_id
            )

    parsed = json.loads(body)
    assert {row["email"] for row in parsed} == {"info@example.com", "press@example.com"}


def test_contacts_report_requires_domain_id():
    with session_scope() as session, pytest.raises(ValueError):
        generate_report(session, report_type="contacts", export_format="csv")


def test_unknown_report_type_raises():
    with session_scope() as session, pytest.raises(ValueError):
        generate_report(session, report_type="not_a_real_report", export_format="csv")


def test_unsupported_format_raises():
    with session_scope() as session, pytest.raises(ValueError):
        generate_report(session, report_type="backlinks", export_format="yaml")
