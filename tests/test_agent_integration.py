import pytest

from actions.executor import ActionExecutor
from actions.permissions import PermissionPolicy, auto_deny
from actions.registry import ActionRegistry
from actions.robot import movement as robot_actions
from actions.smart_home import lights as light_actions
from actions.smart_home import security as security_actions
from brain.agent import RobotAgent
from brain.context import ContextBuilder
from brain.decision_engine import DecisionEngine
from brain.models import IntentType
from brain.planner import Planner
from brain.response_engine import ResponseEngine
from emotions.engine import EmotionalEngine
from emotions.state import EmotionalStateStore
from hardware.simulator import SimulatorHardware
from memory.long_term import LongTermMemory
from memory.people import PeopleDirectory
from memory.repository import JsonFileRepository
from memory.short_term import ShortTermMemory
from personality.personality import Personality


def _build_agent(tmp_path):
    hardware = SimulatorHardware(verbose=False)
    registry = ActionRegistry()
    light_actions.register(registry)
    security_actions.register(registry)
    robot_actions.register(registry, hardware)

    executor = ActionExecutor(registry, PermissionPolicy(confirmation_provider=auto_deny))
    planner = Planner(registry)
    people = PeopleDirectory(JsonFileRepository(tmp_path / "people.json"))
    long_term = LongTermMemory(JsonFileRepository(tmp_path / "memories.json"))
    short_term = ShortTermMemory()
    context_builder = ContextBuilder(short_term, long_term)
    personality = Personality(tmp_path / "personality.json")
    emotional_engine = EmotionalEngine(EmotionalStateStore(tmp_path / "emotion.json"))

    return RobotAgent(
        decision_engine=DecisionEngine(),
        planner=planner,
        executor=executor,
        context_builder=context_builder,
        response_engine=ResponseEngine(),
        personality=personality,
        emotional_engine=emotional_engine,
        people=people,
        long_term=long_term,
        short_term=short_term,
        event_sink=lambda event: None,
    ), hardware


@pytest.mark.asyncio
async def test_action_command_executes_and_replies(tmp_path):
    agent, _ = _build_agent(tmp_path)

    result = await agent.process_turn("Liga a luz da sala.", person_id="person_001")

    assert result.decision.type == IntentType.ACTION
    assert len(result.action_records) == 1
    assert result.action_records[0].outcome.success is True
    assert "sala" in result.reply


@pytest.mark.asyncio
async def test_pure_dialogue_produces_no_action_records(tmp_path):
    agent, _ = _build_agent(tmp_path)

    result = await agent.process_turn("Está muito quente aqui.", person_id="person_001")

    assert result.decision.type == IntentType.DIALOGUE
    assert result.action_records == []
    assert result.reply


@pytest.mark.asyncio
async def test_preference_statement_is_persisted_to_long_term_memory(tmp_path):
    agent, _ = _build_agent(tmp_path)

    await agent.process_turn("Gosto mais quando a sala fica escura.", person_id="person_001")

    memories = agent.long_term.for_person("person_001")
    assert any("escura" in m.text for m in memories)


@pytest.mark.asyncio
async def test_high_risk_action_without_confirmation_channel_is_denied(tmp_path):
    agent, _ = _build_agent(tmp_path)

    result = await agent.process_turn("Destrava a porta principal.", person_id="person_001")

    assert result.action_records[0].outcome.success is False
    assert result.action_records[0].required_confirmation is True
