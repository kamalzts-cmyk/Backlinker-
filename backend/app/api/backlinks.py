import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.errors import NotFoundError
from app.api.schemas import BacklinkDetailOut, BacklinkMonitoringEventOut, BacklinkOut
from app.db.models import Backlink, BacklinkMonitoringEvent, BacklinkObservation
from app.engines.monitoring.recheck import recheck_backlink

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
