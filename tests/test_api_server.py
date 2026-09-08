from __future__ import annotations

from brain.agent import TurnResult
from brain.models import ActionOutcome, ActionRecord, Decision, IntentType
from emotions.state import EmotionalState
from fastapi.testclient import TestClient

from api.server import TTS_AUDIO_MAGIC, TabletBrainBridge, _speak, create_app, expression_for_result, mood_vector_for_result, outgoing_message
from app.main import build_agent


class _FakeEmotionalEngine:
    state = EmotionalState(valence=0.8, energy=0.7, irritation=0.05, curiosity=0.6)


class _FakeAgent:
    emotional_engine = _FakeEmotionalEngine()

    async def process_turn(self, text: str, *args, **kwargs) -> TurnResult:
        return TurnResult(
            reply=f"Resposta para: {text}",
            decision=Decision(type=IntentType.DIALOGUE, confidence=0.8, raw_text=text),
        )


class _FakeTimeAgent(_FakeAgent):
    async def process_turn(self, text: str, *args, **kwargs) -> TurnResult:
        return TurnResult(
            reply="Agora são 19:27.",
            decision=Decision(type=IntentType.ACTION, confidence=1, raw_text=text),
            action_records=[ActionRecord(
                id="time-1",
                name="time.get",
                arguments={},
                outcome=ActionOutcome(
                    success=True,
                    message="Agora são 19:27",
                    data={"time": "19:27", "seconds": 27, "period": "night"},
                ),
            )],
        )


def test_debug_event_endpoint_is_protected_and_can_simulate_real_event() -> None:
    agent = build_agent(interactive_confirmation=False)
    disabled = TestClient(create_app(agent=agent))
    assert disabled.post("/debug/events", json={"type": "person_detected", "data": {}}).status_code == 403

    enabled = TestClient(create_app(agent=agent, debug_events_enabled=True))
    response = enabled.post("/debug/events", json={"type": "person_detected", "data": {"person_id": "joao"}})
    assert response.status_code == 200
    assert response.json()["proposals"][0]["behavior_name"] == "GreetingBehavior"


def test_idle_timeout_can_trigger_playful_and_sleep_proposals() -> None:
    agent = build_agent(interactive_confirmation=False)
    agent.cognition.drive_engine.state.rest = 0.9
    client = TestClient(create_app(agent=agent, debug_events_enabled=True, cognition_tick_enabled=False))

    response = client.post("/debug/events", json={"type": "idle_timeout", "data": {"idle_seconds": 600}})

    assert response.status_code == 200
    names = {p["behavior_name"] for p in response.json()["proposals"]}
    assert "PlayfulIdleBehavior" in names
    assert "SleepBehavior" in names


async def test_bridge_sends_thinking_expression_reply_and_idle() -> None:
    messages: list[dict] = []
    bridge = TabletBrainBridge(_FakeAgent())  # type: ignore[arg-type]

    async def send(message: dict) -> None:
        messages.append(message)

    async def send_bytes(data: bytes) -> None:
        raise AssertionError("no Piper voice configured; binary audio should never be sent")

    await bridge.process_text(text="Olá robô", device_id="tablet_test", send=send, send_bytes=send_bytes)

    assert [message["type"] for message in messages] == [
        "dismiss_scene",
        "set_state",
        "show_transcript",
        "set_expression",
        "show_message",
        "speak",
        "set_state",
    ]
    assert messages[5]["payload"]["text"] == messages[4]["payload"]["message"]
    assert messages[1]["payload"]["state"] == "THINKING"
    assert messages[3]["payload"]["expression"] == "happy"
    assert messages[3]["payload"]["valence"] == 0.8
    assert messages[3]["payload"]["energy"] == 0.7
    assert messages[3]["payload"]["irritation"] == 0.05
    assert messages[3]["payload"]["curiosity"] == 0.6
    assert messages[4]["payload"]["message"] == "Resposta para: Olá robô"
    assert messages[6]["payload"]["state"] == "IDLE"


async def test_clock_scene_does_not_replace_spoken_time() -> None:
    messages: list[dict] = []
    bridge = TabletBrainBridge(_FakeTimeAgent())  # type: ignore[arg-type]

    async def send(message: dict) -> None:
        messages.append(message)

    async def send_bytes(_: bytes) -> None:
        raise AssertionError("no binary TTS expected")

    await bridge.process_text(
        text="Que horas são?", device_id="tablet_test", send=send, send_bytes=send_bytes
    )

    scene = next(message for message in messages if message["type"] == "show_scene")
    speech = next(message for message in messages if message["type"] == "speak")
    assert scene["payload"]["kind"] == "clock"
    assert scene["payload"]["data"]["period"] == "night"
    assert speech["payload"]["text"] == "Agora são 19:27."


def test_question_nudges_curiosity_up_without_discarding_vector() -> None:
    state = EmotionalState(valence=0.5, energy=0.5, irritation=0.05, curiosity=0.6)
    result = TurnResult(
        reply="Porque sim.",
        decision=Decision(type=IntentType.QUESTION, confidence=0.8),
    )
    vector = mood_vector_for_result(result, state)
    assert vector["curiosity"] > 0.6
    assert vector["valence"] == 0.5


def test_ambiguous_nudges_irritation_up_and_valence_down() -> None:
    state = EmotionalState(valence=0.5, energy=0.5, irritation=0.05, curiosity=0.6)
    result = TurnResult(
        reply="Não entendi.",
        decision=Decision(type=IntentType.AMBIGUOUS, confidence=0.4),
    )
    vector = mood_vector_for_result(result, state)
    assert vector["irritation"] > 0.05
    assert vector["valence"] < 0.5


def test_question_maps_to_curious_expression() -> None:
    result = TurnResult(
        reply="Porque sim.",
        decision=Decision(type=IntentType.QUESTION, confidence=0.8),
    )
    assert expression_for_result(result, "calm") == "curious"


class _FakeTts:
    def __init__(self, audio: bytes | None) -> None:
        self.audio = audio

    async def synthesize(self, text: str) -> bytes | None:
        return self.audio


def _recording_sinks() -> tuple[list[dict], list[bytes], "object", "object"]:
    sent_json: list[dict] = []
    sent_bytes: list[bytes] = []

    async def send(message: dict) -> None:
        sent_json.append(message)

    async def send_bytes(data: bytes) -> None:
        sent_bytes.append(data)

    return sent_json, sent_bytes, send, send_bytes


async def test_speak_sends_binary_audio_when_tts_available() -> None:
    sent_json, sent_bytes, send, send_bytes = _recording_sinks()

    await _speak(text="oi", device_id="tablet_test", send=send, send_bytes=send_bytes, tts=_FakeTts(b"fake-wav-bytes"))

    assert not sent_json
    assert sent_bytes == [TTS_AUDIO_MAGIC + b"fake-wav-bytes"]


async def test_speak_falls_back_to_text_message_without_tts() -> None:
    sent_json, sent_bytes, send, send_bytes = _recording_sinks()

    await _speak(text="oi", device_id="tablet_test", send=send, send_bytes=send_bytes, tts=None)

    assert not sent_bytes
    assert sent_json[0]["type"] == "speak"
    assert sent_json[0]["payload"]["text"] == "oi"


async def test_speak_falls_back_to_text_message_when_synthesis_fails() -> None:
    sent_json, sent_bytes, send, send_bytes = _recording_sinks()

    await _speak(text="oi", device_id="tablet_test", send=send, send_bytes=send_bytes, tts=_FakeTts(None))

    assert not sent_bytes
    assert sent_json[0]["type"] == "speak"


def test_outgoing_message_keeps_versioned_envelope() -> None:
    message = outgoing_message("set_state", "tablet_test", {"state": "IDLE"})
    assert message["version"] == 1
    assert message["device_id"] == "tablet_test"
    assert isinstance(message["timestamp"], int)
