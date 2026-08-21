"""Search-pattern backlink discovery. See PRODUCT_SPEC.md §4.2 Layer 2:

    Search discovery -- generated query patterns ("brand", "brand"
    -site:brand.com, "brand" resources, "brand" "according to",
    filetype:pdf "brand", etc.) against a search backend, producing
    candidate URLs to crawl.

and docs/ARCHITECTURE.md risk #3 ("search discovery depends on a search
backend ... needs an explicit decision before Phase 4/7").

**Decision:** reuse `AISearchProvider` (app/engines/search/) -- the same
search backend Phase 18 needed for GEO citation checking. See
app/engines/search/anthropic_provider.py's docstring for the full
rationale; in short, it resolves this risk the same way Phase 18's was
resolved: a real, independently-verified API, not a guessed-at scraping
approach PRODUCT_SPEC.md's own "don't promise all backlinks" caution
(§34) would make hard to justify anyway.

Like Common Crawl (app/engines/backlink/common_crawl.py), this module
only *proposes* candidates -- `BacklinkCandidate` rows with
`source_type=SEARCH_DISCOVERED`, `status=PENDING`. Nothing here inspects
whether the result page actually contains the link; that's still Phase
3's job (`verify_candidate`), the only thing allowed to set
`VERIFIED`.
"""

from sqlalchemy.orm import Session

from app.crawler.normalize import registrable_domain_for_url
from app.db.models import BacklinkCandidate, BacklinkSourceType, Domain
from app.engines.backlink.repository import create_candidate
from app.engines.search.provider import AISearchProvider


# The exact patterns PRODUCT_SPEC.md §4.2 Layer 2 names, parameterized on
# a brand/topic query string. "-site:{own_host}" only applies when the
# caller can name the target's own domain (excludes self-results, not
# external backlink sources); every other pattern applies regardless.
def _query_patterns(brand_query: str, *, exclude_host: str | None) -> list[str]:
    patterns = [
        f'"{brand_query}"',
        f'"{brand_query}" resources',
        f'"{brand_query}" "according to"',
        f'filetype:pdf "{brand_query}"',
    ]
    if exclude_host:
        patterns.insert(1, f'"{brand_query}" -site:{exclude_host}')
    return patterns


async def discover_candidates_from_search(
    session: Session,
    *,
    brand_query: str,
    target_domain: Domain,
    target_url: str,
    provider: AISearchProvider,
    results_per_pattern: int | None = None,
) -> list[BacklinkCandidate]:
    """Runs PRODUCT_SPEC.md's named query patterns for `brand_query`
    through `provider`, turning every distinct result URL into a
    `PENDING` `BacklinkCandidate` targeting `target_url`. Self-results
    (pages already on `target_domain` itself) are skipped -- not
    external backlink sources. Still requires Phase 3 verification
    before any of these can be trusted as real.
    """
    patterns = _query_patterns(brand_query, exclude_host=target_domain.normalized_host)

    seen_urls: set[str] = set()
    created: list[BacklinkCandidate] = []

    for pattern in patterns:
        result = await provider.search(pattern)
        urls = result.citations
        if results_per_pattern is not None:
            urls = urls[:results_per_pattern]

        for url in urls:
            if url in seen_urls:
                continue
            seen_urls.add(url)

            if registrable_domain_for_url(url) == target_domain.normalized_host:
                continue  # a page on the target's own site, not an external source

            candidate = create_candidate(
                session,
                source_url=url,
                target_url=target_url,
                target_domain_id=target_domain.id,
                source_type=BacklinkSourceType.SEARCH_DISCOVERED,
                discovery_method=f"search_pattern:{pattern}",
            )
            created.append(candidate)

    return created
