"""`AnthropicSearchProvider`: a real `AISearchProvider` built against
Claude's documented web search server tool (`POST /v1/messages` with a
`web_search_20250305` tool declaration).

This resolves two open gaps at once, deliberately:

- docs/ARCHITECTURE.md risk #3 (Phase 7 needs "a search backend that
  isn't named in the free-first stack ... needs an explicit decision").
- docs/ARCHITECTURE.md risk #18 (Phase 18 shipped `AISearchProvider`
  with no concrete implementation, because no free/self-hostable
  answer-engine API existed to build a *verified* integration against).

The decision: use Claude's own web search tool as the search backend for
both. It is not free the way Ollama or Common Crawl are (it's billed
per-search plus token usage on whatever Anthropic API key the deployer
configures), but its request/response shape is real, current, and
independently verified against the live API reference at implementation
time (platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool)
-- not guessed at the way an unverified paid competitor's wire format
would have been. That was the actual blocker recorded in risk #18: not
"no paid options exist" but "no paid option's current wire format can be
confirmed from this sandbox." Confirming Anthropic's directly removes
that blocker for this one provider.

Uses the basic `web_search_20250305` tool variant (not the newer
`_20260209` dynamic-filtering variant) deliberately -- this use case is
a single small query, not a token-heavy multi-search research task, and
the basic variant's response shape is a flat list of `web_search_result`
blocks rather than nested `server_tool_use`/`caller`-attributed pairs,
which is simpler to parse correctly.

**Live reachability is unverified in this sandbox** -- same posture as
Phase 13's OllamaProvider. This class is tested with the real Anthropic
Python SDK's HTTP calls intercepted by `respx`, using response bodies
shaped exactly like the documented example, proving the request
construction and response parsing are correct. Run a live smoke test
with a real API key before depending on this in production. See
docs/ARCHITECTURE.md risk #19.
"""

import anthropic

from app.engines.search.errors import AISearchError
from app.engines.search.provider import AISearchProvider, AISearchResult

DEFAULT_MODEL = "claude-opus-5"


class AnthropicSearchProvider(AISearchProvider):
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        max_uses: int = 3,
        timeout: float = 60.0,
    ) -> None:
        # api_key=None (the constructor's own default) lets the SDK try
        # to resolve credentials itself (env var, `ant auth login`
        # profile, ...) -- see the Python SDK's own guidance; never
        # hardcode a key here. If nothing resolves anywhere, the SDK
        # doesn't fail here at construction -- it raises at request time
        # instead (see the TypeError handling in search() below).
        self._client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout)
        self._model = model
        self._max_uses = max_uses

    async def search(self, query: str) -> AISearchResult:
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                messages=[{"role": "user", "content": query}],
                tools=[
                    {
                        "type": "web_search_20250305",
                        "name": "web_search",
                        "max_uses": self._max_uses,
                    }
                ],
            )
        except anthropic.APIError as exc:
            raise AISearchError(f"Anthropic web search request failed: {exc}") from exc
        except TypeError as exc:
            # The SDK raises a plain TypeError (not an APIError subclass)
            # when it can't resolve any credentials at all -- confirmed
            # empirically, not documented as an exception type. Still an
            # honest "the upstream call didn't happen," not a crash.
            raise AISearchError(f"Anthropic client is not configured: {exc}") from exc

        if response.stop_reason == "refusal":
            raise AISearchError("Anthropic declined to answer this query")

        answer_parts: list[str] = []
        citations: list[str] = []
        seen_urls: set[str] = set()

        for block in response.content:
            if block.type == "text":
                answer_parts.append(block.text)
            elif block.type == "web_search_tool_result":
                content = block.content
                if isinstance(content, list):
                    for result in content:
                        url = getattr(result, "url", None)
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            citations.append(url)
                # A dict/object `content` here is a
                # web_search_tool_result_error (e.g. max_uses_exceeded,
                # unavailable) -- that one search's results just aren't
                # counted, not treated as a whole-request failure, since
                # other web_search calls in the same turn may have
                # succeeded.

        return AISearchResult(answer_text="".join(answer_parts), citations=citations)
