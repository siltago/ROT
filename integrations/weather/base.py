from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class WeatherSnapshot:
    temperature: float
    condition: str
    is_dark: bool | None = None
    apparent_temperature: float | None = None
    precipitation_probability: int | None = None
    location: str | None = None


@dataclass(frozen=True)
class DailyWeatherForecast:
    date: str
    minimum_temperature: float
    maximum_temperature: float
    condition: str
    precipitation_probability: int | None = None
    location: str | None = None


class WeatherProvider(ABC):
    @abstractmethod
    async def get_current_weather(self) -> WeatherSnapshot: ...
