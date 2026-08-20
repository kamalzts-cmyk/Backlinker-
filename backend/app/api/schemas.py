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


class LinkGapOpportunityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    candidate_domain_id: uuid.UUID
    candidate_host: str
    competitor_overlap_count: int
    competitor_hosts: list[str]
    confidence: str
    computed_at: datetime
