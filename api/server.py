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
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field, ValidationError

from app.config import settings
from app.main import build_agent
from brain.agent import RobotAgent, TurnResult
from brain.behaviors import BehaviorProposal
from brain.cognition import CognitionEngine
from brain.models import IntentType
from brain.events import EventType, RobotEvent
from emotions.events import EmotionEvent
from emotions.state import EmotionalState
from integrations.music.spotify import SpotifyError
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

# Subjects the "doodling" idle vignette can be told to draw (see
# GET /idle/doodle_subject) -- kept in sync by hand with the tablet's own
# small library of recognizable line-drawings for each one
# (idle_doodle_overlay.dart's `_subjectDrawings`).
# A full swing of natural tiredness (fully rested <-> fully exhausted)
# takes about 10 hours -- see _cognition_tick_loop's energy rate-limit.
_MAX_ENERGY_CHANGE_PER_HOUR = 1.0 / 10
# Kept in sync by hand with tablet_app's _idleActivityRestfulness
# (robot_app.dart) -- which idle vignette kinds count as "genuinely
# engaged/playing" (relieves boredom) vs. "genuinely resting" (speeds up
# energy recovery), reported to the backend via idle_activity_report
# messages (see DeviceSession.active_idle_kind).
_ACTIVE_IDLE_KINDS = {"snake", "checkers", "chess", "doodle", "humming"}
_RESTING_IDLE_KINDS = {"resting", "coffee"}
# How much faster energy recovers while genuinely resting/having a
# coffee, on top of (not instead of) the natural pace above.
_RESTING_ENERGY_RECOVERY_PER_HOUR = 0.35

# How long to stop polling Spotify after it responds 429 (rate limited)
# -- doubles on each consecutive 429 up to the cap. See _music_sync_loop.
_SPOTIFY_RATE_LIMIT_BACKOFF_SECONDS = 60.0
_SPOTIFY_RATE_LIMIT_MAX_BACKOFF_SECONDS = 600.0
# Ambient-listening/offer detection and presenting-mode position sync
# only actually call Spotify on every Nth tick of _music_sync_loop
# (which otherwise runs every MUSIC_POLL_SECONDS, ~1s by default) -- see
# _music_sync_loop. The tablet already extrapolates position locally
# between syncs, so this doesn't cost smoothness, just quota.
_AMBIENT_POLL_EVERY_N_TICKS = 5
_PRESENTING_POLL_EVERY_N_TICKS = 5

_DOODLE_SUBJECTS = [
    "casa", "estrela", "coracao", "sol", "nuvem",
    "arvore", "gato", "peixe", "flor", "robo",
]

# What the "reading" idle vignette can teach, no LLM call involved (same
# "cheap consult" spirit as _DOODLE_SUBJECTS) -- each nudges one existing
# PersonalityTraits field a tiny amount (small and slow on purpose: many
# reading sessions to meaningfully shift, not a personality rewrite) and
# hands the doodle overlay something concrete to try drawing next,
# tying "he read about it" to "he tries to draw it" -- see
# /reading/learn and /idle/doodle_subject.
_READING_LESSONS = [
    {"topic": "sarcasmo", "trait": "sarcasm", "delta": 0.01, "subject": "gato"},
    {"topic": "lógica", "trait": "confidence", "delta": 0.008, "subject": "estrela"},
    {"topic": "humor", "trait": "humor", "delta": 0.01, "subject": "sol"},
    {"topic": "empatia", "trait": "affection", "delta": 0.008, "subject": "coracao"},
    {"topic": "concisão", "trait": "verbosity", "delta": -0.008, "subject": "nuvem"},
    {"topic": "curiosidade científica", "trait": "curiosity", "delta": 0.008, "subject": "arvore"},
]

# A tiny, dependency-free page (no CDN, works fine offline on the LAN):
# drag a food up to feed the robot. Deliberately plain HTML/CSS/JS instead
# of a build step -- this is a five-minute chore page, not an app.
_FEED_PAGE_HTML = """<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Alimentar o Bob</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; user-select: none; }
  body {
    margin: 0; min-height: 100vh; display: flex; flex-direction: column;
    align-items: center; justify-content: flex-end; gap: 24px; padding: 24px;
    background: radial-gradient(circle at 50% 0%, #1a2138, #070b16 70%);
    font-family: -apple-system, Roboto, sans-serif; color: #eef1fb; touch-action: none;
    overflow: hidden;
  }
  h1 { font-size: 15px; font-weight: 600; letter-spacing: 0.4px; opacity: 0.75; margin: 0 0 4px; }
  #hint { font-size: 13px; opacity: 0.5; margin: 0 0 8px; text-align: center; }
  #tray {
    display: flex; gap: 14px; flex-wrap: wrap; justify-content: center;
    padding-bottom: env(safe-area-inset-bottom, 12px);
  }
  .food {
    width: 78px; display: flex; flex-direction: column; align-items: center;
    gap: 6px; touch-action: none; cursor: grab;
    transition: transform 0.15s ease;
  }
  .food-card {
    width: 78px; height: 78px; display: flex; align-items: center;
    justify-content: center; border-radius: 22px;
    background: linear-gradient(160deg, rgba(255,255,255,0.1), rgba(255,255,255,0.03));
    border: 1px solid rgba(255,255,255,0.14);
    box-shadow: 0 6px 18px rgba(0,0,0,0.35);
    transition: background 0.15s ease, box-shadow 0.15s ease;
  }
  .food img { width: 52px; height: 52px; object-fit: contain; pointer-events: none; }
  .food span {
    font-size: 11px; opacity: 0.6; letter-spacing: 0.2px; text-transform: lowercase;
  }
  .food.dragging { transition: none; z-index: 10; }
  .food.dragging .food-card {
    background: linear-gradient(160deg, rgba(46,230,166,0.28), rgba(255,255,255,0.05));
    box-shadow: 0 10px 26px rgba(46,230,166,0.25);
  }
  #toast {
    position: fixed; top: 18px; left: 50%; transform: translateX(-50%) translateY(-140%);
    background: #2ee6a6; color: #06251b; font-weight: 700; padding: 10px 18px;
    border-radius: 999px; font-size: 14px; transition: transform 0.35s ease; white-space: nowrap;
  }
  #toast.show { transform: translateX(-50%) translateY(0); }
</style>
</head>
<body>
  <h1>🤖 alimentar o Bob</h1>
  <p id="hint">arraste uma comida pra cima</p>
  <div id="toast">alimentado! 🍽️</div>
  <div id="tray">__FOOD_TRAY__</div>
<script>
const toast = document.getElementById('toast');
function showToast() {
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 1400);
}
async function feed(food) {
  try {
    await fetch('/feed', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ food }),
    });
    showToast();
  } catch (e) {
    // Offline/unreachable -- silently do nothing, nothing worth
    // surfacing to a casual drag-to-feed gesture.
  }
}
const THRESHOLD = 90;
document.querySelectorAll('.food').forEach((el) => {
  let startY = 0, dragging = false, ignited = false;
  const reset = () => {
    el.classList.remove('dragging');
    el.style.transform = '';
    el.style.opacity = '';
    dragging = false; ignited = false;
  };
  el.addEventListener('pointerdown', (e) => {
    startY = e.clientY; dragging = true; ignited = false;
    el.classList.add('dragging');
    el.setPointerCapture(e.pointerId);
  });
  el.addEventListener('pointermove', (e) => {
    if (!dragging) return;
    const dy = startY - e.clientY;
    if (dy > 0) {
      el.style.transform = `translateY(${-dy}px) scale(${1 + Math.min(dy, THRESHOLD) / THRESHOLD * 0.3})`;
      el.style.opacity = String(Math.max(0.2, 1 - dy / (THRESHOLD * 2)));
    }
    if (dy > THRESHOLD && !ignited) {
      ignited = true;
      feed(el.dataset.food);
    }
  });
  el.addEventListener('pointerup', reset);
  el.addEventListener('pointercancel', reset);
});
</script>
</body>
</html>"""


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


class FeedRequest(BaseModel):
    food: str = "apple"


class IdentityNoteRequest(BaseModel):
    note: str


class IdentityKnowledgeRequest(BaseModel):
    topic: str
    text: str


# Same 5 keys/images the tablet already bundles as
# tablet_app/assets/images/food/<key>.png (see idle_feed_overlay.dart's
# foodEmojiFallback, kept in sync by hand) -- reused here so the /feed
# page shows the real artwork instead of generic emoji, and so
# GET /feed/img/<key> has a closed set of valid keys to serve (never an
# arbitrary path from the request).
_FEED_FOOD_ASSETS_DIR = Path(__file__).resolve().parent.parent / "tablet_app" / "assets" / "images" / "food"
_FEED_FOODS: tuple[tuple[str, str], ...] = (
    ("apple", "maçã"),
    ("pizza", "pizza"),
    ("cookie", "cookie"),
    ("burger", "burger"),
    ("chocolate", "chocolate"),
)


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
    # The wake countdown only runs while the conversation is genuinely
    # quiet: it is held (not just re-armed) for as long as the user is
    # mid-utterance (`user_speaking`, an STT stream is open) or a turn is
    # being processed/spoken (`turn_busy`, LLM + TTS + playback). It's
    # `wake_quiet_since` -- the last moment either of those was true or the
    # timer was re-armed -- that the 10s is counted from.
    turn_busy: int = 0
    user_speaking: bool = False
    wake_quiet_since: float = 0.0
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
    # Which idle self-entertainment vignette this device is currently
    # showing (as picked client-side, see robot_app.dart's
    # _pickIdleActivity), reported via `idle_activity_report` messages --
    # None while nothing's showing. Read by _cognition_tick_loop so
    # "resting"/"coffee" actually restore energy faster, and the active
    # cluster actually relieves boredom, instead of the vignette being
    # purely cosmetic.
    active_idle_kind: str | None = None
    # The last non-null active_idle_kind, kept even after it's dismissed
    # (e.g. by the wake word that's about to start a conversation about
    # it) -- being called over *is* what clears active_idle_kind, so
    # relying on that alone would make "o que você estava fazendo?"
    # always answer "nothing" right when it's asked. Used only for
    # _current_activity_label; never read by the engagement/energy
    # calculations above, which should see the interruption as real.
    last_idle_kind: str | None = None
    # Last hardware state the tablet reported (`device_state` message):
    # {"volume": 0-100, "brightness": 0-100}. Empty until it reports.
    # Feeds the "estado do tablet" style note so Bob can answer "quanto
    # está o volume?" -- see TabletBrainBridge._device_status_label.
    device_state: dict[str, int] = field(default_factory=dict)


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

    # Kept in sync by hand with tablet_app's _idleActivityKinds
    # (robot_app.dart) -- human labels for "o que você está fazendo?" to
    # actually be answerable. "reading" is filled in dynamically below
    # (mentions the actual topic, if there is one).
    _IDLE_ACTIVITY_LABELS = {
        "snake": "brincando com um joguinho de cobrinha",
        "checkers": "jogando damas sozinho",
        "chess": "jogando xadrez sozinho",
        "resting": "descansando",
        "bored": "meio entediado, sem nada de especial pra fazer",
        "coffee": "tomando um café",
        "humming": "cantarolando alguma coisa",
        "doodle": "rabiscando um desenho",
    }

    def _device_status_label(self, device_id: str) -> str | None:
        """"volume 40%, brilho 70%" from the tablet's last `device_state`
        report -- None until it has reported at least once."""
        if self.registry is None:
            return None
        session = self.registry.get(device_id)
        if session is None or not session.device_state:
            return None
        names = {"volume": "volume", "brightness": "brilho"}
        return ", ".join(
            f"{names[key]} {value}%"
            for key, value in session.device_state.items()
            if key in names
        ) or None

    def _current_activity_label(self, device_id: str) -> str | None:
        """A human-readable answer to "o que você está fazendo?" -- from
        the idle vignette the device last reported showing (see
        DeviceSession.active_idle_kind, set by `idle_activity_report`
        messages). Being called (the wake word) is exactly what dismisses
        the idle vignette client-side, clearing active_idle_kind right
        before this turn even starts -- so this falls back to
        `last_idle_kind` (which isn't cleared on dismissal) and phrases
        it in the past tense, rather than always answering "nothing"
        the moment it's actually asked. None only when neither is set/no
        session is known.
        """
        if self.registry is None:
            return None
        session = self.registry.get(device_id)
        if session is None:
            return None
        if session.active_idle_kind is not None:
            return self._activity_phrase(session.active_idle_kind, ongoing=True)
        if session.last_idle_kind is not None:
            return self._activity_phrase(session.last_idle_kind, ongoing=False)
        return None

    def _activity_phrase(self, kind: str, *, ongoing: bool) -> str | None:
        if kind == "reading":
            topic = self.agent.needs_engine.state.last_read_topic
            base = f"lendo sobre {topic}" if topic else "lendo"
        else:
            base = self._IDLE_ACTIVITY_LABELS.get(kind)
        if base is None:
            return None
        if ongoing:
            return base
        return f"{base} até agora, mas parou pra te dar atenção"

    async def process_text(self, *, text: str, device_id: str, send: SendMessage, send_bytes: SendBytes) -> None:
        # While a turn is being processed and spoken the wake countdown is
        # held (see _arm_wake_timeout) -- otherwise a long answer could let
        # the session expire mid-reply, the eye snapping back to standby
        # while he's still talking.
        session = self.registry.get(device_id) if self.registry is not None else None
        if session is not None:
            session.turn_busy += 1
        try:
            await self._process_text(text=text, device_id=device_id, send=send, send_bytes=send_bytes)
        finally:
            if session is not None:
                session.turn_busy = max(0, session.turn_busy - 1)
                session.wake_quiet_since = time.monotonic()

    async def _process_text(self, *, text: str, device_id: str, send: SendMessage, send_bytes: SendBytes) -> None:
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
            current_activity = self._current_activity_label(device_id)
            async with self._turn_lock:
                result = await self.agent.process_turn(
                    cleaned,
                    current_activity=current_activity,
                    device_status=self._device_status_label(device_id),
                )
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
            # "vai jogar"/"joga um pouco" etc. route to idle.play_now (see
            # actions/robot/play.py), which has no side effect of its own
            # -- this is what actually starts a self-entertainment
            # vignette on command, the same message PlayfulIdleBehavior
            # sends autonomously after enough idle time (_dispatch_selected).
            if any(
                record.name == "idle.play_now" and record.outcome and record.outcome.success
                for record in result.action_records
            ):
                await send(outgoing_message("play_idle_animation", device_id))
            # device.set_*/device.change_* (actions/robot/device.py) have no
            # side effect of their own either -- the tablet owns its
            # volume/brightness, so a successful record's `data` is
            # forwarded to it as a `device_control` message.
            for record in result.action_records:
                if (
                    record.name.startswith("device.")
                    and record.outcome
                    and record.outcome.success
                    and record.outcome.data.get("control")
                ):
                    await send(outgoing_message("device_control", device_id, dict(record.outcome.data)))
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
# How often the wake countdown checks whether the conversation is still
# active (see _arm_wake_timeout) -- fine-grained enough that the 10s of
# silence is measured to well under a second.
WAKE_POLL_SECONDS = 0.5

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
    session.wake_quiet_since = time.monotonic()

    async def _expire() -> None:
        # Poll instead of one long sleep: a single sleep(10) armed before a
        # long turn or a long utterance would expire mid-conversation (the
        # eye snapping back to standby while the user is still talking or
        # the robot is still answering). Counting only genuinely quiet time
        # means the window starts once he's done speaking AND nobody is
        # talking.
        while True:
            await asyncio.sleep(WAKE_POLL_SECONDS)
            if session.turn_busy > 0 or session.user_speaking:
                session.wake_quiet_since = time.monotonic()
                continue
            if time.monotonic() - session.wake_quiet_since >= WAKE_TIMEOUT_SECONDS:
                break
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
        self._set_user_speaking(True)
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
            self._set_user_speaking(False)

    def _set_user_speaking(self, speaking: bool) -> None:
        """Mirrors "an utterance is being recorded/transcribed" onto the
        session so the wake countdown holds while the user is mid-sentence
        (see _arm_wake_timeout). Also restarts the quiet clock on the way
        out, so the 10s is counted from when they stopped."""
        session = self.registry.get(self.device_id)
        if session is None:
            return
        session.user_speaking = speaking
        if not speaking:
            session.wake_quiet_since = time.monotonic()

    async def cancel(self, reason: str) -> None:
        if self.active is None:
            return
        active, self.active = self.active, None
        self._set_user_speaking(False)
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

            active_idle_kinds = {
                s.active_idle_kind for s in registry.sessions() if s.active_idle_kind
            }
            is_engaged = bool(active_idle_kinds & _ACTIVE_IDLE_KINDS)
            is_resting = bool(active_idle_kinds & _RESTING_IDLE_KINDS)
            needs = agent.needs_engine.advance(interval, engaged=is_engaged)
            agent.needs_engine.save()

            last = world.activity.last_interaction_at or world.activity.active_since
            idle_seconds = (datetime.now(timezone.utc) - last).total_seconds()

            emotional_state = agent.emotional_engine.state
            # Natural pacing: energy drifts toward its rest-driven target
            # at a fixed, slow rate (~10%/hour -- a full swing takes about
            # 10 hours) regardless of how far off it starts. Rate-limited,
            # not smoothed toward the target -- a percentage smoothing
            # pull (e.g. "15% of the gap per tick") converges in minutes
            # no matter the starting gap, which reads as tiredness
            # swinging almost instantly.
            natural_target = _clamp01(1 - drives.rest)
            max_energy_step = _MAX_ENERGY_CHANGE_PER_HOUR * (interval / 3600)
            energy_delta = natural_target - emotional_state.energy
            energy_step = max(-max_energy_step, min(max_energy_step, energy_delta))
            emotional_state.energy = _clamp01(emotional_state.energy + energy_step)
            # Hunger is an external factor, not part of the natural pace
            # above -- it drains energy directly, uncapped by the 10%/h
            # limit, so being genuinely hungry can tire the robot out
            # faster than resting alone ever would.
            emotional_state.energy = _clamp01(
                emotional_state.energy - needs.hunger * 0.15 * (interval / 3600)
            )
            # Actually resting/having a coffee genuinely speeds up
            # recovery, well past the natural 10%/h pace above -- so the
            # answer to "does resting help him recover?" is yes.
            if is_resting:
                emotional_state.energy = _clamp01(
                    emotional_state.energy + _RESTING_ENERGY_RECOVERY_PER_HOUR * (interval / 3600)
                )
            # Being hungry AND idle for a while compounds into irritation --
            # neither alone is enough to trigger this.
            if needs.hunger > 0.6 and idle_seconds > 300:
                emotional_state.irritation = _clamp01(
                    emotional_state.irritation + needs.hunger * 0.02 * (interval / 3600)
                )

            sessions = registry.sessions()
            for session in sessions:
                payload = emotional_state.model_dump()
                payload["hunger"] = needs.hunger
                payload["boredom"] = needs.boredom
                payload["idle_seconds"] = idle_seconds
                await session.websocket.send_json(
                    outgoing_message("set_expression", session.device_id, payload)
                )

            # With no tablet connected there's nobody to receive whatever
            # initiative gets selected -- and selecting one still spends its
            # per-behavior cooldown and the hourly cap. Skipping here keeps
            # those budgets intact for when a tablet actually connects,
            # instead of Bob having "played" 4x to an empty room and then
            # sitting bored (boredom 100%) for the next hour.
            if not sessions:
                continue

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


def _is_actually_playing(payload: dict | None) -> bool:
    """True only for a Spotify payload that is genuinely playing right now
    (not paused, not absent) -- what "someone is listening" must mean for
    the headphones and the open-the-player offer."""
    return payload is not None and bool(payload.get("is_playing"))


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
    # Whether the "headphones on, listening along" face is currently
    # showing -- set_ambient_listening is actually re-sent every tick
    # (see below), this is just kept for the "presenting just started"
    # reset above.
    was_ambient_listening = False
    # Consecutive 429s from Spotify -- backs off longer each time
    # (capped) instead of retrying at a fixed interval that keeps
    # tripping the same limit right back.
    rate_limit_backoff_streak = 0
    # Ambient detection (headphones/offer) doesn't need per-second
    # freshness the way position-synced lyrics while presenting does --
    # only actually polling Spotify for it every few ticks meaningfully
    # cuts total request volume against Spotify's (fairly tight,
    # Development-Mode) quota.
    ambient_poll_counter = 0
    # The presenting-mode poll doesn't need per-second freshness either --
    # the tablet already extrapolates position locally between updates
    # (see this function's own docstring) and corrects on the next
    # sync, so a slower sync cadence here just means a slightly longer
    # worst-case correction delay, not a less smooth player.
    presenting_poll_counter = 0
    while True:
        try:
            # Once the robot is presenting its own player, it's not
            # "listening along" anymore -- turn the headphones back off.
            if service.presenting and was_ambient_listening:
                was_ambient_listening = False
                for session in registry.sessions():
                    await session.websocket.send_json(outgoing_message(
                        "set_ambient_listening", session.device_id, {"listening": False}))

            # Only mirror playback onto the tablet while the robot itself is
            # the one presenting it (see `MusicExperienceService.presenting`)
            # -- otherwise this loop would show whatever happens to be
            # playing on the user's own Spotify session (phone, PC...)
            # any time it's active, which nobody asked the robot to display.
            presenting_poll_counter += 1
            if service.presenting:
                just_started = not was_presenting
                if just_started:
                    presenting_audience = {s.device_id for s in registry.sessions()}
                if just_started or presenting_poll_counter % _PRESENTING_POLL_EVERY_N_TICKS == 0:
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
            ambient_poll_counter += 1
            if not service.presenting and ambient_poll_counter % _AMBIENT_POLL_EVERY_N_TICKS == 0:
                # Playing somewhere else (phone, PC...) and the robot hasn't
                # been asked for it -- offer once per track instead of either
                # silently ignoring it or showing up uninvited.
                ambient = await service.current_payload()
                # Spotify's currently-playing endpoint keeps returning the
                # last track while it's *paused* (is_playing=false) -- that
                # is not "someone is listening", and treating it as such put
                # the headphones on (and offered the player) with nothing
                # actually playing.
                if not _is_actually_playing(ambient):
                    ambient = None
                offer_now = service.should_offer(ambient is not None)
                # "Listening along": puts headphones on Bob's face while
                # someone else's playback is going, independent of the
                # voice offer above (which only fires once per session/
                # time-window) -- this just tracks whether ambient
                # playback is happening right now.
                # Sent every tick (not just on change) -- same pattern as
                # set_expression below. A device that (re)connects after
                # the state already flipped would otherwise never learn
                # the current value until the next actual change, which
                # could be a long wait.
                is_ambient_listening = ambient is not None
                was_ambient_listening = is_ambient_listening
                for session in registry.sessions():
                    await session.websocket.send_json(outgoing_message(
                        "set_ambient_listening", session.device_id,
                        {"listening": is_ambient_listening}))
                if ambient is not None and offer_now:
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
            rate_limit_backoff_streak = 0
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Spotify sync temporarily unavailable", exc_info=True)
            # Can't confirm ambient playback is still happening (or ever
            # resume confirming it, e.g. mid rate-limit backoff, which can
            # run for hours per Spotify's own Retry-After) -- fail safe to
            # "not listening" rather than leaving the headphones stuck
            # showing whatever the last successful poll happened to see.
            # Sent unconditionally (not just on a tracked True->False
            # transition): a session that connected *during* an ongoing
            # failure never got a real update at all, and could be
            # showing a stale True from before this process even started.
            was_ambient_listening = False
            for session in registry.sessions():
                await session.websocket.send_json(outgoing_message(
                    "set_ambient_listening", session.device_id, {"listening": False}))
            if "429" in str(exc):
                # Spotify is rate-limiting this app -- polling every tick
                # regardless would just keep tripping the same limit right
                # back (as a fixed short backoff did in practice). Prefer
                # Spotify's own Retry-After (the real, authoritative
                # window) when it sent one; otherwise fall back to
                # doubling each consecutive 429, capped at 10 minutes.
                rate_limit_backoff_streak += 1
                if isinstance(exc, SpotifyError) and exc.retry_after:
                    backoff = exc.retry_after
                    source = "Retry-After"
                else:
                    backoff = min(
                        _SPOTIFY_RATE_LIMIT_MAX_BACKOFF_SECONDS,
                        _SPOTIFY_RATE_LIMIT_BACKOFF_SECONDS * (2 ** (rate_limit_backoff_streak - 1)),
                    )
                    source = "exponential fallback"
                logger.warning(
                    "Spotify rate-limited (429) -- backing off %.0fs via %s (streak=%d)",
                    backoff, source, rate_limit_backoff_streak,
                )
                await asyncio.sleep(backoff)
                continue
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
        logger.info("skill_speak broadcasting text=%r to %d session(s)", text, registry.count())
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

    @application.get("/idle/doodle_subject")
    async def doodle_subject() -> dict[str, Any]:
        """A cheap (no LLM call) pick of something for the tablet's
        "doodling" idle vignette to actually draw, instead of a random
        squiggle -- one round trip, no tokens spent, picked from a small
        curated set of subjects the tablet already knows how to render
        (see idle_doodle_overlay.dart's `_subjectDrawings`). Prefers
        whatever he last "read" about (see /reading/learn), one-shot --
        so a reading session sets up what he tries to draw next, then
        falls back to picking at random again."""
        read_subject = bridge.agent.needs_engine.consume_last_read_subject()
        bridge.agent.needs_engine.save()
        return {"subject": read_subject or random.choice(_DOODLE_SUBJECTS)}

    @application.post("/reading/learn")
    async def reading_learn() -> dict[str, Any]:
        """Called once per "reading" idle session (see
        idle_reading_overlay.dart) -- no LLM call, picks one lesson from
        the small curated _READING_LESSONS list, nudges the matching
        PersonalityTraits field a tiny amount (many sessions to add up to
        anything noticeable, on purpose), and remembers its paired
        drawable subject for the next doodle session."""
        lesson = random.choice(_READING_LESSONS)
        traits = bridge.agent.personality.traits
        current = getattr(traits, lesson["trait"])
        setattr(traits, lesson["trait"], _clamp01(current + lesson["delta"]))
        bridge.agent.personality.save()
        bridge.agent.needs_engine.set_last_read_subject(lesson["subject"])
        bridge.agent.needs_engine.set_last_read_topic(lesson["topic"])
        bridge.agent.needs_engine.save()
        return {"topic": lesson["topic"], "trait": lesson["trait"]}

    @application.get("/identity")
    async def get_identity() -> dict[str, Any]:
        """Bob's current persistent self-identity -- who he is, his
        focus areas, and the self-notes he's accumulated so far (see
        memory/identity.py). Read-only introspection, same purpose as
        GET /idle/game_skill for the needs engine."""
        state = bridge.agent.identity_store.state
        return {
            "who": state.who,
            "focus_areas": state.focus_areas,
            "self_notes": state.self_notes,
            "knowledge": [entry.model_dump() for entry in state.knowledge],
        }

    @application.post("/identity/knowledge")
    async def add_identity_knowledge(request: IdentityKnowledgeRequest) -> dict[str, Any]:
        """Injects (or corrects, if the topic already exists) one piece of
        guidance into Bob's brain -- the same thing "Bob, aprenda que..."
        does by voice (see actions/robot/learning.py). Takes effect from
        the next turn."""
        store = bridge.agent.identity_store
        store.add_knowledge(request.topic, request.text)
        store.save()
        return {"knowledge": [entry.model_dump() for entry in store.state.knowledge]}

    @application.post("/identity/note")
    async def add_identity_note(request: IdentityNoteRequest) -> dict[str, Any]:
        """Appends one self-observation to Bob's identity -- this is what
        actually makes the identity *grow* over time instead of staying a
        fixed, hand-written block forever. It's injected into every
        system prompt from the next turn on (see
        memory/identity.py::as_prompt_fragment)."""
        bridge.agent.identity_store.add_self_note(request.note)
        bridge.agent.identity_store.save()
        return {"self_notes": bridge.agent.identity_store.state.self_notes}

    @application.get("/idle/game_skill")
    async def game_skill() -> dict[str, Any]:
        """How much less random chess/checkers moves should be right now
        -- fetched once per match by idle_chess_overlay.dart/
        idle_checkers_overlay.dart to bias move selection."""
        return {"skill": bridge.agent.needs_engine.state.game_skill}

    @application.post("/idle/game_result")
    async def game_result() -> dict[str, Any]:
        """Called when a chess/checkers match concludes (a "loss", in the
        vignette's simulated sense) -- nudges game_skill up a small,
        slow amount. Not a real chess engine; just "prefers captures,
        avoids obvious blunders" a bit more often as this rises."""
        needs = bridge.agent.needs_engine.record_game_result()
        bridge.agent.needs_engine.save()
        return {"skill": needs.game_skill}

    @application.get("/feed", response_class=HTMLResponse)
    async def feed_page() -> str:
        """A tiny mobile-first page, on the same LAN as the robot -- drag
        a food up to feed Bob, no app install, no cloud dependency (see
        the plan doc's part D for why this isn't an Artifact: it needs to
        reach the robot's own websocket sessions directly). The tray shows
        the same reference artwork the tablet uses (via GET /feed/img/*)
        instead of generic emoji, generated from _FEED_FOODS so the two
        never drift apart."""
        tray = "\n    ".join(
            f'<div class="food" data-food="{key}">'
            f'<div class="food-card"><img src="/feed/img/{key}" alt="{label}"></div>'
            f'<span>{label}</span></div>'
            for key, label in _FEED_FOODS
        )
        return _FEED_PAGE_HTML.replace("__FOOD_TRAY__", tray)

    @application.get("/feed/img/{food}")
    async def feed_food_image(food: str) -> FileResponse:
        """Serves the same PNGs bundled into the tablet app
        (tablet_app/assets/images/food/<key>.png) -- `food` is checked
        against the closed _FEED_FOODS list, never used as a raw path, so
        this can't be turned into an arbitrary-file read."""
        valid_keys = {key for key, _ in _FEED_FOODS}
        if food not in valid_keys:
            raise HTTPException(status_code=404, detail="unknown food")
        path = _FEED_FOOD_ASSETS_DIR / f"{food}.png"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="image not found")
        return FileResponse(path, media_type="image/png")

    @application.post("/feed")
    async def feed_robot(request: FeedRequest) -> dict[str, Any]:
        needs = bridge.agent.needs_engine.feed()
        bridge.agent.needs_engine.save()
        # A small, genuine mood lift -- being fed is a nice thing to
        # happen, not just a number going down.
        bridge.agent.emotional_engine.apply_event(EmotionEvent.COMPLIMENT_RECEIVED)
        bridge.agent.emotional_engine.save()
        sent = 0
        for session in registry.sessions():
            await session.websocket.send_json(
                outgoing_message("feed_animation", session.device_id, {"food": request.food})
            )
            sent += 1
        return {"hunger": needs.hunger, "sent_to_devices": sent}

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
                elif message.type == "device_state":
                    session = registry.get(device_id)
                    if session is not None:
                        for key in ("volume", "brightness"):
                            value = message.payload.get(key)
                            if isinstance(value, (int, float)) and not isinstance(value, bool):
                                session.device_state[key] = max(0, min(100, int(round(value))))
                        shared = getattr(bridge.agent, "device_status", None)
                        if shared is not None:
                            shared.state = dict(session.device_state)
                elif message.type == "idle_activity_report":
                    session = registry.get(device_id)
                    if session is not None:
                        kind = message.payload.get("kind")
                        session.active_idle_kind = kind
                        if kind is not None:
                            session.last_idle_kind = kind
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
