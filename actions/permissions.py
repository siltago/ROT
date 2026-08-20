"""Confirmation policy for sensitive actions.

Decides whether a given action requires explicit user confirmation before
execution, based on its registered risk_level/requires_confirmation, and
provides a hook to collect that confirmation.
"""
from __future__ import annotations

from typing import Awaitable, Callable

from actions.registry import ActionSpec

ConfirmationProvider = Callable[[ActionSpec, dict], Awaitable[bool]]


async def auto_deny(spec: ActionSpec, arguments: dict) -> bool:
    """Default confirmation provider: no interactive channel available, so
    sensitive actions are denied rather than silently allowed."""
    return False


class PermissionPolicy:
    def __init__(self, confirmation_provider: ConfirmationProvider = auto_deny) -> None:
        self.confirmation_provider = confirmation_provider

    def needs_confirmation(self, spec: ActionSpec) -> bool:
        return spec.requires_confirmation

    async def confirm(self, spec: ActionSpec, arguments: dict) -> bool:
        return await self.confirmation_provider(spec, arguments)
