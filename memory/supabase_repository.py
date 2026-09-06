"""Supabase-backed Repository implementation.

Same `Repository` contract as `JsonFileRepository` (memory/repository.py) --
callers (e.g. `skills/store.py`'s `SkillLibrary`) don't know or care which
backend they're pointed at. Each record is stored as one row: `id` (text,
primary key), `name` (text, used for fast lookups when the record has one --
e.g. a learned skill's action name), and `data` (jsonb, the full record dict,
mirroring exactly what `JsonFileRepository` would have written to its JSON
array). `query()` fetches everything and filters in Python, same as
`JsonFileRepository.query` does -- the dataset this is used for (learned
skills) is small, so there's no need to translate Python predicates into
Postgres filters.
"""
from __future__ import annotations

import uuid
from typing import Any

from memory.repository import Repository


class SupabaseRepository(Repository):
    def __init__(self, client: Any, table_name: str) -> None:
        self.client = client
        self.table_name = table_name

    def _table(self):
        return self.client.table(self.table_name)

    def add(self, record: dict[str, Any]) -> str:
        record_id = str(record.get("id") or uuid.uuid4())
        record["id"] = record_id
        row: dict[str, Any] = {"id": record_id, "data": record}
        if "name" in record:
            row["name"] = record["name"]
        self._table().insert(row).execute()
        return record_id

    def get(self, record_id: str) -> dict[str, Any] | None:
        response = self._table().select("data").eq("id", record_id).limit(1).execute()
        rows = response.data or []
        return rows[0]["data"] if rows else None

    def all(self) -> list[dict[str, Any]]:
        response = self._table().select("data").execute()
        return [row["data"] for row in (response.data or [])]

    def query(self, predicate) -> list[dict[str, Any]]:
        return [record for record in self.all() if predicate(record)]

    def update(self, record_id: str, updates: dict[str, Any]) -> None:
        current = self.get(record_id)
        if current is None:
            return
        current.update(updates)
        row: dict[str, Any] = {"data": current}
        if "name" in current:
            row["name"] = current["name"]
        self._table().update(row).eq("id", record_id).execute()

    def delete(self, record_id: str) -> None:
        self._table().delete().eq("id", record_id).execute()
