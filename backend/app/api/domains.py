import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.errors import NotFoundError
from app.api.schemas import DomainOut
from app.crawler.repository import get_or_create_domain
from app.db.models import Domain

router = APIRouter(prefix="/domains", tags=["domains"])


class RegisterDomainIn(BaseModel):
    host: str


@router.post("", response_model=DomainOut, status_code=201)
def register_domain(body: RegisterDomainIn, db: Session = Depends(get_db)) -> Domain:
    return get_or_create_domain(db, raw_host=body.host)


@router.get("", response_model=list[DomainOut])
def list_domains(
    q: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
) -> list[Domain]:
    """Every domain this project has ever touched -- the frontend's
    landing page reads from this rather than any per-engine table, since
    a Domain row is created the moment anything (a crawl, a competitor
    relationship, a manually registered host) first references it.
    `q` is a plain case-insensitive substring match on the host, not a
    search index.
    """
    stmt = select(Domain)
    if q:
        stmt = stmt.where(Domain.normalized_host.ilike(f"%{q}%"))
    return list(db.scalars(stmt.order_by(Domain.first_seen_at.desc()).limit(limit)))


@router.get("/{domain_id}", response_model=DomainOut)
def get_domain(domain_id: uuid.UUID, db: Session = Depends(get_db)) -> Domain:
    domain = db.get(Domain, domain_id)
    if domain is None:
        raise NotFoundError(f"no such domain: {domain_id}")
    return domain
