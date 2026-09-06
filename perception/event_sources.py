"""Input adapters produce RobotEvent objects and never make decisions."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from brain.events import EventBus, EventType, RobotEvent
from brain.world_state import period_for_hour


class EventSource(ABC):
    def __init__(self, bus: EventBus, name: str) -> None:
        self.bus = bus
        self.name = name

    async def emit(self, event_type: EventType, data: dict[str, Any] | None = None) -> RobotEvent:
        return await self.bus.publish_async(RobotEvent(type=event_type, source=self.name, data=data or {}))

    @abstractmethod
    async def poll(self) -> list[RobotEvent]: ...


class SimulatedEventSource(EventSource):
    def __init__(self, bus: EventBus) -> None:
        super().__init__(bus, "debug_simulator")

    async def poll(self) -> list[RobotEvent]:
        return []


class ClockEventSource(EventSource):
    def __init__(self, bus: EventBus) -> None:
        super().__init__(bus, "clock")
        self._last_minute: tuple[int, int, int, int, int] | None = None
        self._last_hour: int | None = None
        self._last_period: str | None = None

    async def poll(self, now: datetime | None = None) -> list[RobotEvent]:
        now = now or datetime.now().astimezone()
        minute = (now.year, now.month, now.day, now.hour, now.minute)
        if minute == self._last_minute:
            return []
        events = [RobotEvent(type=EventType.MINUTE_TICK, source=self.name, timestamp=now, data={"hour": now.hour, "minute": now.minute})]
        period = period_for_hour(now.hour)
        if self._last_hour is not None and now.hour != self._last_hour:
            events.append(RobotEvent(type=EventType.HOUR_CHANGED, source=self.name, timestamp=now, data={"hour": now.hour}))
        if self._last_period is not None and period != self._last_period:
            events.append(RobotEvent(type=EventType.DAY_PERIOD_CHANGED, source=self.name, timestamp=now, data={"hour": now.hour, "period": period}))
        self._last_minute, self._last_hour, self._last_period = minute, now.hour, period
        for event in events:
            await self.bus.publish_async(event)
        return events
