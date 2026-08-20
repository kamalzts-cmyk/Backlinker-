"""Opportunity scoring. See PRODUCT_SPEC.md §8/§11-12/§54-55 and
app/db/models.py's OpportunityScore docstring for why this is a smaller,
honestly-scoped component set rather than the full named list in the
spec -- every component here is computed from data this project actually
collected; anything we can't measure (organic traffic, most of all) is
reported unavailable, never fabricated.

Composite formula: a weighted average over only the *available*
components (weights renormalized among whichever ones have real data),
then spam risk is subtracted as a dampener -- a prospect that scores
well on everything else but looks spammy should not rank as highly.
"""

import re
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Contact,
    ContactVerificationStatus,
    CrawlError,
    CrawlJob,
    GuestPostOpportunity,
    LinkGapOpportunity,
    OpportunityScore,
    Page,
)

_WORD_RE = re.compile(r"[a-z]{4,}")  # 4+ letter words only -- crude but stopword-resistant
_STOPWORDS = frozenset(
    {
        "this",
        "that",
        "with",
        "from",
        "your",
        "have",
        "will",
        "about",
        "more",
        "into",
        "their",
        "which",
        "when",
        "what",
        "there",
        "here",
        "than",
        "then",
        "also",
        "such",
        "page",
        "home",
    }
)

# name -> weight (out of 100, among *available* components -- see
# _compute_composite for the renormalization).
_WEIGHTS = {
    "topical_relevance": 25,
    "content_depth": 20,
    "link_probability": 15,
    "contactability": 15,
    "indexability": 10,
    "organic_traffic": 15,
}
_SPAM_RISK_DAMPENING = 0.3


@dataclass
class ScoreComponent:
    name: str
    value: int | None  # 0-100, None if unavailable
    weight: int
    confidence: str  # "measured" | "unavailable"
    detail: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "value": self.value,
            "weight": self.weight,
            "confidence": self.confidence,
            "detail": self.detail,
        }


@dataclass
class OpportunityScoreResult:
    composite_score: int | None
    components: list[ScoreComponent] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)


def compute_opportunity_score(
    session: Session, *, domain_id: uuid.UUID, reference_domain_id: uuid.UUID | None = None
) -> OpportunityScore:
    components = [
        _indexability_component(session, domain_id),
        _content_depth_component(session, domain_id),
        _contactability_component(session, domain_id),
        _link_probability_component(session, domain_id, reference_domain_id),
        _topical_relevance_component(session, domain_id, reference_domain_id),
        _organic_traffic_component(),
    ]
    spam_risk = _spam_risk_component(session, domain_id)

    composite = _compute_composite(components, spam_risk)
    evidence = [f"{c.name}: {c.detail}" for c in components if c.confidence == "measured"]
    evidence.append(f"spam_risk: {spam_risk.detail}")

    return _upsert(
        session,
        domain_id=domain_id,
        reference_domain_id=reference_domain_id,
        composite_score=composite,
        components=[c.to_dict() for c in [*components, spam_risk]],
        evidence=evidence,
    )


def _compute_composite(components: list[ScoreComponent], spam_risk: ScoreComponent) -> int | None:
    available = [c for c in components if c.value is not None]
    if not available:
        return None
    total_weight = sum(c.weight for c in available)
    weighted_sum = sum(c.value * c.weight for c in available)
    base = round(weighted_sum / total_weight)

    if spam_risk.value is not None:
        base = max(0, base - round(spam_risk.value * _SPAM_RISK_DAMPENING))
    return min(100, base)


def _indexability_component(session: Session, domain_id: uuid.UUID) -> ScoreComponent:
    pages = session.scalars(select(Page).where(Page.domain_id == domain_id)).all()
    if not pages:
        return ScoreComponent(
            "indexability", None, _WEIGHTS["indexability"], "unavailable", "no pages crawled yet"
        )
    indexable_count = sum(1 for p in pages if p.is_indexable)
    value = round(100 * indexable_count / len(pages))
    return ScoreComponent(
        "indexability",
        value,
        _WEIGHTS["indexability"],
        "measured",
        f"{indexable_count}/{len(pages)} crawled pages are indexable",
    )


def _content_depth_component(session: Session, domain_id: uuid.UUID) -> ScoreComponent:
    pages = session.scalars(select(Page).where(Page.domain_id == domain_id)).all()
    if not pages:
        return ScoreComponent(
            "content_depth", None, _WEIGHTS["content_depth"], "unavailable", "no pages crawled yet"
        )
    word_counts = [p.word_count or 0 for p in pages]
    avg_words = sum(word_counts) / len(word_counts)
    # deterministic tiers: <200 thin, 200-800 moderate, 800+ substantial
    depth_value = max(0, min(100, round(avg_words / 8)))  # 800 words -> 100
    schema_ratio = sum(1 for p in pages if p.schema_org) / len(pages)
    value = round(min(100, depth_value * 0.8 + schema_ratio * 100 * 0.2))
    return ScoreComponent(
        "content_depth",
        value,
        _WEIGHTS["content_depth"],
        "measured",
        f"avg {round(avg_words)} words/page across {len(pages)} pages, "
        f"{round(schema_ratio * 100)}% with schema.org markup",
    )


def _contactability_component(session: Session, domain_id: uuid.UUID) -> ScoreComponent:
    contacts = session.scalars(select(Contact).where(Contact.domain_id == domain_id)).all()
    if not contacts:
        return ScoreComponent(
            "contactability", None, _WEIGHTS["contactability"], "unavailable", "no contacts discovered"
        )
    named = sum(1 for c in contacts if c.name is not None)
    quality_bonus = sum(
        10
        for c in contacts
        if c.verification_status
        in (ContactVerificationStatus.LIKELY, ContactVerificationStatus.VERIFIED)
    )
    value = min(100, len(contacts) * 15 + named * 10 + quality_bonus)
    return ScoreComponent(
        "contactability",
        value,
        _WEIGHTS["contactability"],
        "measured",
        f"{len(contacts)} contact(s) discovered ({named} named)",
    )


def _link_probability_component(
    session: Session, domain_id: uuid.UUID, reference_domain_id: uuid.UUID | None
) -> ScoreComponent:
    reasons = []
    value = None

    if reference_domain_id is not None:
        gap = session.scalar(
            select(LinkGapOpportunity).where(
                LinkGapOpportunity.primary_domain_id == reference_domain_id,
                LinkGapOpportunity.candidate_domain_id == domain_id,
            )
        )
        if gap is not None:
            value = min(100, gap.competitor_overlap_count * 30)
            reasons.append(f"links to {gap.competitor_overlap_count} tracked competitor(s)")

    guest_post = session.scalar(
        select(GuestPostOpportunity).where(GuestPostOpportunity.domain_id == domain_id)
    )
    if guest_post is not None:
        value = guest_post.guest_post_probability if value is None else round(
            (value + guest_post.guest_post_probability) / 2
        )
        reasons.append(f"guest-post probability {guest_post.guest_post_probability}")

    if value is None:
        return ScoreComponent(
            "link_probability",
            None,
            _WEIGHTS["link_probability"],
            "unavailable",
            "no link-gap or guest-post data for this domain",
        )
    return ScoreComponent(
        "link_probability", value, _WEIGHTS["link_probability"], "measured", "; ".join(reasons)
    )


def _topical_relevance_component(
    session: Session, domain_id: uuid.UUID, reference_domain_id: uuid.UUID | None
) -> ScoreComponent:
    if reference_domain_id is None:
        return ScoreComponent(
            "topical_relevance",
            None,
            _WEIGHTS["topical_relevance"],
            "unavailable",
            "no reference domain given to compare against",
        )

    domain_words = _significant_words(session, domain_id)
    reference_words = _significant_words(session, reference_domain_id)
    if not domain_words or not reference_words:
        return ScoreComponent(
            "topical_relevance",
            None,
            _WEIGHTS["topical_relevance"],
            "unavailable",
            "not enough crawled text on one or both domains",
        )

    overlap = domain_words & reference_words
    union = domain_words | reference_words
    jaccard = len(overlap) / len(union) if union else 0.0
    value = round(min(100, jaccard * 400))  # jaccard is typically small; scale up
    top_shared = ", ".join(sorted(overlap)[:8]) or "none"
    return ScoreComponent(
        "topical_relevance",
        value,
        _WEIGHTS["topical_relevance"],
        "measured",
        f"keyword overlap (crude proxy, not semantic): {top_shared}",
    )


def _significant_words(session: Session, domain_id: uuid.UUID, top_n: int = 40) -> set[str]:
    pages = session.scalars(select(Page).where(Page.domain_id == domain_id)).all()
    text = " ".join(filter(None, (p.title or "" for p in pages)))
    text += " " + " ".join(filter(None, (p.meta_description or "" for p in pages)))
    words = [w for w in _WORD_RE.findall(text.lower()) if w not in _STOPWORDS]
    counts = Counter(words)
    return {word for word, _ in counts.most_common(top_n)}


def _organic_traffic_component() -> ScoreComponent:
    # No traffic data source is integrated (no GA/GSC/SEMrush-style
    # access) -- see PRODUCT_SPEC.md §9/§43: never fabricate traffic.
    return ScoreComponent(
        "organic_traffic",
        None,
        _WEIGHTS["organic_traffic"],
        "unavailable",
        "no traffic data source integrated",
    )


def _spam_risk_component(session: Session, domain_id: uuid.UUID) -> ScoreComponent:
    pages = session.scalars(select(Page).where(Page.domain_id == domain_id)).all()
    jobs = session.scalars(select(CrawlJob).where(CrawlJob.domain_id == domain_id)).all()
    if not pages and not jobs:
        return ScoreComponent("spam_risk", None, 0, "unavailable", "no crawl data")

    error_count = 0
    if jobs:
        job_ids = [j.id for j in jobs]
        error_count = len(
            session.scalars(select(CrawlError).where(CrawlError.crawl_job_id.in_(job_ids))).all()
        )

    total_requests = max(len(pages) + error_count, 1)
    error_ratio = error_count / total_requests

    thin_pages = sum(1 for p in pages if (p.word_count or 0) < 100)
    thin_ratio = thin_pages / len(pages) if pages else 0

    risk = round(min(100, error_ratio * 100 * 0.5 + thin_ratio * 100 * 0.5))
    return ScoreComponent(
        "spam_risk",
        risk,
        0,
        "measured",
        f"{round(error_ratio * 100)}% crawl error rate, {round(thin_ratio * 100)}% thin pages (<100 words)",
    )


def _upsert(
    session: Session,
    *,
    domain_id: uuid.UUID,
    reference_domain_id: uuid.UUID | None,
    composite_score: int | None,
    components: list[dict],
    evidence: list[str],
) -> OpportunityScore:
    query = select(OpportunityScore).where(OpportunityScore.domain_id == domain_id)
    query = (
        query.where(OpportunityScore.reference_domain_id.is_(None))
        if reference_domain_id is None
        else query.where(OpportunityScore.reference_domain_id == reference_domain_id)
    )
    existing = session.scalar(query)
    now = datetime.now(UTC)

    if existing is not None:
        existing.composite_score = composite_score
        existing.components = components
        existing.evidence = evidence
        existing.computed_at = now
        session.flush()
        return existing

    score = OpportunityScore(
        domain_id=domain_id,
        reference_domain_id=reference_domain_id,
        composite_score=composite_score,
        components=components,
        evidence=evidence,
        computed_at=now,
    )
    session.add(score)
    session.flush()
    return score
