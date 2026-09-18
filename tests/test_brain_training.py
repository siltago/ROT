"""Training/learning surface: seeded + taught knowledge, voice-trained
personality nudges, device-control actions, and self-reflection."""
import asyncio

from actions.registry import ActionRegistry
from actions.robot import device as device_actions
from actions.robot import learning as learning_actions
from brain.reflection import SelfReflector
from integrations.llm.base import LLMProvider
from memory.identity import IdentityStore
from memory.repository import InMemoryRepository
from personality.personality import Personality
from personality.seed_knowledge import SEED_KNOWLEDGE, SEED_VERSION


def _identity() -> IdentityStore:
    return IdentityStore(InMemoryRepository())


def _run(coro):
    return asyncio.run(coro)


# --- knowledge / seed ---------------------------------------------------

def test_seed_knowledge_is_injected_on_first_boot():
    store = _identity()
    topics = {entry.topic for entry in store.state.knowledge}
    assert {topic for topic, _ in SEED_KNOWLEDGE} <= topics
    assert store.state.seed_version == SEED_VERSION


def test_seed_is_not_reapplied_or_overwritten_on_next_boot():
    repository = InMemoryRepository()
    first = IdentityStore(repository)
    first.add_knowledge("sarcasmo", "versão ensinada pelo dono")
    first.save()
    second = IdentityStore(repository)
    entries = [e for e in second.state.knowledge if e.topic == "sarcasmo"]
    assert len(entries) == 1
    assert entries[0].text == "versão ensinada pelo dono"


def test_add_knowledge_with_same_topic_replaces_it():
    store = _identity()
    store.add_knowledge("gírias", "use pouco")
    store.add_knowledge("Gírias", "use mais")
    matches = [e for e in store.state.knowledge if e.topic.casefold() == "gírias"]
    assert [m.text for m in matches] == ["use mais"]


def test_knowledge_reaches_the_prompt_fragment():
    store = _identity()
    store.add_knowledge("café", "o dono toma café às 7h")
    assert "café: o dono toma café às 7h" in store.as_prompt_fragment()


def test_knowledge_is_capped():
    store = _identity()
    for i in range(100):
        store.add_knowledge(f"t{i}", "x")
    assert len(store.state.knowledge) == 40


# --- voice training -----------------------------------------------------

def _learning():
    registry = ActionRegistry()
    identity = _identity()
    personality = Personality(store_path=__import__("pathlib").Path("nonexistent_test_personality.json"))
    personality.save = lambda: None  # don't touch disk in tests
    learning_actions.register(registry, identity, personality)
    return registry, identity, personality


def test_identity_learn_stores_knowledge():
    registry, identity, _ = _learning()
    outcome = _run(registry.get("identity.learn").handler(topic="apelido", text="me chamam de Bobão"))
    assert outcome.success
    assert any(e.topic == "apelido" for e in identity.state.knowledge)


def test_personality_adjust_more_sarcasm_raises_it():
    registry, identity, personality = _learning()
    before = personality.traits.sarcasm
    outcome = _run(registry.get("personality.adjust").handler(trait="sarcasmo", direction="mais"))
    assert outcome.success
    assert personality.traits.sarcasm > before
    assert any("sarcasmo" in e.topic for e in identity.state.knowledge)


def test_personality_adjust_less_lowers_and_clamps():
    registry, _, personality = _learning()
    for _ in range(30):
        _run(registry.get("personality.adjust").handler(trait="humor", direction="menos"))
    assert personality.traits.humor == 0.0


def test_personality_adjust_rejects_unknown_trait():
    registry, _, _ = _learning()
    outcome = _run(registry.get("personality.adjust").handler(trait="altura", direction="mais"))
    assert not outcome.success


# --- device control -----------------------------------------------------

def _device_registry():
    registry = ActionRegistry()
    device_actions.register(registry)
    return registry


def test_set_volume_returns_control_payload():
    outcome = _run(_device_registry().get("device.set_volume").handler(level=40))
    assert outcome.success
    assert outcome.data == {"control": "volume", "mode": "set", "value": 40}


def test_set_brightness_rejects_out_of_range():
    outcome = _run(_device_registry().get("device.set_brightness").handler(level=150))
    assert not outcome.success


def test_change_volume_down_is_a_negative_step():
    outcome = _run(_device_registry().get("device.change_volume").handler(direction="down"))
    assert outcome.data["mode"] == "step"
    assert outcome.data["value"] < 0


def test_change_brightness_rejects_unknown_direction():
    outcome = _run(_device_registry().get("device.change_brightness").handler(direction="sideways"))
    assert not outcome.success


# --- self reflection ----------------------------------------------------

class _FakeLLM(LLMProvider):
    def __init__(self, answer: str) -> None:
        self.answer = answer

    async def generate(self, *, system: str, user: str, history: str = "") -> str:
        return self.answer


def test_reflection_stores_a_short_note():
    identity = _identity()
    reflector = SelfReflector(_FakeLLM("  Devo ser mais direto com o dono.  "), identity)
    note = _run(reflector.reflect("user: oi\nrobot: olá"))
    assert note == "Devo ser mais direto com o dono."
    assert identity.state.self_notes == [note]


def test_reflection_nada_stores_nothing():
    identity = _identity()
    reflector = SelfReflector(_FakeLLM("NADA"), identity)
    assert _run(reflector.reflect("user: oi")) is None
    assert identity.state.self_notes == []


def test_reflection_survives_llm_failure():
    class _Broken(LLMProvider):
        async def generate(self, *, system, user, history=""):
            raise RuntimeError("boom")

    reflector = SelfReflector(_Broken(), _identity())
    assert _run(reflector.reflect("user: oi")) is None


def test_reflection_truncates_long_notes():
    identity = _identity()
    reflector = SelfReflector(_FakeLLM("a" * 500), identity)
    note = _run(reflector.reflect("user: oi"))
    assert len(note) == 180


def test_note_turn_only_reflects_every_nth_turn():
    async def scenario():
        identity = _identity()
        reflector = SelfReflector(_FakeLLM("lição"), identity, every_n_turns=3)
        reflector.note_turn("d")
        reflector.note_turn("d")
        await asyncio.sleep(0)
        assert identity.state.self_notes == []
        reflector.note_turn("d")
        await asyncio.sleep(0.05)
        return identity.state.self_notes

    assert _run(scenario()) == ["lição"]


def test_device_status_reads_the_reported_state():
    registry = ActionRegistry()
    status = device_actions.DeviceStatusSource()
    device_actions.register(registry, status)
    handler = registry.get("device.status").handler
    assert not _run(handler()).success  # nothing reported yet
    status.state = {"volume": 40, "brightness": 70}
    outcome = _run(handler())
    assert outcome.success
    assert "40%" in outcome.message and "70%" in outcome.message
