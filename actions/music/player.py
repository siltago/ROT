"""Simulated music-integration actions (stand-in for a future Spotify/etc.
integration). See integrations/ for where the real client would live --
this module only registers the action surface."""
from __future__ import annotations

from actions.registry import ActionRegistry, ActionSpec
from brain.models import ActionOutcome, RiskLevel


async def play_music(query: str) -> ActionOutcome:
    return ActionOutcome(success=True, message=f"Playing '{query}'", data={"query": query})


async def stop_music() -> ActionOutcome:
    return ActionOutcome(success=True, message="Music stopped")


def register(registry: ActionRegistry) -> None:
    registry.register(
        ActionSpec(
            name="music.play",
            description="Play a song, artist, or playlist by name",
            handler=play_music,
            parameters={"query": str},
            risk_level=RiskLevel.LOW,
        )
    )
    registry.register(
        ActionSpec(
            name="music.stop",
            description="Stop music playback",
            handler=stop_music,
            parameters={},
            risk_level=RiskLevel.LOW,
        )
    )
