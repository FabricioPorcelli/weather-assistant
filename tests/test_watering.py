"""Tests de la regla de riego."""

from datetime import date, timedelta

import pytest

from app.advice.models import AdviceKind
from app.advice.watering import evaluate_watering
from tests.helpers import DEFAULT_DAY, make_day, make_forecast, make_history


def _watering_advice(
    rain_mm: list[float],
    *,
    temp_max_c: float,
    upcoming_probability: int = 0,
    upcoming_mm: float = 0.0,
):
    history = make_history(
        [
            make_day(
                day=DEFAULT_DAY - timedelta(days=3 - index),
                precipitation_mm=precipitation_mm,
            )
            for index, precipitation_mm in enumerate(rain_mm)
        ]
    )
    forecast = make_forecast(
        [
            make_day(
                day=DEFAULT_DAY,
                temp_max_c=temp_max_c,
                probability=upcoming_probability,
                precipitation_mm=upcoming_mm,
            ),
            make_day(day=DEFAULT_DAY + timedelta(days=1)),
        ]
    )
    return evaluate_watering(history, forecast, "Madrid")


@pytest.mark.parametrize(
    (
        "rain_mm",
        "temp_max_c",
        "upcoming_probability",
        "upcoming_mm",
        "expected",
    ),
    [
        ([10.0, 0.0, 0.0], 35.0, 0, 0.0, "no"),
        ([5.0, 0.0, 0.0], 24.0, 0, 0.0, "no"),
        ([4.9, 0.0, 0.0], 24.0, 0, 0.0, "maybe"),
        ([2.0, 0.0, 0.0], 30.0, 0, 0.0, "maybe"),
        ([1.9, 0.0, 0.0], 30.0, 0, 0.0, "yes"),
        ([1.9, 0.0, 0.0], 20.0, 0, 0.0, "maybe"),
        ([1.9, 0.0, 0.0], 19.9, 0, 0.0, "no"),
        ([0.0, 0.0, 0.0], 35.0, 60, 5.0, "no"),
        ([0.0, 0.0, 0.0], 35.0, 59, 10.0, "yes"),
        ([0.0, 0.0, 0.0], 35.0, 60, 4.9, "yes"),
    ],
)
def test_watering_rules_and_boundaries(
    rain_mm,
    temp_max_c,
    upcoming_probability,
    upcoming_mm,
    expected,
):
    advice = _watering_advice(
        rain_mm,
        temp_max_c=temp_max_c,
        upcoming_probability=upcoming_probability,
        upcoming_mm=upcoming_mm,
    )

    assert advice.verdict == expected
    assert advice.kind == AdviceKind.WATERING
    assert advice.target_date == DEFAULT_DAY
    assert advice.location_label == "Madrid"
    assert advice.data_sources == ["/v1/history", "/v1/forecast"]


def test_watering_reasons_include_accumulated_rain_and_temperature():
    advice = _watering_advice([1.9, 0.0, 0.0], temp_max_c=30.0)

    reasons = {reason.metric: reason for reason in advice.reasons}
    assert reasons["rain_72h_mm"].value == 1.9
    assert reasons["rain_72h_mm"].unit == "mm"
    assert reasons["temp_max_c"].value == 30.0
    assert reasons["temp_max_c"].unit == "°C"


def test_upcoming_rain_adds_reasons_and_summary():
    advice = _watering_advice(
        [0.0, 0.0, 0.0],
        temp_max_c=35.0,
        upcoming_probability=70,
        upcoming_mm=6.0,
    )

    reasons = {reason.metric: reason for reason in advice.reasons}
    assert advice.verdict == "no"
    assert reasons["forecast_precipitation_probability"].value == 70
    assert reasons["forecast_precipitation_mm"].value == 6.0
    assert "70%" in advice.summary
    assert "6.0 mm" in advice.summary


def test_wet_soil_wins_over_upcoming_rain():
    advice = _watering_advice(
        [10.0, 0.0, 0.0],
        temp_max_c=35.0,
        upcoming_probability=70,
        upcoming_mm=6.0,
    )

    assert advice.verdict == "no"
    assert "Lluvia acumulada" in advice.summary
    assert not any(
        reason.metric == "forecast_precipitation_probability"
        for reason in advice.reasons
    )


def test_watering_includes_heuristic_and_daily_caveats():
    advice = _watering_advice([0.0, 0.0, 0.0], temp_max_c=25.0)

    assert any("heurística" in caveat for caveat in advice.caveats)
    assert any("diario" in caveat for caveat in advice.caveats)


def test_watering_target_date_comes_from_forecast():
    forecast = make_forecast(
        [
            make_day(day=date(2026, 11, 1), temp_max_c=35.0),
            make_day(day=date(2026, 11, 2)),
        ]
    )
    history = make_history(
        [
            make_day(day=date(2026, 10, 29)),
            make_day(day=date(2026, 10, 30)),
            make_day(day=date(2026, 10, 31)),
        ]
    )

    advice = evaluate_watering(history, forecast, "Madrid")

    assert advice.target_date == date(2026, 11, 1)
