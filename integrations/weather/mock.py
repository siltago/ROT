from integrations.weather.base import WeatherProvider, WeatherSnapshot


class MockWeatherProvider(WeatherProvider):
    def __init__(self, snapshot: WeatherSnapshot = WeatherSnapshot(25.0, "clear", False)) -> None:
        self.snapshot = snapshot

    async def get_current_weather(self) -> WeatherSnapshot:
        return self.snapshot
