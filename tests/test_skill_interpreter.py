import asyncio

import pytest

from actions.executor import ActionExecutor
from actions.permissions import PermissionPolicy
from actions.registry import ActionRegistry, ActionSpec
from brain.models import ActionOutcome
from skills.interpreter import SkillInterpreter, safe_eval
from skills.models import LearnedSkillRecord, SkillStep, SkillStepKind


def test_safe_eval_accepts_arithmetic_over_declared_parameters() -> None:
    assert safe_eval("minutes*60", {"minutes": 15}) == 900.0
    assert safe_eval("minutes + 1", {"minutes": 2}) == 3.0
    assert safe_eval("-minutes", {"minutes": 2}) == -2.0


@pytest.mark.parametrize("expr", [
    "__import__('os')",
    "open('x')",
    "minutes.__class__",
    "[x for x in range(3)]",
    "minutes if True else 0",
])
def test_safe_eval_rejects_anything_outside_arithmetic(expr: str) -> None:
    with pytest.raises(ValueError):
        safe_eval(expr, {"minutes": 15})


def test_safe_eval_rejects_undeclared_names() -> None:
    with pytest.raises(ValueError):
        safe_eval("seconds", {"minutes": 15})


@pytest.mark.asyncio
async def test_run_executes_steps_in_order_and_calls_registered_actions() -> None:
    registry = ActionRegistry()
    calls: list[dict] = []

    async def fake_action(**kwargs) -> ActionOutcome:
        calls.append(kwargs)
        return ActionOutcome(success=True, message="ok")

    registry.register(ActionSpec(name="test.action", description="d", handler=fake_action, parameters={"who": str}))
    executor = ActionExecutor(registry, PermissionPolicy())
    interpreter = SkillInterpreter(registry, executor)

    spoken: list[str] = []
    async def speak(text: str) -> None:
        spoken.append(text)

    steps = [
        SkillStep(kind=SkillStepKind.SPEAK, text="Oi {name}"),
        SkillStep(kind=SkillStepKind.CALL_ACTION, action_name="test.action", arguments={"who": "{name}"}),
    ]
    outcome = await interpreter.run(steps, {"name": "Bob"}, speak)

    assert outcome.success is True
    assert spoken == ["Oi Bob"]
    assert calls == [{"who": "Bob"}]


@pytest.mark.asyncio
async def test_run_stops_and_fails_when_a_call_action_step_fails() -> None:
    registry = ActionRegistry()

    async def failing(**kwargs) -> ActionOutcome:
        return ActionOutcome(success=False, message="deu ruim")

    registry.register(ActionSpec(name="test.fail", description="d", handler=failing, parameters={}))
    executor = ActionExecutor(registry, PermissionPolicy())
    interpreter = SkillInterpreter(registry, executor)

    spoken: list[str] = []
    async def speak(text: str) -> None:
        spoken.append(text)

    steps = [
        SkillStep(kind=SkillStepKind.CALL_ACTION, action_name="test.fail", arguments={}),
        SkillStep(kind=SkillStepKind.SPEAK, text="não devia chegar aqui"),
    ]
    outcome = await interpreter.run(steps, {}, speak)

    assert outcome.success is False
    assert spoken == []


def _timer_record() -> LearnedSkillRecord:
    return LearnedSkillRecord(
        name="timer.start",
        description="timer",
        parameters={"minutes": "float"},
        start_steps=[
            SkillStep(kind=SkillStepKind.SPEAK, text="Beleza, timer de {minutes} minutos iniciado."),
            SkillStep(kind=SkillStepKind.WAIT, seconds_expr="minutes*60"),
            SkillStep(kind=SkillStepKind.SPEAK, text="O timer de {minutes} minutos terminou."),
        ],
        stop_steps=[SkillStep(kind=SkillStepKind.SPEAK, text="Timer cancelado.")],
        stop_action_name="timer.start.cancel",
    )


@pytest.mark.asyncio
async def test_speak_before_a_wait_becomes_the_turns_own_reply_not_a_duplicate() -> None:
    # Regression test: a SPEAK step before the first WAIT used to be
    # spoken directly *and* leave the turn's own outcome message empty
    # (falling back to a generic "Pode deixar, já foi." elsewhere in the
    # reply pipeline) -- the same line got said twice, through two
    # different paths, for something as simple as "coloque um timer".
    registry = ActionRegistry()
    executor = ActionExecutor(registry, PermissionPolicy())
    interpreter = SkillInterpreter(registry, executor)
    record = _timer_record()

    background_spoken: list[str] = []
    handler = interpreter.build_handler(record, speak_resolver=_sync_speak(background_spoken))

    outcome = await handler(minutes=0.001)  # ~60ms wait -- short enough for the test to await it

    # The immediate reply carries the recipe's own first line as the
    # turn's real message -- nothing was spoken directly for it.
    assert outcome.message == "Beleza, timer de 0.001 minutos iniciado."
    assert background_spoken == []

    await asyncio.sleep(0.2)  # let the background wait+speak finish
    assert background_spoken == ["O timer de 0.001 minutos terminou."]


def _sync_speak(sink: list[str]):
    async def speak(text: str) -> None:
        sink.append(text)
    return lambda: speak


@pytest.mark.asyncio
async def test_remaining_handler_reports_time_left_on_a_running_wait() -> None:
    # "Quanto tempo falta?" isn't something the LLM ever teaches -- the
    # recipe DSL has no way to introspect its own running wait, so this is
    # a built-in companion the interpreter provides for any WAIT-based
    # skill automatically.
    registry = ActionRegistry()
    executor = ActionExecutor(registry, PermissionPolicy())
    interpreter = SkillInterpreter(registry, executor)
    record = _timer_record()

    assert interpreter.remaining_seconds("timer.start") is None  # not started yet
    remaining_handler = interpreter.build_remaining_handler(record)
    not_running = await remaining_handler()
    assert not_running.message == "Não tem nada rodando agora."

    handler = interpreter.build_handler(record, speak_resolver=_sync_speak([]))
    await handler(minutes=1)  # a full 60s wait -- long enough that it's still running below

    outcome = await remaining_handler()
    assert "falta" in outcome.message.casefold()
    assert "1 minuto" in outcome.message

    # Cancelling clears the running state the query reports on.
    stop_handler = interpreter.build_stop_handler(record, speak_resolver=_sync_speak([]))
    await stop_handler()
    assert interpreter.remaining_seconds("timer.start") is None
    cleared = await remaining_handler()
    assert cleared.message == "Não tem nada rodando agora."


@pytest.mark.asyncio
async def test_stop_handler_speaks_through_its_own_return_message_too() -> None:
    registry = ActionRegistry()
    executor = ActionExecutor(registry, PermissionPolicy())
    interpreter = SkillInterpreter(registry, executor)
    record = _timer_record()

    stop_handler = interpreter.build_stop_handler(record, speak_resolver=_sync_speak([]))
    outcome = await stop_handler()

    assert outcome.success is True
    assert outcome.message == "Timer cancelado."
