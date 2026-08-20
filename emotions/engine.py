"""Applies emotional events and time-decay to an EmotionalState.

All mutation of EmotionalState should go through this engine so decay,
clamping, and baseline-return behavior stay consistent.
"""
from __future__ import annotations

import time

from emotions.events import EVENT_DELTAS, EmotionEvent
from emotions.state import EmotionalState, EmotionalStateStore, _clamp

BASELINE = EmotionalState()

# Per-second pull back toward baseline for each field.
DECAY_RATE = 0.01


class EmotionalEngine:
    def __init__(self, store: EmotionalStateStore) -> None:
        self.store = store
        self._last_update = time.monotonic()

    @property
    def state(self) -> EmotionalState:
        return self.store.state

    def apply_event(self, event: EmotionEvent) -> EmotionalState:
        deltas = EVENT_DELTAS.get(event, {})
        current = self.store.state.model_dump()
        for field, delta in deltas.items():
            current[field] = _clamp(current[field] + delta)
        self.store.state = EmotionalState(**current)
        return self.store.state

    def decay(self, elapsed_seconds: float | None = None) -> EmotionalState:
        """Pull all fields gradually back toward their baseline values."""
        now = time.monotonic()
        elapsed = elapsed_seconds if elapsed_seconds is not None else (now - self._last_update)
        self._last_update = now
        if elapsed <= 0:
            return self.store.state

        pull = min(1.0, DECAY_RATE * elapsed)
        current = self.store.state.model_dump()
        baseline = BASELINE.model_dump()
        for field in current:
            current[field] = _clamp(current[field] + (baseline[field] - current[field]) * pull)
        self.store.state = EmotionalState(**current)
        return self.store.state

    def save(self) -> None:
        self.store.save()
