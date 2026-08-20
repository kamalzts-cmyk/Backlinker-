import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.errors import NotFoundError
from app.api.schemas import GEOObservationOut
from app.db.models import GEOCitationResult, GEOObservation
from app.engines.geo.citations import record_manual_observation

router = APIRouter(prefix="/geo", tags=["geo"])


class RecordObservationIn(BaseModel):
    query: str
    engine: str
    target_domain_id: uuid.UUID
    observed_result: GEOCitationResult
    source_url: str | None = None
    answer_excerpt: str | None = None


@router.post("/observations", response_model=GEOObservationOut, status_code=201)
def create_observation(body: RecordObservationIn, db: Session = Depends(get_db)) -> GEOObservation:
    """Logs what a human observed checking a real answer engine
    themselves. There's no automated check-citation endpoint here: no
    concrete AISearchProvider ships in this project yet (see
    app/db/models.py's Phase 18 comment for why) -- app.engines.geo.
    citations.check_citation exists for when one does, exercised in
    tests via a fake provider.
    """
    try:
        return record_manual_observation(
            db,
            query=body.query,
            engine=body.engine,
            target_domain_id=body.target_domain_id,
            observed_result=body.observed_result,
            source_url=body.source_url,
            answer_excerpt=body.answer_excerpt,
        )
    except ValueError as exc:
        raise NotFoundError(str(exc)) from exc


@router.get("/observations", response_model=list[GEOObservationOut])
def list_observations(
    target_domain_id: uuid.UUID = Query(...), db: Session = Depends(get_db)
) -> list[GEOObservation]:
    return list(
        db.scalars(
            select(GEOObservation)
            .where(GEOObservation.target_domain_id == target_domain_id)
            .order_by(GEOObservation.observed_at.desc())
        )
    )
