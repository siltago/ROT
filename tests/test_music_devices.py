"""Where-to-play: Spotify device matching, the generic "which one?"
choice, and the full ask -> answer -> play flow through the agent."""
import pytest

from actions.executor import ActionExecutor
from actions.music import player as music_actions
from actions.permissions import PermissionPolicy, auto_deny
from actions.registry import ActionRegistry
from brain.agent import RobotAgent
from brain.choice import ChoiceOption, PendingChoice, resolve
from brain.context import ContextBuilder
from brain.decision_engine import DecisionEngine
from brain.planner import Planner
from brain.response_engine import ResponseEngine
from emotions.engine import EmotionalEngine
from emotions.state import EmotionalStateStore
from integrations.music.devices import SpotifyDevice, match_devices, normalize
from integrations.music.models import PlaybackState
from memory.identity import IdentityStore
from memory.long_term import LongTermMemory
from memory.people import PeopleDirectory
from memory.repository import InMemoryRepository, JsonFileRepository
from memory.short_term import ShortTermMemory
from personality.personality import Personality

PC = SpotifyDevice("id-pc", "DESKTOP-AB1", "Computer", is_active=True)
PHONE = SpotifyDevice("id-phone", "Galaxy S23", "Smartphone")
TABLET = SpotifyDevice("id-tab", "Tab S6", "Tablet")


# --- device matching ----------------------------------------------------

def test_normalize_strips_accents_and_punctuation():
    assert normalize("Televisão!") == "televisao"


def test_match_by_kind_alias():
    assert match_devices("toca no pc", [PC, PHONE]) == [PC]
    assert match_devices("no celular", [PC, PHONE]) == [PHONE]


def test_match_by_exact_name_beats_kind():
    twin = SpotifyDevice("id-pc2", "Notebook-Sala", "Computer")
    assert match_devices("no notebook-sala", [PC, twin]) == [twin]


def test_match_same_kind_returns_all():
    twin = SpotifyDevice("id-pc2", "Notebook-Sala", "Computer")
    assert set(match_devices("no computador", [PC, twin])) == {PC, twin}


def test_match_nothing():
    assert match_devices("na geladeira", [PC, PHONE]) == []


def test_aqui_means_the_tablet():
    assert match_devices("aqui mesmo", [PC, TABLET]) == [TABLET]


def test_label_puts_kind_first():
    assert PC.label == "computador DESKTOP-AB1"


# --- choice resolution --------------------------------------------------

def _choice():
    return PendingChoice(
        action="music.play", arguments={"query": "x"}, param="device",
        options=[
            ChoiceOption("computador DESKTOP-AB1", "DESKTOP-AB1", ("pc", "computador")),
            ChoiceOption("celular Galaxy S23", "Galaxy S23", ("celular",)),
        ],
        remember_key="music.device",
    )


def test_resolve_by_alias():
    answer = resolve(_choice(), "no celular")
    assert answer.kind == "picked" and answer.option.value == "Galaxy S23"


def test_resolve_by_ordinal():
    assert resolve(_choice(), "o segundo").option.value == "Galaxy S23"


def test_resolve_any_takes_first():
    assert resolve(_choice(), "tanto faz").option.value == "DESKTOP-AB1"


def test_resolve_cancel():
    assert resolve(_choice(), "deixa pra lá").kind == "cancelled"


def test_resolve_unrelated_is_no_match():
    assert resolve(_choice(), "que horas são").kind == "no_match"


def test_resolve_remember_flag():
    assert resolve(_choice(), "sempre no pc").remember is True
    assert resolve(_choice(), "no pc").remember is False


def test_from_outcome_data_needs_two_options():
    one = {"choice": {"param": "device", "options": [{"label": "a", "value": "a"}]}}
    assert PendingChoice.from_outcome_data("x", {}, one) is None


# --- music.play with devices -------------------------------------------

class _FakeSpotify:
    configured = True


class _FakeService:
    def __init__(self, devices, fail=False):
        self._devices, self.fail = devices, fail
        self.spotify = _FakeSpotify()
        self.played = []
        self.presenting = False

    async def devices(self, *, force=False):
        if self.fail:
            raise RuntimeError("429")
        return self._devices

    async def play(self, query, device_id=None):
        self.played.append((query, device_id))
        return PlaybackState("t1", "Song", "Artist", "Album", "", 0, 1000, True, 0)

    async def payload_for(self, track):
        return track.payload()


def _music_registry(service, identity=None):
    registry = ActionRegistry()
    music_actions.register(registry, service, identity)
    return registry


async def _play(registry, **kwargs):
    return await registry.get("music.play").handler(**kwargs)


@pytest.mark.asyncio
async def test_no_devices_lets_spotify_choose():
    service = _FakeService([])
    outcome = await _play(_music_registry(service), query="metallica")
    assert outcome.success and service.played == [("metallica", None)]


@pytest.mark.asyncio
async def test_single_device_plays_there():
    service = _FakeService([PHONE])
    await _play(_music_registry(service), query="metallica")
    assert service.played == [("metallica", "id-phone")]


@pytest.mark.asyncio
async def test_several_devices_asks_where():
    service = _FakeService([PC, PHONE])
    outcome = await _play(_music_registry(service), query="metallica")
    assert not outcome.success and outcome.message.endswith("?")
    assert service.played == []
    assert len(outcome.data["choice"]["options"]) == 2


@pytest.mark.asyncio
async def test_explicit_device_plays_without_asking():
    service = _FakeService([PC, PHONE])
    outcome = await _play(_music_registry(service), query="metallica", device="no celular")
    assert outcome.success and service.played == [("metallica", "id-phone")]


@pytest.mark.asyncio
async def test_unknown_device_explains_what_is_available():
    service = _FakeService([PC, PHONE])
    outcome = await _play(_music_registry(service), query="x", device="geladeira")
    assert not outcome.success and "DESKTOP-AB1" in outcome.message
    assert service.played == []


@pytest.mark.asyncio
async def test_remembered_preference_skips_the_question():
    identity = IdentityStore(InMemoryRepository())
    identity.state.preferences["music.device"] = "DESKTOP-AB1"
    service = _FakeService([PC, PHONE])
    outcome = await _play(_music_registry(service, identity), query="x")
    assert outcome.success and service.played == [("x", "id-pc")]


@pytest.mark.asyncio
async def test_device_list_failure_falls_back_to_old_behavior():
    service = _FakeService([PC, PHONE], fail=True)
    outcome = await _play(_music_registry(service), query="x")
    assert outcome.success and service.played == [("x", None)]


@pytest.mark.asyncio
async def test_set_default_device_stores_the_matched_name():
    identity = IdentityStore(InMemoryRepository())
    service = _FakeService([PC, PHONE])
    registry = _music_registry(service, identity)
    outcome = await registry.get("music.default_device").handler(device="pc")
    assert outcome.success
    assert identity.state.preferences["music.device"] == "DESKTOP-AB1"
    await registry.get("music.default_device").handler(device="perguntar")
    assert "music.device" not in identity.state.preferences


@pytest.mark.asyncio
async def test_trailing_device_in_the_query_is_split_off():
    service = _FakeService([PC, PHONE])
    await _play(_music_registry(service), query="Metallica no celular")
    assert service.played == [("Metallica", "id-phone")]


@pytest.mark.asyncio
async def test_query_ending_in_a_non_device_is_left_alone():
    service = _FakeService([PC])
    await _play(_music_registry(service), query="Fim de semana no parque")
    assert service.played == [("Fim de semana no parque", "id-pc")]


# --- full flow through the agent ---------------------------------------

def _agent(tmp_path, service, identity):
    registry = ActionRegistry()
    music_actions.register(registry, service, identity)
    short_term = ShortTermMemory()
    long_term = LongTermMemory(JsonFileRepository(tmp_path / "m.json"))
    return RobotAgent(
        decision_engine=DecisionEngine(),
        planner=Planner(registry),
        executor=ActionExecutor(registry, PermissionPolicy(confirmation_provider=auto_deny)),
        context_builder=ContextBuilder(short_term, long_term),
        response_engine=ResponseEngine(),
        personality=Personality(tmp_path / "p.json"),
        emotional_engine=EmotionalEngine(EmotionalStateStore(tmp_path / "e.json")),
        identity_store=identity,
        people=PeopleDirectory(JsonFileRepository(tmp_path / "pp.json")),
        long_term=long_term,
        short_term=short_term,
        event_sink=lambda event: None,
    )


@pytest.mark.asyncio
async def test_agent_asks_then_plays_on_the_chosen_device(tmp_path):
    service = _FakeService([PC, PHONE])
    agent = _agent(tmp_path, service, IdentityStore(InMemoryRepository()))

    asked = await agent.process_turn("Toca música Metallica")
    assert "Onde você quer ouvir" in asked.reply
    assert agent.choice_state.active and service.played == []

    answered = await agent.process_turn("no celular")
    assert service.played == [("Metallica", "id-phone")]
    assert answered.action_records[0].outcome.success
    assert not agent.choice_state.active


@pytest.mark.asyncio
async def test_agent_remembers_when_told_sempre(tmp_path):
    identity = IdentityStore(InMemoryRepository())
    service = _FakeService([PC, PHONE])
    agent = _agent(tmp_path, service, identity)
    await agent.process_turn("Toca música Metallica")
    await agent.process_turn("sempre no pc")
    assert identity.state.preferences["music.device"] == "DESKTOP-AB1"
    await agent.process_turn("Toca música Queen")
    assert service.played[-1] == ("Queen", "id-pc")  # no question this time


@pytest.mark.asyncio
async def test_agent_unrelated_reply_drops_the_question(tmp_path):
    service = _FakeService([PC, PHONE])
    agent = _agent(tmp_path, service, IdentityStore(InMemoryRepository()))
    await agent.process_turn("Toca música Metallica")
    await agent.process_turn("Está muito quente aqui.")
    assert not agent.choice_state.active and service.played == []


@pytest.mark.asyncio
async def test_agent_cancel_drops_the_question(tmp_path):
    service = _FakeService([PC, PHONE])
    agent = _agent(tmp_path, service, IdentityStore(InMemoryRepository()))
    await agent.process_turn("Toca música Metallica")
    result = await agent.process_turn("deixa pra lá")
    assert "deixei quieto" in result.reply and service.played == []


@pytest.mark.asyncio
async def test_asking_where_does_not_add_llm_chatter(tmp_path):
    class _ChattyLLM:
        async def generate(self, *, system, user, history=""):
            return "Colocando pra tocar!"

    service = _FakeService([PC, PHONE])
    agent = _agent(tmp_path, service, IdentityStore(InMemoryRepository()))
    agent.response_engine = ResponseEngine(llm_provider=_ChattyLLM())
    result = await agent.process_turn("Toca música Metallica")
    assert "Onde você quer ouvir" in result.reply
    assert "Colocando" not in result.reply
