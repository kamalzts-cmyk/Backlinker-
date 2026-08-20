import pytest
from pydantic import BaseModel

from app.engines.ai.errors import AIGenerationError
from app.tests.fixtures.fake_ai_provider import FakeAIProvider


class _Verdict(BaseModel):
    ok: bool


@pytest.mark.asyncio
async def test_fake_provider_returns_queued_responses_in_order():
    provider = FakeAIProvider([_Verdict(ok=True), _Verdict(ok=False)])

    first = await provider.generate_structured(prompt="a", response_model=_Verdict)
    second = await provider.generate_structured(prompt="b", response_model=_Verdict)

    assert first.ok is True
    assert second.ok is False
    assert [c["prompt"] for c in provider.calls] == ["a", "b"]


@pytest.mark.asyncio
async def test_fake_provider_raises_when_exhausted():
    provider = FakeAIProvider([])
    with pytest.raises(AIGenerationError):
        await provider.generate_structured(prompt="a", response_model=_Verdict)


@pytest.mark.asyncio
async def test_fake_provider_raises_on_response_model_mismatch():
    class _Other(BaseModel):
        value: int

    provider = FakeAIProvider([_Other(value=1)])
    with pytest.raises(AIGenerationError):
        await provider.generate_structured(prompt="a", response_model=_Verdict)
