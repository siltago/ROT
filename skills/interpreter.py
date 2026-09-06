"""Executes a learned skill's recipe -- the one new execution primitive
this feature introduces. Deliberately NOT `exec()`/`eval()` of LLM-written
Python: a recipe is a JSON list of steps drawn from a small, fixed
vocabulary (`SkillStepKind`), so it is structurally incapable of deleting
a file, reading an environment variable, or doing anything else outside
that vocabulary -- see skills/models.py and PROJECT.md's notes on why.
"""
from __future__ import annotations

import ast
import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from actions.executor import ActionExecutor
from actions.registry import ActionHandler, ActionRegistry
from brain.models import ActionOutcome, ActionRequest
from skills.models import LearnedSkillRecord, SkillStep, SkillStepKind

logger = logging.getLogger(__name__)

Speak = Callable[[str], Awaitable[None]]


@dataclass
class _RunningSkill:
    task: "asyncio.Task[None]"
    started_at: float
    total_seconds: float

_ALLOWED_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div)
_ALLOWED_UNARYOPS = (ast.UAdd, ast.USub)


def safe_eval(expr: str, parameters: dict[str, Any]) -> float:
    """Evaluates a small arithmetic expression (e.g. "minutes*60") against
    a skill's own declared parameters. NOT `eval()` -- walks the parsed AST
    and rejects anything that isn't a number, a declared parameter name, or
    +/-/*// between them. Attribute access, function calls, subscripts,
    comprehensions, imports -- everything else -- raises ValueError instead
    of ever being evaluated.
    """
    try:
        node = ast.parse(expr, mode="eval").body
    except SyntaxError as exc:
        raise ValueError(f"Invalid expression: {expr!r}") from exc
    return _eval_node(node, parameters)


def _eval_node(node: ast.expr, parameters: dict[str, Any]) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id not in parameters:
            raise ValueError(f"Unknown parameter in expression: {node.id!r}")
        value = parameters[node.id]
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"Parameter {node.id!r} is not numeric")
        return float(value)
    if isinstance(node, ast.BinOp) and isinstance(node.op, _ALLOWED_BINOPS):
        left, right = _eval_node(node.left, parameters), _eval_node(node.right, parameters)
        if isinstance(node.op, ast.Add): return left + right
        if isinstance(node.op, ast.Sub): return left - right
        if isinstance(node.op, ast.Mult): return left * right
        return left / right
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, _ALLOWED_UNARYOPS):
        value = _eval_node(node.operand, parameters)
        return value if isinstance(node.op, ast.UAdd) else -value
    raise ValueError(f"Disallowed expression node: {type(node).__name__}")


class SkillInterpreter:
    def __init__(self, registry: ActionRegistry, executor: ActionExecutor) -> None:
        self.registry = registry
        self.executor = executor
        # Keyed by skill name -- a WAIT-containing recipe (a timer, say)
        # must not block the turn that started it for however long the
        # wait is, so it runs as a background task instead; this is what
        # lets the paired stop handler actually cancel it mid-wait, and
        # what a "quanto tempo falta" companion query (see
        # `remaining_seconds`/`SkillRegistrar`) is computed from.
        self._running: dict[str, _RunningSkill] = {}

    def remaining_seconds(self, name: str) -> float | None:
        """None if this skill isn't currently mid-wait -- either it was
        never started, already finished, or was cancelled."""
        running = self._running.get(name)
        if running is None or running.task.done():
            return None
        elapsed = time.monotonic() - running.started_at
        return max(0.0, running.total_seconds - elapsed)

    async def run_synchronously(self, steps: list[SkillStep], parameters: dict[str, Any]) -> ActionOutcome:
        """Runs steps that execute within a real turn -- a SPEAK step here
        contributes to the returned message instead of calling out to TTS
        directly, so the turn's own normal reply pipeline is what actually
        speaks it, exactly once. (`run()` below still speaks immediately
        for steps with no such turn to attach to -- the part of a recipe
        that only starts once a WAIT has already handed the turn back.)
        Without this distinction, a recipe with a SPEAK step before any
        WAIT -- like a timer's own "Beleza, timer iniciado" -- would get
        spoken twice: once here, direct, and once more as the turn's
        separately-generated generic reply.
        """
        spoken: list[str] = []

        async def collect(text: str) -> None:
            if text:
                spoken.append(text)

        outcome = await self.run(steps, parameters, collect)
        if not outcome.success:
            return outcome
        return ActionOutcome(success=True, message=" ".join(spoken))

    async def run(self, steps: list[SkillStep], parameters: dict[str, Any], speak: Speak) -> ActionOutcome:
        for step in steps:
            if step.kind is SkillStepKind.WAIT:
                seconds = safe_eval(step.seconds_expr or "0", parameters)
                await asyncio.sleep(max(0.0, seconds))
            elif step.kind is SkillStepKind.SPEAK:
                try:
                    text = (step.text or "").format(**parameters)
                except (KeyError, IndexError):
                    text = step.text or ""
                await speak(text)
            elif step.kind is SkillStepKind.CALL_ACTION:
                resolved = {key: _resolve_argument(expr, parameters) for key, expr in step.arguments.items()}
                record = await self.executor.execute(ActionRequest(name=step.action_name or "", arguments=resolved))
                if record.outcome is None or not record.outcome.success:
                    message = record.outcome.message if record.outcome else "ação desconhecida"
                    logger.warning("Learned skill step failed: %s -> %s", step.action_name, message)
                    return ActionOutcome(success=False, message=message)
            elif step.kind is SkillStepKind.SET_STATE:
                raise NotImplementedError("SET_STATE steps are reserved, not implemented yet")
        return ActionOutcome(success=True, message="")

    def build_handler(self, record: LearnedSkillRecord, *, speak_resolver: Callable[[], Speak]) -> ActionHandler:
        steps = record.start_steps
        wait_index = next((i for i, step in enumerate(steps) if step.kind is SkillStepKind.WAIT), None)

        async def handler(**kwargs: Any) -> ActionOutcome:
            if wait_index is None:
                return await self.run_synchronously(steps, kwargs)

            # Everything up to the first WAIT still happens within this
            # turn (e.g. a timer's own "Beleza, timer iniciado" becomes
            # the turn's real spoken reply); everything from the WAIT
            # onward can't -- the turn has already ended by the time it
            # matters -- so it runs detached, using speak_resolver() to
            # reach the user directly whenever it eventually does.
            immediate_steps, deferred_steps = steps[:wait_index], steps[wait_index:]
            if immediate_steps:
                immediate_outcome = await self.run_synchronously(immediate_steps, kwargs)
                if not immediate_outcome.success:
                    return immediate_outcome
            else:
                immediate_outcome = ActionOutcome(success=True, message="Combinado, vou te avisar.")

            async def run_in_background() -> None:
                try:
                    await self.run(deferred_steps, kwargs, speak_resolver())
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Learned skill %r failed while running in the background", record.name)
                finally:
                    self._running.pop(record.name, None)

            # A second "coloque outro timer" for the same skill replaces
            # the one already running rather than stacking silently.
            existing = self._running.pop(record.name, None)
            if existing is not None and not existing.task.done():
                existing.task.cancel()
            # The WAIT step's own duration, resolved against this call's
            # actual arguments -- what "quanto tempo falta" (see
            # `remaining_seconds`/`SkillRegistrar`) measures against.
            total_seconds = safe_eval(steps[wait_index].seconds_expr or "0", kwargs)
            task = asyncio.create_task(run_in_background())
            self._running[record.name] = _RunningSkill(task=task, started_at=time.monotonic(), total_seconds=total_seconds)
            return immediate_outcome

        return handler

    def build_remaining_handler(self, record: LearnedSkillRecord) -> ActionHandler:
        """"Quanto tempo falta?" for a WAIT-based skill -- auto-registered
        by SkillRegistrar alongside the stop action for any skill that has
        one, never something the LLM has to think to teach: the recipe DSL
        has no way to introspect a running wait's remaining time on its
        own, so this is a built-in capability of the interpreter itself,
        automatically available for every such skill going forward."""
        async def handler(**kwargs: Any) -> ActionOutcome:
            remaining = self.remaining_seconds(record.name)
            if remaining is None:
                return ActionOutcome(success=True, message="Não tem nada rodando agora.")
            minutes, seconds = divmod(int(remaining) + 1, 60)  # round up to the next second
            if minutes and seconds:
                message = f"Faltam {minutes} minuto{'s' if minutes != 1 else ''} e {seconds} segundo{'s' if seconds != 1 else ''}."
            elif minutes:
                message = f"Faltam {minutes} minuto{'s' if minutes != 1 else ''}."
            else:
                message = f"Faltam {seconds} segundo{'s' if seconds != 1 else ''}."
            return ActionOutcome(success=True, message=message)
        return handler

    def build_stop_handler(self, record: LearnedSkillRecord, *, speak_resolver: Callable[[], Speak]) -> ActionHandler:
        async def handler(**kwargs: Any) -> ActionOutcome:
            running = self._running.pop(record.name, None)
            if running is not None and not running.task.done():
                running.task.cancel()
            return await self.run_synchronously(record.stop_steps or [], kwargs)
        return handler


def _resolve_argument(expr: str, parameters: dict[str, Any]) -> Any:
    """A CALL_ACTION argument can be a numeric expression (like WAIT's,
    e.g. "minutes") or literal/templated text (e.g. "Alarme de {minutes}
    minutos") -- try the safe numeric evaluator first, and fall back to
    plain `str.format` (never `eval()`/`exec()` either way)."""
    try:
        return safe_eval(expr, parameters)
    except ValueError:
        try:
            return expr.format(**parameters)
        except (KeyError, IndexError):
            return expr
