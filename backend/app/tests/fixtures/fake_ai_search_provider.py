"""An in-memory `AISearchProvider` test double, same pattern as
`fake_ai_provider.py`'s `FakeAIProvider`. Queue exact `AISearchResult`
values to return, in call order -- used to prove `check_citation`'s
citation-matching logic is correct without depending on any real answer
engine (none is implemented -- see app/db/models.py's Phase 18 comment).
"""

from app.engines.geo.provider import AISearchProvider, AISearchResult


class FakeAISearchProvider(AISearchProvider):
    def __init__(self, results: list[AISearchResult] | None = None) -> None:
        self._results = list(results or [])
        self.queries: list[str] = []

    async def search(self, query: str) -> AISearchResult:
        self.queries.append(query)
        if not self._results:
            raise RuntimeError("FakeAISearchProvider has no queued results left")
        return self._results.pop(0)
