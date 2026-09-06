"""Ephemeral event-reduced belief about what is happening now."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from brain.events import EventType, RobotEvent


def period_for_hour(hour: int) -> str:
    if 6 <= hour < 12:
        return "morning"
    if 12 <= hour < 18:
        return "afternoon"
    if 18 <= hour < 23:
        return "evening"
    return "night"


@dataclass
class EnvironmentState:
    temperature: float | None = None
    previous_temperature: float | None = None
    weather_condition: str | None = None
    is_dark: bool | None = None


@dataclass
class TimeState:
    hour: int = field(default_factory=lambda: datetime.now().hour)
    period: str = field(default_factory=lambda: period_for_hour(datetime.now().hour))


@dataclass
class ActivityState:
    last_interaction_at: datetime | None = None
    idle_seconds: float = 0.0
    active_since: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class WorldState:
    conversation_active: bool = False
    user_speaking: bool = False
    robot_speaking: bool = False
    processing: bool = False
    current_person_id: str | None = None
    current_room: str | None = None
    people_present: set[str] = field(default_factory=set)
    environment: EnvironmentState = field(default_factory=EnvironmentState)
    time: TimeState = field(default_factory=TimeState)
    activity: ActivityState = field(default_factory=ActivityState)

    @property
    def current_person(self) -> str | None:
        return self.current_person_id

    @current_person.setter
    def current_person(self, value: str | None) -> None:
        self.current_person_id = value

    @property
    def current_weather(self) -> str | None:
        return self.environment.weather_condition

    @current_weather.setter
    def current_weather(self, value: str | None) -> None:
        self.environment.weather_condition = value

    @property
    def last_interaction_at(self) -> datetime | None:
        return self.activity.last_interaction_at

    def mark_user_turn(self, person_id: str | None) -> None:
        WorldStateReducer(self).apply(RobotEvent(type=EventType.USER_SPOKE, data={"person_id": person_id}))

    def finish_turn(self) -> None:
        WorldStateReducer(self).apply(RobotEvent(type=EventType.ROBOT_RESPONSE_FINISHED))


class WorldStateReducer:
    def __init__(self, state: WorldState) -> None:
        self.state = state

    def apply(self, event: RobotEvent) -> None:
        state, data, kind = self.state, event.data, event.type
        if kind in (EventType.PERSON_DETECTED, EventType.USER_RETURNED):
            person_id = str(data.get("person_id") or "unknown")
            state.people_present.add(person_id)
            state.current_person_id = person_id
        elif kind in (EventType.PERSON_LOST, EventType.USER_LEFT):
            person_id = str(data.get("person_id") or "unknown")
            state.people_present.discard(person_id)
            if state.current_person_id == person_id:
                state.current_person_id = next(iter(state.people_present), None)
        elif kind == EventType.USER_STARTED_SPEAKING:
            state.user_speaking = True
            state.conversation_active = True
        elif kind == EventType.USER_STOPPED_SPEAKING:
            state.user_speaking = False
        elif kind == EventType.CONVERSATION_STARTED:
            state.conversation_active = True
        elif kind == EventType.CONVERSATION_ENDED:
            state.conversation_active = False
        elif kind == EventType.USER_SPOKE:
            state.processing = True
            state.user_speaking = False
            state.conversation_active = True
            state.current_person_id = data.get("person_id") or state.current_person_id
            state.activity.last_interaction_at = event.timestamp
            state.activity.idle_seconds = 0.0
        elif kind == EventType.ROBOT_RESPONSE_FINISHED:
            state.processing = False
            state.robot_speaking = False
            state.activity.last_interaction_at = event.timestamp
            state.activity.idle_seconds = 0.0
        elif kind == EventType.WEATHER_UPDATED:
            if "temperature" in data:
                state.environment.previous_temperature = state.environment.temperature
                state.environment.temperature = float(data["temperature"])
            state.environment.weather_condition = data.get("condition", state.environment.weather_condition)
            if "is_dark" in data:
                state.environment.is_dark = bool(data["is_dark"])
        elif kind == EventType.TEMPERATURE_CHANGED:
            state.environment.previous_temperature = float(data.get("previous", state.environment.temperature or 0))
            state.environment.temperature = float(data["temperature"])
        elif kind in (EventType.TIME_TICK, EventType.MINUTE_TICK, EventType.HOUR_CHANGED, EventType.DAY_PERIOD_CHANGED):
            hour = int(data.get("hour", event.timestamp.astimezone().hour))
            state.time.hour = hour
            state.time.period = str(data.get("period", period_for_hour(hour)))
        elif kind == EventType.IDLE_TIMEOUT:
            state.activity.idle_seconds = float(data.get("idle_seconds", state.activity.idle_seconds))
