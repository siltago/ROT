"""Useful low-latency actions that do not require hardware or network APIs."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from actions.registry import ActionRegistry, ActionSpec
from brain.models import ActionOutcome, RiskLevel
from integrations.weather.base import WeatherProvider


async def get_time(timezone_name: str | None = None) -> ActionOutcome:
    try:
        timezone = ZoneInfo(timezone_name) if timezone_name else None
    except ZoneInfoNotFoundError:
        timezone = None
    now = datetime.now(timezone).astimezone() if timezone is None else datetime.now(timezone)
    value = now.strftime("%H:%M")
    spoken_time = _spoken_time(now.hour, now.minute)
    period = "dawn" if 5 <= now.hour < 8 else "day" if 8 <= now.hour < 18 else "night"
    return ActionOutcome(
        success=True,
        message=spoken_time,
        data={
            "time": value,
            "seconds": now.second,
            "date": now.strftime("%d/%m/%Y"),
            "weekday": now.weekday(),
            "period": period,
            "timezone": timezone_name or str(now.tzinfo),
        },
    )


def _spoken_time(hour_24: int, minute: int) -> str:
    hour = hour_24 % 12 or 12
    minute_text = (
        "em ponto"
        if minute == 0
        else f"e {minute} minuto" if minute == 1 else f"e {minute} minutos"
    )
    return f"É uma hora {minute_text}" if hour == 1 else f"São {hour} horas {minute_text}"


async def get_date() -> ActionOutcome:
    now = datetime.now().astimezone()
    value = now.strftime("%d/%m/%Y")
    return ActionOutcome(success=True, message=f"Hoje é {value}", data={"date": value})


async def system_status() -> ActionOutcome:
    return ActionOutcome(success=True, message="Estou funcionando normalmente", data={"status": "ok"})


def register(
    registry: ActionRegistry,
    timezone_name: str | None = None,
    weather_provider: WeatherProvider | None = None,
) -> None:
    async def configured_time() -> ActionOutcome:
        outcome = await get_time(timezone_name)
        if weather_provider is not None:
            try:
                weather = await weather_provider.get_current_weather()
                outcome.data.update({
                    "temperature": weather.temperature,
                    "condition": weather.condition,
                    "is_dark": weather.is_dark,
                    "location": weather.location,
                })
            except Exception:
                pass
        return outcome

    registry.register(ActionSpec(
        name="time.get", description="Get the local current time", handler=configured_time,
        risk_level=RiskLevel.LOW,
    ))
    registry.register(ActionSpec(
        name="date.get", description="Get the local current date", handler=get_date,
        risk_level=RiskLevel.LOW,
    ))
    registry.register(ActionSpec(
        name="system.status", description="Get the robot software status", handler=system_status,
        risk_level=RiskLevel.LOW,
    ))
