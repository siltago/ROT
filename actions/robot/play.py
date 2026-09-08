"""Lets the user directly tell Bob to entertain himself ("vai jogar",
"joga um pouco", "se distraia") instead of that only ever happening on
its own after being idle a while. The action itself has no side effect
-- api/server.py's `process_text` watches for this specific action name
in the turn's action_records and, when it sees it, pushes
`play_idle_animation` straight to that device, the same message
PlayfulIdleBehavior already sends autonomously (see
_dispatch_selected) -- so this reuses the client's own random pick
instead of the backend choosing a kind.
"""
from __future__ import annotations

from actions.registry import ActionRegistry, ActionSpec
from brain.models import ActionOutcome, RiskLevel


async def play_now() -> ActionOutcome:
    return ActionOutcome(success=True, message="Bora, vou me distrair um pouco")


def register(registry: ActionRegistry) -> None:
    registry.register(ActionSpec(
        name="idle.play_now",
        description="Start one of the robot's self-entertainment idle vignettes (games, doodling, reading...) right now, instead of waiting for it to happen on its own after being idle",
        handler=play_now,
        risk_level=RiskLevel.LOW,
    ))
