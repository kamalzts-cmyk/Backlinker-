import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.errors import NotFoundError, UpstreamServiceError
from app.api.schemas import GEOObservationOut
from app.core.config import settings
from app.db.models import GEOCitationResult, GEOObservation
from app.engines.geo.citations import check_citation, record_manual_observation
from app.engines.search.anthropic_provider import AnthropicSearchProvider
from app.engines.search.errors import AISearchError

router = APIRouter(prefix="/geo", tags=["geo"])


class RecordObservationIn(BaseModel):
    query: str
    engine: str
    target_domain_id: uuid.UUID
    observed_result: GEOCitationResult
    source_url: str | None = None
    answer_excerpt: str | None = None


class CheckCitationIn(BaseModel):
    query: str
    target_domain_id: uuid.UUID


@router.post("/observations", response_model=GEOObservationOut, status_code=201)
def create_observation(body: RecordObservationIn, db: Session = Depends(get_db)) -> GEOObservation:
    """Logs what a human observed checking a real answer engine
    themselves -- no API integration needed. See POST /geo/check for the
    automated path.
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


@router.post("/check", response_model=GEOObservationOut, status_code=201)
async def check_citation_endpoint(
    body: CheckCitationIn, db: Session = Depends(get_db)
) -> GEOObservation:
    """Automated citation check via `AnthropicSearchProvider` (Claude's
    web search tool -- see app/engines/search/anthropic_provider.py for
    why this is the concrete provider). Requires an Anthropic API key
    configured for this deployment (ANTHROPIC_API_KEY or an `ant auth
    login` profile); a failed upstream call is a 502, never a fabricated
    result.
    """
    provider = AnthropicSearchProvider(
        api_key=settings.anthropic_api_key, model=settings.anthropic_model
    )
    try:
        return await check_citation(
            db,
            query=body.query,
            engine=f"anthropic:{settings.anthropic_model}",
            target_domain_id=body.target_domain_id,
            provider=provider,
        )
    except ValueError as exc:
        raise NotFoundError(str(exc)) from exc
    except AISearchError as exc:
        raise UpstreamServiceError(str(exc)) from exc


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
