"""Aggregates everything the response engine needs to produce a reply:
personality, emotion, active person, relevant memories, and recent dialogue.
Keeps that assembly logic out of agent.py and response_engine.py.
"""
from __future__ import annotations

from dataclasses import dataclass

from emotions.state import EmotionalState
from memory.long_term import LongTermMemory, MemoryRecord
from memory.people import PersonProfile
from memory.short_term import ShortTermMemory
from personality.personality import PersonalityTraits
from personality.style import StyleGuide, build_style_guide


@dataclass
class TurnContext:
    person: PersonProfile | None
    personality: PersonalityTraits
    emotion: EmotionalState
    style: StyleGuide
    recent_dialogue: str
    relevant_memories: list[MemoryRecord]


class ContextBuilder:
    def __init__(self, short_term: ShortTermMemory, long_term: LongTermMemory) -> None:
        self.short_term = short_term
        self.long_term = long_term

    def build(
        self,
        person: PersonProfile | None,
        personality: PersonalityTraits,
        emotion: EmotionalState,
    ) -> TurnContext:
        style = build_style_guide(personality, emotion, person)
        memories = self.long_term.for_person(person.id) if person else []
        # Most important, then most recent -- "relevant" should mean more
        # than just "last inserted"; a durable preference outranks small talk.
        ranked = sorted(memories, key=lambda m: (m.importance, m.created_at), reverse=True)
        return TurnContext(
            person=person,
            personality=personality,
            emotion=emotion,
            style=style,
            recent_dialogue=self.short_term.as_context_text(),
            relevant_memories=ranked[:4],
        )
