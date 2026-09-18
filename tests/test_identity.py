"""IdentityStore: Bob's persistent self-identity -- starts from the
default self-concept, persists across stores sharing a repository (same
contract as NeedsStore), and self_notes accumulate/cap the same way
learned skills or needs would."""
from memory.identity import DEFAULT_FOCUS_AREAS, DEFAULT_WHO, IdentityState, IdentityStore
from memory.repository import InMemoryRepository


def _store() -> IdentityStore:
    return IdentityStore(InMemoryRepository())


def test_starts_from_the_default_identity():
    store = _store()
    assert store.state.who == DEFAULT_WHO
    assert store.state.focus_areas == list(DEFAULT_FOCUS_AREAS)
    assert store.state.self_notes == []


def test_add_self_note_appends_it():
    store = _store()
    store.add_self_note("gosta de tocar rock à noite")
    assert store.state.self_notes == ["gosta de tocar rock à noite"]


def test_add_self_note_ignores_blank_text():
    store = _store()
    store.add_self_note("   ")
    assert store.state.self_notes == []


def test_self_notes_cap_drops_the_oldest():
    store = _store()
    for i in range(40):
        store.add_self_note(f"nota {i}")
    assert len(store.state.self_notes) == 30
    assert store.state.self_notes[0] == "nota 10"
    assert store.state.self_notes[-1] == "nota 39"


def test_state_persists_across_stores_sharing_a_repository():
    repository = InMemoryRepository()
    first = IdentityStore(repository)
    first.add_self_note("percebeu que o dono gosta de café de manhã")
    first.save()

    second = IdentityStore(repository)
    assert second.state.self_notes == first.state.self_notes


def test_as_prompt_fragment_mentions_who_and_focus_areas():
    store = _store()
    fragment = store.as_prompt_fragment()
    assert DEFAULT_WHO in fragment
    for area in DEFAULT_FOCUS_AREAS:
        assert area in fragment


def test_as_prompt_fragment_mentions_self_notes_once_added():
    store = _store()
    store.add_self_note("aprendeu a reconhecer sarcasmo")
    assert "aprendeu a reconhecer sarcasmo" in store.as_prompt_fragment()


def test_as_prompt_fragment_omits_self_notes_section_when_empty():
    store = _store()
    assert "aprendeu sobre si mesmo" not in store.as_prompt_fragment()


def test_load_falls_back_to_default_when_repository_get_raises():
    class _BrokenRepository(InMemoryRepository):
        def get(self, record_id: str):
            raise RuntimeError("table missing")

    store = IdentityStore(_BrokenRepository())
    # Falls back to defaults (seed knowledge still applied in memory).
    assert store.state.who == IdentityState().who
    assert store.state.self_notes == []
