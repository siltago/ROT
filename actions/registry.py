"""Central registry of everything the robot is capable of doing.

The LLM/decision engine can only *request* actions by name + arguments. It
never calls a handler directly. Only ActionExecutor (actions/executor.py)
looks up handlers here and invokes them, after validation and permission
checks.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from brain.models import ActionOutcome, RiskLevel

ActionHandler = Callable[..., Awaitable[ActionOutcome]]


@dataclass
class ActionSpec:
    name: str
    description: str
    handler: ActionHandler
    parameters: dict[str, type] = field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.LOW
    requires_confirmation: bool = False
    timeout_seconds: float = 5.0
    permissions: list[str] = field(default_factory=list)


class ActionRegistry:
    def __init__(self) -> None:
        self._actions: dict[str, ActionSpec] = {}

    def register(self, spec: ActionSpec) -> None:
        if spec.name in self._actions:
            raise ValueError(f"Action '{spec.name}' is already registered")
        self._actions[spec.name] = spec

    def get(self, name: str) -> ActionSpec | None:
        return self._actions.get(name)

    def all(self) -> list[ActionSpec]:
        return list(self._actions.values())

    def validate_arguments(self, name: str, arguments: dict[str, Any]) -> list[str]:
        """Return a list of validation error strings (empty = valid)."""
        spec = self.get(name)
        if spec is None:
            return [f"Unknown action '{name}'"]
        errors = []
        for param, expected_type in spec.parameters.items():
            if param not in arguments:
                errors.append(f"Missing required parameter '{param}'")
                continue
            value = arguments[param]
            if expected_type is float and isinstance(value, int) and not isinstance(value, bool):
                continue  # ints are acceptable wherever a float is expected
            if not isinstance(value, expected_type):
                errors.append(
                    f"Parameter '{param}' expected {expected_type.__name__}, "
                    f"got {type(value).__name__}"
                )
        return errors
