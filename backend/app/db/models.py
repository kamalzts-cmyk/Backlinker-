"""Phase 1 models: the crawl layer only (see docs/DATABASE.md).

Backlink/prospect/contact/outreach tables are deliberately not modeled yet
-- they belong to later phases and depend on data this layer produces.
Adding them now, empty, would be exactly the kind of premature scaffolding
PRODUCT_SPEC.md warns against.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CrawlJobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class CrawlSchedule(str, enum.Enum):
    ONE_TIME = "one_time"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class CrawlMethod(str, enum.Enum):
    HTTP = "http"
    PLAYWRIGHT = "playwright"


class CrawlErrorReason(str, enum.Enum):
    BLOCKED_ROBOTS = "blocked_robots"
    BLOCKED_CAPTCHA = "blocked_captcha"
    TIMEOUT = "timeout"
    DNS_FAIL = "dns_fail"
    HTTP_4XX = "http_4xx"
    HTTP_5XX = "http_5xx"
    OTHER = "other"


class LinkPosition(str, enum.Enum):
    NAV = "nav"
    FOOTER = "footer"
    BODY = "body"
    SIDEBAR = "sidebar"
    UNKNOWN = "unknown"


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Domain(TimestampMixin, Base):
    """A normalized host. Every engine keys off normalized_host — see
    docs/DATABASE.md §Conventions and docs/ARCHITECTURE.md risk #8.
    """

    __tablename__ = "domains"

    id: Mapped[uuid.UUID] = _uuid_pk()
    raw_host: Mapped[str] = mapped_column(String(255))
    normalized_host: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_crawled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    robots_txt_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    robots_txt_raw: Mapped[str | None] = mapped_column(Text, nullable=True)

    crawl_jobs: Mapped[list["CrawlJob"]] = relationship(back_populates="domain")
    pages: Mapped[list["Page"]] = relationship(back_populates="domain")


class CrawlJob(TimestampMixin, Base):
    __tablename__ = "crawl_jobs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    domain_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("domains.id"), index=True)
    start_url: Mapped[str] = mapped_column(String(2048))
    status: Mapped[CrawlJobStatus] = mapped_column(
        Enum(CrawlJobStatus, name="crawl_job_status"), default=CrawlJobStatus.PENDING
    )
    schedule: Mapped[CrawlSchedule] = mapped_column(
        Enum(CrawlSchedule, name="crawl_schedule"), default=CrawlSchedule.ONE_TIME
    )
    max_pages: Mapped[int] = mapped_column(Integer, default=50)
    pages_crawled: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    domain: Mapped[Domain] = relationship(back_populates="crawl_jobs")
    requests: Mapped[list["CrawlRequest"]] = relationship(back_populates="crawl_job")
    errors: Mapped[list["CrawlError"]] = relationship(back_populates="crawl_job")


class CrawlRequest(TimestampMixin, Base):
    """One row per URL fetch attempt. See docs/DATABASE.md §Crawl layer."""

    __tablename__ = "crawl_requests"

    id: Mapped[uuid.UUID] = _uuid_pk()
    crawl_job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("crawl_jobs.id"), index=True)
    url: Mapped[str] = mapped_column(String(2048))
    method: Mapped[CrawlMethod] = mapped_column(Enum(CrawlMethod, name="crawl_method"))
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    redirect_chain: Mapped[list | None] = mapped_column(JSON, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    html_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    text_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    structure_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    timing_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    crawl_job: Mapped[CrawlJob] = relationship(back_populates="requests")


class CrawlError(TimestampMixin, Base):
    __tablename__ = "crawl_errors"

    id: Mapped[uuid.UUID] = _uuid_pk()
    crawl_job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("crawl_jobs.id"), index=True)
    url: Mapped[str] = mapped_column(String(2048))
    reason: Mapped[CrawlErrorReason] = mapped_column(Enum(CrawlErrorReason, name="crawl_error_reason"))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    crawl_job: Mapped[CrawlJob] = relationship(back_populates="errors")


class Page(TimestampMixin, Base):
    """Current-state snapshot of a crawled URL. See docs/DATABASE.md
    §Crawl layer for the full target field set -- Phase 1 implements the
    deterministic subset; schema.org/OG/Twitter/entity extraction is
    Phase 2 (docs/ARCHITECTURE.md Phase 2 exit criteria).
    """

    __tablename__ = "pages"

    id: Mapped[uuid.UUID] = _uuid_pk()
    domain_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("domains.id"), index=True)
    crawl_request_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crawl_requests.id"), nullable=True
    )
    url: Mapped[str] = mapped_column(String(2048), index=True)
    canonical_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    h1: Mapped[list | None] = mapped_column(JSON, nullable=True)
    headings: Mapped[list | None] = mapped_column(JSON, nullable=True)  # [{tag: "h2", text: "..."}]
    word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    robots_meta_noindex: Mapped[bool] = mapped_column(Boolean, default=False)
    robots_meta_nofollow: Mapped[bool] = mapped_column(Boolean, default=False)
    is_indexable: Mapped[bool] = mapped_column(Boolean, default=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    html_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    text_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    structure_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    crawled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    domain: Mapped[Domain] = relationship(back_populates="pages")
    outbound_links: Mapped[list["PageLink"]] = relationship(back_populates="source_page")


class PageLink(TimestampMixin, Base):
    """Every extracted link, internal or external -- the raw material the
    backlink engine (Phase 3+) is built from. See docs/DATABASE.md
    §Links.
    """

    __tablename__ = "page_links"

    id: Mapped[uuid.UUID] = _uuid_pk()
    source_page_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pages.id"), index=True)
    source_url: Mapped[str] = mapped_column(String(2048))
    target_url: Mapped[str] = mapped_column(String(2048))
    target_domain_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("domains.id"), nullable=True, index=True
    )
    anchor_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    surrounding_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    rel_nofollow: Mapped[bool] = mapped_column(Boolean, default=False)
    rel_sponsored: Mapped[bool] = mapped_column(Boolean, default=False)
    rel_ugc: Mapped[bool] = mapped_column(Boolean, default=False)
    target_blank: Mapped[bool] = mapped_column(Boolean, default=False)
    link_position: Mapped[LinkPosition] = mapped_column(
        Enum(LinkPosition, name="link_position"), default=LinkPosition.UNKNOWN
    )
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    source_page: Mapped[Page] = relationship(back_populates="outbound_links")
