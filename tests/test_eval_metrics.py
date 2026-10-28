"""Tests de las métricas y fixtures del runner de evals."""

from datetime import date

import pytest

from app.clients.weather_api import Location, LocationNotFound
from evals.run_evals import (
    EVALS_DIR,
    FixtureWeatherApi,
    _expected_args,
    _extract_numbers,
    _is_subset,
    _numbers_grounded,
    summarize,
)


def test_extract_numbers_from_text():
    assert _extract_numbers("Probabilidad 70% y 5.0 mm a las 2026-03-04") == [
        70.0,
        5.0,
        2026.0,
        -3.0,
        -4.0,
    ]


def test_groundedness_accepts_rounding():
    results = {"call_1": {"probability": 70, "mm": 5.04}}

    assert _numbers_grounded("Hay 70% y 5 mm.", results)
    assert not _numbers_grounded("Hay 99% y 5 mm.", results)


def test_json_subset_ignores_extra_keys():
    expected = {"location": {"city": "Madrid"}, "activity": "outdoor_event"}
    actual = {
        "location": {"city": "Madrid", "label": "Madrid"},
        "activity": "outdoor_event",
        "top_n": 3,
    }

    assert _is_subset(expected, actual)


def test_expected_args_accepts_dict_or_list():
    assert _expected_args({"args": {"location": {"city": "Madrid"}}}) == [
        {"location": {"city": "Madrid"}}
    ]
    assert _expected_args({"args": [{"a": 1}, {"b": 2}]}) == [{"a": 1}, {"b": 2}]


async def test_fixture_weather_client_serves_forecast_and_history():
    client = FixtureWeatherApi(EVALS_DIR / "fixtures" / "madrid_rainy.json")
    location = Location(city="Madrid")

    current = await client.get_current(location)
    forecast = await client.get_forecast(location, days=2)
    history = await client.get_history(
        location,
        start=date(2026, 3, 1),
        end=date(2026, 3, 3),
    )

    assert current.location == "Madrid, España"
    assert len(forecast.days) == 2
    assert len(history.days) == 3


async def test_fixture_weather_client_rejects_unknown_location():
    client = FixtureWeatherApi(EVALS_DIR / "fixtures" / "madrid_rainy.json")

    with pytest.raises(LocationNotFound):
        await client.get_current(Location(city="CiudadInventada"))


def _result(passed: bool, latency_ms: float, tokens: int) -> dict:
    return {
        "passed": passed,
        "tools_match": passed,
        "args_match": passed,
        "verdict_match": None,
        "best_date_match": None,
        "mentions_match": passed,
        "grounded": True,
        "latency_ms": latency_ms,
        "usage": {
            "prompt_tokens": tokens,
            "completion_tokens": 0,
            "total_tokens": tokens,
        },
        "cost_usd": 0.0,
    }


def test_summarize_aggregates_metrics():
    summary = summarize(
        [
            _result(True, 100.0, 10),
            _result(False, 300.0, 20),
        ]
    )

    assert summary["cases"] == 2
    assert summary["passed"] == 1
    assert summary["pass_rate"] == 0.5
    assert summary["tools_accuracy"] == 0.5
    assert summary["latency_p50_ms"] == 200.0
    assert summary["total_tokens"] == 30
