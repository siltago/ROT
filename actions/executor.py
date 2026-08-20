"""The single choke point through which every action actually runs.

The decision engine / LLM layer can propose ActionRequests, but only this
executor is allowed to invoke a handler. It validates arguments against the
registry, applies the permission policy (confirmation for sensitive
actions), executes with a timeout, and returns a fully logged ActionRecord.
"""
from __future__ import annotations

import asyncio
import uuid

from actions.permissions import PermissionPolicy
from actions.registry import ActionRegistry
from brain.models import ActionOutcome, ActionRecord, ActionRequest


class ActionValidationError(Exception):
    pass


class ActionExecutor:
    def __init__(self, registry: ActionRegistry, permissions: PermissionPolicy) -> None:
        self.registry = registry
        self.permissions = permissions
        self.log: list[ActionRecord] = []

    async def execute(self, request: ActionRequest) -> ActionRecord:
        spec = self.registry.get(request.name)
        record_id = str(uuid.uuid4())

        if spec is None:
            record = ActionRecord(
                id=record_id,
                name=request.name,
                arguments=request.arguments,
                outcome=ActionOutcome(success=False, message=f"Unknown action '{request.name}'"),
            )
            self.log.append(record)
            return record

        errors = self.registry.validate_arguments(request.name, request.arguments)
        if errors:
            record = ActionRecord(
                id=record_id,
                name=request.name,
                arguments=request.arguments,
                risk_level=spec.risk_level,
                required_confirmation=spec.requires_confirmation,
                outcome=ActionOutcome(success=False, message="; ".join(errors)),
            )
            self.log.append(record)
            return record

        confirmed = True
        if self.permissions.needs_confirmation(spec):
            confirmed = await self.permissions.confirm(spec, request.arguments)
            if not confirmed:
                record = ActionRecord(
                    id=record_id,
                    name=request.name,
                    arguments=request.arguments,
                    risk_level=spec.risk_level,
                    required_confirmation=True,
                    confirmed=False,
                    outcome=ActionOutcome(success=False, message="Confirmation denied or not obtained"),
                )
                self.log.append(record)
                return record

        try:
            outcome = await asyncio.wait_for(
                spec.handler(**request.arguments), timeout=spec.timeout_seconds
            )
        except asyncio.TimeoutError:
            outcome = ActionOutcome(success=False, message=f"Action '{request.name}' timed out")
        except Exception as exc:  # noqa: BLE001 -- action handlers are untrusted-ish plugins
            outcome = ActionOutcome(success=False, message=f"Action '{request.name}' failed: {exc}")

        record = ActionRecord(
            id=record_id,
            name=request.name,
            arguments=request.arguments,
            risk_level=spec.risk_level,
            required_confirmation=spec.requires_confirmation,
            confirmed=confirmed,
            outcome=outcome,
        )
        self.log.append(record)
        return record

    async def execute_many(self, requests: list[ActionRequest]) -> list[ActionRecord]:
        return [await self.execute(r) for r in requests]
