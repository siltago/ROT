"""Future streaming speech interfaces. Not implemented in this phase --
text/CLI input is used to validate the brain first (see app/main.py).

Designed so a future streaming pipeline (mic -> VAD -> streaming ASR ->
brain -> streaming TTS) can plug in without changing brain/*.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator


class SpeechToText(ABC):
    @abstractmethod
    async def stream_transcript(self, audio_stream) -> AsyncIterator[str]:
        """Yield partial/final transcript chunks as audio arrives."""


class TextToSpeech(ABC):
    @abstractmethod
    async def stream_audio(self, text_stream: AsyncIterator[str]) -> AsyncIterator[bytes]:
        """Yield audio chunks as response text streams in, for low latency."""


class VoiceActivityDetector(ABC):
    @abstractmethod
    def is_speech(self, audio_chunk: bytes) -> bool:
        ...
