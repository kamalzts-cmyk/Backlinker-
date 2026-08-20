"""An in-memory `AIProvider` test double for exercising AI-assisted code
paths without a real Ollama server. Queue exact `response_model` instances
to return, in call order -- later phases (outreach personalization,
GEO/AI-search intelligence) that build on `AIProvider` should use this
rather than mocking HTTP against `OllamaProvider` directly, since they
don't care about Ollama's wire format, only about the `AIProvider`
contract.
"""

from pydantic import BaseModel

from app.engines.ai.errors import AIGenerationError
from app.engines.ai.provider import AIProvider, T


class FakeAIProvider(AIProvider):
    def __init__(self, responses: list[BaseModel] | None = None) -> None:
        self._responses = list(responses or [])
        self.calls: list[dict] = []

    async def generate_structured(
        self,
        *,
        prompt: str,
        response_model: type[T],
        system: str | None = None,
    ) -> T:
        self.calls.append({"prompt": prompt, "response_model": response_model, "system": system})
        if not self._responses:
            raise AIGenerationError("FakeAIProvider has no queued responses left")
        response = self._responses.pop(0)
        if not isinstance(response, response_model):
            raise AIGenerationError(
                f"FakeAIProvider's next queued response is a {type(response).__name__}, "
                f"caller requested {response_model.__name__}"
            )
        return response
