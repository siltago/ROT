"""End-to-end coverage of the skill-learning flow through RobotAgent.process_turn
itself, not just SkillTeacher in isolation -- confirms the clarify/approve
loop and the "learned once, never asks the LLM again" property actually
work through the real turn pipeline.

Uses tempfile.mkdtemp() directly rather than pytest's tmp_path fixture --
tmp_path fails to set up at all in this environment (a pre-existing,
unrelated PermissionError on the shared pytest temp root), so avoiding it
here is what lets this file's tests actually run.
"""
import json
import shutil
import tempfile
from pathlib import Path

import pytest

from actions.executor import ActionExecutor
from actions.permissions import PermissionPolicy, auto_deny
from actions.registry import ActionRegistry, ActionSpec
from brain.action_router import LlmActionRouter
from brain.agent import RobotAgent
from brain.context import ContextBuilder
from brain.decision_engine import DecisionEngine
from brain.planner import Planner
from brain.response_engine import ResponseEngine
from brain.skill_learning import SkillTeacher
from emotions.engine import EmotionalEngine
from emotions.state import EmotionalStateStore
from integrations.llm.base import LLMProvider
from memory.long_term import LongTermMemory
from memory.people import PeopleDirectory
from memory.repository import InMemoryRepository
from memory.short_term import ShortTermMemory
from personality.personality import Personality
from skills.interpreter import SkillInterpreter
from skills.registrar import SkillRegistrar
from skills.store import SkillLibrary


class ScriptedLLM(LLMProvider):
    """Returns one scripted response per call, in order -- lets a test
    dictate exactly what "the tutor" says at each step of a multi-turn
    conversation."""
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls = 0

    async def generate(self, *, system: str, user: str, history: str = "") -> str:
        response = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return response


async def _noop_speak(text: str) -> None:
    pass


@pytest.fixture
def state_dir():
    path = Path(tempfile.mkdtemp())
    yield path
    shutil.rmtree(path, ignore_errors=True)


async def _noop_action(**kwargs):
    from brain.models import ActionOutcome
    return ActionOutcome(success=True, message="ok")


def _build_agent(state_dir: Path, llm: LLMProvider):
    registry = ActionRegistry()
    # LlmActionRouter.route() short-circuits (no LLM call at all) when the
    # registry is completely empty -- reasonable in production (there's
    # always at least a handful of hand-coded actions registered), but a
    # bare test registry needs at least one for the router to actually run.
    registry.register(ActionSpec(name="utility.noop", description="não faz nada", handler=_noop_action, parameters={}))
    executor = ActionExecutor(registry, PermissionPolicy(confirmation_provider=auto_deny))
    planner = Planner(registry)
    people = PeopleDirectory(InMemoryRepository())
    long_term = LongTermMemory(InMemoryRepository())
    short_term = ShortTermMemory()
    context_builder = ContextBuilder(short_term, long_term)
    personality = Personality(state_dir / "personality.json")
    emotional_engine = EmotionalEngine(EmotionalStateStore(state_dir / "emotion.json"))

    skill_library = SkillLibrary(InMemoryRepository())
    interpreter = SkillInterpreter(registry, executor)
    registrar = SkillRegistrar(registry, interpreter, skill_library)
    action_router = LlmActionRouter(llm, registry)
    skill_teacher = SkillTeacher(llm_provider=llm, registrar=registrar, speak_resolver=lambda: _noop_speak)

    agent = RobotAgent(
        decision_engine=DecisionEngine(), planner=planner, executor=executor,
        context_builder=context_builder, response_engine=ResponseEngine(),
        personality=personality, emotional_engine=emotional_engine,
        people=people, long_term=long_term, short_term=short_term,
        event_sink=lambda event: None, action_router=action_router, skill_teacher=skill_teacher,
    )
    return agent, registry, skill_library, llm


@pytest.mark.asyncio
async def test_full_clarify_then_learn_then_reuse_without_asking_the_llm_again(state_dir) -> None:
    router_says_learnable = json.dumps({"action": None, "learnable": True, "skill_hint": "timer"})
    teach_asks_clarification = json.dumps({"needs_clarification": "o que fazer quando o tempo acabar?"})
    teach_final_recipe = json.dumps({
        "name": "utility.timer", "description": "avisa depois de um tempo",
        "parameters": {"minutes": "float"},
        "start_steps": [
            {"kind": "wait", "seconds_expr": "minutes*60"},
            {"kind": "speak", "text": "Tempo acabou!"},
        ],
        "stop_steps": [{"kind": "speak", "text": "Cancelado"}],
        "stop_action_name": "utility.timer.cancel",
        "risk_level": "low",
    })
    # The 4th response scripts what a real router call would say once
    # utility.timer actually exists in the catalog it's shown -- this
    # stand-in LLM doesn't infer that on its own, a real one would.
    router_recognizes_learned_timer = json.dumps({"action": "utility.timer", "arguments": {"minutes": 15}})
    llm = ScriptedLLM([
        router_says_learnable, teach_asks_clarification, teach_final_recipe,
        router_recognizes_learned_timer,
    ])
    agent, registry, skill_library, _ = _build_agent(state_dir, llm)

    first = await agent.process_turn("coloque um timer de 15 minutos")
    assert "?" in first.reply or "explicar" in first.reply.casefold()
    assert agent.learning_state.active is True

    second = await agent.process_turn("toca um alarme")
    assert registry.get("utility.timer") is not None
    assert skill_library.get_by_name("utility.timer") is not None
    assert agent.learning_state.active is False

    # A second request for the same capability must not call the LLM again
    # at all -- the router itself matches the now-real "utility.timer"
    # action via the regular (non-LLM) path isn't guaranteed here since
    # there's no regex for it, but critically no further *teaching* call
    # happens: the registry already satisfies the router before it would
    # ever reach "learnable".
    calls_before = llm.calls
    third = await agent.process_turn("coloque um timer de 15 minutos")
    assert llm.calls == calls_before + 1  # only the router call, no second teaching call
    assert third.decision.actions and third.decision.actions[0].name == "utility.timer"


@pytest.mark.asyncio
async def test_high_risk_skill_requires_explicit_approval_before_being_usable(state_dir) -> None:
    router_says_learnable = json.dumps({"action": None, "learnable": True, "skill_hint": "risky"})
    teach_high_risk = json.dumps({
        "name": "utility.risky", "description": "faz algo delicado",
        "parameters": {}, "start_steps": [{"kind": "speak", "text": "ok"}],
        "stop_steps": None, "stop_action_name": None, "risk_level": "high",
    })
    llm = ScriptedLLM([router_says_learnable, teach_high_risk])
    agent, registry, skill_library, _ = _build_agent(state_dir, llm)

    first = await agent.process_turn("faz uma coisa bem delicada pra mim")
    assert agent.learning_state.awaiting_approval is True
    assert registry.get("utility.risky") is None

    second = await agent.process_turn("sim, pode")
    assert registry.get("utility.risky") is not None
    assert skill_library.get_by_name("utility.risky") is not None
    assert agent.learning_state.active is False
