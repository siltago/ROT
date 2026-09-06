from actions.executor import ActionExecutor
from actions.permissions import PermissionPolicy
from actions.registry import ActionRegistry
from memory.repository import InMemoryRepository
from skills.interpreter import SkillInterpreter
from skills.models import LearnedSkillRecord, SkillStep, SkillStepKind
from skills.registrar import SkillRegistrar
from skills.store import SkillLibrary


async def _noop_speak(text: str) -> None:
    pass


def _build_registrar() -> SkillRegistrar:
    registry = ActionRegistry()
    executor = ActionExecutor(registry, PermissionPolicy())
    interpreter = SkillInterpreter(registry, executor)
    library = SkillLibrary(InMemoryRepository())
    return SkillRegistrar(registry, interpreter, library)


def test_wait_based_skill_gets_a_remaining_companion_action_for_free() -> None:
    registrar = _build_registrar()
    record = LearnedSkillRecord(
        name="utility.timer", description="timer",
        parameters={"minutes": "float"},
        start_steps=[SkillStep(kind=SkillStepKind.WAIT, seconds_expr="minutes*60")],
        stop_steps=[SkillStep(kind=SkillStepKind.SPEAK, text="Cancelado")],
        stop_action_name="utility.timer.cancel",
    )

    registrar.register_learned(record, speak_resolver=lambda: _noop_speak)

    assert registrar.registry.get("utility.timer") is not None
    assert registrar.registry.get("utility.timer.cancel") is not None
    assert registrar.registry.get("utility.timer.remaining") is not None


def test_one_shot_skill_with_no_wait_gets_no_remaining_action() -> None:
    registrar = _build_registrar()
    record = LearnedSkillRecord(
        name="utility.greet", description="cumprimenta",
        parameters={}, start_steps=[SkillStep(kind=SkillStepKind.SPEAK, text="Oi!")],
        stop_steps=None, stop_action_name=None,
    )

    registrar.register_learned(record, speak_resolver=lambda: _noop_speak)

    assert registrar.registry.get("utility.greet") is not None
    assert registrar.registry.get("utility.greet.remaining") is None
