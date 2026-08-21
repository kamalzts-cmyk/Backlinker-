"""Phase 7: prospect discovery. See app/db/models.py's Prospect
docstring for the full rationale -- in short: independent discovery of
topically relevant sites (PRODUCT_SPEC.md §4.4), distinct from
search-pattern *backlink* discovery (§4.2 Layer 2,
app/engines/backlink/search_discovery.py), which looks for pages that
might already mention a specific target. This module doesn't care
whether a site has ever mentioned the target -- it's asking "is this
site topically relevant enough to be worth pitching at all."

Reuses the same `AISearchProvider` search backend as
app/engines/backlink/search_discovery.py and app/engines/geo/citations.py
-- see app/engines/search/anthropic_provider.py for why this resolves
docs/ARCHITECTURE.md risk #3.

`category` is deterministic (which query template surfaced the result),
never inferred from page content we haven't crawled.
`topical_fit_score` is an explicitly-labeled crude keyword-overlap proxy
-- see the model docstring for why a real comparison belongs to Phase
11's opportunity scoring instead.
"""

import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.crawler.normalize import registrable_domain_for_url
from app.crawler.repository import get_or_create_domain
from app.db.models import Prospect, ProspectCategory
from app.engines.search.provider import AISearchProvider

_WORD_RE = re.compile(r"[a-z]{3,}")

# The categories PRODUCT_SPEC.md §4.4 names, each with a query template
# built around the caller's topic string.
_QUERY_TEMPLATES: dict[ProspectCategory, str] = {
    ProspectCategory.ROUNDUP: '"best {topic}" tools',
    ProspectCategory.RESOURCE_PAGE: '"{topic}" resources',
    ProspectCategory.GUEST_POST_BLOG: '"{topic}" "write for us"',
    ProspectCategory.INDUSTRY_PUBLICATION: '"{topic}" blog',
}


def _words(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def _topical_fit_score(topic_words: set[str], host: str, answer_text: str) -> int:
    if not topic_words:
        return 0
    overlap = topic_words & (_words(host) | _words(answer_text))
    return min(100, round(100 * len(overlap) / len(topic_words)))


async def discover_prospects(
    session: Session,
    *,
    topic: str,
    provider: AISearchProvider,
    results_per_pattern: int | None = None,
) -> list[Prospect]:
    topic_words = _words(topic)
    seen_hosts: set[str] = set()
    created: list[Prospect] = []

    for category, template in _QUERY_TEMPLATES.items():
        query = template.format(topic=topic)
        result = await provider.search(query)
        urls = result.citations[:results_per_pattern] if results_per_pattern else result.citations

        for url in urls:
            host = registrable_domain_for_url(url)
            if host in seen_hosts:
                continue
            seen_hosts.add(host)

            domain = get_or_create_domain(session, raw_host=host)
            score = _topical_fit_score(topic_words, host, result.answer_text)
            evidence = [f"Surfaced by {category.value} query: {query}", f"Result URL: {url}"]
            if result.answer_text:
                evidence.append(f"Search summary: {result.answer_text[:300]}")

            created.append(
                _upsert(
                    session,
                    domain_id=domain.id,
                    topic_query=topic,
                    category=category,
                    source_url=url,
                    topical_fit_score=score,
                    evidence=evidence,
                )
            )

    return created


def _upsert(
    session: Session,
    *,
    domain_id: uuid.UUID,
    topic_query: str,
    category: ProspectCategory,
    source_url: str,
    topical_fit_score: int,
    evidence: list[str],
) -> Prospect:
    existing = session.scalar(
        select(Prospect).where(Prospect.domain_id == domain_id, Prospect.topic_query == topic_query)
    )
    if existing is not None:
        existing.category = category
        existing.source_url = source_url
        existing.topical_fit_score = topical_fit_score
        existing.evidence = evidence
        session.flush()
        return existing

    prospect = Prospect(
        domain_id=domain_id,
        topic_query=topic_query,
        category=category,
        source_url=source_url,
        topical_fit_score=topical_fit_score,
        evidence=evidence,
    )
    session.add(prospect)
    session.flush()
    return prospect
