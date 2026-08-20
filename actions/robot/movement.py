"""Robot-body actions. These are the only actions that touch `RobotHardware`
-- everything is routed through the abstract interface, never a concrete
driver, so swapping SimulatorHardware for ESP32Hardware requires no changes
here.
"""
from __future__ import annotations

from functools import partial

from actions.registry import ActionRegistry, ActionSpec
from brain.models import ActionOutcome, RiskLevel
from hardware.base import RobotHardware


async def look_at(hardware: RobotHardware, person_id: str) -> ActionOutcome:
    await hardware.look_at(person_id)
    return ActionOutcome(success=True, message=f"Looking at {person_id}")


async def set_expression(hardware: RobotHardware, expression: str) -> ActionOutcome:
    await hardware.set_expression(expression)
    return ActionOutcome(success=True, message=f"Expression set to {expression}")


async def move_head(hardware: RobotHardware, angle: float) -> ActionOutcome:
    await hardware.move_head(angle)
    return ActionOutcome(success=True, message=f"Head moved to {angle} degrees")


def register(registry: ActionRegistry, hardware: RobotHardware) -> None:
    registry.register(
        ActionSpec(
            name="robot.look_at",
            description="Turn the robot's head/gaze toward a known person",
            handler=partial(look_at, hardware),
            parameters={"person_id": str},
            risk_level=RiskLevel.LOW,
        )
    )
    registry.register(
        ActionSpec(
            name="robot.set_expression",
            description="Set the robot's facial expression",
            handler=partial(set_expression, hardware),
            parameters={"expression": str},
            risk_level=RiskLevel.LOW,
        )
    )
    registry.register(
        ActionSpec(
            name="robot.move_head",
            description="Rotate the robot's head to a given angle",
            handler=partial(move_head, hardware),
            parameters={"angle": float},
            risk_level=RiskLevel.LOW,
        )
    )
