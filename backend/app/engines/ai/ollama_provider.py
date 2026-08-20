"""Ollama-backed `AIProvider`, built against Ollama's documented
structured-output API (`POST /api/generate` with a JSON Schema in the
`format` field and `stream: false` -- see
https://github.com/ollama/ollama/blob/main/docs/api.md#request-structured-outputs).

**Sandbox caveat:** Ollama itself cannot be installed or reached from this
build environment -- both `ollama.com/install.sh` and the GitHub releases
used to install it are policy-denied by the outbound proxy here (the same
egress-allowlist restriction already documented for Common Crawl, see
`../../../../docs/ARCHITECTURE.md` risk #14). This module is written and
tested against Ollama's real, documented request/response shape, with the
HTTP transport mocked (`respx`) to prove the request construction and
response parsing are correct -- but live connectivity to a real Ollama
server has not been exercised in this sandbox. Run a live smoke test
against a real `ollama serve` before depending on this in production; see
risk #17.
"""

import json

import httpx
from pydantic import ValidationError

from app.engines.ai.errors import AIGenerationError
from app.engines.ai.provider import AIProvider, T


class OllamaProvider(AIProvider):
    def __init__(self, *, host: str, model: str, timeout: float = 60.0) -> None:
        self._host = host.rstrip("/")
        self._model = model
        self._timeout = timeout

    async def generate_structured(
        self,
        *,
        prompt: str,
        response_model: type[T],
        system: str | None = None,
    ) -> T:
        payload: dict = {
            "model": self._model,
            "prompt": prompt,
            "format": response_model.model_json_schema(),
            "stream": False,
        }
        if system is not None:
            payload["system"] = system

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(f"{self._host}/api/generate", json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise AIGenerationError(f"Ollama request failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise AIGenerationError(f"Ollama returned a non-JSON envelope: {exc}") from exc

        raw_response = data.get("response")
        if not isinstance(raw_response, str):
            raise AIGenerationError(
                "Ollama response envelope had no string 'response' field"
            )

        try:
            structured = json.loads(raw_response)
        except json.JSONDecodeError as exc:
            raise AIGenerationError(
                f"Ollama's 'response' field was not valid JSON: {exc}"
            ) from exc

        try:
            return response_model.model_validate(structured)
        except ValidationError as exc:
            raise AIGenerationError(
                f"Ollama's structured output didn't match {response_model.__name__}: {exc}"
            ) from exc
