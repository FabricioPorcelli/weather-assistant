"""Orquesta consultas a weather-api y reglas puras."""

from datetime import date, timedelta

from app.advice.activities import (
    ACTIVITY_PROFILES,
    activity_caveats,
    confidence_for_offset,
    evaluate_activity_day,
)
from app.advice.best_day import clip_range, range_caveat, rank_evaluations
from app.advice.clothing import evaluate_clothing
from app.advice.errors import InvalidAdviceRequest, OutOfRangeError
from app.advice.models import (
    ActivityId,
    Advice,
    AdviceKind,
    BestDayResult,
    Confidence,
    DateRange,
    DayEvaluation,
)
from app.advice.umbrella import evaluate_umbrella
from app.advice.watering import evaluate_watering
from app.clients.weather_api import (
    MAX_FORECAST_DAYS,
    DailyForecast,
    Forecast,
    Location,
    WeatherApi,
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


def _require_activity(activity: ActivityId) -> None:
    """Falla antes de hacer HTTP si la actividad no está soportada."""
    if activity not in ACTIVITY_PROFILES:
        raise InvalidAdviceRequest(f"Actividad no soportada: {activity}")


def _confidence_for_day(forecast: Forecast, day: DailyForecast) -> Confidence:
    """Calcula la confianza según la distancia con el primer día del pronóstico."""
    offset_days = (day.date - forecast.days[0].date).days
    return confidence_for_offset(offset_days)


def _next_day_probability(
    forecast: Forecast,
    day: DailyForecast,
) -> int | None:
    """Busca la probabilidad del día siguiente dentro del pronóstico."""
    next_date = day.date + timedelta(days=1)
    for candidate in forecast.days:
        if candidate.date == next_date:
            return candidate.precipitation_probability
    return None


async def _previous_day_precipitation(
    day: DailyForecast,
    forecast: Forecast,
    location: Location,
    client: WeatherApi,
) -> float:
    """Obtiene la lluvia del día anterior desde pronóstico o histórico."""
    previous_date = day.date - timedelta(days=1)
    for candidate in forecast.days:
        if candidate.date == previous_date:
            return candidate.precipitation_mm

    history = await client.get_history(
        location,
        start=previous_date,
        end=previous_date,
    )
    return history.days[0].precipitation_mm


async def build_advice(
    kind: AdviceKind,
    location: Location,
    client: WeatherApi,
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


async def _build_watering(location: Location, client: WeatherApi) -> Advice:
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


async def evaluate_activity(
    activity: ActivityId,
    location: Location,
    client: WeatherApi,
    target_date: date,
) -> DayEvaluation:
    """Evalúa una actividad para un día concreto."""
    _require_activity(activity)
    forecast = await client.get_forecast(location, days=MAX_FORECAST_DAYS)
    day = _resolve_day(forecast, target_date)

    previous_rain_mm = 0.0
    next_day_probability = None
    if activity == ActivityId.EXTERIOR_PAINTING:
        previous_rain_mm = await _previous_day_precipitation(
            day,
            forecast,
            location,
            client,
        )
        next_day_probability = _next_day_probability(forecast, day)

    return evaluate_activity_day(
        activity,
        day,
        confidence=_confidence_for_day(forecast, day),
        previous_day_precipitation_mm=previous_rain_mm,
        next_day_precipitation_probability=next_day_probability,
    )


async def find_best_day(
    activity: ActivityId,
    location: Location,
    client: WeatherApi,
    start: date,
    end: date,
    top_n: int = 3,
) -> BestDayResult:
    """Evalúa un rango y devuelve el ranking de mejores días."""
    _require_activity(activity)
    if start > end:
        raise InvalidAdviceRequest("start no puede ser posterior a end")
    if top_n < 1:
        raise InvalidAdviceRequest("top_n debe ser al menos 1")

    forecast = await client.get_forecast(location, days=MAX_FORECAST_DAYS)
    effective_start, effective_end, was_clipped = clip_range(forecast, start, end)
    days = [
        day for day in forecast.days if effective_start <= day.date <= effective_end
    ]

    evaluations = []
    for day in days:
        previous_rain_mm = 0.0
        next_day_probability = None
        if activity == ActivityId.EXTERIOR_PAINTING:
            previous_rain_mm = await _previous_day_precipitation(
                day,
                forecast,
                location,
                client,
            )
            next_day_probability = _next_day_probability(forecast, day)

        evaluations.append(
            evaluate_activity_day(
                activity,
                day,
                confidence=_confidence_for_day(forecast, day),
                previous_day_precipitation_mm=previous_rain_mm,
                next_day_precipitation_probability=next_day_probability,
            )
        )

    ranking, has_acceptable_day = rank_evaluations(evaluations, top_n)
    caveats = activity_caveats(activity)
    if was_clipped:
        caveats.append(range_caveat(start, end, effective_start, effective_end))

    return BestDayResult(
        activity=activity,
        location_label=_location_label(location, forecast.location),
        range=DateRange(start=effective_start, end=effective_end),
        ranking=ranking,
        has_acceptable_day=has_acceptable_day,
        caveats=caveats,
    )
