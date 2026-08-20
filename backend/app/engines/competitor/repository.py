"""DB write/read helpers for competitor relationships."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CompetitorRelationship


def add_competitor(
    session: Session, *, primary_domain_id: uuid.UUID, competitor_domain_id: uuid.UUID
) -> CompetitorRelationship:
    existing = session.scalar(
        select(CompetitorRelationship).where(
            CompetitorRelationship.primary_domain_id == primary_domain_id,
            CompetitorRelationship.competitor_domain_id == competitor_domain_id,
        )
    )
    if existing is not None:
        return existing

    relationship = CompetitorRelationship(
        primary_domain_id=primary_domain_id, competitor_domain_id=competitor_domain_id
    )
    session.add(relationship)
    session.flush()
    return relationship


def list_competitor_domain_ids(session: Session, primary_domain_id: uuid.UUID) -> list[uuid.UUID]:
    return list(
        session.scalars(
            select(CompetitorRelationship.competitor_domain_id).where(
                CompetitorRelationship.primary_domain_id == primary_domain_id
            )
        )
    )
