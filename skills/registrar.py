"""Turns a taught (or reloaded-from-storage) `LearnedSkillRecord` into a
real, live `ActionSpec` -- registering a new ActionSpec into an already-
running ActionRegistry after startup is safe (confirmed: ActionExecutor/
Planner/LlmActionRouter all hold the same live registry instance and call
`.get()`/`.all()` fresh every time, no caching to invalidate), so this is
the one function used both right after learning something new and when
reloading everything from Supabase at boot.
"""
from __future__ import annotations

import logging
from typing import Awaitable, Callable

from actions.registry import ActionRegistry, ActionSpec
from brain.models import RiskLevel
from skills.interpreter import SkillInterpreter
from skills.models import LearnedSkillRecord, SkillStepKind
from skills.store import SkillLibrary

logger = logging.getLogger(__name__)

_TYPE_MAP: dict[str, type] = {"str": str, "float": float, "int": int, "bool": bool}

# A learned skill's handler may legitimately run a WAIT step lasting
# minutes -- but that wait now happens in a detached background task (see
# SkillInterpreter.build_handler), so the synchronous part ActionExecutor
# actually awaits returns almost immediately either way. A modest timeout
# is still safer than the default 5s in case a learned CALL_ACTION chain
# is slow.
_LEARNED_SKILL_TIMEOUT_SECONDS = 15.0


class SkillRegistrar:
    def __init__(self, registry: ActionRegistry, interpreter: SkillInterpreter, skill_library: SkillLibrary) -> None:
        self.registry = registry
        self.interpreter = interpreter
        self.skill_library = skill_library

    def register_learned(self, record: LearnedSkillRecord, *, speak_resolver: Callable[[], Callable[[str], Awaitable[None]]]) -> None:
        self._register_one(
            name=record.name, description=record.description, parameters=record.parameters,
            risk_level=record.risk_level, requires_confirmation=record.requires_confirmation,
            handler=self.interpreter.build_handler(record, speak_resolver=speak_resolver),
        )
        if record.stop_action_name and record.stop_steps:
            # Canceling something is never the risky half -- always LOW
            # risk / no confirmation, regardless of the start skill's own
            # classification.
            self._register_one(
                name=record.stop_action_name, description=f"Cancela: {record.description}",
                parameters={}, risk_level=RiskLevel.LOW, requires_confirmation=False,
                handler=self.interpreter.build_stop_handler(record, speak_resolver=speak_resolver),
            )
        if any(step.kind is SkillStepKind.WAIT for step in record.start_steps):
            # A WAIT-based skill (a timer, say) gets a "how much time is
            # left" query for free -- not something the LLM ever has to
            # think to teach (the recipe DSL has no way to introspect a
            # running wait on its own), just a built-in companion to any
            # skill that waits at all.
            self._register_one(
                name=f"{record.name}.remaining", description=f"Diz quanto tempo falta: {record.description}",
                parameters={}, risk_level=RiskLevel.LOW, requires_confirmation=False,
                handler=self.interpreter.build_remaining_handler(record),
            )

    def _register_one(self, *, name, description, parameters, risk_level, requires_confirmation, handler) -> None:
        if self.registry.get(name) is not None:
            # A hand-coded action always wins -- never silently overwritten
            # by something learned (this also makes reloading idempotent:
            # calling register_learned twice for the same skill just skips
            # the second time instead of raising).
            logger.warning("Skipping learned skill registration -- name already exists: %r", name)
            return
        self.registry.register(ActionSpec(
            name=name, description=description,
            parameters={key: _TYPE_MAP.get(value, str) for key, value in parameters.items()},
            handler=handler, risk_level=risk_level, requires_confirmation=requires_confirmation,
            timeout_seconds=_LEARNED_SKILL_TIMEOUT_SECONDS,
        ))

    def load_all(self, *, speak_resolver: Callable[[], Callable[[str], Awaitable[None]]]) -> None:
        for record in self.skill_library.all():
            self.register_learned(record, speak_resolver=speak_resolver)
