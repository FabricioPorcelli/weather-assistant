"""Regla determinista para decidir si hace falta paraguas."""

from app.advice.models import Advice, AdviceKind, Reason
from app.advice.rules_config import (
    UMBRELLA_MAYBE_MM,
    UMBRELLA_MAYBE_PROBABILITY,
    UMBRELLA_YES_MM,
    UMBRELLA_YES_PROBABILITY,
)
from app.clients.weather_api import DailyForecast

DAILY_CAVEAT = "El pronóstico es diario: no distingue mañana, tarde o noche."


def umbrella_verdict(day: DailyForecast) -> str:
    """Devuelve `yes`, `maybe` o `no` según probabilidad y lluvia prevista."""
    probability = day.precipitation_probability or 0

    if (
        probability >= UMBRELLA_YES_PROBABILITY
        or day.precipitation_mm >= UMBRELLA_YES_MM
    ):
        return "yes"
    if (
        probability >= UMBRELLA_MAYBE_PROBABILITY
        or day.precipitation_mm >= UMBRELLA_MAYBE_MM
    ):
        return "maybe"
    return "no"


def evaluate_umbrella(day: DailyForecast, location_label: str) -> Advice:
    """Construye el consejo de paraguas para un día del pronóstico."""
    probability = day.precipitation_probability or 0
    precipitation_mm = round(day.precipitation_mm, 1)
    verdict = umbrella_verdict(day)

    if verdict == "yes":
        summary = (
            f"Probabilidad de precipitación de {probability}% y "
            f"{precipitation_mm:.1f} mm: se recomienda paraguas."
        )
    elif verdict == "maybe":
        summary = (
            f"Probabilidad de precipitación de {probability}% y "
            f"{precipitation_mm:.1f} mm: conviene un paraguas plegable o "
            "impermeable liviano."
        )
    else:
        summary = (
            f"Probabilidad de precipitación de {probability}% y "
            f"{precipitation_mm:.1f} mm: no se recomienda paraguas."
        )

    caveats = [DAILY_CAVEAT]
    if day.precipitation_probability is None:
        caveats.append(
            "weather-api no informó probabilidad de precipitación; "
            "se usó solo la lluvia prevista."
        )

    return Advice(
        kind=AdviceKind.UMBRELLA,
        verdict=verdict,
        summary=summary,
        reasons=[
            Reason(
                metric="precipitation_probability",
                value=probability,
                unit="%",
            ),
            Reason(
                metric="precipitation_mm",
                value=precipitation_mm,
                unit="mm",
            ),
        ],
        target_date=day.date,
        location_label=location_label,
        data_sources=["/v1/forecast"],
        caveats=caveats,
    )
