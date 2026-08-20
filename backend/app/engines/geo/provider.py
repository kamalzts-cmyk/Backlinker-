"""The AI-search ("answer engine") provider interface. See
app/db/models.py's Phase 18 comment block for why no concrete
implementation ships here, unlike Phase 13's OllamaProvider.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class AISearchResult:
    answer_text: str
    citations: list[str]  # URLs the answer engine says it drew on


class AISearchProvider(ABC):
    @abstractmethod
    async def search(self, query: str) -> AISearchResult:
        """Runs `query` against a real answer engine and returns its
        answer plus whatever citation URLs it reports. Implementations
        must return citations exactly as the engine reported them --
        never inferred, deduplicated against assumptions, or
        supplemented with guesses.
        """
        raise NotImplementedError
