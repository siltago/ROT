from actions.executor import ActionExecutor
from actions.permissions import PermissionPolicy, auto_deny
from actions.registry import ActionRegistry
from actions.utilities import weather
from brain.models import ActionRequest
from integrations.weather.base import DailyWeatherForecast, WeatherSnapshot
from integrations.weather.mock import MockWeatherProvider
from integrations.weather.open_meteo import OpenMeteoWeatherProvider


class _LocationProvider(OpenMeteoWeatherProvider):
    async def set_location(self, name: str) -> str:
        self.location = "Campinas, São Paulo"
        return self.location

    async def get_current_weather(self) -> WeatherSnapshot:
        return WeatherSnapshot(24.2, "clear", False, location=self.location)

    async def get_daily_forecast(self, day_offset: int = 1) -> DailyWeatherForecast:
        return DailyWeatherForecast(
            date="2026-09-03",
            minimum_temperature=15.2,
            maximum_temperature=24.4,
            condition="cloudy",
            precipitation_probability=60,
            location="Sorocaba, São Paulo",
        )


async def test_weather_without_location_fails_without_inventing_temperature() -> None:
    registry = ActionRegistry()
    weather.register(registry, OpenMeteoWeatherProvider())
    executor = ActionExecutor(registry, PermissionPolicy(confirmation_provider=auto_deny))
    record = await executor.execute(ActionRequest(name="weather.get"))
    assert record.outcome is not None and not record.outcome.success
    assert record.outcome.data["location_required"] is True


async def test_weather_returns_structured_visual_data() -> None:
    registry = ActionRegistry()
    provider = MockWeatherProvider(WeatherSnapshot(
        temperature=21.4,
        condition="rain",
        is_dark=False,
        precipitation_probability=85,
        location="Campinas",
    ))
    weather.register(registry, provider)
    executor = ActionExecutor(registry, PermissionPolicy(confirmation_provider=auto_deny))
    record = await executor.execute(ActionRequest(name="weather.get"))
    assert record.outcome is not None and record.outcome.success
    assert record.outcome.data["temperature"] == 21.4
    assert record.outcome.data["condition"] == "rain"
    assert "85%" in record.outcome.message
    assert "Agora" in record.outcome.message


async def test_setting_city_immediately_returns_weather() -> None:
    registry = ActionRegistry()
    weather.register(registry, _LocationProvider())
    executor = ActionExecutor(registry, PermissionPolicy(confirmation_provider=auto_deny))
    record = await executor.execute(ActionRequest(
        name="weather.set_location", arguments={"city": "Campinas"}
    ))
    assert record.outcome is not None and record.outcome.success
    assert record.outcome.data["temperature"] == 24.2
    assert "24 graus" in record.outcome.message


async def test_tomorrow_forecast_mentions_minimum_maximum_condition_and_rain() -> None:
    registry = ActionRegistry()
    weather.register(registry, _LocationProvider())
    executor = ActionExecutor(registry, PermissionPolicy(confirmation_provider=auto_deny))
    record = await executor.execute(ActionRequest(
        name="weather.forecast", arguments={"day_offset": 1}
    ))
    assert record.outcome is not None and record.outcome.success
    assert "mínima será 15" in record.outcome.message
    assert "máxima 24" in record.outcome.message
    assert "nublado" in record.outcome.message
    assert "60%" in record.outcome.message
