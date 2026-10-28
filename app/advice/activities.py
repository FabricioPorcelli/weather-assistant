"""Perfiles y puntaje de actividades al aire libre."""

from dataclasses import dataclass
from typing import Final, Literal

from app.advice.errors import InvalidAdviceRequest
from app.advice.models import (
    ActivityId,
    ActivityVerdict,
    Confidence,
    DayEvaluation,
    Reason,
)
from app.advice.rules_config import (
    ACTIVITY_ACCEPTABLE_MIN_SCORE,
    ACTIVITY_IDEAL_MIN_SCORE,
    ACTIVITY_MAX_TEMPERATURE_PENALTY,
    ACTIVITY_TEMPERATURE_PENALTY_PER_C,
    CONFIDENCE_HIGH_MAX_OFFSET,
    CONFIDENCE_MEDIUM_MAX_OFFSET,
)
from app.clients.weather_api import DailyForecast

DAILY_CAVEAT = "El pronóstico es diario: no distingue mañana, tarde o noche."
NO_HUMIDITY_CAVEAT = (
    "El pronóstico diario no incluye humedad, así que no se usa para días futuros."
)
PAINTING_SURFACE_CAVEAT = (
    "La humedad de la superficie se aproxima con la lluvia del día anterior."
)

TemperatureMetric = Literal["average", "max"]


@dataclass(frozen=True, slots=True)
class ActivityProfile:
    """Condiciones y penalizaciones de una actividad."""

    ideal_min_c: float
    ideal_max_c: float
    temperature_metric: TemperatureMetric = "average"
    probability_veto: int | None = None
    precipitation_veto_mm: float | None = None
    wind_veto_kmh: float | None = None
    max_temperature_veto_c: float | None = None
    probability_penalty_threshold: int | None = None
    probability_penalty: int = 0
    wind_penalty_threshold_kmh: float | None = None
    wind_penalty: int = 0
    previous_rain_veto_mm: float | None = None
    next_day_probability_penalty_threshold: int | None = None
    next_day_probability_penalty: int = 0
    wind_ideal_min_kmh: float | None = None
    wind_ideal_max_kmh: float | None = None
    wind_outside_penalty: int = 0


ACTIVITY_PROFILES: Final[dict[ActivityId, ActivityProfile]] = {
    ActivityId.OUTDOOR_EVENT: ActivityProfile(
        ideal_min_c=18.0,
        ideal_max_c=28.0,
        probability_veto=40,
        precipitation_veto_mm=1.0,
        wind_veto_kmh=35.0,
        probability_penalty_threshold=20,
        probability_penalty=20,
        wind_penalty_threshold_kmh=20.0,
        wind_penalty=20,
    ),
    ActivityId.OUTDOOR_EXERCISE: ActivityProfile(
        ideal_min_c=10.0,
        ideal_max_c=22.0,
        probability_veto=60,
        precipitation_veto_mm=5.0,
        wind_veto_kmh=40.0,
        max_temperature_veto_c=33.0,
        probability_penalty_threshold=20,
        probability_penalty=15,
    ),
    ActivityId.EXTERIOR_PAINTING: ActivityProfile(
        ideal_min_c=15.0,
        ideal_max_c=28.0,
        probability_veto=30,
        precipitation_veto_mm=0.2,
        wind_veto_kmh=25.0,
        previous_rain_veto_mm=1.0,
        next_day_probability_penalty_threshold=40,
        next_day_probability_penalty=20,
    ),
    ActivityId.DRYING_LAUNDRY: ActivityProfile(
        ideal_min_c=20.0,
        ideal_max_c=32.0,
        temperature_metric="max",
        probability_veto=40,
        precipitation_veto_mm=1.0,
        wind_ideal_min_kmh=10.0,
        wind_ideal_max_kmh=30.0,
        wind_outside_penalty=15,
    ),
}


def confidence_for_offset(offset_days: int) -> Confidence:
    """Clasifica la confianza según los días transcurridos desde hoy."""
    if offset_days <= CONFIDENCE_HIGH_MAX_OFFSET:
        return Confidence.HIGH
    if offset_days <= CONFIDENCE_MEDIUM_MAX_OFFSET:
        return Confidence.MEDIUM
    return Confidence.LOW


def _temperature_value(
    day: DailyForecast,
    profile: ActivityProfile,
) -> float:
    """Usa la media o la máxima según lo que pida el perfil."""
    if profile.temperature_metric == "max":
        return day.temp_max_c
    return (day.temp_max_c + day.temp_min_c) / 2


def _temperature_penalty(value: float, profile: ActivityProfile) -> int:
    """Resta puntos por cada grado fuera del rango ideal."""
    if value < profile.ideal_min_c:
        distance = profile.ideal_min_c - value
    elif value > profile.ideal_max_c:
        distance = value - profile.ideal_max_c
    else:
        return 0

    penalty = int(distance * ACTIVITY_TEMPERATURE_PENALTY_PER_C)
    return min(penalty, ACTIVITY_MAX_TEMPERATURE_PENALTY)


def _blockers(
    profile: ActivityProfile,
    day: DailyForecast,
    previous_day_precipitation_mm: float,
) -> list[str]:
    """Explica todas las condiciones que descartan el día."""
    blockers: list[str] = []
    probability = day.precipitation_probability or 0

    if profile.probability_veto is not None and probability >= profile.probability_veto:
        blockers.append(
            f"Probabilidad de precipitación de {probability}% "
            f"(máximo {profile.probability_veto}%)."
        )
    if (
        profile.precipitation_veto_mm is not None
        and day.precipitation_mm >= profile.precipitation_veto_mm
    ):
        blockers.append(
            f"Lluvia prevista de {day.precipitation_mm:.1f} mm "
            f"(máximo {profile.precipitation_veto_mm:.1f} mm)."
        )
    if (
        profile.wind_veto_kmh is not None
        and day.wind_speed_kmh >= profile.wind_veto_kmh
    ):
        blockers.append(
            f"Viento de {day.wind_speed_kmh:.1f} km/h "
            f"(máximo {profile.wind_veto_kmh:.1f} km/h)."
        )
    if (
        profile.max_temperature_veto_c is not None
        and day.temp_max_c >= profile.max_temperature_veto_c
    ):
        blockers.append(
            f"Temperatura máxima de {day.temp_max_c:.1f} °C "
            f"(máximo {profile.max_temperature_veto_c:.1f} °C)."
        )
    if (
        profile.previous_rain_veto_mm is not None
        and previous_day_precipitation_mm >= profile.previous_rain_veto_mm
    ):
        blockers.append(
            f"Lluvia de {previous_day_precipitation_mm:.1f} mm el día anterior "
            f"(máximo {profile.previous_rain_veto_mm:.1f} mm)."
        )

    return blockers


def _reasons(
    profile: ActivityProfile,
    day: DailyForecast,
    previous_day_precipitation_mm: float,
    next_day_precipitation_probability: int | None,
) -> list[Reason]:
    """Incluye las cifras usadas para puntuar el día."""
    reasons = [
        Reason(
            metric=(
                "temp_max_c"
                if profile.temperature_metric == "max"
                else "average_temperature_c"
            ),
            value=round(_temperature_value(day, profile), 1),
            unit="°C",
        ),
        Reason(
            metric="precipitation_mm",
            value=round(day.precipitation_mm, 1),
            unit="mm",
        ),
        Reason(
            metric="wind_speed_kmh",
            value=round(day.wind_speed_kmh, 1),
            unit="km/h",
        ),
    ]
    if day.precipitation_probability is not None:
        reasons.insert(
            1,
            Reason(
                metric="precipitation_probability",
                value=day.precipitation_probability,
                unit="%",
            ),
        )
    if profile.previous_rain_veto_mm is not None:
        reasons.append(
            Reason(
                metric="previous_day_precipitation_mm",
                value=round(previous_day_precipitation_mm, 1),
                unit="mm",
            )
        )
    if (
        profile.next_day_probability_penalty_threshold is not None
        and next_day_precipitation_probability is not None
    ):
        reasons.append(
            Reason(
                metric="next_day_precipitation_probability",
                value=next_day_precipitation_probability,
                unit="%",
            )
        )
    return reasons


def _score(
    profile: ActivityProfile,
    day: DailyForecast,
    next_day_precipitation_probability: int | None,
) -> int:
    """Calcula el puntaje de un día sin vetos."""
    total_penalty = _temperature_penalty(
        _temperature_value(day, profile),
        profile,
    )
    probability = day.precipitation_probability or 0

    if (
        profile.probability_penalty_threshold is not None
        and probability >= profile.probability_penalty_threshold
    ):
        total_penalty += profile.probability_penalty

    if (
        profile.wind_penalty_threshold_kmh is not None
        and day.wind_speed_kmh >= profile.wind_penalty_threshold_kmh
    ):
        total_penalty += profile.wind_penalty

    if (
        profile.wind_ideal_min_kmh is not None
        and day.wind_speed_kmh < profile.wind_ideal_min_kmh
    ):
        total_penalty += profile.wind_outside_penalty
    if (
        profile.wind_ideal_max_kmh is not None
        and day.wind_speed_kmh > profile.wind_ideal_max_kmh
    ):
        total_penalty += profile.wind_outside_penalty

    if (
        profile.next_day_probability_penalty_threshold is not None
        and next_day_precipitation_probability is not None
        and next_day_precipitation_probability
        >= profile.next_day_probability_penalty_threshold
    ):
        total_penalty += profile.next_day_probability_penalty

    return max(0, 100 - total_penalty)


def _verdict(score: int) -> ActivityVerdict:
    """Traduce el puntaje a un veredicto configurable."""
    if score >= ACTIVITY_IDEAL_MIN_SCORE:
        return ActivityVerdict.IDEAL
    if score >= ACTIVITY_ACCEPTABLE_MIN_SCORE:
        return ActivityVerdict.ACCEPTABLE
    return ActivityVerdict.NOT_RECOMMENDED


def evaluate_activity_day(
    activity: ActivityId,
    day: DailyForecast,
    *,
    confidence: Confidence,
    previous_day_precipitation_mm: float = 0.0,
    next_day_precipitation_probability: int | None = None,
) -> DayEvaluation:
    """Evalúa un día para una actividad, aplicando vetos y penalizaciones."""
    profile = ACTIVITY_PROFILES.get(activity)
    if profile is None:
        raise InvalidAdviceRequest(f"Actividad no soportada: {activity}")

    blockers = _blockers(profile, day, previous_day_precipitation_mm)
    reasons = _reasons(
        profile,
        day,
        previous_day_precipitation_mm,
        next_day_precipitation_probability,
    )

    if blockers:
        score = 0
        verdict = ActivityVerdict.NOT_RECOMMENDED
    else:
        score = _score(
            profile,
            day,
            next_day_precipitation_probability,
        )
        verdict = _verdict(score)

    return DayEvaluation(
        date=day.date,
        score=score,
        verdict=verdict,
        reasons=reasons,
        blockers=blockers,
        confidence=confidence,
    )


def activity_caveats(activity: ActivityId) -> list[str]:
    """Limitaciones comunes de las actividades, más las propias de cada una."""
    caveats = [DAILY_CAVEAT, NO_HUMIDITY_CAVEAT]
    if activity == ActivityId.EXTERIOR_PAINTING:
        caveats.append(PAINTING_SURFACE_CAVEAT)
    return caveats
