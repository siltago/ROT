"""Ollama-backed LLM provider. Local, free, no external API billing --
quality/latency depend entirely on local hardware. Talks to Ollama's REST
API directly (no extra SDK dependency beyond httpx).

Requires Ollama running locally (`ollama serve`, usually automatic after
install) and a model already pulled (e.g. `ollama pull llama3.1`).
"""
from __future__ import annotations

import httpx

from integrations.llm.base import LLMProvider


class OllamaProvider(LLMProvider):
    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:11434",
        timeout: float = 120.0,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def generate(self, *, system: str, user: str, history: str = "") -> str:
        messages = [{"role": "system", "content": system}]
        if history:
            messages.append({"role": "user", "content": f"Conversa recente:\n{history}"})
        messages.append({"role": "user", "content": user})

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                json={"model": self.model, "messages": messages, "stream": False},
            )
            response.raise_for_status()
            data = response.json()
            return data["message"]["content"].strip()
