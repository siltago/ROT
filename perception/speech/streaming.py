"""Provider-neutral contracts for incremental speech-to-text sessions."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import Awaitable, Callable


class SttSessionState(StrEnum):
    IDLE = "idle"
    STARTING = "starting"
    STREAMING = "streaming"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERROR = "error"


@dataclass(frozen=True)
class SttSessionConfig:
    stream_id: str
    sample_rate: int = 24000
    channels: int = 1
    encoding: str = "pcm_s16le"
    language: str = "pt"


@dataclass(frozen=True)
class SpeechTranscript:
    stream_id: str
    raw_text: str
    normalized_text: str
    is_final: bool
    confidence: float | None = None


TranscriptCallback = Callable[[SpeechTranscript], Awaitable[None]]


class SttSession(ABC):
    state: SttSessionState = SttSessionState.IDLE

    @abstractmethod
    async def push_audio(self, chunk: bytes) -> None: ...

    @abstractmethod
    async def end(self) -> None: ...

    @abstractmethod
    async def cancel(self) -> None: ...


class SpeechToTextProvider(ABC):
    name: str

    @abstractmethod
    async def start_session(
        self, config: SttSessionConfig, on_transcript: TranscriptCallback
    ) -> SttSession: ...
