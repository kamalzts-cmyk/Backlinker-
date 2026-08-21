from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.errors import UpstreamServiceError
from app.api.schemas import ProspectOut
from app.core.config import settings
from app.db.models import Domain, Prospect
from app.engines.prospects.discover import discover_prospects
from app.engines.search.anthropic_provider import AnthropicSearchProvider
from app.engines.search.errors import AISearchError

router = APIRouter(prefix="/prospects", tags=["prospects"])


class DiscoverProspectsIn(BaseModel):
    topic: str
    results_per_pattern: int | None = None


def _to_out(session: Session, prospect: Prospect) -> ProspectOut:
    domain = session.get(Domain, prospect.domain_id)
    return ProspectOut(
        id=prospect.id,
        domain_id=prospect.domain_id,
        domain_host=domain.normalized_host if domain else str(prospect.domain_id),
        topic_query=prospect.topic_query,
        category=prospect.category.value,
        source_url=prospect.source_url,
        topical_fit_score=prospect.topical_fit_score,
        evidence=prospect.evidence,
        discovered_at=prospect.discovered_at,
    )


@router.post("/discover", response_model=list[ProspectOut], status_code=201)
async def discover_prospects_endpoint(
    body: DiscoverProspectsIn, db: Session = Depends(get_db)
) -> list[ProspectOut]:
    """Phase 7: PRODUCT_SPEC.md §4.4 independent prospect discovery --
    see app/engines/prospects/discover.py for the query patterns and
    why `topical_fit_score` is an explicitly-labeled crude proxy, not a
    substitute for `POST /opportunities/score?reference_domain_id=`.
    """
    provider = AnthropicSearchProvider(
        api_key=settings.anthropic_api_key, model=settings.anthropic_model
    )
    try:
        prospects = await discover_prospects(
            db, topic=body.topic, provider=provider, results_per_pattern=body.results_per_pattern
        )
    except AISearchError as exc:
        raise UpstreamServiceError(str(exc)) from exc
    return [_to_out(db, p) for p in prospects]


@router.get("", response_model=list[ProspectOut])
def list_prospects(
    topic: str | None = Query(default=None),
    min_score: int = Query(default=0, ge=0, le=100),
    db: Session = Depends(get_db),
) -> list[ProspectOut]:
    stmt = select(Prospect).where(Prospect.topical_fit_score >= min_score)
    if topic is not None:
        stmt = stmt.where(Prospect.topic_query == topic)
    prospects = list(db.scalars(stmt.order_by(Prospect.topical_fit_score.desc())))
    return [_to_out(db, p) for p in prospects]
