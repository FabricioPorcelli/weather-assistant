"""Datos de prueba compartidos por los tests de consejos."""

from datetime import UTC, date, datetime, time, timedelta

from app.advice.models import (
    ActivityVerdict,
    Confidence,
    DayEvaluation,
)
from app.clients.weather_api import CurrentWeather, DailyForecast, Forecast, History

DEFAULT_DAY = date(2026, 10, 27)


def make_day(
    *,
    day: date = DEFAULT_DAY,
    probability: int | None = 0,
    precipitation_mm: float = 0.0,
    wind_speed_kmh: float = 10.0,
    temp_max_c: float = 25.0,
    temp_min_c: float = 15.0,
    conditions: str = "Despejado",
) -> DailyForecast:
    """Construye un día de pronóstico con valores controlados."""
    return DailyForecast(
        date=day,
        temp_max_c=temp_max_c,
        temp_min_c=temp_min_c,
        temp_c=(temp_max_c + temp_min_c) / 2,
        precipitation_mm=precipitation_mm,
        precipitation_probability=probability,
        conditions=conditions,
        wind_speed_kmh=wind_speed_kmh,
        sunrise=time(7, 0),
        sunset=time(19, 0),
    )


def make_forecast_range(
    *,
    start: date = DEFAULT_DAY,
    count: int = 15,
    **day_kwargs,
) -> list[DailyForecast]:
    """Construye una lista de días consecutivos con los mismos valores."""
    return [
        make_day(day=start + timedelta(days=index), **day_kwargs)
        for index in range(count)
    ]


def make_forecast(
    days: list[DailyForecast],
    *,
    location: str = "Madrid, Spain",
) -> Forecast:
    """Construye un pronóstico a partir de sus días."""
    return Forecast(location=location, days=days)


def make_history(
    days: list[DailyForecast],
    *,
    location: str = "Madrid, Spain",
) -> History:
    """Construye un histórico a partir de sus días."""
    return History(location=location, days=days)


def make_evaluation(
    *,
    day: date = DEFAULT_DAY,
    score: int = 100,
    verdict: ActivityVerdict = ActivityVerdict.IDEAL,
    confidence: Confidence = Confidence.HIGH,
    blockers: list[str] | None = None,
) -> DayEvaluation:
    """Construye una evaluación ya calculada para tests de ranking."""
    return DayEvaluation(
        date=day,
        score=score,
        verdict=verdict,
        reasons=[],
        blockers=blockers or [],
        confidence=confidence,
    )


def make_current(
    *,
    feels_like_c: float = 20.0,
    temperature_c: float = 21.0,
    humidity: int = 55,
    location: str = "Madrid, Spain",
) -> CurrentWeather:
    """Construye un clima actual con valores controlados."""
    return CurrentWeather(
        location=location,
        temperature_c=temperature_c,
        feels_like_c=feels_like_c,
        humidity=humidity,
        conditions="Parcialmente nublado",
        wind_speed_kmh=12.0,
        precipitation_mm=0.0,
        updated_at=datetime(2026, 10, 27, 12, tzinfo=UTC),
    )
