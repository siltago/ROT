"""Placeholder for the future ESP32-backed hardware implementation.

Not implemented yet -- no real firmware or transport exists. This stub
exists only to show the seam: once a transport (WiFi/serial) is chosen,
`ESP32Hardware` implements `RobotHardware` by encoding each call as a
`hardware.protocol.Command`, sending it, and awaiting a `CommandResult`.
The brain will not need to change when this is filled in.
"""
from __future__ import annotations

from hardware.base import RobotHardware


class ESP32Hardware(RobotHardware):
    def __init__(self, *_, **__) -> None:
        raise NotImplementedError(
            "ESP32Hardware is not implemented yet. Use SimulatorHardware."
        )

    async def move_head(self, angle: float) -> None:  # pragma: no cover
        raise NotImplementedError

    async def look_at(self, person_id: str) -> None:  # pragma: no cover
        raise NotImplementedError

    async def set_expression(self, expression: str) -> None:  # pragma: no cover
        raise NotImplementedError

    async def move(self, linear: float, angular: float) -> None:  # pragma: no cover
        raise NotImplementedError

    async def speak(self, text: str) -> None:  # pragma: no cover
        raise NotImplementedError
