"""Abstract hardware interface.

Nothing above this layer (brain, actions, decision engine) may import a
concrete hardware implementation. Code should depend on `RobotHardware`
only, obtained via dependency injection (see app/config.py + app/main.py).
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class RobotHardware(ABC):
    """Physical/simulated capabilities of the robot body.

    Every concrete implementation (simulator, ESP32, future drivers) must
    implement this same surface so the brain never changes when the body
    changes.
    """

    @abstractmethod
    async def move_head(self, angle: float) -> None:
        """Rotate the head to `angle` degrees (relative to center, -90..90)."""

    @abstractmethod
    async def look_at(self, person_id: str) -> None:
        """Orient toward a known person. Resolution of position is up to the
        implementation (e.g. via last known face-tracking coordinates)."""

    @abstractmethod
    async def set_expression(self, expression: str) -> None:
        """Set a facial/emotional expression, e.g. 'happy', 'curious'."""

    @abstractmethod
    async def move(self, linear: float, angular: float) -> None:
        """Drive the base. linear: m/s forward(+)/back(-). angular: rad/s."""

    @abstractmethod
    async def speak(self, text: str) -> None:
        """Produce speech output (TTS or simulated print)."""
