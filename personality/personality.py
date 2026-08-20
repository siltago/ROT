"""Stable, persistent personality traits -- not the moment-to-moment mood.

Personality changes rarely, if ever (maybe slow drift over long timescales
in the future). It is distinct from emotions.state.EmotionalState, which
fluctuates turn to turn.
"""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, v))


class PersonalityTraits(BaseModel):
    curiosity: float = Field(default=0.85, ge=0.0, le=1.0)
    humor: float = Field(default=0.70, ge=0.0, le=1.0)
    sarcasm: float = Field(default=0.20, ge=0.0, le=1.0)
    affection: float = Field(default=0.70, ge=0.0, le=1.0)
    initiative: float = Field(default=0.60, ge=0.0, le=1.0)
    verbosity: float = Field(default=0.40, ge=0.0, le=1.0)


class Personality:
    """Loads/persists a single PersonalityTraits profile for the robot."""

    def __init__(self, store_path: Path, traits: PersonalityTraits | None = None) -> None:
        self.store_path = store_path
        self.traits = traits or PersonalityTraits()

    @classmethod
    def load(cls, store_path: Path) -> "Personality":
        if store_path.exists():
            data = json.loads(store_path.read_text(encoding="utf-8"))
            return cls(store_path, PersonalityTraits(**data))
        return cls(store_path)

    def save(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self.store_path.write_text(
            self.traits.model_dump_json(indent=2), encoding="utf-8"
        )

    def adjust(self, **deltas: float) -> None:
        """Nudge traits by small deltas, clamped to [0, 1]. Used sparingly --
        personality should feel stable, not reactive like emotion."""
        current = self.traits.model_dump()
        for key, delta in deltas.items():
            if key in current:
                current[key] = _clamp(current[key] + delta)
        self.traits = PersonalityTraits(**current)
