from __future__ import annotations

import pytest

from integrations.llm.openai_provider import OpenAIProvider


class _FakeResponse:
    output_text = "  Olá!  "


class _FakeResponses:
    def __init__(self) -> None:
        self.arguments: dict | None = None

    async def create(self, **kwargs):
        self.arguments = kwargs
        return _FakeResponse()


class _FakeClient:
    def __init__(self) -> None:
        self.responses = _FakeResponses()


async def test_openai_provider_uses_responses_api_with_short_output() -> None:
    client = _FakeClient()
    provider = OpenAIProvider(
        api_key="test-key",
        model="gpt-test",
        client=client,
    )

    reply = await provider.generate(
        system="Responda em português.",
        user="Oi",
        history="Pessoa: tudo bem?",
    )

    assert reply == "Olá!"
    assert client.responses.arguments == {
        "model": "gpt-test",
        "instructions": "Responda em português.",
        "input": "Conversa recente:\nPessoa: tudo bem?\n\nMensagem atual:\nOi",
        "reasoning": {"effort": "none"},
        "text": {"verbosity": "low"},
        "max_output_tokens": 180,
        "store": False,
    }


async def test_openai_provider_requires_api_key_on_generation() -> None:
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        await OpenAIProvider(api_key="").generate(system="s", user="u")
