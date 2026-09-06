from __future__ import annotations

from actions.registry import ActionRegistry, ActionSpec
from brain.models import ActionOutcome, RiskLevel
from integrations.weather.open_meteo import LocationNotConfiguredError, OpenMeteoWeatherProvider


def register(registry: ActionRegistry, provider: OpenMeteoWeatherProvider, location_name: str = "") -> None:
    async def get_weather() -> ActionOutcome:
        try:
            snapshot = await provider.get_current_weather()
        except LocationNotConfiguredError:
            return ActionOutcome(
                success=False,
                message="Ainda não sei onde estou. Em qual cidade eu estou?",
                data={"location_required": True},
            )
        except Exception:
            return ActionOutcome(success=False, message="Não consegui consultar a previsão agora.")
        label = snapshot.location or location_name
        place = f" em {label}" if label else ""
        rain = (
            f" A chance de chuva chega a {snapshot.precipitation_probability}%."
            if snapshot.precipitation_probability is not None else ""
        )
        condition = _condition_text(snapshot.condition, snapshot.is_dark)
        feel = _temperature_feel(snapshot.temperature)
        return ActionOutcome(
            success=True,
            message=(
                f"Agora está fazendo {round(snapshot.temperature)} graus{place}. "
                f"{condition} e o tempo está {feel}.{rain}"
            ),
            data={
                "temperature": snapshot.temperature,
                "apparent_temperature": snapshot.apparent_temperature,
                "condition": snapshot.condition,
                "is_dark": snapshot.is_dark,
                "precipitation_probability": snapshot.precipitation_probability,
                "location": label,
            },
        )

    async def set_location(city: str) -> ActionOutcome:
        cleaned = city.strip().rstrip(".?!")
        if len(cleaned) < 2:
            return ActionOutcome(success=False, message="Me diga o nome da cidade.")
        try:
            resolved = await provider.set_location(cleaned)
            snapshot = await provider.get_current_weather()
        except Exception:
            return ActionOutcome(success=False, message=f"Não encontrei a cidade {cleaned}.")
        return ActionOutcome(
            success=True,
            message=f"Entendi. Estou em {resolved}, e agora está fazendo {round(snapshot.temperature)} graus.",
            data={
                "location": resolved,
                "temperature": snapshot.temperature,
                "apparent_temperature": snapshot.apparent_temperature,
                "condition": snapshot.condition,
                "is_dark": snapshot.is_dark,
                "precipitation_probability": snapshot.precipitation_probability,
            },
        )

    async def get_forecast(day_offset: int = 1) -> ActionOutcome:
        try:
            forecast = await provider.get_daily_forecast(day_offset)
        except LocationNotConfiguredError:
            return ActionOutcome(
                success=False,
                message="Ainda não sei onde estou. Em qual cidade eu estou?",
                data={"location_required": True},
            )
        except Exception:
            return ActionOutcome(success=False, message="Não consegui consultar a previsão de amanhã agora.")
        place = f" em {forecast.location}" if forecast.location else ""
        condition = _forecast_condition_text(forecast.condition)
        rain = (
            f", com {forecast.precipitation_probability}% de chance de chuva"
            if forecast.precipitation_probability is not None else ""
        )
        return ActionOutcome(
            success=True,
            message=(
                f"Amanhã{place}, a mínima será {round(forecast.minimum_temperature)} e a máxima "
                f"{round(forecast.maximum_temperature)} graus. {condition}{rain}."
            ),
            data={
                "date": forecast.date,
                "minimum_temperature": forecast.minimum_temperature,
                "maximum_temperature": forecast.maximum_temperature,
                "condition": forecast.condition,
                "precipitation_probability": forecast.precipitation_probability,
                "location": forecast.location,
                "period_label": "AMANHÃ",
            },
        )

    registry.register(ActionSpec(
        name="weather.get",
        description="Get current weather for the robot location",
        handler=get_weather,
        risk_level=RiskLevel.LOW,
    ))
    registry.register(ActionSpec(
        name="weather.set_location",
        description="Set the robot location after an explicit user statement",
        handler=set_location,
        parameters={"city": str},
        risk_level=RiskLevel.LOW,
    ))
    registry.register(ActionSpec(
        name="weather.forecast",
        description="Get the weather forecast for a future day",
        handler=get_forecast,
        parameters={"day_offset": int},
        risk_level=RiskLevel.LOW,
    ))


def _condition_text(condition: str, is_dark: bool | None) -> str:
    normalized = condition.casefold()
    if normalized == "clear":
        return "O céu está limpo" if is_dark else "O céu está ensolarado"
    if normalized == "cloudy":
        return "O céu está nublado"
    if normalized == "drizzle":
        return "Está garoando"
    if normalized == "rain":
        return "Está chovendo"
    if normalized == "storm":
        return "Há tempestade"
    if normalized == "snow":
        return "Está nevando"
    return "O tempo está estável"


def _temperature_feel(temperature: float) -> str:
    if temperature <= 15:
        return "frio"
    if temperature <= 22:
        return "fresco"
    if temperature <= 28:
        return "agradável"
    return "quente"


def _forecast_condition_text(condition: str) -> str:
    return {
        "clear": "O céu deve ficar limpo",
        "cloudy": "O céu deve ficar nublado",
        "drizzle": "Pode garoar",
        "rain": "Há previsão de chuva",
        "storm": "Há previsão de tempestade",
        "snow": "Há previsão de neve",
    }.get(condition.casefold(), "O tempo deve ficar estável")
