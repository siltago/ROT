"""Turns a Decision's proposed actions into validated ActionRequests ready
for the executor. This is the "think before acting" checkpoint: it never
executes anything itself, it only validates shape/arguments against the
ActionRegistry so the executor doesn't waste a round-trip on garbage.
"""
from __future__ import annotations

from dataclasses import dataclass

from actions.registry import ActionRegistry
from brain.models import ActionRequest, Decision


@dataclass
class Plan:
    valid_actions: list[ActionRequest]
    rejected: list[tuple[ActionRequest, list[str]]]  # (request, validation errors)


class Planner:
    def __init__(self, registry: ActionRegistry) -> None:
        self.registry = registry

    def plan(self, decision: Decision) -> Plan:
        valid: list[ActionRequest] = []
        rejected: list[tuple[ActionRequest, list[str]]] = []
        for request in decision.actions:
            errors = self.registry.validate_arguments(request.name, request.arguments)
            if errors:
                rejected.append((request, errors))
            else:
                valid.append(request)
        return Plan(valid_actions=valid, rejected=rejected)
