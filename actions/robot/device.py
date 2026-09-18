"""Small controls over the tablet Bob is running on (volume, screen
brightness) -- he's the one deciding when to use them ("tá alto demais",
"tá escuro aqui"), just like any other action.

Like idle.play_now (actions/robot/play.py), these handlers touch nothing
themselves: the tablet is the one that owns the hardware. Each returns the
control as `data`, and api/server.py's process_text forwards a successful
`device.*` record to that device as a `device_control` message. Levels are
percentages (0-100); "up"/"down" moves a fixed step from wherever it is.
"""
from __future__ import annotations

from actions.registry import ActionRegistry, ActionSpec
from brain.models import ActionOutcome, RiskLevel

# How far one "aumenta"/"diminui" moves, in percentage points.
STEP_PERCENT = 15

_UP = ("up", "mais", "aumentar", "aumenta", "subir", "sobe")
_DOWN = ("down", "menos", "diminuir", "diminui", "baixar", "abaixa")

_LABELS = {"volume": "o volume", "brightness": "o brilho"}


class DeviceStatusSource:
    """Last hardware state the tablet reported, shared between the websocket
    layer (which updates it on every `device_state` message) and the
    `device.status` action (which reads it to answer "quanto está o
    volume?"). Single tablet per home, so one shared value is enough."""

    def __init__(self) -> None:
        self.state: dict[str, int] = {}

    def summary(self) -> str | None:
        parts = []
        if "volume" in self.state:
            parts.append(f"volume em {self.state['volume']}%")
        if "brightness" in self.state:
            parts.append(f"brilho em {self.state['brightness']}%")
        return ", ".join(parts) or None


def _step_direction(direction: str) -> int | None:
    key = direction.strip().casefold()
    if key in _UP:
        return 1
    if key in _DOWN:
        return -1
    return None


def register(registry: ActionRegistry, status: DeviceStatusSource | None = None) -> None:
    async def read_status() -> ActionOutcome:
        summary = status.summary() if status is not None else None
        if summary is None:
            return ActionOutcome(success=False, message="Ainda não consegui ler o estado do tablet")
        return ActionOutcome(success=True, message=f"Tá com {summary}")

    registry.register(ActionSpec(
        name="device.status",
        description=(
            "Read the tablet's current volume and screen brightness "
            "('quanto está o volume?', 'como está o brilho?', 'qual o volume atual?')"
        ),
        handler=read_status,
        risk_level=RiskLevel.LOW,
    ))

    def make_set(control: str):
        async def handler(level: int) -> ActionOutcome:
            if isinstance(level, bool) or not 0 <= int(level) <= 100:
                return ActionOutcome(success=False, message="Me diz um valor de 0 a 100")
            return ActionOutcome(
                success=True,
                message=f"Deixei {_LABELS[control]} em {int(level)}%",
                data={"control": control, "mode": "set", "value": int(level)},
            )
        return handler

    def make_step(control: str):
        async def handler(direction: str) -> ActionOutcome:
            sign = _step_direction(direction)
            if sign is None:
                return ActionOutcome(success=False, message="Aumentar ou diminuir?")
            word = "Aumentei" if sign > 0 else "Diminuí"
            return ActionOutcome(
                success=True,
                message=f"{word} {_LABELS[control]}",
                data={"control": control, "mode": "step", "value": sign * STEP_PERCENT},
            )
        return handler

    for control, noun in (("volume", "the tablet's speaker volume"), ("brightness", "the tablet's screen brightness")):
        registry.register(ActionSpec(
            name=f"device.set_{control}",
            description=f"Set {noun} to an exact percentage, level 0-100 (e.g. 'volume em 50')",
            handler=make_set(control),
            parameters={"level": int},
            risk_level=RiskLevel.LOW,
        ))
        registry.register(ActionSpec(
            name=f"device.change_{control}",
            description=(
                f"Raise or lower {noun} a bit from where it is now ('aumenta o "
                f"{'volume' if control == 'volume' else 'brilho'}', 'tá alto/baixo/escuro/claro demais'); "
                "direction is 'up' or 'down'"
            ),
            handler=make_step(control),
            parameters={"direction": str},
            risk_level=RiskLevel.LOW,
        ))
