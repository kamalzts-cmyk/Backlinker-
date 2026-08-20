"""Unit tests for the AI provider layer.

`OllamaProvider`'s HTTP transport is mocked (respx) with responses shaped
exactly like Ollama's documented `/api/generate` structured-output API --
this sandbox cannot reach a real Ollama server (see the module docstring
in `app/engines/ai/ollama_provider.py` and docs/ARCHITECTURE.md risk #17)
so these tests prove the request construction and response parsing are
correct, not that a live server is reachable. Run a live smoke test
before depending on this in production.
"""

import json

import httpx
import pytest
import respx
from pydantic import BaseModel

from app.engines.ai.errors import AIGenerationError
from app.engines.ai.ollama_provider import OllamaProvider

_HOST = "http://ollama-test.invalid:11434"


class _Verdict(BaseModel):
    is_guest_post_friendly: bool
    reason: str


@pytest.mark.asyncio
@respx.mock
async def test_generate_structured_parses_a_real_ollama_response_shape():
    route = respx.post(f"{_HOST}/api/generate").mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "qwen2.5:7b",
                "created_at": "2026-08-20T00:00:00Z",
                "response": json.dumps(
                    {"is_guest_post_friendly": True, "reason": "Explicit write-for-us page"}
                ),
                "done": True,
            },
        )
    )

    provider = OllamaProvider(host=_HOST, model="qwen2.5:7b")
    result = await provider.generate_structured(
        prompt="Does this page welcome guest posts?",
        response_model=_Verdict,
        system="You are an SEO analyst.",
    )

    assert result.is_guest_post_friendly is True
    assert result.reason == "Explicit write-for-us page"

    request_body = json.loads(route.calls[0].request.content)
    assert request_body["model"] == "qwen2.5:7b"
    assert request_body["stream"] is False
    assert request_body["system"] == "You are an SEO analyst."
    assert request_body["format"] == _Verdict.model_json_schema()


@pytest.mark.asyncio
@respx.mock
async def test_generate_structured_raises_on_http_failure():
    respx.post(f"{_HOST}/api/generate").mock(return_value=httpx.Response(503))

    provider = OllamaProvider(host=_HOST, model="qwen2.5:7b")
    with pytest.raises(AIGenerationError):
        await provider.generate_structured(prompt="hello", response_model=_Verdict)


@pytest.mark.asyncio
@respx.mock
async def test_generate_structured_raises_on_non_json_response_field():
    respx.post(f"{_HOST}/api/generate").mock(
        return_value=httpx.Response(200, json={"response": "not valid json {{{", "done": True})
    )

    provider = OllamaProvider(host=_HOST, model="qwen2.5:7b")
    with pytest.raises(AIGenerationError):
        await provider.generate_structured(prompt="hello", response_model=_Verdict)


@pytest.mark.asyncio
@respx.mock
async def test_generate_structured_raises_when_output_fails_schema_validation():
    respx.post(f"{_HOST}/api/generate").mock(
        return_value=httpx.Response(
            200,
            json={"response": json.dumps({"is_guest_post_friendly": "maybe"}), "done": True},
        )
    )

    provider = OllamaProvider(host=_HOST, model="qwen2.5:7b")
    with pytest.raises(AIGenerationError):
        await provider.generate_structured(prompt="hello", response_model=_Verdict)


@pytest.mark.asyncio
@respx.mock
async def test_generate_structured_raises_when_envelope_has_no_response_field():
    respx.post(f"{_HOST}/api/generate").mock(return_value=httpx.Response(200, json={"done": True}))

    provider = OllamaProvider(host=_HOST, model="qwen2.5:7b")
    with pytest.raises(AIGenerationError):
        await provider.generate_structured(prompt="hello", response_model=_Verdict)
