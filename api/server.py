"""WebSocket gateway between tablet perception and the Robot Brain."""

from __future__ import annotations

import asyncio
import io
import json
import logging
import random
import struct
import time
import wave
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, ValidationError

from app.config import settings
from app.main import build_agent
from brain.agent import RobotAgent, TurnResult
from brain.behaviors import BehaviorProposal
from brain.cognition import CognitionEngine
from brain.models import IntentType
from brain.events import EventType, RobotEvent
from emotions.state import EmotionalState
from integrations.stt.openai_realtime import OpenAIRealtimeSttProvider
from integrations.tts.piper_provider import PiperTtsProvider, RobotVoiceEffect
from perception.event_sources import ClockEventSource
from perception.speech.wake_word import matches_wake_word
from perception.speech.yes_no import classify_yes_no
from perception.speech.streaming import (
    SpeechToTextProvider,
    SpeechTranscript,
    SttSession,
    SttSessionConfig,
)

if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


class DeviceMessage(BaseModel):
    version: int = 1
    type: str
    device_id: str
    timestamp: int
    payload: dict[str, Any] = Field(default_factory=dict)


class DebugEventRequest(BaseModel):
    type: EventType
    source: str = "debug_api"
    data: dict[str, Any] = Field(default_factory=dict)


def outgoing_message(message_type: str, device_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    message: dict[str, Any] = {
        "version": 1,
        "type": message_type,
        "device_id": device_id,
        "timestamp": int(time.time() * 1000),
    }
    if payload is not None:
        message["payload"] = payload
    return message


@dataclass
class DeviceSession:
    device_id: str
    websocket: WebSocket
    capabilities: set[str] = field(default_factory=set)
    # Wake-word gate: standby (awake=False) never reaches an LLM call, no
    # matter how much gets said near the robot -- audio capture and STT stay
    # on continuously (that's the whole point, they're reliable), but only
    # a matched wake word or an already-awake session lets a transcript
    # become a real turn.
    awake: bool = False
    wake_timeout_task: "asyncio.Task[None] | None" = None
    # The client's own VAD sometimes splits "ei Bob" into two separate final
    # transcripts (e.g. "Ei," then "Bob" a beat later), neither of which
    # matches alone. Remembering the last non-matching standby transcript
    # briefly lets us also try the joined text.
    standby_buffer: str = ""
    standby_buffer_at: float = 0.0
    # The client's VAD is also known to chop a single utterance into several
    # short back-to-back audio segments, each becoming its own STT stream and
    # final transcript. If two of those chattered fragments transcribe to
    # essentially the same thing, remembering the last processed command lets
    # us suppress the second one instead of answering the same thing twice.
    last_command_text: str = ""
    last_command_at: float = 0.0
    # Set by the tablet itself (a `speech_playback_done` message) once it has
    # actually finished playing speech and resumed its mic -- the real
    # signal a turn is over, instead of the server guessing/estimating how
    # long that would take and sleeping a fixed amount (which measurably
    # drifted from reality: network transfer time, decode, and the client's
    # own fixed mic-resume delay are all outside what a duration estimate
    # can account for).
    playback_done: asyncio.Event = field(default_factory=asyncio.Event)
    # Non-empty while the robot has asked "vi que você está ouvindo o
    # Spotify em <device>, quer que eu abra o player aqui?" and is waiting
    # for a yes/no -- holds the offered track_id so the answer can be tied
    # back to it. `awake` is set alongside this so the mic stays listening
    # for the reply exactly like a normal wake.
    pending_music_offer: str = ""


class DeviceRegistry:
    def __init__(self) -> None:
        self._sessions: dict[str, DeviceSession] = {}

    def connect(self, session: DeviceSession) -> None:
        # The tablet resends device_hello on every reconnect, including
        # brief ones that don't affect the ongoing conversation. Replacing
        # the session outright would silently drop `awake`/wake_timeout_task
        # for an in-progress wake -- the eye stays green client-side (it
        # only reacts to explicit wake_state messages) while the backend
        # quietly reverts to standby and ignores the next command. Update
        # the transport in place instead so mid-wake state survives.
        existing = self._sessions.get(session.device_id)
        if existing is not None:
            existing.websocket = session.websocket
            existing.capabilities = session.capabilities
            return
        self._sessions[session.device_id] = session

    def disconnect(self, device_id: str, websocket: WebSocket) -> None:
        current = self._sessions.get(device_id)
        if current and current.websocket is websocket:
            self._sessions.pop(device_id, None)

    def get(self, device_id: str) -> DeviceSession | None:
        return self._sessions.get(device_id)

    def count(self) -> int:
        return len(self._sessions)

    def sessions(self) -> tuple[DeviceSession, ...]:
        return tuple(self._sessions.values())


async def _dispatch_selected(
    selected: BehaviorProposal,
    registry: DeviceRegistry,
    cognition: CognitionEngine,
    tts: "PiperTtsProvider | None" = None,
) -> None:
    """Pushes a chosen autonomous behavior to every connected tablet, then
    marks it complete. Shared by the manual /debug/events endpoint and the
    background cognition tick loop -- same effect, different trigger."""
    for session in registry.sessions():
        if selected.proposed_action == "idle.play":
            await session.websocket.send_json(outgoing_message("play_idle_animation", session.device_id))
        elif selected.proposed_action == "robot.sleep":
            await session.websocket.send_json(
                outgoing_message("set_state", session.device_id, {"state": "SLEEPING"})
            )
        if selected.response_hint:
            await session.websocket.send_json(
                outgoing_message("show_message", session.device_id, {"title": "Robot", "message": selected.response_hint})
            )
            await _speak(
                text=selected.response_hint,
                device_id=session.device_id,
                send=session.websocket.send_json,
                send_bytes=session.websocket.send_bytes,
                tts=tts,
            )
    await cognition.complete_initiative(selected)


def expression_for_result(result: TurnResult, mood: str) -> str:
    if result.decision.type == IntentType.AMBIGUOUS:
        return "confused"
    if result.decision.type == IntentType.QUESTION:
        return "curious"
    return {
        "cheerful": "happy",
        "curious": "curious",
        "tired": "sleepy",
        "down": "sad",
        "irritated": "confused",
    }.get(mood, "neutral")


def mood_vector_for_result(result: TurnResult, state: EmotionalState) -> dict[str, float]:
    """Continuous emotional signal for the face renderer.

    Unlike `expression_for_result` (a discrete label kept for logging/back-compat),
    this is the raw vector the tablet uses to draw a continuously varying eye
    shape/color instead of picking from a fixed template. Intent-based hints are
    applied as small transient nudges on top of the persisted vector rather than
    replacing it, so the signal stays continuous.
    """
    vector = state.model_dump()
    if result.decision.type == IntentType.AMBIGUOUS:
        vector["irritation"] = _clamp01(vector["irritation"] + 0.15)
        vector["valence"] = _clamp01(vector["valence"] - 0.1)
    elif result.decision.type == IntentType.QUESTION:
        vector["curiosity"] = _clamp01(vector["curiosity"] + 0.2)
    return vector


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


SendMessage = Callable[[dict[str, Any]], Awaitable[None]]
SendBytes = Callable[[bytes], Awaitable[None]]

# Prefixes a Piper-synthesized WAV so the tablet can tell it apart from any
# other binary frame; mirrors the RBA1 magic already used the other way
# (tablet -> brain, mic audio) in AudioStreamer.frameAudio (Dart side).
TTS_AUDIO_MAGIC = b"RBT1"

# Fixed, local acknowledgement for the wake word -- deliberately not routed
# through the LLM: waking up should be instant and free, every time.
WAKE_GREETINGS = [
    "Olá, como posso ajudar?",
    "Oi, pode falar.",
    "Diga, estou ouvindo.",
]

async def _speak(*, text: str, device_id: str, send: SendMessage, send_bytes: SendBytes, tts: PiperTtsProvider | None) -> float:
    """Sends speech as Piper audio (binary) when a voice model is loaded and
    synthesis succeeds; otherwise falls back to the plain-text `speak`
    message the tablet already knows how to say with flutter_tts. Callers
    never need to know which path was taken.

    Returns an estimate, in seconds, of how long that speech takes to
    actually play back on the tablet. This call only awaits synthesizing
    and *sending* the audio -- it returns long before the tablet has
    finished playing it. Callers that need to know when the robot is truly
    done talking (e.g. to arm an inactivity timer without its countdown
    silently overlapping still-ongoing playback) should sleep this many
    seconds first.
    """
    audio = await tts.synthesize(text) if tts is not None else None
    if audio is not None:
        await send_bytes(TTS_AUDIO_MAGIC + audio)
        return _wav_duration_seconds(audio)
    await send(outgoing_message("speak", device_id, {"text": text, "language": "pt-BR"}))
    return _estimate_speech_seconds(text)


def _wav_duration_seconds(wav_bytes: bytes) -> float:
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
            frames = wav_file.getnframes()
            rate = wav_file.getframerate()
            if rate > 0:
                return frames / float(rate)
    except Exception:
        logger.exception("Failed to read WAV duration; using a flat fallback estimate")
    return 2.0


def _estimate_speech_seconds(text: str) -> float:
    """Rough reading-speed estimate for the flutter_tts fallback path, where
    there's no synthesized audio to measure -- better than treating that
    speech as instantaneous."""
    return _estimate_speech_seconds_from_word_count(len(text.split()))


def _estimate_speech_seconds_from_word_count(word_count: int) -> float:
    return max(1.0, word_count / 2.5)  # ~150 words/minute speaking pace


async def _speak_and_wait_for_playback(
    *,
    text: str,
    device_id: str,
    send: SendMessage,
    send_bytes: SendBytes,
    tts: "PiperTtsProvider | None",
    session: "DeviceSession | None",
) -> None:
    """Speaks `text`, then waits for the tablet's own `speech_playback_done`
    signal that it actually finished playing and resumed its mic -- the real
    end of the turn, rather than a server-side guess at how long that takes
    (measured live to drift noticeably from reality: network transfer,
    decode, and the client's own fixed mic-resume delay all sit outside
    what a duration estimate alone can see). Falls back to a generous fixed
    ceiling, built on that same estimate, if the signal never arrives (an
    older client, or the message getting lost) so a turn can never hang
    forever.
    """
    if session is not None:
        session.playback_done.clear()
    estimated_seconds = await _speak(text=text, device_id=device_id, send=send, send_bytes=send_bytes, tts=tts)
    if session is None:
        await asyncio.sleep(estimated_seconds + PLAYBACK_TIMING_SAFETY_MARGIN_SECONDS)
        return
    ceiling = max(estimated_seconds + PLAYBACK_TIMING_SAFETY_MARGIN_SECONDS, PLAYBACK_CONFIRMATION_CEILING_SECONDS)
    try:
        await asyncio.wait_for(session.playback_done.wait(), timeout=ceiling)
    except asyncio.TimeoutError:
        logger.warning("speech_playback_done never arrived within %.1fs; proceeding anyway", ceiling)


class TabletBrainBridge:
    def __init__(self, agent: RobotAgent, registry: "DeviceRegistry | None" = None, tts: PiperTtsProvider | None = None) -> None:
        from brain.presentation import PresentationPlanner

        self.agent = agent
        self.registry = registry
        self.tts = tts
        self.presentation_planner = PresentationPlanner()
        self._turn_lock = asyncio.Lock()

    async def process_text(self, *, text: str, device_id: str, send: SendMessage, send_bytes: SendBytes) -> None:
        cleaned = text.strip()
        if not cleaned:
            return
        await send(outgoing_message("dismiss_scene", device_id, {"reason": "new_turn"}))
        await send(outgoing_message("set_state", device_id, {"state": "THINKING"}))
        await send(
            outgoing_message(
                "show_transcript",
                device_id,
                {"text": cleaned, "final": True},
            )
        )
        try:
            async with self._turn_lock:
                result = await self.agent.process_turn(cleaned)
                state = self.agent.emotional_engine.state
                mood = state.mood_label()
            expression = expression_for_result(result, mood)
            mood_vector = mood_vector_for_result(result, state)
            await send(
                outgoing_message(
                    "set_expression",
                    device_id,
                    {
                        "expression": expression,
                        "intensity": 0.8,
                        "mood": mood,
                        **mood_vector,
                    },
                )
            )
            await send(
                outgoing_message(
                    "show_message",
                    device_id,
                    {"title": "Robot", "message": result.reply},
                )
            )
            scene = self.presentation_planner.plan(result)
            if scene is not None:
                await send(outgoing_message("show_scene", device_id, scene.to_payload()))
            # Wait for the tablet's own signal that it's actually done
            # playing the reply before returning -- otherwise the caller's
            # post-turn wake-timeout re-arm starts its countdown while the
            # robot is still talking, silently eating into the time it's
            # meant to give the user afterward.
            await _speak_and_wait_for_playback(
                text=result.reply,
                device_id=device_id,
                send=send,
                send_bytes=send_bytes,
                tts=self.tts,
                session=self.registry.get(device_id) if self.registry is not None else None,
            )
            await send(outgoing_message("set_state", device_id, {"state": "IDLE"}))
        except Exception:
            logger.exception("Failed to process tablet speech")
            await send(outgoing_message("set_state", device_id, {"state": "ERROR"}))
            await send(
                outgoing_message(
                    "show_message",
                    device_id,
                    {
                        "title": "Erro",
                        "message": "Não consegui consultar o cérebro agora. Verifique o servidor de IA.",
                        "is_error": True,
                    },
                )
            )


@dataclass
class AudioStreamSession:
    stream_id: str
    stt: SttSession
    expected_sequence: int = 0
    received_chunks: int = 0
    missing_chunks: int = 0
    duplicate_chunks: int = 0
    final_forwarded: bool = False
    # Whether the device was awake when this utterance's recording *began*.
    # The STT provider's finalization round-trip can take a second or more,
    # long enough to straddle the wake timeout -- a command that started
    # well within the awake window can otherwise still get discarded as a
    # standby transcript just because its final result happened to land a
    # moment after the timer expired. Deciding by start time instead of
    # final-arrival time closes that race.
    awake_at_start: bool = False


# How long an awakened session stays awake without hearing anything else.
# Re-armed after every reply and after every genuine (non-empty) transcript,
# so this is the pause budget *between* exchanges, not a ceiling on the
# conversation's total length. Lowered from 30s back to 10s per explicit
# request, now that the real bug behind needing it longer -- background
# noise re-arming the timer on empty transcripts, keeping sessions "awake"
# indefinitely -- is fixed at the source rather than papered over with a
# bigger number.
WAKE_TIMEOUT_SECONDS = 10.0

# How long a non-matching standby transcript is remembered so it can be
# joined with the next one (the client VAD sometimes splits "ei Bob" into
# two finals).
STANDBY_BUFFER_WINDOW_SECONDS = 3.0

# How long a processed command is remembered so a near-duplicate arriving
# right after it (the client VAD chopping one utterance into two chattered
# fragments that both transcribe similarly) can be suppressed instead of
# triggering a second LLM turn -- long enough to cover that chatter, short
# enough to never swallow a genuine, distinct follow-up command. Measured
# live: a real chattered duplicate landed 9.76s after the first, so 6s
# wasn't enough to catch it.
DUPLICATE_COMMAND_WINDOW_SECONDS = 12.0

# Extra slack folded into the estimate used as a *fallback ceiling* (see
# PLAYBACK_CONFIRMATION_CEILING_SECONDS) and as the actual wait when there's
# no session to signal against at all. Measured live: the tablet's mic
# didn't actually resume listening until ~1.4s after our duration estimate
# alone would have had us stop waiting -- audio needs time to reach the
# device and start playing, and the client itself adds a fixed ~450ms delay
# before resuming the mic after playback completes.
PLAYBACK_TIMING_SAFETY_MARGIN_SECONDS = 1.5

# Minimum time to wait for the tablet's `speech_playback_done` signal before
# giving up and proceeding anyway (a lost message, or an older client that
# doesn't send it, must never hang a turn forever). The real per-turn wait
# is normally far shorter than this -- it ends the moment the signal
# arrives -- this is only the safety net for when it doesn't.
PLAYBACK_CONFIRMATION_CEILING_SECONDS = 8.0


def _arm_wake_timeout(session: DeviceSession) -> None:
    """(Re)starts the countdown that reverts a session to standby.

    Module-level (not a method) so it can be reused anywhere a session goes
    "awake" and needs its own expiry -- both a real wake-word match and a
    proactive robot-initiated question ("quer que eu abra o player aqui?")
    need the exact same not-stuck-awake-forever guarantee.
    """
    if session.wake_timeout_task is not None:
        session.wake_timeout_task.cancel()

    async def _expire() -> None:
        await asyncio.sleep(WAKE_TIMEOUT_SECONDS)
        session.awake = False
        session.pending_music_offer = ""
        with suppress(Exception):
            await session.websocket.send_json(
                outgoing_message("wake_state", session.device_id, {"awake": False})
            )

    session.wake_timeout_task = asyncio.create_task(_expire())


class AudioStreamCoordinator:
    """Owns at most one incremental STT stream for a tablet WebSocket."""

    def __init__(
        self,
        provider: SpeechToTextProvider,
        bridge: TabletBrainBridge,
        device_id: str,
        send: SendMessage,
        send_bytes: SendBytes,
        registry: DeviceRegistry,
    ) -> None:
        self.provider = provider
        self.bridge = bridge
        self.device_id = device_id
        self.send = send
        self.send_bytes = send_bytes
        self.registry = registry
        self.active: AudioStreamSession | None = None
        self._completed_streams: set[str] = set()

    async def start(self, payload: dict[str, Any]) -> None:
        await self.cancel("replaced_by_new_stream")
        stream_id = str(payload.get("stream_id", "")).strip()
        audio_format = payload.get("format", {})
        session = self.registry.get(self.device_id)
        awake_at_start = session.awake if session is not None else False
        logger.info("audio_stream_start stream_id=%r awake=%s", stream_id, awake_at_start)
        if not stream_id:
            raise ValueError("audio_stream_start requires stream_id")
        config = SttSessionConfig(
            stream_id=stream_id,
            sample_rate=int(audio_format.get("sample_rate", 24000)),
            channels=int(audio_format.get("channels", 1)),
            encoding=str(audio_format.get("encoding", "pcm_s16le")),
        )

        async def on_transcript(transcript: SpeechTranscript) -> None:
            await self._on_transcript(transcript)

        try:
            stt = await self.provider.start_session(config, on_transcript)
        except Exception as exc:
            logger.exception("Failed to start STT stream %s", stream_id)
            await self.send(outgoing_message("audio_stream_error", self.device_id, {
                "stream_id": stream_id,
                "code": "STT_START_FAILED",
                "message": str(exc),
                "fallback_recommended": True,
            }))
            return
        self.active = AudioStreamSession(stream_id=stream_id, stt=stt, awake_at_start=awake_at_start)
        await self.send(outgoing_message("audio_stream_ready", self.device_id, {
            "stream_id": stream_id,
            "provider": self.provider.name,
        }))

    async def push_binary(self, frame: bytes) -> None:
        if self.active is None:
            logger.info("push_binary dropped: no active stream")
            return
        if len(frame) < 8 or frame[:4] != b"RBA1":
            raise ValueError("invalid binary audio frame")
        sequence = struct.unpack(">I", frame[4:8])[0]
        if sequence < self.active.expected_sequence:
            self.active.duplicate_chunks += 1
            return
        if sequence > self.active.expected_sequence:
            self.active.missing_chunks += sequence - self.active.expected_sequence
        self.active.expected_sequence = sequence + 1
        self.active.received_chunks += 1
        await self.active.stt.push_audio(frame[8:])

    async def end(self, stream_id: str) -> None:
        active = self.active
        if active is None or active.stream_id != stream_id:
            logger.info(
                "audio_stream_end stream_id=%r ignored (active=%r)",
                stream_id, active.stream_id if active is not None else None,
            )
            return
        logger.info(
            "audio_stream_end stream_id=%r received_chunks=%d",
            stream_id, active.received_chunks,
        )
        try:
            await active.stt.end()
        except Exception as exc:
            logger.exception("Failed to finalize STT stream %s", stream_id)
            await active.stt.cancel()
            # Observed live to recur every so often: OpenAI occasionally
            # takes longer than the 12s finalization timeout to send back a
            # transcript for one utterance. That's this one utterance lost
            # (no transcript), not evidence the pipeline itself is broken --
            # the very next stream typically finalizes normally. Recommending
            # fallback here throws away the reliable, wake-word-gated
            # pipeline for the rest of the session over a single slow
            # response, permanently landing on the legacy on-device
            # recognizer (known unreliable on this hardware) instead of just
            # losing the one utterance and continuing normally.
            await self.send(outgoing_message("audio_stream_error", self.device_id, {
                "stream_id": stream_id,
                "code": "STT_FINALIZATION_FAILED",
                "message": str(exc),
                "fallback_recommended": False,
            }))
        finally:
            await self.send(outgoing_message("audio_stream_closed", self.device_id, {
                "stream_id": stream_id,
                "received_chunks": active.received_chunks,
                "missing_chunks": active.missing_chunks,
                "duplicate_chunks": active.duplicate_chunks,
            }))
            self.active = None

    async def cancel(self, reason: str) -> None:
        if self.active is None:
            return
        active, self.active = self.active, None
        await active.stt.cancel()
        # This path only ever fires for routine supersession/teardown --
        # a new utterance's stream replacing the previous one
        # ("replaced_by_new_stream", the normal way two consecutive
        # utterances are chained), the client pausing its own mic to let
        # the robot talk ("client_cancelled"), or the socket going away
        # ("connection_lost"). None of these are an STT reliability
        # problem, so `fallback_recommended` must stay false -- the client
        # otherwise treats *any* audio_stream_error as a signal to
        # permanently abandon this pipeline for the legacy on-device
        # recognizer (see robot_app.dart), which would silently and
        # irreversibly break the wake-word gate for the rest of the
        # session on every single routine cancellation.
        await self.send(outgoing_message("audio_stream_error", self.device_id, {
            "stream_id": active.stream_id,
            "code": reason,
            "fallback_recommended": False,
        }))

    async def _on_transcript(self, transcript: SpeechTranscript) -> None:
        if self.active is None or transcript.stream_id != self.active.stream_id:
            return
        if transcript.is_final and transcript.stream_id in self._completed_streams:
            return
        message_type = "transcript_final" if transcript.is_final else "transcript_partial"
        await self.send(outgoing_message(message_type, self.device_id, {
            "stream_id": transcript.stream_id,
            "raw_transcript": transcript.raw_text,
            "normalized_transcript": transcript.normalized_text,
            "text": transcript.normalized_text,
            "confidence": transcript.confidence,
        }))
        if not transcript.is_final:
            return
        self._completed_streams.add(transcript.stream_id)
        self.active.final_forwarded = True

        try:
            await self._handle_final_transcript(transcript)
        except Exception:
            logger.exception("_on_transcript failed")

    async def _handle_final_transcript(self, transcript: SpeechTranscript) -> None:
        session = self.registry.get(self.device_id)
        text = transcript.normalized_text.strip()
        learning_state = getattr(self.bridge.agent, "learning_state", None)
        if session is not None and learning_state is not None and learning_state.active and text:
            # A skill-teaching attempt in progress owns the next turn
            # entirely (a clarifying answer or a yes/no approval) --
            # RobotAgent.process_turn already knows how to handle it, so
            # this just needs to keep the mic listening regardless of the
            # current wake state, same principle as pending_music_offer
            # below.
            session.awake = True
            try:
                await self.bridge.process_text(
                    text=transcript.normalized_text, device_id=self.device_id,
                    send=self.send, send_bytes=self.send_bytes,
                )
            finally:
                _arm_wake_timeout(session)
            return
        if session is not None and session.pending_music_offer and text:
            await self._handle_music_offer_reply(session, text)
            return
        if session is not None and not session.awake and self.active is not None and self.active.awake_at_start:
            # The device was awake when this utterance started recording;
            # it only looks asleep now because the STT provider's
            # finalization round-trip (a second or more) let the wake
            # timeout race ahead of this result. Treat it as the awake
            # turn it actually was rather than discarding it as standby.
            logger.info("awake transcript=%r (recovered: timeout raced finalization)", text)
            session.awake = True
            # Re-arm unconditionally here (unlike the general case below,
            # which skips empty text) -- recovering the session at all means
            # restarting its watchdog, otherwise an empty-text recovery
            # would leave `awake` stuck true with no timer ever scheduled
            # to revert it.
            _arm_wake_timeout(session)
        if session is not None and not session.awake:
            matched = matches_wake_word(text)
            joined_with: str | None = None
            if not matched and session.standby_buffer and text:
                now = time.monotonic()
                if now - session.standby_buffer_at <= STANDBY_BUFFER_WINDOW_SECONDS:
                    joined = f"{session.standby_buffer} {text}".strip()
                    if matches_wake_word(joined):
                        matched = True
                        joined_with = session.standby_buffer
            if matched:
                logger.info("standby transcript=%r joined_with=%r wake_matched=True", text, joined_with)
                session.standby_buffer = ""
                session.awake = True
                logger.info("wake_state sent: awake=True device=%r", self.device_id)
                try:
                    # The wake word always means "I want the robot", not
                    # whatever ambient presentation (e.g. the music scene)
                    # happens to be showing -- drop it immediately, and stop
                    # the music sync loop from re-showing it on its own.
                    music_service = getattr(self.bridge.agent, "music_service", None)
                    if music_service is not None:
                        music_service.presenting = False
                    await self.send(outgoing_message("dismiss_scene", self.device_id, {"reason": "wake_word"}))
                    await self.send(outgoing_message("wake_state", self.device_id, {"awake": True}))
                    await self.send(outgoing_message("set_state", self.device_id, {"state": "LISTENING"}))
                    # Waits for the tablet's own signal that it's actually
                    # done playing the greeting and has resumed its mic --
                    # not a guess at how long that takes. Without this, a
                    # chunk of the user's reply window is silently spent on
                    # the robot still talking, and the mic isn't even
                    # listening for most of it (paused for echo prevention
                    # while the greeting plays).
                    await _speak_and_wait_for_playback(
                        text=random.choice(WAKE_GREETINGS),
                        device_id=self.device_id,
                        send=self.send,
                        send_bytes=self.send_bytes,
                        tts=self.bridge.tts,
                        session=session,
                    )
                    # Not a real conversation turn (no LLM call) -- just
                    # touch the activity clock so cognition doesn't treat
                    # the robot as having sat idle through its own wake-up.
                    self.bridge.agent.world_state.mark_user_turn(None)
                    self.bridge.agent.world_state.finish_turn()
                finally:
                    # Armed even if something above raised -- otherwise a
                    # partial failure (e.g. a send error, or a world_state
                    # hiccup) leaves the session stuck "awake" forever with
                    # no timer to ever revert it.
                    _arm_wake_timeout(session)
                    logger.info("wake timeout armed: device=%r", self.device_id)
            else:
                logger.info("standby transcript=%r wake_matched=False", text)
                session.standby_buffer = text
                session.standby_buffer_at = time.monotonic()
            # Standby only ever spots the wake word here -- audio/STT keep
            # running (that's what makes this reliable), but nothing said
            # before the wake word ever reaches process_turn/the LLM.
            return

        # Only genuine speech content re-arms the timeout -- background
        # noise/silence still finalizes as an empty transcript fairly often
        # (the client's VAD fires on ambient sound), and re-arming on that
        # kept sessions "awake" indefinitely in practice (observed live:
        # 5+ minutes straight of nothing but empty transcripts, each
        # quietly resetting the clock) even though nobody was actually
        # there anymore.
        if session is not None and text:
            _arm_wake_timeout(session)

        if session is not None and text and self._is_duplicate_command(session, text):
            logger.info("duplicate command suppressed: %r (last=%r)", text, session.last_command_text)
            return

        if session is not None and text:
            session.last_command_text = text
            session.last_command_at = time.monotonic()
        logger.info("awake transcript=%r", text)
        await self.bridge.process_text(
            text=transcript.normalized_text,
            device_id=self.device_id,
            send=self.send,
            send_bytes=self.send_bytes,
        )
        # process_text can take several seconds (LLM call + TTS synthesis).
        # The timeout armed above only covers the wait *before* that call --
        # without re-arming here, it can expire while the robot is still
        # generating/speaking its reply, snapping the eye back to standby
        # mid-turn even though the conversation is very much still active.
        # Re-arming now gives the user a fresh, undiminished window that
        # starts only once the robot is done talking. Still gated on `text`:
        # process_text is a no-op for empty text (nothing was actually said),
        # so there's nothing here to extend the window for either.
        if session is not None and text:
            _arm_wake_timeout(session)

    async def _handle_music_offer_reply(self, session: DeviceSession, text: str) -> None:
        offered_track = session.pending_music_offer
        session.pending_music_offer = ""
        answer = classify_yes_no(text)
        music_service = getattr(self.bridge.agent, "music_service", None)
        if answer is True and music_service is not None:
            logger.info("music offer accepted: track_id=%r", offered_track)
            music_service.presenting = True
            reply = "Show, abrindo aqui!"
        elif answer is False:
            logger.info("music offer declined: track_id=%r", offered_track)
            reply = "Combinado, deixo quieto."
        else:
            # Didn't parse as a clear yes/no -- treat it as a normal command
            # instead of getting stuck waiting for an answer that may never
            # come in the expected shape.
            logger.info("music offer reply unclear=%r, treating as a normal command", text)
            _arm_wake_timeout(session)
            await self.bridge.process_text(
                text=text, device_id=self.device_id, send=self.send, send_bytes=self.send_bytes,
            )
            return
        try:
            await _speak_and_wait_for_playback(
                text=reply, device_id=self.device_id, send=self.send,
                send_bytes=self.send_bytes, tts=self.bridge.tts, session=session,
            )
        finally:
            _arm_wake_timeout(session)

    @staticmethod
    def _is_duplicate_command(session: DeviceSession, text: str) -> bool:
        """True when `text` looks like the client's VAD re-sending part of
        the command it just chattered into two (or more) audio segments --
        the same normalized text, or one being a substring of the other,
        within a short window of the last command actually processed."""
        if not session.last_command_text:
            return False
        if time.monotonic() - session.last_command_at > DUPLICATE_COMMAND_WINDOW_SECONDS:
            return False
        normalized = text.casefold()
        last = session.last_command_text.casefold()
        return normalized == last or normalized in last or last in normalized


async def _cognition_tick_loop(
    bridge: TabletBrainBridge,
    registry: DeviceRegistry,
    clock: ClockEventSource,
    interval: float,
) -> None:
    """The one piece Cognition v0.2 was missing: something that calls it over
    time. Ages drives (tiredness included), nudges energy/eyes accordingly,
    and lets idle behaviors (self-entertainment, sleep) actually fire on
    their own instead of only via the manual /debug/events endpoint."""
    agent = bridge.agent
    while True:
        await asyncio.sleep(interval)
        try:
            await clock.poll()

            world = agent.world_state
            was_active = world.processing or world.conversation_active
            drives = agent.cognition.drive_engine.advance(interval, active=was_active)

            emotional_state = agent.emotional_engine.state
            target_energy = _clamp01(1 - drives.rest)
            emotional_state.energy = _clamp01(
                emotional_state.energy + (target_energy - emotional_state.energy) * 0.15
            )

            sessions = registry.sessions()
            for session in sessions:
                await session.websocket.send_json(
                    outgoing_message("set_expression", session.device_id, emotional_state.model_dump())
                )

            last = world.activity.last_interaction_at or world.activity.active_since
            idle_seconds = (datetime.now(timezone.utc) - last).total_seconds()
            result = await agent.cognition.process_event(
                RobotEvent(type=EventType.IDLE_TIMEOUT, source="cognition_tick", data={"idle_seconds": idle_seconds})
            )
            logger.info(
                "cognition_tick idle_seconds=%.0f rest=%.2f proposals=%s selected=%s",
                idle_seconds,
                drives.rest,
                [p.name for p in result.proposals],
                result.selected.name if result.selected else None,
            )
            if result.selected is not None:
                await _dispatch_selected(result.selected, registry, agent.cognition, bridge.tts)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Cognition tick failed")


async def _music_sync_loop(
    agent: RobotAgent, registry: DeviceRegistry, interval: float, tts: PiperTtsProvider | None,
) -> None:
    """Spotify remains the clock: every update carries a fresh observed position.

    The tablet extrapolates only between updates, then immediately corrects on
    pause, seek, track change or the next poll.
    """
    service = getattr(agent, "music_service", None)
    if service is None or not service.spotify.configured:
        return
    was_presenting = False
    # Devices that were actually connected at the moment `presenting` last
    # turned on. Deliberately NOT "every currently connected session" on
    # every tick -- a device that (re)connects *while* presenting is still
    # true (e.g. the tablet app cold-starting after `presenting` was left
    # on from an earlier session, or simply reconnecting) would otherwise
    # have the scene pushed onto it despite never having asked for it,
    # which is exactly "the player opens by itself on startup". A device
    # only gets shown the scene from the transition that actually turned
    # it on; it won't retroactively join an already-running one.
    presenting_audience: set[str] = set()
    while True:
        try:
            # Only mirror playback onto the tablet while the robot itself is
            # the one presenting it (see `MusicExperienceService.presenting`)
            # -- otherwise this loop would show whatever happens to be
            # playing on the user's own Spotify session (phone, PC...)
            # any time it's active, which nobody asked the robot to display.
            if service.presenting:
                if not was_presenting:
                    presenting_audience = {s.device_id for s in registry.sessions()}
                payload = await service.current_payload()
                if payload is None:
                    service.presenting = False
                else:
                    was_presenting = True
                    scene = {"kind": "music", "variant": payload["mode"], "persistent": True, "data": payload}
                    for session in registry.sessions():
                        if session.device_id not in presenting_audience:
                            continue
                        await session.websocket.send_json(outgoing_message("show_scene", session.device_id, scene))
            if not service.presenting and was_presenting:
                was_presenting = False
                for session in registry.sessions():
                    if session.device_id not in presenting_audience:
                        continue
                    await session.websocket.send_json(outgoing_message(
                        "dismiss_scene", session.device_id, {"reason": "spotify_stopped"}))
                presenting_audience = set()
            if not service.presenting:
                # Playing somewhere else (phone, PC...) and the robot hasn't
                # been asked for it -- offer once per track instead of either
                # silently ignoring it or showing up uninvited.
                ambient = await service.current_payload()
                if ambient is not None and service.should_offer(ambient["track_id"]):
                    for session in registry.sessions():
                        if session.awake or session.pending_music_offer:
                            continue
                        session.pending_music_offer = ambient["track_id"]
                        session.awake = True
                        device_name = ambient.get("device_name") or "outro dispositivo"
                        try:
                            await session.websocket.send_json(
                                outgoing_message("wake_state", session.device_id, {"awake": True}))
                            await _speak_and_wait_for_playback(
                                text=f"Vi que você está ouvindo o Spotify em {device_name}. "
                                     "Quer que eu abra o player aqui?",
                                device_id=session.device_id,
                                send=session.websocket.send_json,
                                send_bytes=session.websocket.send_bytes,
                                tts=tts,
                                session=session,
                            )
                        except Exception:
                            logger.warning("Failed to offer music scene to %s", session.device_id, exc_info=True)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Spotify sync temporarily unavailable", exc_info=True)
        await asyncio.sleep(max(.5, interval))


def create_app(
    agent: RobotAgent | None = None,
    stt_provider: SpeechToTextProvider | None = None,
    debug_events_enabled: bool | None = None,
    cognition_tick_enabled: bool = True,
) -> FastAPI:
    registry = DeviceRegistry()
    tts_provider = (
        PiperTtsProvider.try_create(
            settings.piper_voice_path,
            RobotVoiceEffect(
                noise_scale=settings.piper_noise_scale,
                noise_w_scale=settings.piper_noise_w_scale,
                length_scale=settings.piper_length_scale,
                pitch_shift_semitones=settings.piper_pitch_shift_semitones,
                ring_mod_hz=settings.piper_ring_mod_hz,
                ring_mod_wet=settings.piper_ring_mod_wet,
                bitcrush_levels=settings.piper_bitcrush_levels,
            ),
        )
        if settings.piper_enabled
        else None
    )

    async def _skill_speak(text: str) -> None:
        # A learned skill's speech (e.g. a timer firing minutes after the
        # turn that started it ended) has no live "turn"/websocket to
        # answer through -- broadcast to every currently connected tablet,
        # same as the existing autonomous-behavior dispatch already does.
        for session in registry.sessions():
            try:
                await session.websocket.send_json(
                    outgoing_message("show_message", session.device_id, {"title": "Bob", "message": text})
                )
                await _speak(
                    text=text, device_id=session.device_id, send=session.websocket.send_json,
                    send_bytes=session.websocket.send_bytes, tts=tts_provider,
                )
            except Exception:
                logger.warning("Failed to speak learned-skill message to %s", session.device_id, exc_info=True)

    active_agent = agent or build_agent(interactive_confirmation=False, speak_resolver=lambda: _skill_speak)
    bridge = TabletBrainBridge(active_agent, registry=registry, tts=tts_provider)
    provider = stt_provider or OpenAIRealtimeSttProvider(
        api_key=settings.openai_api_key,
        model=settings.stt_model,
        timeout=settings.stt_timeout,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        tasks: list[asyncio.Task] = []
        try:
            await bridge.agent.smart_home_service.synchronize()
        except Exception:
            logger.info("Home Assistant indisponível na inicialização; o primeiro comando tentará novamente")
        if cognition_tick_enabled:
            clock = ClockEventSource(bridge.agent.event_bus)
            tasks.append(asyncio.create_task(
                _cognition_tick_loop(bridge, registry, clock, settings.cognition_tick_seconds)
            ))
        tasks.append(asyncio.create_task(
            _music_sync_loop(bridge.agent, registry, settings.music_poll_seconds, bridge.tts)
        ))
        yield
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task

    application = FastAPI(title="Robot Brain Tablet API", version="0.1.0", lifespan=lifespan)
    application.state.registry = registry
    application.state.bridge = bridge
    application.state.cognition = bridge.agent.cognition
    application.state.smart_home_provider = bridge.agent.smart_home_service.provider
    application.state.music_service = getattr(bridge.agent, "music_service", None)

    @application.get("/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "devices": registry.count(), "llm": settings.llm_provider}

    @application.post("/debug/events")
    async def inject_debug_event(request: DebugEventRequest) -> dict[str, Any]:
        enabled = settings.debug_events_enabled if debug_events_enabled is None else debug_events_enabled
        if not enabled:
            raise HTTPException(status_code=403, detail="Debug event injection is disabled")
        result = await bridge.agent.cognition.process_event(
            RobotEvent(type=request.type, source=request.source, data=request.data)
        )
        selected = result.selected
        if selected is not None:
            await _dispatch_selected(selected, registry, bridge.agent.cognition, bridge.tts)
        return {
            "event_id": result.event.id,
            "proposals": [
                {"id": p.id, "behavior_name": p.name, "priority": p.priority, "reason": p.reason}
                for p in result.proposals
            ],
            "selected": None if selected is None else {
                "id": selected.id,
                "behavior_name": selected.name,
                "suggested_response": selected.response_hint,
                "suggested_action": selected.proposed_action,
                "requires_llm": selected.requires_llm,
            },
            "metrics": result.metrics,
        }

    @application.post("/debug/idle_animation")
    async def trigger_idle_animation(kind: str | None = None) -> dict[str, Any]:
        """Manual override for testing: pushes play_idle_animation straight to
        every connected tablet, bypassing cognition/cooldowns entirely. In
        production the tablet always picks locally at random -- this exists
        only so a specific one (e.g. "snake") can be forced on demand."""
        enabled = settings.debug_events_enabled if debug_events_enabled is None else debug_events_enabled
        if not enabled:
            raise HTTPException(status_code=403, detail="Debug event injection is disabled")
        payload = {"kind": kind} if kind else None
        sent = 0
        for session in registry.sessions():
            await session.websocket.send_json(outgoing_message("play_idle_animation", session.device_id, payload))
            sent += 1
        return {"sent_to_devices": sent, "kind": kind}

    @application.post("/debug/speak")
    async def trigger_speak(text: str) -> dict[str, Any]:
        """Manual voice-tuning aid: synthesizes `text` and sends it straight
        to every connected tablet, bypassing cognition/behavior cooldowns
        entirely (those gate autonomous *initiative*, not this). Lets a new
        RobotVoiceEffect setting be heard immediately after a restart."""
        enabled = settings.debug_events_enabled if debug_events_enabled is None else debug_events_enabled
        if not enabled:
            raise HTTPException(status_code=403, detail="Debug event injection is disabled")
        sent = 0
        for session in registry.sessions():
            await _speak(
                text=text,
                device_id=session.device_id,
                send=session.websocket.send_json,
                send_bytes=session.websocket.send_bytes,
                tts=bridge.tts,
            )
            sent += 1
        return {"sent_to_devices": sent, "used_piper": bridge.tts is not None}

    @application.websocket("/ws/device")
    async def device_socket(websocket: WebSocket) -> None:
        await websocket.accept()
        device_id = "unknown"
        audio: AudioStreamCoordinator | None = None
        turn_tasks: set[asyncio.Task[None]] = set()
        try:
            while True:
                incoming = await websocket.receive()
                if incoming.get("type") == "websocket.disconnect":
                    raise WebSocketDisconnect
                if incoming.get("bytes") is not None:
                    if audio is not None:
                        await audio.push_binary(incoming["bytes"])
                    continue
                raw_text = incoming.get("text")
                if raw_text is None:
                    continue
                raw = json.loads(raw_text)
                try:
                    message = DeviceMessage.model_validate(raw)
                except ValidationError:
                    logger.warning("Ignoring invalid device message")
                    continue
                device_id = message.device_id
                if audio is None:
                    audio = AudioStreamCoordinator(
                        provider, bridge, device_id, websocket.send_json, websocket.send_bytes, registry
                    )
                if message.type == "device_hello":
                    capabilities = {str(value) for value in message.payload.get("capabilities", [])}
                    is_fresh_connection = registry.get(device_id) is None
                    registry.connect(DeviceSession(device_id, websocket, capabilities))
                    music_service = getattr(bridge.agent, "music_service", None)
                    if is_fresh_connection and music_service is not None and music_service.presenting:
                        # A genuinely new connection (not a brief reconnect
                        # of an already-tracked session -- see
                        # DeviceRegistry.connect) inheriting a leftover
                        # `presenting=True` from earlier is exactly "the
                        # player opens by itself on startup". A cold app
                        # start should never assume it wants to see
                        # whatever was being shown before it existed.
                        music_service.presenting = False
                        await websocket.send_json(
                            outgoing_message("dismiss_scene", device_id, {"reason": "fresh_connection"})
                        )
                    await websocket.send_json(
                        outgoing_message("set_state", device_id, {"state": "LISTENING"})
                    )
                    # The tablet's wake indicator only ever changes on an
                    # explicit wake_state message, with no client-side
                    # timeout of its own -- if the backend restarts (or a
                    # reconnect races) while a wake_timeout_task is pending,
                    # that message never arrives and the eye can get stuck
                    # showing "awake". Resync it to the authoritative
                    # server-side state on every (re)connect.
                    current = registry.get(device_id)
                    await websocket.send_json(
                        outgoing_message("wake_state", device_id, {
                            "awake": current.awake if current is not None else False,
                        })
                    )
                elif message.type == "recognized_speech" and message.payload.get("is_final", False):
                    task = asyncio.create_task(bridge.process_text(
                        text=str(message.payload.get("text", "")), device_id=device_id,
                        send=websocket.send_json, send_bytes=websocket.send_bytes,
                    ))
                    turn_tasks.add(task)
                    task.add_done_callback(turn_tasks.discard)
                elif message.type == "audio_stream_start":
                    await audio.start(message.payload)
                elif message.type == "audio_stream_end":
                    await audio.end(str(message.payload.get("stream_id", "")))
                elif message.type == "audio_stream_cancel":
                    await audio.cancel("client_cancelled")
                elif message.type == "speech_playback_done":
                    session = registry.get(device_id)
                    logger.info("speech_playback_done received: session_found=%s", session is not None)
                    if session is not None:
                        session.playback_done.set()
                elif message.type == "device_status":
                    logger.debug("Status from %s: %s", device_id, message.payload)
        except WebSocketDisconnect:
            pass
        finally:
            if audio is not None:
                await audio.cancel("connection_lost")
            for task in turn_tasks:
                task.cancel()
            registry.disconnect(device_id, websocket)

    return application


app = create_app()


def main() -> None:
    uvicorn.run(app, host=settings.api_host, port=settings.api_port, reload=False)


if __name__ == "__main__":
    main()
