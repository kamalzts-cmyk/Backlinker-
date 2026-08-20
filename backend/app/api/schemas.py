"""Pydantic response models for the API layer. Kept in one module for
now -- split per-resource if/when this grows unwieldy (see
PRODUCT_SPEC.md's "no giant files" rule).
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DomainOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    raw_host: str
    normalized_host: str
    first_seen_at: datetime
    last_crawled_at: datetime | None


class CrawlJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    domain_id: uuid.UUID
    start_url: str
    status: str
    max_pages: int
    pages_crawled: int
    started_at: datetime | None
    finished_at: datetime | None


class CrawlJobDetailOut(CrawlJobOut):
    page_count: int
    error_count: int


class BacklinkObservationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    anchor_text: str | None
    surrounding_text: str | None
    rel_nofollow: bool
    rel_sponsored: bool
    rel_ugc: bool
    link_position: str
    link_type: str
    source_type: str
    confidence_score: int
    observed_at: datetime


class BacklinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_url: str
    target_url: str
    first_seen_at: datetime
    last_seen_at: datetime
    latest_observation: BacklinkObservationOut


class BacklinkDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_url: str
    target_url: str
    first_seen_at: datetime
    last_seen_at: datetime
    # Full history, most recent first -- what makes a backlink observation
    # useful instead of a boolean. See docs/CRAWLER.md §6.
    observations: list[BacklinkObservationOut]


class CompetitorRelationshipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    primary_domain_id: uuid.UUID
    competitor_domain_id: uuid.UUID
    competitor_host: str


class ContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    domain_id: uuid.UUID
    name: str | None
    job_title: str | None
    email: str | None
    phone: str | None
    verification_status: str
    confidence_score: int


class GuestPostOpportunityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    domain_id: uuid.UUID
    guideline_page_url: str | None
    editor_email: str | None
    word_count_min: int | None
    word_count_max: int | None
    mentions_dofollow: bool
    mentions_nofollow: bool
    mentions_sponsored: bool
    mentions_author_bio: bool
    appears_closed: bool
    distinct_authors_observed: int
    guest_post_probability: int
    evidence: list[str]
    computed_at: datetime


class ScoreComponentOut(BaseModel):
    name: str
    value: int | None
    weight: int
    confidence: str
    detail: str


class OpportunityScoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    domain_id: uuid.UUID
    reference_domain_id: uuid.UUID | None
    composite_score: int | None
    components: list[ScoreComponentOut]
    evidence: list[str]
    computed_at: datetime


class LinkGapOpportunityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    candidate_domain_id: uuid.UUID
    candidate_host: str
    competitor_overlap_count: int
    competitor_hosts: list[str]
    confidence: str
    evidence: list[str]
    computed_at: datetime


class OutreachStrategyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    domain_id: uuid.UUID
    contact_id: uuid.UUID
    opportunity_type: str
    guest_post_opportunity_id: uuid.UUID | None
    link_gap_opportunity_id: uuid.UUID | None
    reason: str
    evidence: list[str]
    angle: str | None
    ai_generated: bool
    recommended_content_asset: str | None
    expected_link_probability: int | None
    difficulty: str
    computed_at: datetime
