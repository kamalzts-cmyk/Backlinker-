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
from app.engines.guest_post.detect import discover_guest_post_opportunity
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


def test_list_domains_reflects_real_registered_domains_and_supports_search():
    client.post("/domains", json={"host": "list-domains-alpha.example"})
    client.post("/domains", json={"host": "list-domains-beta.example"})

    all_response = client.get("/domains")
    assert all_response.status_code == 200
    hosts = {d["normalized_host"] for d in all_response.json()}
    assert {"list-domains-alpha.example", "list-domains-beta.example"} <= hosts

    filtered_response = client.get("/domains", params={"q": "alpha"})
    filtered_hosts = {d["normalized_host"] for d in filtered_response.json()}
    assert filtered_hosts == {"list-domains-alpha.example"}


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
    assert any("competitor-a.example" in e for e in rows[0]["evidence"])


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


@pytest.mark.asyncio
async def test_guest_posts_endpoints_reflect_a_real_opportunity():
    with FixtureServer() as base_url:
        opportunity = await discover_guest_post_opportunity(
            f"{base_url}/write-for-us-detailed.html", max_pages=1
        )
    assert opportunity is not None

    response = client.get("/guest-posts", params={"domain_id": str(opportunity.domain_id)})
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["word_count_min"] == 1200
    assert rows[0]["editor_email"] == "editor@example.com"

    detail = client.get(f"/guest-posts/{rows[0]['id']}")
    assert detail.status_code == 200
    assert detail.json()["guest_post_probability"] == rows[0]["guest_post_probability"]


@pytest.mark.asyncio
async def test_opportunity_score_endpoint():
    with FixtureServer() as base_url:
        contacts = await discover_contacts_for_domain(f"{base_url}/contact.html", max_pages=1)
    domain_id = str(contacts[0].domain_id)

    response = client.post("/opportunities/score", params={"domain_id": domain_id})
    assert response.status_code == 200
    body = response.json()
    assert body["composite_score"] is not None
    by_name = {c["name"]: c for c in body["components"]}
    assert by_name["organic_traffic"]["value"] is None
    assert by_name["organic_traffic"]["confidence"] == "unavailable"
    assert by_name["contactability"]["confidence"] == "measured"


@pytest.mark.asyncio
async def test_outreach_strategy_endpoints_reflect_a_real_generic_strategy():
    with FixtureServer() as base_url:
        contacts = await discover_contacts_for_domain(f"{base_url}/contact.html", max_pages=1)
    contact_id = str(contacts[0].id)

    # use_ai=false -- no live Ollama in this sandbox (Phase 13 caveat);
    # this exercises the deterministic fields only.
    response = client.post(
        "/outreach/strategy", params={"contact_id": contact_id, "use_ai": "false"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["opportunity_type"] == "generic"
    assert body["angle"] is None
    assert body["ai_generated"] is False
    assert body["recommended_content_asset"] is None

    fetched = client.get(f"/outreach/strategy/{contact_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == body["id"]


def test_outreach_strategy_404_for_unknown_contact():
    response = client.get("/outreach/strategy/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


@pytest.mark.asyncio
async def test_campaigns_endpoints_track_a_real_funnel():
    with FixtureServer() as base_url:
        contacts = await discover_contacts_for_domain(f"{base_url}/contact.html", max_pages=1)
    contact_id = str(contacts[0].id)

    strategy_response = client.post(
        "/outreach/strategy", params={"contact_id": contact_id, "use_ai": "false"}
    )
    strategy_id = strategy_response.json()["id"]

    create_response = client.post(
        "/campaigns",
        json={"outreach_strategy_id": strategy_id, "target_url": "https://example.com/asset"},
    )
    assert create_response.status_code == 201
    campaign_id = create_response.json()["id"]
    assert create_response.json()["current_stage"] is None

    event_response = client.post(
        f"/campaigns/{campaign_id}/events", json={"stage": "sent", "detail": "sent via Gmail"}
    )
    assert event_response.status_code == 200
    assert event_response.json()["stage"] == "sent"

    detail_response = client.get(f"/campaigns/{campaign_id}")
    assert detail_response.status_code == 200
    body = detail_response.json()
    assert body["current_stage"] == "sent"
    assert len(body["events"]) == 1

    check_response = client.post(f"/campaigns/{campaign_id}/check-backlink")
    assert check_response.status_code == 200
    assert check_response.json()["current_stage"] == "sent"  # no matching backlink yet


def test_create_campaign_404_for_unknown_strategy():
    response = client.post(
        "/campaigns",
        json={
            "outreach_strategy_id": "00000000-0000-0000-0000-000000000000",
            "target_url": "https://example.com/asset",
        },
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


@pytest.mark.asyncio
async def test_backlink_recheck_endpoint_detects_no_change_on_a_stable_link():
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
            candidate_id = candidate.id

        observation = await verify_candidate(candidate_id)
        assert observation is not None

        backlinks_response = client.get(
            "/backlinks", params={"target_domain_id": str(target_domain.id)}
        )
        backlink_id = backlinks_response.json()[0]["id"]

        recheck_response = client.post(f"/backlinks/{backlink_id}/recheck")
        assert recheck_response.status_code == 200
        assert recheck_response.json() == []  # nothing changed -- same fixture content

        events_response = client.get(f"/backlinks/{backlink_id}/monitoring-events")
        assert events_response.status_code == 200
        assert events_response.json() == []


def test_backlink_recheck_404_for_unknown_backlink():
    response = client.post("/backlinks/00000000-0000-0000-0000-000000000000/recheck")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


@pytest.mark.asyncio
async def test_reports_endpoint_exports_a_real_backlinks_csv():
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

    response = client.get(
        "/reports/backlinks",
        params={"format": "csv", "target_domain_id": str(target_domain_id)},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert "example.com/follow-target" in response.text


def test_reports_endpoint_404_for_unknown_report_type():
    response = client.get("/reports/not_a_real_report")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_geo_observations_endpoints_record_and_list_a_real_manual_observation():
    from app.crawler.repository import get_or_create_domain

    with session_scope() as session:
        domain = get_or_create_domain(session, raw_host="geo-api-example.com")
        domain_id = str(domain.id)

    create_response = client.post(
        "/geo/observations",
        json={
            "query": "who writes the best SEO guides",
            "engine": "chatgpt_search",
            "target_domain_id": domain_id,
            "observed_result": "cited",
            "source_url": "https://geo-api-example.com/guide",
        },
    )
    assert create_response.status_code == 201
    assert create_response.json()["observed_result"] == "cited"

    list_response = client.get("/geo/observations", params={"target_domain_id": domain_id})
    assert list_response.status_code == 200
    rows = list_response.json()
    assert len(rows) == 1
    assert rows[0]["source_url"] == "https://geo-api-example.com/guide"


def test_geo_observations_endpoint_rejects_cited_without_source_url():
    from app.crawler.repository import get_or_create_domain

    with session_scope() as session:
        domain = get_or_create_domain(session, raw_host="geo-api-example-2.com")
        domain_id = str(domain.id)

    response = client.post(
        "/geo/observations",
        json={
            "query": "x",
            "engine": "perplexity",
            "target_domain_id": domain_id,
            "observed_result": "cited",
        },
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
