"""Person profiles: per-person relationship data, distinct from long-term
memory records (which reference a person_id but live in LongTermMemory).
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from memory.repository import Repository


class PersonProfile(BaseModel):
    id: str
    name: str
    relationship: str = "unknown"  # e.g. "friend", "family", "guest", "unknown"
    familiarity: float = Field(default=0.1, ge=0.0, le=1.0)
    trust: float = Field(default=0.1, ge=0.0, le=1.0)
    preferences: dict[str, str] = Field(default_factory=dict)


class PeopleDirectory:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def get(self, person_id: str) -> PersonProfile | None:
        row = self.repository.get(person_id)
        return PersonProfile(**row) if row else None

    def get_or_create(self, person_id: str, name: str | None = None) -> PersonProfile:
        existing = self.get(person_id)
        if existing:
            return existing
        profile = PersonProfile(id=person_id, name=name or person_id)
        self.repository.add(profile.model_dump())
        return profile

    def upsert(self, profile: PersonProfile) -> None:
        if self.repository.get(profile.id):
            self.repository.update(profile.id, profile.model_dump())
        else:
            self.repository.add(profile.model_dump())

    def all(self) -> list[PersonProfile]:
        return [PersonProfile(**r) for r in self.repository.all()]
