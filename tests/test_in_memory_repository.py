from memory.repository import InMemoryRepository


def test_in_memory_repository_crud_without_disk() -> None:
    repository = InMemoryRepository()
    record_id = repository.add({"name": "Thiago"})
    assert repository.get(record_id) == {"id": record_id, "name": "Thiago"}
    repository.update(record_id, {"name": "T"})
    assert repository.query(lambda row: row["name"] == "T")
    repository.delete(record_id)
    assert repository.get(record_id) is None
