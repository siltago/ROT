"""Emotional state: fluctuates turn to turn, decays toward baseline over time.

Distinct from personality (stable traits). Never allowed to gate or block
correct execution of validated commands -- see actions/executor.py, which
never consults EmotionalState before executing.
"""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


class EmotionalState(BaseModel):
    valence: float = Field(default=0.5, ge=0.0, le=1.0)   # negative..positive mood
    energy: float = Field(default=0.6, ge=0.0, le=1.0)    # tired..alert
    irritation: float = Field(default=0.05, ge=0.0, le=1.0)
    curiosity: float = Field(default=0.6, ge=0.0, le=1.0)

    def mood_label(self) -> str:
        """A coarse human-readable label, useful for logging/response style."""
        if self.irritation > 0.6:
            return "irritated"
        if self.valence > 0.7 and self.energy > 0.5:
            return "cheerful"
        if self.curiosity > 0.75:
            return "curious"
        if self.energy < 0.25:
            return "tired"
        if self.valence < 0.3:
            return "down"
        return "calm"


class EmotionalStateStore:
    """Persists EmotionalState to disk between runs."""

    def __init__(self, store_path: Path, state: EmotionalState | None = None) -> None:
        self.store_path = store_path
        self.state = state or EmotionalState()

    @classmethod
    def load(cls, store_path: Path) -> "EmotionalStateStore":
        if store_path.exists():
            data = json.loads(store_path.read_text(encoding="utf-8"))
            return cls(store_path, EmotionalState(**data))
        return cls(store_path)

    def save(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self.store_path.write_text(self.state.model_dump_json(indent=2), encoding="utf-8")
