"""Persists learned skills. Same shape as memory/people.py's
PeopleDirectory (a thin pydantic-model wrapper around a Repository) --
only the backend differs (Supabase in production, see app/main.py).
"""
from __future__ import annotations

from memory.repository import Repository
from skills.models import LearnedSkillRecord


class SkillLibrary:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def get_by_name(self, name: str) -> LearnedSkillRecord | None:
        matches = self.repository.query(lambda r: r.get("name") == name)
        return LearnedSkillRecord(**matches[0]) if matches else None

    def add(self, record: LearnedSkillRecord) -> str:
        return self.repository.add(record.model_dump_json_safe())

    def all(self) -> list[LearnedSkillRecord]:
        return [LearnedSkillRecord(**r) for r in self.repository.all()]

    def record_failure(self, name: str) -> None:
        """Increments failure_count for a skill that misbehaved at
        execution time. Unused by anything else in v1 -- a hook left in
        place for a future revise-on-failure loop, so that loop doesn't
        need a schema migration to work with."""
        record = self.get_by_name(name)
        if record is not None:
            self.repository.update(record.id, {"failure_count": record.failure_count + 1})
