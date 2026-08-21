"""Unit tests for AnthropicSearchProvider. Its HTTP transport is mocked
(respx) with responses shaped exactly like the documented web search
tool response (verified live against platform.claude.com at
implementation time -- see the module's docstring) -- this sandbox has
no Anthropic API key configured for this project's own deployment, so
these tests prove the request construction and response parsing are
correct, not that a live call succeeds. Run a live smoke test with a
real key before depending on this in production.
"""

import httpx
import pytest
import respx

from app.engines.search.anthropic_provider import AnthropicSearchProvider
from app.engines.search.errors import AISearchError

_API_URL = "https://api.anthropic.com/v1/messages"


def _message_response(content: list[dict], stop_reason: str = "end_turn") -> dict:
    return {
        "id": "msg_test123",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5",
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 100, "output_tokens": 50},
    }


@pytest.mark.asyncio
@respx.mock
async def test_search_parses_a_real_web_search_response_shape():
    route = respx.post(_API_URL).mock(
        return_value=httpx.Response(
            200,
            json=_message_response(
                [
                    {"type": "text", "text": "I'll search for that."},
                    {
                        "type": "server_tool_use",
                        "id": "srvtoolu_01",
                        "name": "web_search",
                        "input": {"query": "claude shannon birth date"},
                    },
                    {
                        "type": "web_search_tool_result",
                        "tool_use_id": "srvtoolu_01",
                        "content": [
                            {
                                "type": "web_search_result",
                                "url": "https://en.wikipedia.org/wiki/Claude_Shannon",
                                "title": "Claude Shannon - Wikipedia",
                                "encrypted_content": "abc123",
                                "page_age": "April 30, 2025",
                            }
                        ],
                    },
                    {
                        "type": "text",
                        "text": "Claude Shannon was born on April 30, 1916.",
                        "citations": [
                            {
                                "type": "web_search_result_location",
                                "url": "https://en.wikipedia.org/wiki/Claude_Shannon",
                                "title": "Claude Shannon - Wikipedia",
                                "encrypted_index": "xyz",
                                "cited_text": "Claude Elwood Shannon (April 30, 1916 ...)",
                            }
                        ],
                    },
                ]
            ),
        )
    )

    provider = AnthropicSearchProvider(api_key="test-key")
    result = await provider.search("when was claude shannon born")

    assert route.called
    request_body = route.calls[0].request.content
    import json as _json

    body = _json.loads(request_body)
    assert body["messages"] == [{"role": "user", "content": "when was claude shannon born"}]
    assert body["tools"] == [{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}]

    assert result.citations == ["https://en.wikipedia.org/wiki/Claude_Shannon"]
    assert "April 30, 1916" in result.answer_text


@pytest.mark.asyncio
@respx.mock
async def test_search_returns_empty_citations_when_no_search_happened():
    respx.post(_API_URL).mock(
        return_value=httpx.Response(
            200, json=_message_response([{"type": "text", "text": "Paris is the capital of France."}])
        )
    )

    provider = AnthropicSearchProvider(api_key="test-key")
    result = await provider.search("what is the capital of france")

    assert result.citations == []
    assert result.answer_text == "Paris is the capital of France."


@pytest.mark.asyncio
@respx.mock
async def test_search_deduplicates_repeated_urls_across_multiple_searches():
    respx.post(_API_URL).mock(
        return_value=httpx.Response(
            200,
            json=_message_response(
                [
                    {
                        "type": "web_search_tool_result",
                        "tool_use_id": "srvtoolu_01",
                        "content": [
                            {"type": "web_search_result", "url": "https://example.com/a", "title": "A"}
                        ],
                    },
                    {
                        "type": "web_search_tool_result",
                        "tool_use_id": "srvtoolu_02",
                        "content": [
                            {"type": "web_search_result", "url": "https://example.com/a", "title": "A"},
                            {"type": "web_search_result", "url": "https://example.com/b", "title": "B"},
                        ],
                    },
                    {"type": "text", "text": "done"},
                ]
            ),
        )
    )

    provider = AnthropicSearchProvider(api_key="test-key")
    result = await provider.search("query")

    assert result.citations == ["https://example.com/a", "https://example.com/b"]


@pytest.mark.asyncio
@respx.mock
async def test_search_ignores_a_web_search_tool_result_error_block():
    respx.post(_API_URL).mock(
        return_value=httpx.Response(
            200,
            json=_message_response(
                [
                    {
                        "type": "web_search_tool_result",
                        "tool_use_id": "srvtoolu_01",
                        "content": {"type": "web_search_tool_result_error", "error_code": "max_uses_exceeded"},
                    },
                    {"type": "text", "text": "I could not complete the search."},
                ]
            ),
        )
    )

    provider = AnthropicSearchProvider(api_key="test-key")
    result = await provider.search("query")

    assert result.citations == []
    assert result.answer_text == "I could not complete the search."


@pytest.mark.asyncio
@respx.mock
async def test_search_raises_on_refusal_stop_reason():
    respx.post(_API_URL).mock(
        return_value=httpx.Response(
            200, json=_message_response([{"type": "text", "text": ""}], stop_reason="refusal")
        )
    )

    provider = AnthropicSearchProvider(api_key="test-key")
    with pytest.raises(AISearchError):
        await provider.search("query")


@pytest.mark.asyncio
@respx.mock
async def test_search_raises_on_http_failure():
    respx.post(_API_URL).mock(return_value=httpx.Response(529, json={"error": {"message": "overloaded"}}))

    provider = AnthropicSearchProvider(api_key="test-key")
    with pytest.raises(AISearchError):
        await provider.search("query")


@pytest.mark.asyncio
async def test_search_raises_a_clean_error_when_no_credentials_are_configured(monkeypatch):
    # Explicitly clear any ambient credential env vars so this doesn't
    # depend on what happens to be set in whatever environment runs the
    # suite -- the SDK fails before any HTTP call is made in this case,
    # so nothing here needs respx. Confirms the real credential-missing
    # failure mode (a bare TypeError from the SDK) is caught and
    # surfaced as AISearchError, not left to crash the caller.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    provider = AnthropicSearchProvider()
    with pytest.raises(AISearchError):
        await provider.search("query")
