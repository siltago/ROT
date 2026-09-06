"""Typed, in-process events used by cognition and perception adapters."""
from __future__ import annotations

import asyncio
import inspect
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class EventType(StrEnum):
    PERSON_DETECTED = "person_detected"
    PERSON_LOST = "person_lost"
    UNKNOWN_PERSON_DETECTED = "unknown_person_detected"
    NEW_OBJECT_DETECTED = "new_object_detected"
    UNUSUAL_EVENT = "unusual_event"
    USER_STARTED_SPEAKING = "user_started_speaking"
    USER_STOPPED_SPEAKING = "user_stopped_speaking"
    USER_SPOKE = "user_spoke"
    CONVERSATION_STARTED = "conversation_started"
    CONVERSATION_ENDED = "conversation_ended"
    WEATHER_UPDATED = "weather_updated"
    TEMPERATURE_CHANGED = "temperature_changed"
    TIME_TICK = "time_tick"
    MINUTE_TICK = "minute_tick"
    HOUR_CHANGED = "hour_changed"
    DAY_PERIOD_CHANGED = "day_period_changed"
    IDLE_TIMEOUT = "idle_timeout"
    USER_RETURNED = "user_returned"
    USER_LEFT = "user_left"
    DEVICE_CONNECTED = "device_connected"
    DEVICE_DISCONNECTED = "device_disconnected"
    BATTERY_LOW = "battery_low"
    ACTION_COMPLETED = "action_completed"
    ACTION_FAILED = "action_failed"
    ROBOT_RESPONSE_FINISHED = "robot_response_finished"
    INITIATIVE_PROPOSED = "initiative_proposed"
    INITIATIVE_SUPPRESSED = "initiative_suppressed"
    INITIATIVE_STARTED = "initiative_started"
    INITIATIVE_COMPLETED = "initiative_completed"


class RobotEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    type: EventType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "internal"
    data: dict[str, Any] = Field(default_factory=dict)


EventHandler = Callable[[RobotEvent], None | Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[EventType | str, list[EventHandler]] = defaultdict(list)
        self.handler_errors = 0

    def subscribe(self, event_type: EventType | str, handler: EventHandler) -> Callable[[], None]:
        key = self._key(event_type)
        self._handlers[key].append(handler)

        def unsubscribe() -> None:
            if handler in self._handlers[key]:
                self._handlers[key].remove(handler)

        return unsubscribe

    def publish(self, event: RobotEvent | EventType | str, data: dict[str, Any] | None = None, *, source: str = "internal") -> RobotEvent:
        robot_event = self._coerce(event, data, source)
        for handler in self._subscribers(robot_event.type):
            try:
                result = handler(robot_event)
                if inspect.isawaitable(result):
                    task = asyncio.get_running_loop().create_task(result)
                    task.add_done_callback(self._capture_task_error)
            except Exception:
                self._record_error(robot_event)
        return robot_event

    async def publish_async(self, event: RobotEvent | EventType | str, data: dict[str, Any] | None = None, *, source: str = "internal") -> RobotEvent:
        robot_event = self._coerce(event, data, source)
        for handler in self._subscribers(robot_event.type):
            try:
                result = handler(robot_event)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                self._record_error(robot_event)
        return robot_event

    def _subscribers(self, event_type: EventType) -> list[EventHandler]:
        return [*self._handlers.get(event_type, []), *self._handlers.get("*", [])]

    @staticmethod
    def _key(event_type: EventType | str) -> EventType | str:
        if event_type == "*":
            return "*"
        return event_type if isinstance(event_type, EventType) else EventType(event_type)

    @staticmethod
    def _coerce(event: RobotEvent | EventType | str, data: dict[str, Any] | None, source: str) -> RobotEvent:
        if isinstance(event, RobotEvent):
            return event
        return RobotEvent(type=EventType(event), source=source, data=data or {})

    def _capture_task_error(self, task: asyncio.Task[None]) -> None:
        try:
            task.result()
        except Exception:
            self.handler_errors += 1
            logger.exception("event_subscriber_failed", extra={"component": "event_bus"})

    def _record_error(self, event: RobotEvent) -> None:
        self.handler_errors += 1
        logger.exception("event_subscriber_failed", extra={"event_id": event.id, "event_type": event.type.value})
