"""FastAPI app factory. See docs/API.md.

API-first: the eventual frontend is just a client of this. Routes are
domain-centric (no `projects`/auth layer exists yet -- see
docs/ARCHITECTURE.md §9); once that's built it wraps these, it doesn't
replace them.
"""

from fastapi import FastAPI

from app.api import (
    backlinks,
    campaigns,
    competitors,
    contacts,
    crawl,
    domains,
    geo,
    guest_posts,
    opportunities,
    outreach,
    reports,
)
from app.api.errors import register_error_handlers


def create_app() -> FastAPI:
    app = FastAPI(title="LinkIntel API")
    register_error_handlers(app)
    app.include_router(domains.router)
    app.include_router(crawl.router)
    app.include_router(backlinks.router)
    app.include_router(competitors.router)
    app.include_router(contacts.router)
    app.include_router(guest_posts.router)
    app.include_router(opportunities.router)
    app.include_router(outreach.router)
    app.include_router(campaigns.router)
    app.include_router(reports.router)
    app.include_router(geo.router)
    return app


app = create_app()
