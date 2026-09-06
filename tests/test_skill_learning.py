import json

import pytest

from actions.executor import ActionExecutor
from actions.permissions import PermissionPolicy
from actions.registry import ActionRegistry
from brain.skill_learning import SkillTeacher, SkillTeachStatus
from integrations.llm.base import LLMProvider
from memory.repository import InMemoryRepository
from skills.interpreter import SkillInterpreter
from skills.registrar import SkillRegistrar
from skills.store import SkillLibrary


class FakeLLM(LLMProvider):
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[str] = []

    async def generate(self, *, system: str, user: str, history: str = "") -> str:
        self.calls.append(user)
        return self.response


async def _noop_speak(text: str) -> None:
    pass


def _build_teacher(llm: LLMProvider) -> tuple[SkillTeacher, ActionRegistry, SkillLibrary]:
    registry = ActionRegistry()
    executor = ActionExecutor(registry, PermissionPolicy())
    interpreter = SkillInterpreter(registry, executor)
    library = SkillLibrary(InMemoryRepository())
    registrar = SkillRegistrar(registry, interpreter, library)
    teacher = SkillTeacher(llm_provider=llm, registrar=registrar, speak_resolver=lambda: _noop_speak)
    return teacher, registry, library


@pytest.mark.asyncio
async def test_needs_clarification_does_not_save_anything() -> None:
    llm = FakeLLM(json.dumps({"needs_clarification": "o que tocar quando o tempo acabar?"}))
    teacher, registry, library = _build_teacher(llm)

    result = await teacher.start("coloque um timer de 15 minutos")

    assert result.status is SkillTeachStatus.NEEDS_CLARIFICATION
    assert "tocar" in result.message
    assert library.all() == []
    assert registry.get("utility.timer") is None


@pytest.mark.asyncio
async def test_low_risk_skill_is_learned_and_registered_immediately() -> None:
    recipe = {
        "name": "utility.greet", "description": "cumprimenta alguém",
        "parameters": {"name": "str"},
        "start_steps": [{"kind": "speak", "text": "Oi {name}!"}],
        "stop_steps": None, "stop_action_name": None, "risk_level": "low",
    }
    llm = FakeLLM(json.dumps(recipe))
    teacher, registry, library = _build_teacher(llm)

    result = await teacher.start("cumprimente as pessoas pra mim")

    assert result.status is SkillTeachStatus.LEARNED
    assert registry.get("utility.greet") is not None
    assert library.get_by_name("utility.greet") is not None


@pytest.mark.asyncio
async def test_high_risk_skill_waits_for_approval_before_registering() -> None:
    recipe = {
        "name": "utility.risky", "description": "faz algo arriscado",
        "parameters": {}, "start_steps": [{"kind": "speak", "text": "ok"}],
        "stop_steps": None, "stop_action_name": None, "risk_level": "high",
    }
    llm = FakeLLM(json.dumps(recipe))
    teacher, registry, library = _build_teacher(llm)

    result = await teacher.start("faz uma coisa arriscada")

    assert result.status is SkillTeachStatus.READY_FOR_APPROVAL
    assert result.record is not None
    assert registry.get("utility.risky") is None
    assert library.all() == []

    teacher.approve(result.record)

    assert registry.get("utility.risky") is not None
    assert library.get_by_name("utility.risky") is not None


@pytest.mark.asyncio
async def test_recipe_referencing_unknown_action_fails_closed() -> None:
    recipe = {
        "name": "utility.bad", "description": "chama ação inexistente",
        "parameters": {}, "start_steps": [{"kind": "call_action", "action_name": "nope.nope", "arguments": {}}],
        "stop_steps": None, "stop_action_name": None, "risk_level": "low",
    }
    llm = FakeLLM(json.dumps(recipe))
    teacher, registry, library = _build_teacher(llm)

    result = await teacher.start("faz algo que não existe")

    assert result.status is SkillTeachStatus.FAILED
    assert registry.get("utility.bad") is None
    assert library.all() == []


@pytest.mark.asyncio
async def test_wait_step_without_a_paired_stop_fails_closed() -> None:
    # Enforces "never teach a start without a stop" structurally, not just
    # via the prompt -- a wait-based skill with no stop_steps/
    # stop_action_name must never be saved half-taught.
    recipe = {
        "name": "utility.half_timer", "description": "timer incompleto",
        "parameters": {"minutes": "float"},
        "start_steps": [{"kind": "wait", "seconds_expr": "minutes*60"}],
        "stop_steps": None, "stop_action_name": None, "risk_level": "low",
    }
    llm = FakeLLM(json.dumps(recipe))
    teacher, registry, library = _build_teacher(llm)

    result = await teacher.start("coloque um timer de 15 minutos")

    assert result.status is SkillTeachStatus.FAILED
    assert library.all() == []


@pytest.mark.asyncio
async def test_second_clarification_round_gives_up_instead_of_looping() -> None:
    llm = FakeLLM(json.dumps({"needs_clarification": "e de novo?"}))
    teacher, registry, library = _build_teacher(llm)

    result = await teacher.continue_with_answer("pedido original", "pergunta anterior", "resposta")

    assert result.status is SkillTeachStatus.FAILED
