import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.errors import NotFoundError
from app.api.schemas import OutreachStrategyOut
from app.core.config import settings
from app.db.models import OutreachStrategy
from app.engines.ai.ollama_provider import OllamaProvider
from app.engines.outreach.strategy import generate_outreach_strategy

router = APIRouter(prefix="/outreach", tags=["outreach"])


@router.post("/strategy", response_model=OutreachStrategyOut)
async def create_strategy(
    contact_id: uuid.UUID = Query(...),
    primary_domain_id: uuid.UUID | None = Query(default=None),
    use_ai: bool = Query(default=True),
    db: Session = Depends(get_db),
) -> OutreachStrategy:
    """Recomputes (upserts) on every call, same as /link-gaps and
    /opportunities/score -- see app/engines/outreach/strategy.py for what
    each field means and why `angle` may be None. `use_ai=false` skips
    the AI angle-synthesis step entirely (deterministic fields only).
    """
    ai_provider = OllamaProvider(host=settings.ollama_host, model=settings.ollama_model) if use_ai else None
    return await generate_outreach_strategy(
        db,
        contact_id=contact_id,
        primary_domain_id=primary_domain_id,
        ai_provider=ai_provider,
    )


@router.get("/strategy/{contact_id}", response_model=OutreachStrategyOut)
def get_strategy(contact_id: uuid.UUID, db: Session = Depends(get_db)) -> OutreachStrategy:
    strategy = db.scalar(select(OutreachStrategy).where(OutreachStrategy.contact_id == contact_id))
    if strategy is None:
        raise NotFoundError(f"no outreach strategy for contact: {contact_id}")
    return strategy
