"""Abstract LLM provider interface.

Mirrors the hardware/base.py pattern: brain/response_engine.py depends only
on `LLMProvider`, never on a concrete client. Swapping Ollama for the Claude
API (or any other provider) later means writing a new class here and
changing one line of wiring in app/main.py -- nothing in brain/ changes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, *, system: str, user: str, history: str = "") -> str:
        """Generate a reply given a system prompt, the user's message, and
        optional recent-conversation context. Must raise on failure -- the
        caller (ResponseEngine) is responsible for falling back gracefully,
        this method should not swallow errors into an empty string."""
