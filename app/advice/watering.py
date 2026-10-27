"""Regla determinista para decidir si conviene regar."""

from app.advice.models import Advice, AdviceKind, Reason
from app.advice.rules_config import (
    WATERING_HOT_DRY_MM,
    WATERING_HOT_TEMP_C,
    WATERING_MILD_DRY_MM,
    WATERING_MILD_TEMP_C,
    WATERING_SOIL_WET_MM,
    WATERING_UPCOMING_MM,
    WATERING_UPCOMING_PROBABILITY,
)
from app.clients.weather_api import Forecast, History

DAILY_CAVEAT = "El pronóstico es diario: no distingue mañana, tarde o noche."
HEURISTIC_CAVEAT = (
    "Es una heurística: no reemplaza un balance hídrico real "
    "(la evapotranspiración sería más exacta)."
)


def evaluate_watering(
    history: History,
    forecast: Forecast,
    location_label: str,
) -> Advice:
    """Construye el consejo de riego con histórico y pronóstico diario."""
    today = forecast.days[0]
    rain_72h_mm = round(
        sum(day.precipitation_mm for day in history.days),
        1,
    )
    next_48h = forecast.days[:2]
    upcoming_rain = next(
        (
            day
            for day in next_48h
            if (day.precipitation_probability or 0) >= WATERING_UPCOMING_PROBABILITY
            and day.precipitation_mm >= WATERING_UPCOMING_MM
        ),
        None,
    )
    upcoming_rain_is_reason = False

    if rain_72h_mm >= WATERING_SOIL_WET_MM:
        verdict = "no"
        summary = (
            f"Lluvia acumulada de {rain_72h_mm:.1f} mm en 72 h: no se recomienda regar."
        )
    elif upcoming_rain is not None:
        verdict = "no"
        upcoming_rain_is_reason = True
        summary = (
            f"Se esperan {upcoming_rain.precipitation_mm:.1f} mm con "
            f"{upcoming_rain.precipitation_probability}% de probabilidad en las "
            "próximas 48 h: conviene esperar antes de regar."
        )
    elif today.temp_max_c >= WATERING_HOT_TEMP_C and rain_72h_mm < WATERING_HOT_DRY_MM:
        verdict = "yes"
        summary = (
            f"Lluvia acumulada de {rain_72h_mm:.1f} mm en 72 h y máxima de "
            f"{today.temp_max_c:.1f} °C: se recomienda riego profundo temprano "
            "o al atardecer."
        )
    elif (
        today.temp_max_c >= WATERING_MILD_TEMP_C and rain_72h_mm < WATERING_MILD_DRY_MM
    ):
        verdict = "maybe"
        summary = (
            f"Lluvia acumulada de {rain_72h_mm:.1f} mm en 72 h y máxima de "
            f"{today.temp_max_c:.1f} °C: regar solo si la tierra está seca."
        )
    else:
        verdict = "no"
        summary = (
            f"Lluvia acumulada de {rain_72h_mm:.1f} mm en 72 h y máxima de "
            f"{today.temp_max_c:.1f} °C: no se recomienda regar."
        )

    reasons = [
        Reason(metric="rain_72h_mm", value=rain_72h_mm, unit="mm"),
        Reason(
            metric="temp_max_c",
            value=round(today.temp_max_c, 1),
            unit="°C",
        ),
    ]
    if upcoming_rain is not None and upcoming_rain_is_reason:
        reasons.extend(
            [
                Reason(
                    metric="forecast_precipitation_probability",
                    value=upcoming_rain.precipitation_probability or 0,
                    unit="%",
                ),
                Reason(
                    metric="forecast_precipitation_mm",
                    value=round(upcoming_rain.precipitation_mm, 1),
                    unit="mm",
                ),
            ]
        )

    return Advice(
        kind=AdviceKind.WATERING,
        verdict=verdict,
        summary=summary,
        reasons=reasons,
        target_date=today.date,
        location_label=location_label,
        data_sources=["/v1/history", "/v1/forecast"],
        caveats=[DAILY_CAVEAT, HEURISTIC_CAVEAT],
    )
