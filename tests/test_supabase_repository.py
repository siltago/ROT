from unittest.mock import MagicMock

from memory.supabase_repository import SupabaseRepository


def _client_returning(data):
    client = MagicMock()
    client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = data
    client.table.return_value.select.return_value.execute.return_value.data = data
    return client


def test_add_inserts_a_row_with_id_and_name_extracted() -> None:
    client = MagicMock()
    repo = SupabaseRepository(client, table_name="learned_skills")

    record_id = repo.add({"id": "abc", "name": "utility.timer", "description": "d"})

    assert record_id == "abc"
    client.table.assert_called_with("learned_skills")
    inserted = client.table.return_value.insert.call_args[0][0]
    assert inserted["id"] == "abc"
    assert inserted["name"] == "utility.timer"
    assert inserted["data"] == {"id": "abc", "name": "utility.timer", "description": "d"}


def test_get_returns_the_stored_data_blob() -> None:
    client = _client_returning([{"data": {"id": "abc", "name": "utility.timer"}}])
    repo = SupabaseRepository(client, table_name="learned_skills")

    result = repo.get("abc")

    assert result == {"id": "abc", "name": "utility.timer"}


def test_get_returns_none_when_no_row_matches() -> None:
    client = _client_returning([])
    repo = SupabaseRepository(client, table_name="learned_skills")

    assert repo.get("missing") is None


def test_all_and_query_unwrap_every_row() -> None:
    rows = [{"data": {"id": "a", "name": "x"}}, {"data": {"id": "b", "name": "y"}}]
    client = _client_returning(rows)
    repo = SupabaseRepository(client, table_name="learned_skills")

    assert repo.all() == [{"id": "a", "name": "x"}, {"id": "b", "name": "y"}]
    assert repo.query(lambda r: r["name"] == "y") == [{"id": "b", "name": "y"}]


def test_delete_calls_eq_with_the_record_id() -> None:
    client = MagicMock()
    repo = SupabaseRepository(client, table_name="learned_skills")

    repo.delete("abc")

    client.table.return_value.delete.return_value.eq.assert_called_with("id", "abc")
