"""Phase 18: AI-search / GEO intelligence. See app/db/models.py's
GEOObservation docstring for the full rationale -- in short: this
project tracks whether a publisher gets cited by an answer engine for a
query, and every such claim is a logged `{query, engine, timestamp,
observed_result, source_url}` observation, never an unevidenced
assertion (PRODUCT_SPEC.md §4.8).

Two ways to produce that log:

- `record_manual_observation()` -- a human checked a real answer engine
  themselves and reports what they saw. Needs no API integration.
- `check_citation()` -- automated, via an `AISearchProvider` (see
  app/engines/search/ -- `AnthropicSearchProvider` is the concrete
  implementation, built on Claude's web search tool). The citation match
  itself is deterministic: does any URL the provider returned resolve to
  the same registrable domain being checked? Never a fuzzy/semantic
  judgment call.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.crawler.normalize import registrable_domain_for_url
from app.db.models import Domain, GEOCitationResult, GEOObservation
from app.engines.search.provider import AISearchProvider

_EXCERPT_MAX_CHARS = 500


def record_manual_observation(
    session: Session,
    *,
    query: str,
    engine: str,
    target_domain_id: uuid.UUID,
    observed_result: GEOCitationResult,
    source_url: str | None = None,
    answer_excerpt: str | None = None,
) -> GEOObservation:
    if observed_result == GEOCitationResult.CITED and not source_url:
        raise ValueError("source_url is required when observed_result is CITED")

    observation = GEOObservation(
        query=query,
        engine=engine,
        target_domain_id=target_domain_id,
        observed_result=observed_result,
        source_url=source_url,
        answer_excerpt=(answer_excerpt or "")[:_EXCERPT_MAX_CHARS] or None,
        observed_at=datetime.now(UTC),
    )
    session.add(observation)
    session.flush()
    return observation


async def check_citation(
    session: Session,
    *,
    query: str,
    engine: str,
    target_domain_id: uuid.UUID,
    provider: AISearchProvider,
) -> GEOObservation:
    domain = session.get(Domain, target_domain_id)
    if domain is None:
        raise ValueError(f"no such domain: {target_domain_id}")

    result = await provider.search(query)

    matching_url = next(
        (
            url
            for url in result.citations
            if _same_registrable_domain(url, domain.normalized_host)
        ),
        None,
    )

    observation = GEOObservation(
        query=query,
        engine=engine,
        target_domain_id=target_domain_id,
        observed_result=GEOCitationResult.CITED if matching_url else GEOCitationResult.NOT_CITED,
        source_url=matching_url,
        answer_excerpt=result.answer_text[:_EXCERPT_MAX_CHARS] or None,
        observed_at=datetime.now(UTC),
    )
    session.add(observation)
    session.flush()
    return observation


def _same_registrable_domain(url: str, normalized_host: str) -> bool:
    return registrable_domain_for_url(url) == normalized_host
