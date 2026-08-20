import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.errors import NotFoundError
from app.api.schemas import BacklinkDetailOut, BacklinkOut
from app.db.models import Backlink, BacklinkObservation

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
