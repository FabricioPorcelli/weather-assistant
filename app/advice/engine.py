"""Orquestador del motor de consejos.

Este módulo decide qué datos pedir a weather-api y delega la decisión en una
regla pura. Las reglas no hacen HTTP: reciben datos y devuelven un `Advice`.
"""

from datetime import date, timedelta

from app.advice.clothing import evaluate_clothing
from app.advice.errors import InvalidAdviceRequest, OutOfRangeError
from app.advice.models import Advice, AdviceKind
from app.advice.umbrella import evaluate_umbrella
from app.advice.watering import evaluate_watering
from app.clients.weather_api import (
    MAX_FORECAST_DAYS,
    DailyForecast,
    Forecast,
    Location,
    WeatherApiClient,
)

WATERING_FORECAST_DAYS = 2
WATERING_HISTORY_DAYS = 3


def _location_label(location: Location, resolved_location: str) -> str:
    """Prioriza el texto que eligió el usuario sobre el que devuelve la API."""
    return location.label or resolved_location


def _resolve_day(forecast: Forecast, target_date: date | None) -> DailyForecast:
    """Busca el día pedido; si no está en el pronóstico, no lo inventa."""
    if target_date is None:
        return forecast.days[0]

    for day in forecast.days:
        if day.date == target_date:
            return day

    raise OutOfRangeError(
        f"La fecha {target_date.isoformat()} no está dentro del pronóstico disponible"
    )


async def build_advice(
    kind: AdviceKind,
    location: Location,
    client: WeatherApiClient,
    *,
    target_date: date | None = None,
    comfort_offset_c: float = 0.0,
) -> Advice:
    """Genera el consejo pedido consultando solo los datos necesarios."""
    if kind == AdviceKind.WATERING:
        if target_date is not None:
            raise InvalidAdviceRequest(
                "El consejo de riego no acepta una fecha: siempre usa hoy"
            )
        return await _build_watering(location, client)

    if kind == AdviceKind.UMBRELLA:
        forecast = await client.get_forecast(location, days=MAX_FORECAST_DAYS)
        day = _resolve_day(forecast, target_date)
        return evaluate_umbrella(day, _location_label(location, forecast.location))

    if kind == AdviceKind.CLOTHING:
        forecast = await client.get_forecast(location, days=MAX_FORECAST_DAYS)
        day = _resolve_day(forecast, target_date)
        is_today = day.date == forecast.days[0].date

        if is_today:
            current = await client.get_current(location)
            reference_temperature_c = current.feels_like_c + comfort_offset_c
            reference_source = "feels_like"
        else:
            reference_temperature_c = (
                day.temp_max_c + day.temp_min_c
            ) / 2 + comfort_offset_c
            reference_source = "daily_average"

        return evaluate_clothing(
            day,
            reference_temperature_c=reference_temperature_c,
            reference_source=reference_source,
            location_label=_location_label(location, forecast.location),
        )

    raise InvalidAdviceRequest(f"Tipo de consejo no soportado: {kind}")


async def _build_watering(location: Location, client: WeatherApiClient) -> Advice:
    """Obtiene el histórico y el pronóstico que necesita la regla de riego."""
    forecast = await client.get_forecast(location, days=WATERING_FORECAST_DAYS)
    today = forecast.days[0].date
    history = await client.get_history(
        location,
        start=today - timedelta(days=WATERING_HISTORY_DAYS),
        end=today - timedelta(days=1),
    )
    return evaluate_watering(
        history,
        forecast,
        _location_label(location, forecast.location),
    )
