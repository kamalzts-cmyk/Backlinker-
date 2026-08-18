"""DB write helpers for the backlink engine. Mirrors the pattern in
app/crawler/repository.py: engine logic stays here, orchestration in
verify.py.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.crawler.extractors.links import LinkData
from app.db.models import (
    Backlink,
    BacklinkCandidate,
    BacklinkCandidateStatus,
    BacklinkObservation,
    BacklinkRejectionReason,
    BacklinkSourceType,
)
from app.engines.backlink.classify import classify_link_type


def create_candidate(
    session: Session,
    *,
    source_url: str,
    target_url: str,
    target_domain_id: uuid.UUID,
    source_type: BacklinkSourceType,
    discovery_method: str | None = None,
) -> BacklinkCandidate:
    candidate = BacklinkCandidate(
        source_url=source_url,
        target_url=target_url,
        target_domain_id=target_domain_id,
        source_type=source_type,
        discovery_method=discovery_method,
    )
    session.add(candidate)
    session.flush()
    return candidate


def reject_candidate(
    session: Session, *, candidate: BacklinkCandidate, reason: BacklinkRejectionReason
) -> None:
    candidate.status = BacklinkCandidateStatus.REJECTED
    candidate.rejection_reason = reason
    candidate.verified_at = datetime.now(UTC)


def record_verified_observation(
    session: Session,
    *,
    candidate: BacklinkCandidate | None,
    source_url: str,
    source_domain_id: uuid.UUID,
    target_url: str,
    target_domain_id: uuid.UUID,
    link: LinkData,
    source_canonical_url: str | None,
    source_http_status: int | None,
    source_is_indexable: bool,
    crawl_request_id: uuid.UUID | None,
    confidence_score: int,
) -> BacklinkObservation:
    """Record one direct-verification observation and upsert the
    corresponding current-state `backlinks` row. Called only when the
    target link was actually found on the crawled source page -- see
    app/engines/backlink/verify.py for the check sequence.
    """
    observation = BacklinkObservation(
        candidate_id=candidate.id if candidate else None,
        source_url=source_url,
        source_domain_id=source_domain_id,
        target_url=target_url,
        target_domain_id=target_domain_id,
        anchor_text=link.anchor_text,
        surrounding_text=link.surrounding_text,
        rel_nofollow=link.rel_nofollow,
        rel_sponsored=link.rel_sponsored,
        rel_ugc=link.rel_ugc,
        link_position=link.link_position,
        link_type=classify_link_type(link),
        source_canonical_url=source_canonical_url,
        source_http_status=source_http_status,
        source_is_indexable=source_is_indexable,
        source_type=BacklinkSourceType.DIRECT_CRAWL,
        confidence_score=confidence_score,
        crawl_request_id=crawl_request_id,
    )
    session.add(observation)
    session.flush()

    if candidate is not None:
        candidate.status = BacklinkCandidateStatus.VERIFIED
        candidate.verified_at = observation.observed_at

    _upsert_backlink(
        session,
        source_domain_id=source_domain_id,
        target_domain_id=target_domain_id,
        source_url=source_url,
        target_url=target_url,
        observation=observation,
    )
    return observation


def _upsert_backlink(
    session: Session,
    *,
    source_domain_id: uuid.UUID,
    target_domain_id: uuid.UUID,
    source_url: str,
    target_url: str,
    observation: BacklinkObservation,
) -> Backlink:
    existing = session.scalar(
        select(Backlink).where(Backlink.source_url == source_url, Backlink.target_url == target_url)
    )
    if existing is not None:
        existing.latest_observation_id = observation.id
        existing.last_seen_at = observation.observed_at
        return existing

    backlink = Backlink(
        source_domain_id=source_domain_id,
        target_domain_id=target_domain_id,
        source_url=source_url,
        target_url=target_url,
        latest_observation_id=observation.id,
        first_seen_at=observation.observed_at,
        last_seen_at=observation.observed_at,
    )
    session.add(backlink)
    session.flush()
    return backlink
