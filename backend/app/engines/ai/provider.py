"""The AI provider interface.

`PRODUCT_SPEC.md` names Ollama (local, free) as the default AI provider,
with structured (schema-constrained) generation used wherever AI assists
deterministic extraction -- never to invent facts, only to structure or
judge content that's already been crawled. Every use site passes a
Pydantic `response_model` so the provider's output is validated, not
trusted blindly.

Any provider implementation (Ollama today, optionally a paid API later)
implements this same interface, so business code in `app/engines/*` never
depends on which provider is configured.
"""

from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class AIProvider(ABC):
    """Generates a structured, schema-validated response from a prompt."""

    @abstractmethod
    async def generate_structured(
        self,
        *,
        prompt: str,
        response_model: type[T],
        system: str | None = None,
    ) -> T:
        """Generate a response conforming to `response_model`.

        Raises `AIGenerationError` (see `errors.py`) if the provider is
        unreachable, returns malformed output, or returns output that
        doesn't validate against `response_model`. Never returns a
        partially-populated or best-effort instance -- callers get either
        a fully valid `response_model` or an exception.
        """
        raise NotImplementedError
