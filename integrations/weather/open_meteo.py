"""Free weather provider backed by Open-Meteo's public forecast API."""
from __future__ import annotations

import asyncio
import json
import time
from urllib.parse import urlencode
from urllib.request import urlopen

from integrations.weather.base import DailyWeatherForecast, WeatherProvider, WeatherSnapshot
from memory.repository import Repository


class LocationNotConfiguredError(RuntimeError):
    pass


class OpenMeteoWeatherProvider(WeatherProvider):
    def __init__(
        self,
        latitude: float | None = None,
        longitude: float | None = None,
        location: str = "",
        timeout: float = 6,
        repository: Repository | None = None,
    ) -> None:
        self.latitude = latitude
        self.longitude = longitude
        self.location = location
        self.timeout = timeout
        self.repository = repository
        self._cached: WeatherSnapshot | None = None
        self._cached_at = 0.0
        self._restore_location()

    async def get_current_weather(self) -> WeatherSnapshot:
        if self.latitude is None or self.longitude is None:
            raise LocationNotConfiguredError("robot location is not configured")
        if self._cached is not None and time.monotonic() - self._cached_at < 600:
            return self._cached
        return await asyncio.to_thread(self._fetch)

    async def set_location(self, name: str) -> str:
        resolved = await asyncio.to_thread(self._geocode, name)
        self.latitude = float(resolved["latitude"])
        self.longitude = float(resolved["longitude"])
        state = resolved.get("admin1")
        self.location = f"{resolved['name']}, {state}" if state else str(resolved["name"])
        self._cached = None
        self._cached_at = 0
        if self.repository is not None:
            stored = {
                "name": self.location,
                "latitude": self.latitude,
                "longitude": self.longitude,
            }
            existing = self.repository.all()
            if existing:
                self.repository.update(str(existing[0]["id"]), stored)
            else:
                self.repository.add(stored)
        return self.location

    async def get_daily_forecast(self, day_offset: int = 1) -> DailyWeatherForecast:
        if self.latitude is None or self.longitude is None:
            raise LocationNotConfiguredError("robot location is not configured")
        return await asyncio.to_thread(self._fetch_daily, day_offset)

    def _fetch_daily(self, day_offset: int) -> DailyWeatherForecast:
        requested = max(0, min(day_offset, 6))
        query = urlencode({
            "latitude": self.latitude,
            "longitude": self.longitude,
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "forecast_days": requested + 1,
            "timezone": "auto",
        })
        with urlopen(f"https://api.open-meteo.com/v1/forecast?{query}", timeout=self.timeout) as response:
            payload = json.load(response)
        daily = payload["daily"]
        return DailyWeatherForecast(
            date=str(daily["time"][requested]),
            minimum_temperature=float(daily["temperature_2m_min"][requested]),
            maximum_temperature=float(daily["temperature_2m_max"][requested]),
            condition=_condition_from_wmo(int(daily["weather_code"][requested])),
            precipitation_probability=int(daily["precipitation_probability_max"][requested]),
            location=self.location,
        )

    def _geocode(self, name: str) -> dict:
        query = urlencode({"name": name, "count": 1, "language": "pt", "format": "json"})
        with urlopen(f"https://geocoding-api.open-meteo.com/v1/search?{query}", timeout=self.timeout) as response:
            payload = json.load(response)
        results = payload.get("results", [])
        if not results:
            raise ValueError(f"location not found: {name}")
        return results[0]

    def _restore_location(self) -> None:
        if self.repository is None:
            return
        stored = self.repository.all()
        if not stored:
            return
        location = stored[0]
        self.location = str(location.get("name", self.location))
        self.latitude = float(location["latitude"])
        self.longitude = float(location["longitude"])

    def _fetch(self) -> WeatherSnapshot:
        query = urlencode({
            "latitude": self.latitude,
            "longitude": self.longitude,
            "current": "temperature_2m,apparent_temperature,is_day,weather_code,precipitation",
            "hourly": "precipitation_probability",
            "forecast_days": 1,
            "timezone": "auto",
        })
        with urlopen(f"https://api.open-meteo.com/v1/forecast?{query}", timeout=self.timeout) as response:
            payload = json.load(response)
        current = payload["current"]
        hourly = payload.get("hourly", {})
        probabilities = hourly.get("precipitation_probability", [])
        probability = max((int(value) for value in probabilities if value is not None), default=None)
        snapshot = WeatherSnapshot(
            temperature=float(current["temperature_2m"]),
            apparent_temperature=float(current["apparent_temperature"]),
            condition=_condition_from_wmo(int(current["weather_code"])),
            is_dark=not bool(current["is_day"]),
            precipitation_probability=probability,
            location=self.location,
        )
        self._cached = snapshot
        self._cached_at = time.monotonic()
        return snapshot


def _condition_from_wmo(code: int) -> str:
    if code == 0:
        return "clear"
    if code in {1, 2, 3, 45, 48}:
        return "cloudy"
    if code in {51, 53, 55, 56, 57}:
        return "drizzle"
    if code in {61, 63, 65, 66, 67, 80, 81, 82}:
        return "rain"
    if code in {71, 73, 75, 77, 85, 86}:
        return "snow"
    if code in {95, 96, 99}:
        return "storm"
    return "cloudy"
