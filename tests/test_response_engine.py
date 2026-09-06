from __future__ import annotations

from brain.context import TurnContext
import pytest

from brain.models import ActionOutcome, ActionRecord, Decision, IntentType
from brain.response_engine import ResponseEngine, _build_system_prompt
from emotions.state import EmotionalState
from memory.long_term import MemoryKind, MemoryRecord
from memory.people import PersonProfile
from personality.personality import PersonalityTraits
from personality.style import StyleGuide


def _style() -> StyleGuide:
    return StyleGuide(tone="neutral", warmth="friendly", playfulness="mostly straightforward", verbosity="concise", notes=[])


def _context(*, person: PersonProfile | None = None, memories: list[MemoryRecord] | None = None) -> TurnContext:
    return TurnContext(
        person=person,
        personality=PersonalityTraits(),
        emotion=EmotionalState(),
        style=_style(),
        recent_dialogue="",
        relevant_memories=memories or [],
    )


def test_prompt_mentions_known_memories_when_present() -> None:
    memories = [MemoryRecord(kind=MemoryKind.SEMANTIC, text="prefere luz baixa à noite", person_id="joao", importance=0.7)]
    prompt = _build_system_prompt(_context(person=PersonProfile(id="joao", name="João"), memories=memories))
    assert "prefere luz baixa à noite" in prompt


def test_prompt_omits_memory_line_when_none_known() -> None:
    prompt = _build_system_prompt(_context(person=PersonProfile(id="joao", name="João")))
    assert "O que você lembra" not in prompt


def test_prompt_asks_for_a_direct_answer_to_questions() -> None:
    prompt = _build_system_prompt(_context())
    assert "pergunta direta" in prompt


def test_prompt_contains_bob_identity_and_anti_assistant_rules() -> None:
    prompt = _build_system_prompt(_context())
    assert "Você é Bob" in prompt
    assert "não seja servil" in prompt
    assert "não transforme toda resposta em pergunta" in prompt


@pytest.mark.asyncio
async def test_local_fallback_sounds_like_bob() -> None:
    engine = ResponseEngine()
    greeting = await engine.generate(Decision(type=IntentType.DIALOGUE, confidence=0.8, raw_text="oi"), _context(), [])
    question = await engine.generate(Decision(type=IntentType.QUESTION, confidence=0.8, raw_text="por quê?"), _context(), [])
    assert greeting == "Oi. Eu tava te ouvindo."
    assert question == "Essa eu ainda não sei responder direito. Prefiro admitir a inventar."


@pytest.mark.asyncio
async def test_generic_action_success_uses_bob_voice_without_fake_detail() -> None:
    engine = ResponseEngine()
    record = ActionRecord(id="action-1", name="test.action", arguments={}, outcome=ActionOutcome(success=True, message="Pronto."))
    reply = await engine.generate(Decision(type=IntentType.ACTION, confidence=0.9, raw_text="faz isso"), _context(), [record])
    assert reply == "Pode deixar, já foi."
