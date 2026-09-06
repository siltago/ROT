"""OpenAI Responses API provider for free-form robot conversation."""
from __future__ import annotations

from typing import Any

from openai import AsyncOpenAI

from integrations.llm.base import LLMProvider


class OpenAIProvider(LLMProvider):
    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gpt-5.4-mini-2026-03-17",
        timeout: float = 30.0,
        client: Any | None = None,
    ) -> None:
        self.api_key = api_key.strip()
        self.model = model
        self.timeout = timeout
        self.client = client

    async def generate(self, *, system: str, user: str, history: str = "") -> str:
        if self.client is None:
            if not self.api_key:
                raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
            self.client = AsyncOpenAI(api_key=self.api_key, timeout=self.timeout)
        input_text = user
        if history:
            input_text = f"Conversa recente:\n{history}\n\nMensagem atual:\n{user}"

        response = await self.client.responses.create(
            model=self.model,
            instructions=system,
            input=input_text,
            reasoning={"effort": "none"},
            text={"verbosity": "low"},
            max_output_tokens=180,
            store=False,
        )
        reply = response.output_text.strip()
        if not reply:
            raise RuntimeError("OpenAI returned an empty response")
        return reply
