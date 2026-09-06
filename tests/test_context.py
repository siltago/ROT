from __future__ import annotations

from brain.context import ContextBuilder
from emotions.state import EmotionalState
from memory.long_term import LongTermMemory, MemoryKind, MemoryRecord
from memory.repository import InMemoryRepository
from memory.short_term import ShortTermMemory
from personality.personality import PersonalityTraits


def test_relevant_memories_ranks_importance_over_insertion_order() -> None:
    long_term = LongTermMemory(InMemoryRepository())
    long_term.remember(MemoryRecord(kind=MemoryKind.EPISODIC, text="falou sobre o trabalho", person_id="joao", importance=0.35))
    long_term.remember(MemoryRecord(kind=MemoryKind.SEMANTIC, text="odeia barulho alto", person_id="joao", importance=0.8))

    builder = ContextBuilder(ShortTermMemory(), long_term)
    from memory.people import PersonProfile

    context = builder.build(PersonProfile(id="joao", name="João"), PersonalityTraits(), EmotionalState())

    assert context.relevant_memories[0].text == "odeia barulho alto"


def test_relevant_memories_empty_for_unknown_person() -> None:
    builder = ContextBuilder(ShortTermMemory(), LongTermMemory(InMemoryRepository()))
    context = builder.build(None, PersonalityTraits(), EmotionalState())
    assert context.relevant_memories == []
