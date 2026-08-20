"""Episodic + semantic long-term memory, backed by a Repository.

Not every utterance becomes a memory. `MemoryCandidate` production happens
in the decision engine; this module only decides whether a candidate is
worth persisting and stores it.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from brain.models import utcnow
from memory.repository import Repository


class MemoryKind(str, Enum):
    EPISODIC = "episodic"   # "we talked about X on Tuesday"
    SEMANTIC = "semantic"   # "prefers dim environments" (durable fact/preference)


class MemoryRecord(BaseModel):
    id: str = ""
    kind: MemoryKind
    text: str
    person_id: str | None = None
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    created_at: str = Field(default_factory=lambda: utcnow().isoformat())


MIN_IMPORTANCE_TO_STORE = 0.3


class LongTermMemory:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def remember(self, record: MemoryRecord) -> str | None:
        """Store a memory candidate if it clears the importance bar."""
        if record.importance < MIN_IMPORTANCE_TO_STORE:
            return None
        return self.repository.add(record.model_dump())

    def for_person(self, person_id: str) -> list[MemoryRecord]:
        rows = self.repository.query(lambda r: r.get("person_id") == person_id)
        return [MemoryRecord(**r) for r in rows]

    def search(self, keyword: str) -> list[MemoryRecord]:
        keyword_lower = keyword.lower()
        rows = self.repository.query(lambda r: keyword_lower in r.get("text", "").lower())
        return [MemoryRecord(**r) for r in rows]

    def all(self) -> list[MemoryRecord]:
        return [MemoryRecord(**r) for r in self.repository.all()]


def score_candidate(text: str) -> float:
    """Very simple heuristic importance scorer for a memory candidate.

    A first pass, deterministic and local (no LLM call needed) -- keeps
    latency low for the common case. Preference/opinion language scores
    higher than incidental chatter.
    """
    text_lower = text.lower()
    preference_markers = [
        "gosto", "prefiro", "não gosto", "odeio", "adoro", "sempre",
        "nunca", "costumo", "like", "prefer", "hate", "love", "always", "never",
    ]
    if any(marker in text_lower for marker in preference_markers):
        return 0.7
    if len(text_lower.split()) <= 3:
        return 0.1
    return 0.35
