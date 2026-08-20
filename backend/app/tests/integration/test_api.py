"""Real end-to-end tests of the FastAPI layer: TestClient -> real route
handlers -> real engines -> real Postgres test database. `/crawl` and the
backlink/competitor setup below use the real fixture HTTP server, not
mocks -- same discipline as every other integration test in this suite.
"""

import pytest
from fastapi.testclient import TestClient

from app.db.base import session_scope
from app.db.models import BacklinkSourceType
from app.engines.backlink.repository import create_candidate
from app.engines.backlink.verify import verify_candidate
from app.engines.contact.discover import discover_contacts_for_domain
from app.main import app
from app.tests.fixtures.server import FixtureServer

client = TestClient(app)


def test_register_and_get_domain():
    response = client.post("/domains", json={"host": "WWW.Example-API-Test.com"})
    assert response.status_code == 201
    body = response.json()
    assert body["normalized_host"] == "example-api-test.com"

    domain_id = body["id"]
    fetched = client.get(f"/domains/{domain_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == domain_id


def test_get_domain_404_for_unknown_id():
    response = client.get("/domains/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_crawl_endpoint_runs_a_real_crawl_and_reports_page_count():
    with FixtureServer() as base_url:
        response = client.post("/crawl", json={"url": f"{base_url}/index.html", "max_pages": 5})
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "completed"
    assert body["page_count"] >= 1

    fetched = client.get(f"/crawl/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["page_count"] == body["page_count"]


@pytest.mark.asyncio
async def test_backlinks_endpoints_reflect_a_real_verified_backlink():
    from app.crawler.repository import get_or_create_domain

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

    response = client.get("/backlinks", params={"target_domain_id": str(target_domain_id)})
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["target_url"] == "https://example.com/follow-target"
    assert rows[0]["latest_observation"]["anchor_text"] == "Example Corp"

    detail = client.get(f"/backlinks/{rows[0]['id']}")
    assert detail.status_code == 200
    assert len(detail.json()["observations"]) == 1


@pytest.mark.asyncio
async def test_competitors_and_link_gaps_endpoints_end_to_end():
    from app.crawler.repository import get_or_create_domain

    with FixtureServer(host="127.0.0.5") as source_url:
        with session_scope() as session:
            primary = get_or_create_domain(session, raw_host="api-primary.example")
            # matches the target the fixture page actually links to --
            # see links_competitor_a_only.html
            competitor = get_or_create_domain(session, raw_host="competitor-a.example")
            primary_id, competitor_id = primary.id, competitor.id

        add_competitor_response = client.post(
            "/competitors",
            json={"primary_domain_id": str(primary_id), "competitor_host": "competitor-a.example"},
        )
        assert add_competitor_response.status_code == 201
        assert add_competitor_response.json()["competitor_host"] == "competitor-a.example"

        with session_scope() as session:
            candidate = create_candidate(
                session,
                source_url=f"{source_url}/links_competitor_a_only.html",
                target_url="https://competitor-a.example/product",
                target_domain_id=competitor_id,
                source_type=BacklinkSourceType.USER_PROVIDED,
            )
            candidate_id = candidate.id

        observation = await verify_candidate(candidate_id)
        assert observation is not None

        response = client.get("/link-gaps", params={"primary_domain_id": str(primary_id)})

    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["competitor_overlap_count"] == 1
    assert rows[0]["confidence"] == "low"
    assert "competitor-a.example" in rows[0]["competitor_hosts"]


@pytest.mark.asyncio
async def test_contacts_endpoints_list_and_verify_a_real_contact():
    with FixtureServer() as base_url:
        contacts = await discover_contacts_for_domain(f"{base_url}/contact.html", max_pages=1)
    assert contacts

    domain_id = str(contacts[0].domain_id)
    response = client.get("/contacts", params={"domain_id": domain_id})
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 2
    assert {r["email"] for r in rows} == {"info@example.com", "press@example.com"}
    assert all(r["verification_status"] == "role_address" for r in rows)

    # role addresses on example.com -- real DNS, real MX (example.com has one)
    contact_id = rows[0]["id"]
    verify_response = client.post(f"/contacts/{contact_id}/verify-email")
    assert verify_response.status_code == 200
    assert verify_response.json()["confidence_score"] > 0
