"""Central deterministic thresholds for Cognition v0.2."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class DriveRates:
    social_idle_per_hour: float = 0.12
    curiosity_novelty: float = 0.16
    helpfulness_request: float = 0.10
    rest_activity_per_hour: float = 0.08
    initiative_social_relief: float = 0.08
    decay_per_hour: float = 0.03


@dataclass(frozen=True)
class CognitionConfig:
    initiative_enabled: bool = True
    max_initiatives_per_hour: int = 4
    global_cooldown_seconds: float = 120.0
    minimum_proposal_priority: float = 0.35
    hot_temperature_celsius: float = 29.0
    cold_temperature_celsius: float = 16.0
    significant_temperature_delta: float = 2.0
    recent_conversation_seconds: float = 300.0
    idle_social_seconds: float = 900.0
    person_return_window_seconds: float = 1800.0
    quiet_period_start_hour: int = 23
    quiet_period_end_hour: int = 6
    proposal_ttl_seconds: float = 30.0
    # Self-entertainment doesn't need anyone present -- lower bar than
    # idle_social_seconds (which is for "ask the human to talk").
    playful_idle_seconds: float = 180.0
    sleep_idle_seconds: float = 300.0
    sleepy_rest_threshold: float = 0.75
    behavior_cooldowns: dict[str, float] = field(default_factory=lambda: {
        "GreetingBehavior": 1800.0, "WeatherBehavior": 3600.0,
        "IdleBehavior": 1200.0, "CuriosityBehavior": 600.0,
        "SocialBehavior": 900.0, "HelpfulnessBehavior": 300.0,
        "PlayfulIdleBehavior": 600.0, "SleepBehavior": 1800.0,
    })
    drive_rates: DriveRates = field(default_factory=DriveRates)
