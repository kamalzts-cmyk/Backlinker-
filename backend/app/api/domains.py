import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
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


@router.get("/{domain_id}", response_model=DomainOut)
def get_domain(domain_id: uuid.UUID, db: Session = Depends(get_db)) -> Domain:
    domain = db.get(Domain, domain_id)
    if domain is None:
        raise NotFoundError(f"no such domain: {domain_id}")
    return domain
