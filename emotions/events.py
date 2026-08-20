"""Named emotional events and the deltas they apply to EmotionalState.

Keeping this table explicit (instead of ad-hoc adjustments scattered around
the codebase) makes emotional behavior auditable and easy to tune.
"""
from __future__ import annotations

from enum import Enum


class EmotionEvent(str, Enum):
    COMPLIMENT_RECEIVED = "compliment_received"
    INTERESTING_INTERACTION = "interesting_interaction"
    REPEATED_INTERRUPTION = "repeated_interruption"
    LONG_IDLE = "long_idle"
    SUCCESSFUL_ACTION = "successful_action"
    FAILED_ACTION = "failed_action"
    RUDE_INPUT = "rude_input"
    NEW_PERSON_MET = "new_person_met"


# Deltas applied to (valence, energy, irritation, curiosity) on each event.
EVENT_DELTAS: dict[EmotionEvent, dict[str, float]] = {
    EmotionEvent.COMPLIMENT_RECEIVED: {"valence": 0.08, "irritation": -0.03},
    EmotionEvent.INTERESTING_INTERACTION: {"curiosity": 0.10, "valence": 0.03},
    EmotionEvent.REPEATED_INTERRUPTION: {"irritation": 0.06},
    EmotionEvent.LONG_IDLE: {"energy": -0.05},
    EmotionEvent.SUCCESSFUL_ACTION: {"valence": 0.03},
    EmotionEvent.FAILED_ACTION: {"valence": -0.04, "irritation": 0.03},
    EmotionEvent.RUDE_INPUT: {"irritation": 0.10, "valence": -0.05},
    EmotionEvent.NEW_PERSON_MET: {"curiosity": 0.05},
}
