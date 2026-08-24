from __future__ import annotations

from brain.agent import TurnResult
from brain.models import Decision, IntentType
from api.server import TabletBrainBridge, expression_for_result, outgoing_message


class _FakeState:
    def mood_label(self) -> str:
        return "cheerful"


class _FakeEmotionalEngine:
    state = _FakeState()


class _FakeAgent:
    emotional_engine = _FakeEmotionalEngine()

    async def process_turn(self, text: str) -> TurnResult:
        return TurnResult(
            reply=f"Resposta para: {text}",
            decision=Decision(type=IntentType.DIALOGUE, confidence=0.8, raw_text=text),
        )


async def test_bridge_sends_thinking_expression_reply_and_idle() -> None:
    messages: list[dict] = []
    bridge = TabletBrainBridge(_FakeAgent())  # type: ignore[arg-type]

    async def send(message: dict) -> None:
        messages.append(message)

    await bridge.process_text(text="Olá robô", device_id="tablet_test", send=send)

    assert [message["type"] for message in messages] == [
        "set_state",
        "show_transcript",
        "set_expression",
        "show_message",
        "speak",
        "set_state",
    ]
    assert messages[4]["payload"]["text"] == messages[3]["payload"]["message"]
    assert messages[0]["payload"]["state"] == "THINKING"
    assert messages[2]["payload"]["expression"] == "happy"
    assert messages[3]["payload"]["message"] == "Resposta para: Olá robô"
    assert messages[5]["payload"]["state"] == "IDLE"


def test_question_maps_to_curious_expression() -> None:
    result = TurnResult(
        reply="Porque sim.",
        decision=Decision(type=IntentType.QUESTION, confidence=0.8),
    )
    assert expression_for_result(result, "calm") == "curious"


def test_outgoing_message_keeps_versioned_envelope() -> None:
    message = outgoing_message("set_state", "tablet_test", {"state": "IDLE"})
    assert message["version"] == 1
    assert message["device_id"] == "tablet_test"
    assert isinstance(message["timestamp"], int)
