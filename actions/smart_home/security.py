"""High-risk smart-home actions requiring explicit confirmation."""
from __future__ import annotations

from actions.registry import ActionRegistry, ActionSpec
from brain.models import ActionOutcome, RiskLevel


async def door_unlock(door: str) -> ActionOutcome:
    return ActionOutcome(success=True, message=f"Door '{door}' unlocked", data={"door": door})


def register(registry: ActionRegistry) -> None:
    registry.register(
        ActionSpec(
            name="door.unlock",
            description="Unlock a named door",
            handler=door_unlock,
            parameters={"door": str},
            risk_level=RiskLevel.HIGH,
            requires_confirmation=True,
        )
    )
