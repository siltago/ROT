"""Storage abstraction for memory.

Concrete stores (JSON files today; SQLite/Postgres/vector DB later) implement
this interface. Nothing outside memory/ should know how records are
persisted.
"""
from __future__ import annotations

import json
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Iterable


class Repository(ABC):
    @abstractmethod
    def add(self, record: dict[str, Any]) -> str:
        """Persist a record, return its id."""

    @abstractmethod
    def get(self, record_id: str) -> dict[str, Any] | None:
        ...

    @abstractmethod
    def all(self) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def query(self, predicate) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def update(self, record_id: str, updates: dict[str, Any]) -> None:
        ...

    @abstractmethod
    def delete(self, record_id: str) -> None:
        ...


class JsonFileRepository(Repository):
    """Simple JSON-file-backed repository. One file = one list of records.

    Adequate for a first version; swap for SQLite/Postgres/vector DB later
    by implementing the same Repository interface.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    def _read(self) -> list[dict[str, Any]]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, records: list[dict[str, Any]]) -> None:
        self.path.write_text(json.dumps(records, indent=2, default=str), encoding="utf-8")

    def add(self, record: dict[str, Any]) -> str:
        records = self._read()
        record_id = record.get("id") or str(uuid.uuid4())
        record["id"] = record_id
        records.append(record)
        self._write(records)
        return record_id

    def get(self, record_id: str) -> dict[str, Any] | None:
        for r in self._read():
            if r.get("id") == record_id:
                return r
        return None

    def all(self) -> list[dict[str, Any]]:
        return self._read()

    def query(self, predicate) -> list[dict[str, Any]]:
        return [r for r in self._read() if predicate(r)]

    def update(self, record_id: str, updates: dict[str, Any]) -> None:
        records = self._read()
        for r in records:
            if r.get("id") == record_id:
                r.update(updates)
        self._write(records)

    def delete(self, record_id: str) -> None:
        records = [r for r in self._read() if r.get("id") != record_id]
        self._write(records)
