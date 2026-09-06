"""Deterministic presentation planning for screen-capable robot clients.

The planner turns already validated action outcomes into semantic scene
recipes.  It never executes an action and never emits renderer-specific code.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from brain.agent import TurnResult


@dataclass(frozen=True)
class SceneSpec:
    kind: str
    variant: str = "default"
    data: dict[str, Any] = field(default_factory=dict)
    duration_ms: int | None = 3000
    persistent: bool = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "variant": self.variant,
            "data": self.data,
            "persistent": self.persistent,
            **({"duration_ms": self.duration_ms} if self.duration_ms is not None else {}),
        }


class PresentationPlanner:
    """Select a full-screen scene only when structured output benefits from it."""

    def plan(self, result: TurnResult) -> SceneSpec | None:
        for record in result.action_records:
            outcome = record.outcome
            if outcome is None or not outcome.success:
                continue
            if record.name == "time.get" and outcome.data.get("time"):
                return SceneSpec(kind="clock", data=outcome.data, duration_ms=3000)
            if record.name == "date.get" and outcome.data.get("date"):
                return SceneSpec(kind="date", data={"date": outcome.data["date"]})
            if record.name in {"weather.get", "weather.forecast", "weather.set_location"} and (
                outcome.data.get("temperature") is not None
                or outcome.data.get("minimum_temperature") is not None
            ):
                condition = str(outcome.data.get("condition", "cloudy")).lower()
                variant = self._weather_variant(condition, is_dark=outcome.data.get("is_dark") is True)
                return SceneSpec(kind="weather", variant=variant, data=outcome.data, duration_ms=10000)
            if record.name == "music.play":
                return SceneSpec(
                    kind="music",
                    variant=str(outcome.data.get("mode", "player")),
                    data=outcome.data,
                    duration_ms=None,
                    persistent=True,
                )
            if record.name == "music.stop":
                return None
        return None

    @staticmethod
    def _weather_variant(condition: str, *, is_dark: bool = False) -> str:
        if any(word in condition for word in ("storm", "thunder", "tempest")):
            return "storm"
        if any(word in condition for word in ("rain", "drizzle", "chuva", "garoa")):
            return "rain"
        if any(word in condition for word in ("clear", "sun", "limpo", "sol")):
            return "night" if is_dark else "sunny"
        return "cloudy"
