"""Regla determinista para recomendar ropa y abrigo."""

from typing import Literal

from app.advice.models import Advice, AdviceKind, Reason
from app.advice.rules_config import (
    CLOTHING_LEVELS,
    TEMPERATURE_RANGE_C,
    WIND_ADJUSTMENT_KMH,
    ClothingLevel,
)
from app.advice.umbrella import DAILY_CAVEAT, umbrella_verdict
from app.clients.weather_api import DailyForecast

ReferenceSource = Literal["feels_like", "daily_average"]


def select_clothing_level(reference_temperature_c: float) -> ClothingLevel:
    """Busca el nivel de abrigo que corresponde a la temperatura de referencia."""
    for level in CLOTHING_LEVELS:
        if reference_temperature_c >= level.min_temperature_c:
            return level
    return CLOTHING_LEVELS[-1]


def _colder_level(level: ClothingLevel) -> ClothingLevel:
    """Devuelve un nivel más abrigado, sin pasarse del máximo."""
    index = CLOTHING_LEVELS.index(level)
    return CLOTHING_LEVELS[min(index + 1, len(CLOTHING_LEVELS) - 1)]


def evaluate_clothing(
    day: DailyForecast,
    *,
    reference_temperature_c: float,
    reference_source: ReferenceSource,
    location_label: str,
) -> Advice:
    """Construye el consejo de ropa para un día del pronóstico."""
    reference_temperature_c = round(reference_temperature_c, 1)
    base_level = select_clothing_level(reference_temperature_c)
    final_level = base_level
    summary_parts = [
        f"Temperatura de referencia {reference_temperature_c:.1f} °C: "
        f"{base_level.description}."
    ]
    reasons = [
        Reason(
            metric="reference_temperature_c",
            value=reference_temperature_c,
            unit="°C",
        )
    ]
    caveats = [DAILY_CAVEAT]

    if reference_source == "daily_average":
        caveats.append(
            "Para días futuros se usa el promedio de máxima y mínima, "
            "porque el pronóstico diario no trae sensación térmica."
        )

    if day.wind_speed_kmh >= WIND_ADJUSTMENT_KMH:
        final_level = _colder_level(base_level)
        reasons.append(
            Reason(
                metric="wind_speed_kmh",
                value=round(day.wind_speed_kmh, 1),
                unit="km/h",
            )
        )
        if final_level.verdict == base_level.verdict:
            summary_parts.append(
                f"Viento de {day.wind_speed_kmh:.1f} km/h: se mantiene el nivel "
                "más abrigado y se sugiere cortaviento."
            )
        else:
            summary_parts.append(
                f"Viento de {day.wind_speed_kmh:.1f} km/h: se pasa a "
                f"{final_level.description} y se sugiere cortaviento."
            )

    temperature_range_c = round(day.temp_max_c - day.temp_min_c, 1)
    if temperature_range_c >= TEMPERATURE_RANGE_C:
        reasons.append(
            Reason(
                metric="temperature_range_c",
                value=temperature_range_c,
                unit="°C",
            )
        )
        caveats.append(
            f"Amplitud térmica de {temperature_range_c:.1f} °C: "
            "conviene llevar una capa extra."
        )

    if umbrella_verdict(day) == "yes":
        caveats.append("Se esperan lluvias: sumá un impermeable.")

    data_sources = ["/v1/forecast"]
    if reference_source == "feels_like":
        data_sources.insert(0, "/v1/weather")

    return Advice(
        kind=AdviceKind.CLOTHING,
        verdict=final_level.verdict,
        summary=" ".join(summary_parts),
        reasons=reasons,
        target_date=day.date,
        location_label=location_label,
        data_sources=data_sources,
        caveats=caveats,
    )
