import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.errors import NotFoundError
from app.api.schemas import CampaignDetailOut, CampaignEventOut, CampaignOut
from app.db.models import Campaign, CampaignFunnelStage
from app.engines.campaigns.funnel import check_backlink_detected, create_campaign, record_event

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


class CreateCampaignIn(BaseModel):
    outreach_strategy_id: uuid.UUID
    target_url: str


class RecordEventIn(BaseModel):
    stage: CampaignFunnelStage
    detail: str | None = None


@router.post("", response_model=CampaignOut, status_code=201)
def create_campaign_endpoint(body: CreateCampaignIn, db: Session = Depends(get_db)) -> Campaign:
    """Creating a Campaign is not a send -- see app/engines/campaigns/funnel.py.
    There is no send-email step anywhere in this codebase; this just
    records that a human is about to (or has) pitched `target_url`
    (their own asset) to the strategy's contact.
    """
    try:
        return create_campaign(
            db, outreach_strategy_id=body.outreach_strategy_id, target_url=body.target_url
        )
    except ValueError as exc:
        raise NotFoundError(str(exc)) from exc


@router.get("/{campaign_id}", response_model=CampaignDetailOut)
def get_campaign(campaign_id: uuid.UUID, db: Session = Depends(get_db)) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise NotFoundError(f"no such campaign: {campaign_id}")
    return campaign


@router.post("/{campaign_id}/events", response_model=CampaignEventOut)
def record_event_endpoint(
    campaign_id: uuid.UUID, body: RecordEventIn, db: Session = Depends(get_db)
):
    """The human reports a real-world funnel transition (a reply came
    in, a bounce notice arrived, ...). This endpoint never sends
    anything -- it only records what the human tells it happened.
    """
    try:
        return record_event(db, campaign_id=campaign_id, stage=body.stage, detail=body.detail)
    except ValueError as exc:
        raise NotFoundError(str(exc)) from exc


@router.post("/{campaign_id}/check-backlink", response_model=CampaignDetailOut)
def check_backlink_endpoint(campaign_id: uuid.UUID, db: Session = Depends(get_db)) -> Campaign:
    """Checks the real `backlinks` table for a verified link matching
    this campaign's target_url -- see the module docstring in
    app/engines/campaigns/funnel.py for why BACKLINK_DETECTED and
    BACKLINK_VERIFIED are recorded together rather than as two separable
    moments. A no-match leaves the campaign unchanged, never fabricates
    progress.
    """
    try:
        return check_backlink_detected(db, campaign_id=campaign_id)
    except ValueError as exc:
        raise NotFoundError(str(exc)) from exc
