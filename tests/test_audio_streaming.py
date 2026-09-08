from __future__ import annotations

import asyncio
import struct

from api.server import (
    AudioStreamCoordinator,
    DeviceRegistry,
    DeviceSession,
    TabletBrainBridge,
    _speak_and_wait_for_playback,
)
from brain.agent import TurnResult
from brain.models import Decision, IntentType
from emotions.state import EmotionalState
from perception.speech.streaming import (
    SpeechToTextProvider,
    SpeechTranscript,
    SttSession,
    SttSessionConfig,
    SttSessionState,
)


class _FakeWebSocket:
    async def send_json(self, data: dict) -> None:
        pass


def _awake_registry(device_id: str = "tablet_test") -> DeviceRegistry:
    # These tests exercise the STT plumbing, not the wake-word gate, so the
    # device starts pre-awake and every final transcript reaches the agent
    # exactly like before that gate existed.
    registry = DeviceRegistry()
    registry.connect(DeviceSession(device_id, _FakeWebSocket(), awake=True))  # type: ignore[arg-type]
    return registry


class FakeAgent:
    class Emotional:
        state = EmotionalState()

    emotional_engine = Emotional()

    def __init__(self) -> None:
        self.turns: list[str] = []

    async def process_turn(self, text: str, *args, **kwargs) -> TurnResult:
        self.turns.append(text)
        return TurnResult(
            reply="ok",
            decision=Decision(type=IntentType.DIALOGUE, confidence=1, raw_text=text),
        )


class FakeSession(SttSession):
    def __init__(self) -> None:
        self.state = SttSessionState.STREAMING
        self.chunks: list[bytes] = []
        self.ended = False
        self.cancelled = False

    async def push_audio(self, chunk: bytes) -> None:
        self.chunks.append(chunk)

    async def end(self) -> None:
        self.ended = True

    async def cancel(self) -> None:
        self.cancelled = True


class FakeProvider(SpeechToTextProvider):
    name = "fake"

    def __init__(self) -> None:
        self.session = FakeSession()
        self.callback = None

    async def start_session(self, config: SttSessionConfig, on_transcript):
        self.callback = on_transcript
        return self.session


async def test_partial_never_reaches_brain_and_final_is_idempotent() -> None:
    agent = FakeAgent()
    provider = FakeProvider()
    messages: list[dict] = []

    async def send(message: dict) -> None:
        messages.append(message)

    async def send_bytes(data: bytes) -> None:
        pass

    coordinator = AudioStreamCoordinator(
        provider, TabletBrainBridge(agent), "tablet_test", send, send_bytes, _awake_registry()  # type: ignore[arg-type]
    )
    await coordinator.start({
        "stream_id": "audio_1",
        "format": {"sample_rate": 24000, "channels": 1, "encoding": "pcm_s16le"},
    })
    assert provider.callback is not None
    partial = SpeechTranscript("audio_1", "olá", "olá", False)
    final = SpeechTranscript("audio_1", "olá robô", "olá robô", True)
    await provider.callback(partial)
    assert agent.turns == []
    await provider.callback(final)
    await provider.callback(final)
    assert agent.turns == ["olá robô"]
    assert [m["type"] for m in messages].count("transcript_partial") == 1
    assert [m["type"] for m in messages].count("transcript_final") == 1


async def test_binary_sequence_tracks_gaps_and_duplicates() -> None:
    provider = FakeProvider()

    async def send(message: dict) -> None:
        pass

    async def send_bytes(data: bytes) -> None:
        pass

    coordinator = AudioStreamCoordinator(
        provider, TabletBrainBridge(FakeAgent()), "tablet_test", send, send_bytes, _awake_registry()  # type: ignore[arg-type]
    )
    await coordinator.start({"stream_id": "audio_2", "format": {"sample_rate": 24000}})
    await coordinator.push_binary(b"RBA1" + struct.pack(">I", 0) + b"a")
    await coordinator.push_binary(b"RBA1" + struct.pack(">I", 2) + b"c")
    await coordinator.push_binary(b"RBA1" + struct.pack(">I", 2) + b"dup")
    assert provider.session.chunks == [b"a", b"c"]
    assert coordinator.active is not None
    assert coordinator.active.missing_chunks == 1
    assert coordinator.active.duplicate_chunks == 1


async def test_chattered_duplicate_command_is_suppressed() -> None:
    # The client's VAD can chop one utterance into two back-to-back audio
    # segments, each becoming its own stream with its own final transcript.
    # If both land on essentially the same text, the second one must not
    # trigger a second LLM turn.
    agent = FakeAgent()
    provider = FakeProvider()

    async def send(message: dict) -> None:
        pass

    async def send_bytes(data: bytes) -> None:
        pass

    coordinator = AudioStreamCoordinator(
        provider, TabletBrainBridge(agent), "tablet_test", send, send_bytes, _awake_registry()  # type: ignore[arg-type]
    )

    await coordinator.start({"stream_id": "chatter_1", "format": {"sample_rate": 24000}})
    await provider.callback(SpeechTranscript("chatter_1", "tudo bem", "tudo bem", True))

    provider.session = FakeSession()
    await coordinator.start({"stream_id": "chatter_2", "format": {"sample_rate": 24000}})
    await provider.callback(SpeechTranscript("chatter_2", "tudo bem", "tudo bem", True))

    assert agent.turns == ["tudo bem"]


async def test_distinct_followup_command_is_not_suppressed() -> None:
    agent = FakeAgent()
    provider = FakeProvider()

    async def send(message: dict) -> None:
        pass

    async def send_bytes(data: bytes) -> None:
        pass

    coordinator = AudioStreamCoordinator(
        provider, TabletBrainBridge(agent), "tablet_test", send, send_bytes, _awake_registry()  # type: ignore[arg-type]
    )

    await coordinator.start({"stream_id": "turn_1", "format": {"sample_rate": 24000}})
    await provider.callback(SpeechTranscript("turn_1", "tudo bem", "tudo bem", True))

    provider.session = FakeSession()
    await coordinator.start({"stream_id": "turn_2", "format": {"sample_rate": 24000}})
    await provider.callback(SpeechTranscript("turn_2", "que horas são", "que horas são", True))

    assert agent.turns == ["tudo bem", "que horas são"]


async def test_command_started_while_awake_survives_timeout_racing_finalization() -> None:
    # The STT provider's finalization round-trip can take a second or more --
    # long enough for the wake timeout to fire in between. A command that
    # started recording while genuinely awake must still be honored even if
    # `session.awake` has already flipped back to False by the time its
    # final transcript arrives.
    agent = FakeAgent()
    provider = FakeProvider()
    registry = DeviceRegistry()
    registry.connect(DeviceSession("tablet_test", _FakeWebSocket(), awake=True))  # type: ignore[arg-type]

    async def send(message: dict) -> None:
        pass

    async def send_bytes(data: bytes) -> None:
        pass

    coordinator = AudioStreamCoordinator(
        provider, TabletBrainBridge(agent), "tablet_test", send, send_bytes, registry
    )

    await coordinator.start({"stream_id": "raced_1", "format": {"sample_rate": 24000}})
    # Simulate the wake timeout expiring while this utterance was still
    # in flight (e.g. finalization took long enough to race it).
    registry.get("tablet_test").awake = False  # type: ignore[union-attr]
    await provider.callback(SpeechTranscript("raced_1", "que horas são", "que horas são", True))

    assert agent.turns == ["que horas são"]
    assert registry.get("tablet_test").awake is True  # type: ignore[union-attr]


async def test_speak_and_wait_for_playback_returns_once_signaled() -> None:
    # The tablet signals real completion via `speech_playback_done` instead
    # of the server guessing how long speech takes to play back. Once that
    # signal arrives, the wait must end immediately rather than sitting out
    # its full fallback ceiling.
    session = DeviceSession("tablet_test", _FakeWebSocket(), awake=True)  # type: ignore[arg-type]

    async def send(message: dict) -> None:
        pass

    async def send_bytes(data: bytes) -> None:
        pass

    async def signal_soon() -> None:
        await asyncio.sleep(0)
        session.playback_done.set()

    asyncio.ensure_future(signal_soon())
    # A tight outer timeout: if the signal is ignored and it falls through
    # to the multi-second fallback ceiling instead, this fails fast rather
    # than hanging the test suite.
    await asyncio.wait_for(
        _speak_and_wait_for_playback(
            text="oi", device_id="tablet_test", send=send, send_bytes=send_bytes, tts=None, session=session
        ),
        timeout=1.0,
    )


async def test_new_stream_cancels_previous_and_disconnect_cleans_up() -> None:
    provider = FakeProvider()

    async def send(message: dict) -> None:
        pass

    async def send_bytes(data: bytes) -> None:
        pass

    coordinator = AudioStreamCoordinator(
        provider, TabletBrainBridge(FakeAgent()), "tablet_test", send, send_bytes, _awake_registry()  # type: ignore[arg-type]
    )
    await coordinator.start({"stream_id": "first", "format": {"sample_rate": 24000}})
    first = provider.session
    provider.session = FakeSession()
    await coordinator.start({"stream_id": "second", "format": {"sample_rate": 24000}})
    assert first.cancelled is True
    await coordinator.cancel("connection_lost")
    assert provider.session.cancelled is True
    assert coordinator.active is None
