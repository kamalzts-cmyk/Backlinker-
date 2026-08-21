import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.errors import NotFoundError, UpstreamServiceError
from app.api.schemas import (
    BacklinkCandidateOut,
    BacklinkDetailOut,
    BacklinkMonitoringEventOut,
    BacklinkOut,
)
from app.core.config import settings
from app.db.models import (
    Backlink,
    BacklinkCandidate,
    BacklinkMonitoringEvent,
    BacklinkObservation,
    Domain,
)
from app.engines.backlink.search_discovery import discover_candidates_from_search
from app.engines.backlink.verify import verify_candidate
from app.engines.monitoring.recheck import recheck_backlink
from app.engines.search.anthropic_provider import AnthropicSearchProvider
from app.engines.search.errors import AISearchError

router = APIRouter(prefix="/backlinks", tags=["backlinks"])


@router.get("", response_model=list[BacklinkOut])
def list_backlinks(
    target_domain_id: uuid.UUID | None = Query(default=None),
    source_domain_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
) -> list[Backlink]:
    stmt = select(Backlink)
    if target_domain_id is not None:
        stmt = stmt.where(Backlink.target_domain_id == target_domain_id)
    if source_domain_id is not None:
        stmt = stmt.where(Backlink.source_domain_id == source_domain_id)
    return list(db.scalars(stmt.order_by(Backlink.last_seen_at.desc()).limit(limit)))


class DiscoverSearchIn(BaseModel):
    brand_query: str
    target_domain_id: uuid.UUID
    target_url: str
    results_per_pattern: int | None = None


@router.post("/discover-search", response_model=list[BacklinkCandidateOut], status_code=201)
async def discover_search_endpoint(
    body: DiscoverSearchIn, db: Session = Depends(get_db)
) -> list[BacklinkCandidate]:
    """Phase 7: runs PRODUCT_SPEC.md §4.2 Layer 2's named query patterns
    for `brand_query` through `AnthropicSearchProvider` (see
    app/engines/backlink/search_discovery.py for why this resolves
    docs/ARCHITECTURE.md risk #3) and creates a `PENDING`
    `BacklinkCandidate` per distinct result URL. These are candidates
    only -- see `GET /backlinks/candidates` to list them and
    `POST /backlinks/candidates/{id}/verify` for the real Phase 3 check
    before trusting any of them.
    """
    target_domain = db.get(Domain, body.target_domain_id)
    if target_domain is None:
        raise NotFoundError(f"no such domain: {body.target_domain_id}")

    provider = AnthropicSearchProvider(
        api_key=settings.anthropic_api_key, model=settings.anthropic_model
    )
    try:
        return await discover_candidates_from_search(
            db,
            brand_query=body.brand_query,
            target_domain=target_domain,
            target_url=body.target_url,
            provider=provider,
            results_per_pattern=body.results_per_pattern,
        )
    except AISearchError as exc:
        raise UpstreamServiceError(str(exc)) from exc


@router.get("/candidates", response_model=list[BacklinkCandidateOut])
def list_candidates(
    target_domain_id: uuid.UUID = Query(...),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[BacklinkCandidate]:
    stmt = select(BacklinkCandidate).where(BacklinkCandidate.target_domain_id == target_domain_id)
    if status is not None:
        stmt = stmt.where(BacklinkCandidate.status == status)
    return list(db.scalars(stmt.order_by(BacklinkCandidate.created_at.desc())))


@router.post("/candidates/{candidate_id}/verify", response_model=BacklinkCandidateOut)
async def verify_candidate_endpoint(
    candidate_id: uuid.UUID, db: Session = Depends(get_db)
) -> BacklinkCandidate:
    """Phase 3's real direct verification: crawls the candidate's
    source_url for real and checks whether the target link is actually
    there. This is the only thing allowed to turn a candidate --
    regardless of how it was discovered (Common Crawl, search-pattern,
    user-provided) -- into a verified `Backlink`.
    """
    if db.get(BacklinkCandidate, candidate_id) is None:
        raise NotFoundError(f"no such backlink candidate: {candidate_id}")

    try:
        await verify_candidate(candidate_id)
    except ValueError as exc:
        raise NotFoundError(str(exc)) from exc

    candidate = db.get(BacklinkCandidate, candidate_id)
    db.refresh(candidate)
    return candidate


@router.get("/{backlink_id}", response_model=BacklinkDetailOut)
def get_backlink(backlink_id: uuid.UUID, db: Session = Depends(get_db)):
    backlink = db.get(Backlink, backlink_id)
    if backlink is None:
        raise NotFoundError(f"no such backlink: {backlink_id}")

    observations = list(
        db.scalars(
            select(BacklinkObservation)
            .where(
                BacklinkObservation.source_url == backlink.source_url,
                BacklinkObservation.target_url == backlink.target_url,
            )
            .order_by(BacklinkObservation.observed_at.desc())
        )
    )
    return BacklinkDetailOut(
        id=backlink.id,
        source_url=backlink.source_url,
        target_url=backlink.target_url,
        first_seen_at=backlink.first_seen_at,
        last_seen_at=backlink.last_seen_at,
        observations=observations,
    )


@router.post("/{backlink_id}/recheck", response_model=list[BacklinkMonitoringEventOut])
async def recheck_backlink_endpoint(backlink_id: uuid.UUID, db: Session = Depends(get_db)):
    """Re-crawls the backlink's source page for real (Phase 3's
    pipeline, reused) and diffs the result against its last known state
    -- see app/engines/monitoring/recheck.py for exactly what's
    detected and why "target changed" isn't. Returns whatever changed
    (empty list if nothing did); never fabricates an alert.
    """
    try:
        await recheck_backlink(backlink_id)
    except ValueError as exc:
        raise NotFoundError(str(exc)) from exc

    return list(
        db.scalars(
            select(BacklinkMonitoringEvent)
            .where(BacklinkMonitoringEvent.backlink_id == backlink_id)
            .order_by(BacklinkMonitoringEvent.detected_at.desc())
        )
    )


@router.get("/{backlink_id}/monitoring-events", response_model=list[BacklinkMonitoringEventOut])
def list_monitoring_events(backlink_id: uuid.UUID, db: Session = Depends(get_db)):
    if db.get(Backlink, backlink_id) is None:
        raise NotFoundError(f"no such backlink: {backlink_id}")
    return list(
        db.scalars(
            select(BacklinkMonitoringEvent)
            .where(BacklinkMonitoringEvent.backlink_id == backlink_id)
            .order_by(BacklinkMonitoringEvent.detected_at.desc())
        )
    )
