"""In-memory simulated hardware. Prints/logs actions instead of driving a body."""
from __future__ import annotations

from hardware.base import RobotHardware


class SimulatorHardware(RobotHardware):
    def __init__(self, verbose: bool = True) -> None:
        self.verbose = verbose
        self.state: dict[str, object] = {
            "head_angle": 0.0,
            "expression": "neutral",
            "linear": 0.0,
            "angular": 0.0,
            "looking_at": None,
        }
        self.history: list[dict] = []

    def _log(self, action: str, **kwargs) -> None:
        entry = {"action": action, **kwargs}
        self.history.append(entry)
        if self.verbose:
            args = " ".join(f"{k}={v}" for k, v in kwargs.items())
            print(f"[Simulator] {action} {args}".rstrip())

    async def move_head(self, angle: float) -> None:
        self.state["head_angle"] = angle
        self._log("head.rotate", angle=angle)

    async def look_at(self, person_id: str) -> None:
        self.state["looking_at"] = person_id
        self._log("head.look_at", person_id=person_id)

    async def set_expression(self, expression: str) -> None:
        self.state["expression"] = expression
        self._log("face.set_expression", expression=expression)

    async def move(self, linear: float, angular: float) -> None:
        self.state["linear"] = linear
        self.state["angular"] = angular
        self._log("base.move", linear=linear, angular=angular)

    async def speak(self, text: str) -> None:
        self._log("tts.speak", text=text)
