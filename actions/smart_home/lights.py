"""Simulated smart-home light/climate actions. Not connected to any real
integration yet -- registered here so the decision engine has something
concrete to request and the executor has something to run end to end."""
from __future__ import annotations

from actions.registry import ActionRegistry, ActionSpec
from brain.models import ActionOutcome, RiskLevel


async def light_turn_on(room: str) -> ActionOutcome:
    return ActionOutcome(success=True, message=f"Light in {room} turned on", data={"room": room})


async def light_turn_off(room: str) -> ActionOutcome:
    return ActionOutcome(success=True, message=f"Light in {room} turned off", data={"room": room})


async def climate_set_temperature(temperature: float) -> ActionOutcome:
    return ActionOutcome(
        success=True,
        message=f"Temperature set to {temperature} degrees",
        data={"temperature": temperature},
    )


def register(registry: ActionRegistry) -> None:
    registry.register(
        ActionSpec(
            name="light.turn_on",
            description="Turn on the light in a given room",
            handler=light_turn_on,
            parameters={"room": str},
            risk_level=RiskLevel.LOW,
            requires_confirmation=False,
        )
    )
    registry.register(
        ActionSpec(
            name="light.turn_off",
            description="Turn off the light in a given room",
            handler=light_turn_off,
            parameters={"room": str},
            risk_level=RiskLevel.LOW,
            requires_confirmation=False,
        )
    )
    registry.register(
        ActionSpec(
            name="climate.set_temperature",
            description="Set the target temperature in Celsius",
            handler=climate_set_temperature,
            parameters={"temperature": float},
            risk_level=RiskLevel.LOW,
            requires_confirmation=False,
        )
    )
