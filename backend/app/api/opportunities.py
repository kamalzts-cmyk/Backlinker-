import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.schemas import OpportunityScoreOut
from app.db.models import OpportunityScore
from app.engines.scoring.opportunity import compute_opportunity_score

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


@router.post("/score", response_model=OpportunityScoreOut)
def score_domain(
    domain_id: uuid.UUID = Query(...),
    reference_domain_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
) -> OpportunityScore:
    """Recomputes on every call, same as /link-gaps -- see
    app/engines/scoring/opportunity.py for what each component means and
    why several may report "unavailable" rather than a guessed number.
    """
    return compute_opportunity_score(db, domain_id=domain_id, reference_domain_id=reference_domain_id)
