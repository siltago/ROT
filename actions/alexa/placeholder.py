"""Placeholder for future Alexa / smart-home-hub integration.

No real Alexa Skills Kit / Smart Home API call is made yet -- this exists
to reserve the module location described in PROJECT.md so a real
integration can be dropped in later without restructuring actions/.
"""
from __future__ import annotations

from actions.registry import ActionRegistry


def register(registry: ActionRegistry) -> None:
    """No actions registered yet; real Alexa integration is future work."""
    return
