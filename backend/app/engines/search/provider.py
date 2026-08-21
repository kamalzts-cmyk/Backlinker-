"""The web-search provider interface. Shared by two engines that both
need "run a query against a real search backend, get URLs back":

- Phase 18 (app/engines/geo/citations.py): does an answer engine cite
  this domain for a query.
- Phase 7 (app/engines/backlink/search_discovery.py): which pages does
  a search-pattern query surface as backlink candidates.

Originally written for Phase 18 alone (as app/engines/geo/provider.py);
moved here once Phase 7 needed the identical capability rather than
inventing a second, parallel search abstraction. See
app/engines/search/anthropic_provider.py for the concrete implementation
and its docstring for why it's a legitimate resolution of both
docs/ARCHITECTURE.md risk #3 (Phase 7's search backend) and risk #18
(Phase 18's answer-engine provider).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class AISearchResult:
    answer_text: str
    citations: list[str]  # URLs the search backend says it drew on


class AISearchProvider(ABC):
    @abstractmethod
    async def search(self, query: str) -> AISearchResult:
        """Runs `query` against a real search backend and returns its
        answer plus whatever result/citation URLs it reports.
        Implementations must return citations exactly as the backend
        reported them -- never inferred, deduplicated against
        assumptions, or supplemented with guesses.
        """
        raise NotImplementedError
