"""Working memory / conversation memory: the recent turns of dialogue.

Purely in-process, bounded, not persisted. Feeds context to the decision
engine and response engine for the current session.
"""
from __future__ import annotations

from collections import deque

from brain.models import Turn


class ShortTermMemory:
    def __init__(self, max_turns: int = 20) -> None:
        self._turns: deque[Turn] = deque(maxlen=max_turns)

    def add(self, turn: Turn) -> None:
        self._turns.append(turn)

    def recent(self, n: int | None = None) -> list[Turn]:
        turns = list(self._turns)
        return turns[-n:] if n else turns

    def as_context_text(self, n: int = 6) -> str:
        lines = [f"{t.speaker}: {t.text}" for t in self.recent(n)]
        return "\n".join(lines)

    def clear(self) -> None:
        self._turns.clear()
