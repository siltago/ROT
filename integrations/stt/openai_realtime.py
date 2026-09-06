"""OpenAI Realtime transcription behind provider-neutral contracts."""
from __future__ import annotations

import asyncio
import base64
import json
from contextlib import suppress
from typing import Any

from perception.speech.streaming import (
    SpeechToTextProvider,
    SpeechTranscript,
    SttSession,
    SttSessionConfig,
    SttSessionState,
    TranscriptCallback,
)


class OpenAIRealtimeSttProvider(SpeechToTextProvider):
    name = "openai_realtime"

    def __init__(self, *, api_key: str, model: str = "gpt-live-transcribe", timeout: float = 10) -> None:
        self.api_key = api_key.strip()
        self.model = model
        self.timeout = timeout

    async def start_session(
        self, config: SttSessionConfig, on_transcript: TranscriptCallback
    ) -> SttSession:
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required for realtime STT")
        if config.sample_rate != 24000:
            raise ValueError("OpenAI realtime PCM requires 24000 Hz")
        import websockets

        socket = await asyncio.wait_for(
            websockets.connect(
                "wss://api.openai.com/v1/realtime?intent=transcription",
                additional_headers={"Authorization": f"Bearer {self.api_key}"},
                max_size=2**22,
            ),
            timeout=self.timeout,
        )
        session = OpenAIRealtimeSttSession(socket, config, on_transcript)
        await session.start(self.model)
        return session


class OpenAIRealtimeSttSession(SttSession):
    def __init__(self, socket: Any, config: SttSessionConfig, callback: TranscriptCallback) -> None:
        self.socket = socket
        self.config = config
        self.callback = callback
        self.state = SttSessionState.STARTING
        self._partial = ""
        self._reader: asyncio.Task[None] | None = None
        self._completed = asyncio.Event()

    async def start(self, model: str) -> None:
        await self.socket.send(json.dumps({
            "type": "session.update",
            "session": {
                "type": "transcription",
                "audio": {"input": {
                    "format": {"type": "audio/pcm", "rate": 24000},
                    "transcription": {
                        "model": model,
                        "languages": [self.config.language],
                        "delay": "medium",
                    },
                    "turn_detection": None,
                }},
            },
        }))
        self.state = SttSessionState.STREAMING
        self._reader = asyncio.create_task(self._read_events())

    async def push_audio(self, chunk: bytes) -> None:
        if self.state != SttSessionState.STREAMING:
            raise RuntimeError(f"Cannot push audio while session is {self.state}")
        await self.socket.send(json.dumps({
            "type": "input_audio_buffer.append",
            "audio": base64.b64encode(chunk).decode("ascii"),
        }))

    async def end(self) -> None:
        if self.state != SttSessionState.STREAMING:
            return
        self.state = SttSessionState.FINALIZING
        await self.socket.send(json.dumps({"type": "input_audio_buffer.commit"}))
        await asyncio.wait_for(self._completed.wait(), timeout=12)
        if self.state == SttSessionState.ERROR:
            raise RuntimeError("Realtime STT session failed")
        self.state = SttSessionState.COMPLETED
        await self._close()

    async def cancel(self) -> None:
        if self.state in {SttSessionState.CANCELLED, SttSessionState.COMPLETED}:
            return
        self.state = SttSessionState.CANCELLED
        await self._close()

    async def _read_events(self) -> None:
        try:
            async for raw in self.socket:
                event = json.loads(raw)
                event_type = event.get("type")
                if event_type == "conversation.item.input_audio_transcription.delta":
                    self._partial += str(event.get("delta", ""))
                    await self.callback(SpeechTranscript(
                        stream_id=self.config.stream_id,
                        raw_text=self._partial,
                        normalized_text=self._partial,
                        is_final=False,
                    ))
                elif event_type == "conversation.item.input_audio_transcription.completed":
                    text = str(event.get("transcript", "")).strip()
                    # Fire the callback in the background rather than
                    # awaiting it here. Our own downstream handling of a
                    # final transcript (wake-word matching, then possibly
                    # waiting seconds for the tablet to confirm it's done
                    # speaking) can take a while -- and `end()` (called
                    # directly from the main WebSocket receive loop) awaits
                    # `_completed`, so awaiting the callback here would
                    # transitively block that loop from reading any further
                    # incoming messages, *including* the very
                    # `speech_playback_done` confirmation the downstream
                    # handling is waiting on. That was a real, confirmed
                    # self-deadlock: the confirmation always arrived only
                    # after the wait's own timeout gave up and the loop
                    # was finally free to read it.
                    asyncio.create_task(self.callback(SpeechTranscript(
                        stream_id=self.config.stream_id,
                        raw_text=text,
                        normalized_text=text,
                        is_final=True,
                    )))
                    self._completed.set()
                elif event_type == "error":
                    self.state = SttSessionState.ERROR
                    self._completed.set()
                    return
        finally:
            if self.state == SttSessionState.FINALIZING:
                self._completed.set()

    async def _close(self) -> None:
        await self.socket.close()
        if self._reader and self._reader is not asyncio.current_task():
            self._reader.cancel()
            with suppress(asyncio.CancelledError):
                await self._reader
