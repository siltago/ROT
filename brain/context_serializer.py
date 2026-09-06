"""Minimal allow-listed context sent when a proposal actually needs an LLM."""
from typing import Any

from brain.behaviors import BehaviorContext
from brain.events import RobotEvent


class ContextSerializer:
    def serialize(self, event: RobotEvent, context: BehaviorContext) -> dict[str, Any]:
        personality = context.personality
        emotion = context.emotional_state
        return {
            "event": event.type.value,
            "relationship": "known" if context.world_state.current_person_id not in (None, "unknown") else "unknown",
            "personality": {
                "humor": getattr(personality, "humor", None),
                "verbosity": getattr(personality, "verbosity", None),
            },
            "emotion": {"energy": getattr(emotion, "energy", None)},
        }
