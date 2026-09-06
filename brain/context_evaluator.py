"""Turns raw WorldState into deterministic semantic context."""
from dataclasses import dataclass
from datetime import datetime, timezone

from brain.cognition_config import CognitionConfig
from brain.world_state import WorldState


@dataclass(frozen=True)
class DerivedContext:
    user_available: bool
    user_busy: bool
    user_recently_interacted: bool
    conversation_recent: bool
    environment_hot: bool
    environment_cold: bool
    environment_dark: bool
    social_opportunity: bool
    initiative_allowed: bool
    quiet_period: bool


class ContextEvaluator:
    def __init__(self, config: CognitionConfig = CognitionConfig()) -> None:
        self.config = config

    def evaluate(self, world: WorldState, *, now: datetime | None = None) -> DerivedContext:
        now = now or datetime.now(timezone.utc)
        last = world.activity.last_interaction_at
        elapsed = float("inf") if last is None else max(0.0, (now - last).total_seconds())
        busy = world.user_speaking or world.robot_speaking or world.processing
        present = bool(world.people_present or world.current_person_id)
        quiet = world.time.hour >= self.config.quiet_period_start_hour or world.time.hour < self.config.quiet_period_end_hour
        recent = elapsed <= self.config.recent_conversation_seconds
        temp = world.environment.temperature
        return DerivedContext(
            user_available=present and not busy, user_busy=busy,
            user_recently_interacted=recent,
            conversation_recent=world.conversation_active and recent,
            environment_hot=temp is not None and temp >= self.config.hot_temperature_celsius,
            environment_cold=temp is not None and temp <= self.config.cold_temperature_celsius,
            environment_dark=world.environment.is_dark is True,
            social_opportunity=present and not busy and elapsed >= self.config.idle_social_seconds,
            initiative_allowed=self.config.initiative_enabled and not busy and not quiet,
            quiet_period=quiet,
        )
