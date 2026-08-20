"""Crawl layer (Phase 1-2) + backlink engine (Phase 3) models. See
docs/DATABASE.md.

Prospect/contact/outreach tables are deliberately not modeled yet -- they
belong to later phases and depend on data these layers produce. Adding
them now, empty, would be exactly the kind of premature scaffolding
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
    UniqueConstraint,
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


# Shared column type: reused (not re-instantiated) everywhere a
# link_position column is needed. SQLAlchemy/Alembic track "has this PG
# enum type already been created" by object identity, not by name -- two
# separate `Enum(LinkPosition, name="link_position")` instances across
# different tables produce two CREATE TYPE statements for the same name
# and the second one fails.
_LINK_POSITION_TYPE = Enum(LinkPosition, name="link_position")


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
    # Normalized, capped visible text (see app/crawler/extractors/page.py)
    # -- for full-text search (docs/DATABASE.md indexing strategy) and
    # downstream text analysis (e.g. app/engines/guest_post/detect.py).
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    robots_meta_noindex: Mapped[bool] = mapped_column(Boolean, default=False)
    robots_meta_nofollow: Mapped[bool] = mapped_column(Boolean, default=False)
    is_indexable: Mapped[bool] = mapped_column(Boolean, default=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    html_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    text_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    structure_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Phase 2: structured metadata + deterministic contact-info candidates
    # (docs/CRAWLER.md §4 Page-level). JSON-LD only for schema_org -- see
    # app/crawler/extractors/schema.py. contact_emails/contact_phones are
    # raw candidates found in page text, not verified `contacts` rows --
    # that association/verification is Phase 8/9.
    schema_org: Mapped[list | None] = mapped_column(JSON, nullable=True)
    open_graph: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    twitter_card: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    images: Mapped[list | None] = mapped_column(JSON, nullable=True)
    pdf_links: Mapped[list | None] = mapped_column(JSON, nullable=True)
    social_links: Mapped[list | None] = mapped_column(JSON, nullable=True)
    embeds: Mapped[list | None] = mapped_column(JSON, nullable=True)
    contact_emails: Mapped[list | None] = mapped_column(JSON, nullable=True)
    contact_phones: Mapped[list | None] = mapped_column(JSON, nullable=True)

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
        _LINK_POSITION_TYPE, default=LinkPosition.UNKNOWN
    )
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    source_page: Mapped[Page] = relationship(back_populates="outbound_links")


# ---------------------------------------------------------------------------
# Phase 3: backlink discovery + direct verification (see docs/DATABASE.md
# §Backlink engine, docs/CRAWLER.md §6, PRODUCT_SPEC.md §4.2).
#
# Two-stage pipeline: a BacklinkCandidate ("source_url might link to
# target_url", from some discovery mechanism) is *directly verified* by
# crawling source_url ourselves -- only that crawl can produce a VERIFIED
# BacklinkObservation. Observations are append-only (one per verification
# run); Backlink is the derived current-state row per (source_url,
# target_url) pair, giving first_seen/last_seen history for free.
# ---------------------------------------------------------------------------


class BacklinkSourceType(str, enum.Enum):
    """How a candidate URL was discovered. Distinct from an observation's
    verification method, which is always DIRECT_CRAWL once VERIFIED --
    see PRODUCT_SPEC.md §2's provenance/confidence table.
    """

    DIRECT_CRAWL = "direct_crawl"
    COMMON_CRAWL = "common_crawl"
    SEARCH_DISCOVERED = "search_discovered"
    USER_PROVIDED = "user_provided"


# Shared instance for the same reason as _LINK_POSITION_TYPE above -- used
# on both BacklinkCandidate.source_type and BacklinkObservation.source_type.
_BACKLINK_SOURCE_TYPE = Enum(BacklinkSourceType, name="backlink_source_type")


class BacklinkCandidateStatus(str, enum.Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"


class BacklinkRejectionReason(str, enum.Enum):
    SOURCE_UNREACHABLE = "source_unreachable"
    TARGET_NOT_FOUND = "target_not_found"
    BLOCKED = "blocked"


class BacklinkLinkType(str, enum.Enum):
    """Deterministic subset only -- NAVIGATION/FOOTER come from
    link_position, SPONSORED/UGC from rel attributes. The fuller taxonomy
    in PRODUCT_SPEC.md §4.2 (guest_post, directory, citation, resource_page,
    ...) requires content judgment and is AI-assisted link-context
    classification (Phase 12), not guessed here.
    """

    NAVIGATION = "navigation"
    FOOTER = "footer"
    SPONSORED = "sponsored"
    UGC = "ugc"
    UNKNOWN = "unknown"


class BacklinkCandidate(TimestampMixin, Base):
    __tablename__ = "backlink_candidates"

    id: Mapped[uuid.UUID] = _uuid_pk()
    source_url: Mapped[str] = mapped_column(String(2048))
    target_url: Mapped[str] = mapped_column(String(2048))
    target_domain_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("domains.id"), index=True)
    source_type: Mapped[BacklinkSourceType] = mapped_column(_BACKLINK_SOURCE_TYPE)
    discovery_method: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[BacklinkCandidateStatus] = mapped_column(
        Enum(BacklinkCandidateStatus, name="backlink_candidate_status"),
        default=BacklinkCandidateStatus.PENDING,
    )
    rejection_reason: Mapped[BacklinkRejectionReason | None] = mapped_column(
        Enum(BacklinkRejectionReason, name="backlink_rejection_reason"), nullable=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    target_domain: Mapped[Domain] = relationship()
    observations: Mapped[list["BacklinkObservation"]] = relationship(back_populates="candidate")


class BacklinkObservation(TimestampMixin, Base):
    """Append-only: one row per verification run. See docs/DATABASE.md
    §Backlink engine -- this is what powers "follow -> nofollow" history.
    """

    __tablename__ = "backlink_observations"

    id: Mapped[uuid.UUID] = _uuid_pk()
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("backlink_candidates.id"), nullable=True, index=True
    )
    source_url: Mapped[str] = mapped_column(String(2048))
    source_domain_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("domains.id"), index=True)
    target_url: Mapped[str] = mapped_column(String(2048))
    target_domain_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("domains.id"), index=True)
    anchor_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    surrounding_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    rel_nofollow: Mapped[bool] = mapped_column(Boolean, default=False)
    rel_sponsored: Mapped[bool] = mapped_column(Boolean, default=False)
    rel_ugc: Mapped[bool] = mapped_column(Boolean, default=False)
    link_position: Mapped[LinkPosition] = mapped_column(_LINK_POSITION_TYPE)
    link_type: Mapped[BacklinkLinkType] = mapped_column(
        Enum(BacklinkLinkType, name="backlink_link_type"), default=BacklinkLinkType.UNKNOWN
    )
    source_canonical_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    source_http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_is_indexable: Mapped[bool] = mapped_column(Boolean, default=True)
    # Provenance columns per PRODUCT_SPEC.md §3.1 / docs/DATABASE.md
    # §Conventions. source_type here is the *verification* method
    # (always DIRECT_CRAWL for a VERIFIED row); see BacklinkCandidate for
    # discovery lineage.
    source_type: Mapped[BacklinkSourceType] = mapped_column(_BACKLINK_SOURCE_TYPE)
    confidence_score: Mapped[int] = mapped_column(Integer)
    crawl_request_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crawl_requests.id"), nullable=True
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    candidate: Mapped[BacklinkCandidate | None] = relationship(back_populates="observations")


class Backlink(TimestampMixin, Base):
    """Current-state denormalized view of a source->target pair, always
    derived from BacklinkObservation -- never hand-edited. See
    docs/DATABASE.md §Backlink engine.
    """

    __tablename__ = "backlinks"

    id: Mapped[uuid.UUID] = _uuid_pk()
    source_domain_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("domains.id"), index=True)
    target_domain_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("domains.id"), index=True)
    source_url: Mapped[str] = mapped_column(String(2048))
    target_url: Mapped[str] = mapped_column(String(2048))
    latest_observation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("backlink_observations.id"))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    latest_observation: Mapped[BacklinkObservation] = relationship()

    __table_args__ = (UniqueConstraint("source_url", "target_url", name="uq_backlinks_source_target"),)


# ---------------------------------------------------------------------------
# Phase 5: competitor intelligence + link gap (see docs/DATABASE.md
# §Competitor intelligence, PRODUCT_SPEC.md §4.3/§7 and §13-14).
#
# No "project" concept exists yet (that's the Identity/API layer, not
# built -- see docs/ARCHITECTURE.md §9). A competitor relationship is
# just "domain A treats domain B as a competitor," keyed directly on
# domains like the backlink engine. Link gaps are computed purely from
# existing `backlinks` rows -- no new crawling mechanism: a "competitor
# crawl" is just backlink discovery/verification (Phase 3/4) run with the
# competitor's domain as the target.
# ---------------------------------------------------------------------------


class LinkGapConfidence(str, enum.Enum):
    """Deterministic tiering from competitor_overlap_count alone --
    PRODUCT_SPEC.md §13's qualitative examples (1 competitor -> MEDIUM,
    3 competitors -> HIGH), not the full weighted Opportunity Score
    (that requires relevance/authority/traffic/etc. and is Phase 11).
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CompetitorRelationship(TimestampMixin, Base):
    __tablename__ = "competitor_relationships"

    id: Mapped[uuid.UUID] = _uuid_pk()
    primary_domain_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("domains.id"), index=True)
    competitor_domain_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("domains.id"), index=True)

    primary_domain: Mapped[Domain] = relationship(foreign_keys=[primary_domain_id])
    competitor_domain: Mapped[Domain] = relationship(foreign_keys=[competitor_domain_id])

    __table_args__ = (
        UniqueConstraint("primary_domain_id", "competitor_domain_id", name="uq_competitor_pair"),
    )


class LinkGapOpportunity(TimestampMixin, Base):
    """One row per (primary_domain, candidate_domain): a domain that
    links to at least one tracked competitor but not (yet) to the
    primary domain. Recomputed (upserted) each time compute_link_gap
    runs -- see app/engines/competitor/gap.py.
    """

    __tablename__ = "link_gap_opportunities"

    id: Mapped[uuid.UUID] = _uuid_pk()
    primary_domain_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("domains.id"), index=True)
    candidate_domain_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("domains.id"), index=True)
    competitor_overlap_count: Mapped[int] = mapped_column(Integer)
    competitor_domain_ids: Mapped[list] = mapped_column(JSON)  # list of UUID strings
    confidence: Mapped[LinkGapConfidence] = mapped_column(
        Enum(LinkGapConfidence, name="link_gap_confidence")
    )
    # Phase 12 (see PRODUCT_SPEC.md §3.2): human-readable evidence, same
    # field shape as GuestPostOpportunity.evidence and
    # OpportunityScore.evidence -- every opportunity-shaped row in this
    # project carries its own "why," not a separate polymorphic table
    # joined in after the fact (see docs/ARCHITECTURE.md's Phase 12 note
    # on why evidence is colocated with what it explains).
    evidence: Mapped[list] = mapped_column(JSON)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("primary_domain_id", "candidate_domain_id", name="uq_link_gap_pair"),
    )


# ---------------------------------------------------------------------------
# Phase 8: contact intelligence (see docs/DATABASE.md §Contact
# intelligence, PRODUCT_SPEC.md §4.6).
#
# Built on top of the Phase 2 page-level extraction (Page.contact_emails/
# contact_phones/schema_org) -- discovery here means crawling a domain
# (reusing Phase 1/2's run_crawl), classifying which of its pages are
# contact-relevant (about/contact/team/author/guest-post/press), and
# turning what those pages plainly contain into Contact rows with full
# provenance. Never a capped top-N list, and never a guessed name/role
# pairing beyond what schema.org markup or an unambiguous single-person
# page gives for free -- see app/engines/contact/discover.py.
# ---------------------------------------------------------------------------


class ContactVerificationStatus(str, enum.Enum):
    """PRODUCT_SPEC.md §4.6/§12-13's mandatory enum -- never collapse
    these into a single "verified" bucket. Only DIRECTLY_PUBLISHED and
    ROLE_ADDRESS are set by Phase 8 itself (a plainly-visible email is a
    deterministic fact); VERIFIED/CATCH_ALL/INVALID require the Phase 9
    DNS/MX/SMTP verification layers, and PATTERN_INFERRED requires the
    pattern-guessing this project deliberately does not do without
    evidence.
    """

    DIRECTLY_PUBLISHED = "directly_published"
    VERIFIED = "verified"
    LIKELY = "likely"
    CATCH_ALL = "catch_all"
    ROLE_ADDRESS = "role_address"
    PATTERN_INFERRED = "pattern_inferred"
    UNKNOWN = "unknown"
    INVALID = "invalid"


# Shared instance -- reused on both Contact.verification_status and
# EmailVerification.result_status. See _LINK_POSITION_TYPE's comment
# earlier in this file (docs/ARCHITECTURE.md risk #13/#15) for why a
# fresh `Enum(ContactVerificationStatus, name=...)` per column breaks
# Alembic autogenerate.
_CONTACT_VERIFICATION_STATUS_TYPE = Enum(
    ContactVerificationStatus, name="contact_verification_status"
)


class ContactPageType(str, enum.Enum):
    HOME = "home"
    ABOUT = "about"
    CONTACT = "contact"
    TEAM = "team"
    AUTHOR = "author"
    GUEST_POST = "guest_post"
    PRESS = "press"
    OTHER = "other"


class Contact(TimestampMixin, Base):
    """A person or role-address discovered on a domain. Identity is
    (domain_id, email) when an email exists, else (domain_id, phone) --
    see app/engines/contact/repository.py's get_or_create_contact.
    """

    __tablename__ = "contacts"

    id: Mapped[uuid.UUID] = _uuid_pk()
    domain_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("domains.id"), index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verification_status: Mapped[ContactVerificationStatus] = mapped_column(
        _CONTACT_VERIFICATION_STATUS_TYPE,
        default=ContactVerificationStatus.UNKNOWN,
    )
    confidence_score: Mapped[int] = mapped_column(Integer, default=0)

    sources: Mapped[list["ContactSource"]] = relationship(back_populates="contact")

    __table_args__ = (
        UniqueConstraint("domain_id", "email", name="uq_contacts_domain_email"),
        UniqueConstraint("domain_id", "phone", name="uq_contacts_domain_phone"),
    )


class ContactSource(TimestampMixin, Base):
    """Provenance detail per contact -- a contact can have multiple
    sources (e.g. found on both the team page and an author bio).
    """

    __tablename__ = "contact_sources"

    id: Mapped[uuid.UUID] = _uuid_pk()
    contact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("contacts.id"), index=True)
    source_url: Mapped[str] = mapped_column(String(2048))
    source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_type: Mapped[ContactPageType] = mapped_column(Enum(ContactPageType, name="contact_page_type"))
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    contact: Mapped[Contact] = relationship(back_populates="sources")

    __table_args__ = (UniqueConstraint("contact_id", "source_url", name="uq_contact_source"),)


# ---------------------------------------------------------------------------
# Phase 9: email verification (see docs/DATABASE.md, PRODUCT_SPEC.md §4.6
# §13-14). Deterministic layers only -- syntax, domain DNS existence, MX
# records, and a disposable-domain list. SMTP-level mailbox/catch-all
# probing (RCPT TO) needs outbound port 25, which is blocked in this
# project's build sandbox and, per PRODUCT_SPEC.md, is inherently
# unreliable and never involves actually sending mail -- see
# app/engines/contact/verify_email.py's module docstring.
# ---------------------------------------------------------------------------


class EmailVerificationLayer(str, enum.Enum):
    SYNTAX = "syntax"
    DNS = "dns"
    MX = "mx"
    SMTP = "smtp"  # modeled for completeness; not reachable from this environment


class EmailVerification(TimestampMixin, Base):
    """One row per verification attempt -- kept historical (an address
    can go from valid to bouncing over time), not overwritten in place.
    """

    __tablename__ = "email_verifications"

    id: Mapped[uuid.UUID] = _uuid_pk()
    contact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("contacts.id"), index=True)
    layer_reached: Mapped[EmailVerificationLayer] = mapped_column(
        Enum(EmailVerificationLayer, name="email_verification_layer")
    )
    is_disposable_domain: Mapped[bool] = mapped_column(Boolean, default=False)
    result_status: Mapped[ContactVerificationStatus] = mapped_column(
        _CONTACT_VERIFICATION_STATUS_TYPE
    )
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# Phase 10: guest-post intelligence (see PRODUCT_SPEC.md §16/§24).
#
# Reuses Phase 8's page-type classification (a page classified
# ContactPageType.GUEST_POST) and, per PRODUCT_SPEC.md's own caution
# ("don't trust only a 'Write for us' page -- look at actual published
# evidence"), factors in how many *distinct* authors have already been
# observed on the domain's AUTHOR-classified pages (via existing Contact
# rows) as a proxy for "does this site actually publish more than one
# person." It is a proxy, not confirmed third-party authorship -- we
# can't yet tell staff writers from guest contributors without more
# signal (byline/employment data), and the probability score and its
# evidence list say so explicitly rather than overclaiming certainty.
# ---------------------------------------------------------------------------


class GuestPostOpportunity(TimestampMixin, Base):
    __tablename__ = "guest_post_opportunities"

    id: Mapped[uuid.UUID] = _uuid_pk()
    domain_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("domains.id"), unique=True, index=True)
    guideline_page_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    editor_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    word_count_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    word_count_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mentions_dofollow: Mapped[bool] = mapped_column(Boolean, default=False)
    mentions_nofollow: Mapped[bool] = mapped_column(Boolean, default=False)
    mentions_sponsored: Mapped[bool] = mapped_column(Boolean, default=False)
    mentions_author_bio: Mapped[bool] = mapped_column(Boolean, default=False)
    appears_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    distinct_authors_observed: Mapped[int] = mapped_column(Integer, default=0)
    guest_post_probability: Mapped[int] = mapped_column(Integer)
    evidence: Mapped[list] = mapped_column(JSON)  # list[str] -- see docstring above
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# Phase 11: opportunity scoring (see PRODUCT_SPEC.md §8/§11-12/§54-55).
#
# Deliberately NOT the full named component set from PRODUCT_SPEC.md §8
# (Relevance/Authority/Traffic/Editorial Quality/Link Probability/
# Topical Fit/Contactability/Indexability) -- several of those need data
# we don't have (organic traffic has no integrated source; "authority"
# in the DR/DA sense is explicitly rejected by PRODUCT_SPEC.md §8 as the
# wrong metric anyway). Instead: a smaller set of components computed
# only from data this project actually collected, each with a
# `confidence` of "measured" or "unavailable" -- never a fabricated
# number standing in for a missing signal. See
# app/engines/scoring/opportunity.py for the exact formula.
# ---------------------------------------------------------------------------


class OpportunityScore(TimestampMixin, Base):
    __tablename__ = "opportunity_scores"

    id: Mapped[uuid.UUID] = _uuid_pk()
    domain_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("domains.id"), index=True)
    # The site this opportunity is being evaluated *for* -- topical
    # relevance and link-gap-derived link probability are meaningless
    # without one. Nullable: a domain can still get a partial score
    # (content depth, contactability, indexability, spam risk) on its
    # own.
    reference_domain_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("domains.id"), nullable=True, index=True
    )
    composite_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    components: Mapped[list] = mapped_column(JSON)  # list[{name, value, weight, confidence, detail}]
    evidence: Mapped[list] = mapped_column(JSON)  # list[str]
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("domain_id", "reference_domain_id", name="uq_opportunity_score_pair"),
    )
