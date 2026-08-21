"""An in-memory `AISearchProvider` test double, same pattern as
`fake_ai_provider.py`'s `FakeAIProvider`. Queue exact `AISearchResult`
values to return, in call order -- used by both Phase 18 (citation
checking) and Phase 7 (search-pattern discovery) tests so their
matching/parsing logic can be proven without depending on live network
access to the real `AnthropicSearchProvider` (app/engines/search/).
"""

from app.engines.search.provider import AISearchProvider, AISearchResult


class FakeAISearchProvider(AISearchProvider):
    def __init__(self, results: list[AISearchResult] | None = None) -> None:
        self._results = list(results or [])
        self.queries: list[str] = []

    async def search(self, query: str) -> AISearchResult:
        self.queries.append(query)
        if not self._results:
            raise RuntimeError("FakeAISearchProvider has no queued results left")
        return self._results.pop(0)
