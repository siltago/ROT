"""Slow-changing internal motivations, distinct from emotion and personality."""
from dataclasses import dataclass

from brain.cognition_config import CognitionConfig
from brain.events import EventType, RobotEvent


def clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


@dataclass
class DriveState:
    curiosity: float = 0.55
    social: float = 0.45
    helpfulness: float = 0.70
    playfulness: float = 0.45
    rest: float = 0.10

    def clamp_all(self) -> None:
        for name in ("curiosity", "social", "helpfulness", "playfulness", "rest"):
            setattr(self, name, clamp(getattr(self, name)))


class DriveEngine:
    def __init__(self, state: DriveState | None = None, config: CognitionConfig = CognitionConfig()) -> None:
        self.state = state or DriveState()
        self.config = config

    def apply_event(self, event: RobotEvent) -> DriveState:
        rates = self.config.drive_rates
        if event.type in (EventType.UNKNOWN_PERSON_DETECTED, EventType.NEW_OBJECT_DETECTED, EventType.UNUSUAL_EVENT):
            self.state.curiosity += rates.curiosity_novelty
        elif event.type == EventType.IDLE_TIMEOUT:
            self.state.social += rates.social_idle_per_hour * max(0.0, float(event.data.get("idle_seconds", 0))) / 3600
        elif event.type == EventType.USER_SPOKE and bool(event.data.get("help_request")):
            self.state.helpfulness += rates.helpfulness_request
        elif event.type == EventType.INITIATIVE_COMPLETED:
            self.state.social -= rates.initiative_social_relief
        self.state.clamp_all()
        return self.state

    def advance(self, seconds: float, *, active: bool = True) -> DriveState:
        hours = max(0.0, seconds) / 3600
        rate = self.config.drive_rates.decay_per_hour * hours
        for name in ("curiosity", "social", "helpfulness", "playfulness"):
            value = getattr(self.state, name)
            setattr(self.state, name, value + (0.5 - value) * rate)
        self.state.rest += self.config.drive_rates.rest_activity_per_hour * hours if active else -rate
        self.state.clamp_all()
        return self.state
