"""Tests de definiciones, validación y ejecución de herramientas."""

import json
from datetime import date

import pytest

from app.advice.models import (
    ActivityId,
    BestDayResult,
    Confidence,
    DateRange,
)
from app.agent.tools import (
    TOOL_DEFINITIONS,
    _drop_low_confidence,
    _format_date_label,
    execute_tool,
)
from app.clients.weather_api import LocationNotFound
from tests.fakes import FakeWeatherApi
from tests.helpers import (
    DEFAULT_DAY,
    make_day,
    make_evaluation,
    make_forecast,
    make_forecast_range,
)


def _madrid_forecast(**day_kwargs):
    return make_forecast(make_forecast_range(**day_kwargs))


def _arguments(**kwargs) -> str:
    return json.dumps(kwargs, ensure_ascii=False)


def test_tool_definitions_include_all_tools():
    names = {definition["function"]["name"] for definition in TOOL_DEFINITIONS}

    assert names == {
        "get_current_weather",
        "get_forecast",
        "get_hourly_forecast",
        "get_umbrella_advice",
        "get_clothing_advice",
        "get_watering_advice",
        "get_activity_advice",
        "find_best_day",
    }


async def test_get_current_weather_tool():
    fake = FakeWeatherApi()
    result = await execute_tool(
        "get_current_weather",
        _arguments(location={"city": "Madrid"}),
        fake,
    )

    assert result["location"] == "Madrid, Spain"
    assert ("current", "Madrid") in fake.calls


async def test_get_forecast_tool():
    fake = FakeWeatherApi()
    result = await execute_tool(
        "get_forecast",
        _arguments(location={"city": "Madrid"}, days=3),
        fake,
        reference_date=DEFAULT_DAY,
    )

    assert result["location"] == "Madrid"
    assert result["days"][0]["date_label"] == "martes 27"
    assert ("forecast", "Madrid", 3) in fake.calls


async def test_get_hourly_forecast_tool():
    fake = FakeWeatherApi()
    result = await execute_tool(
        "get_hourly_forecast",
        _arguments(location={"city": "Madrid"}, hours=6),
        fake,
    )

    assert result["location"] == "Madrid"
    assert len(result["hours"]) == 6
    assert result["hours"][0]["datetime"] == "2026-10-27T09:00:00"
    assert ("hourly", "Madrid", 6) in fake.calls


async def test_umbrella_tool_accepts_date_alias():
    fake = FakeWeatherApi(
        forecasts={
            "Madrid": make_forecast([make_day(probability=70, precipitation_mm=2.0)])
        }
    )
    result = await execute_tool(
        "get_umbrella_advice",
        _arguments(
            location={"city": "Madrid"},
            date=DEFAULT_DAY.isoformat(),
        ),
        fake,
        reference_date=DEFAULT_DAY,
    )

    assert result["kind"] == "umbrella"
    assert result["verdict"] == "yes"
    assert result["target_date_label"] == "martes 27"


async def test_clothing_tool():
    fake = FakeWeatherApi()
    result = await execute_tool(
        "get_clothing_advice",
        _arguments(location={"city": "Madrid"}),
        fake,
    )

    assert result["kind"] == "clothing"
    assert "verdict" in result


async def test_watering_tool():
    fake = FakeWeatherApi()
    result = await execute_tool(
        "get_watering_advice",
        _arguments(location={"city": "Madrid"}),
        fake,
    )

    assert result["kind"] == "watering"
    assert "verdict" in result


async def test_watering_tool_rejects_date():
    fake = FakeWeatherApi()
    result = await execute_tool(
        "get_watering_advice",
        _arguments(
            location={"city": "Madrid"},
            date=DEFAULT_DAY.isoformat(),
        ),
        fake,
    )

    assert "error" in result


async def test_activity_tool():
    fake = FakeWeatherApi()
    result = await execute_tool(
        "get_activity_advice",
        _arguments(
            location={"city": "Madrid"},
            activity="outdoor_event",
            date=DEFAULT_DAY.isoformat(),
        ),
        fake,
        reference_date=DEFAULT_DAY,
    )

    assert result["date"] == DEFAULT_DAY.isoformat()
    assert result["date_label"] == "martes 27"
    assert result["verdict_label"] == "ideal"
    assert result["score"] == 100


async def test_best_day_tool():
    fake = FakeWeatherApi()
    result = await execute_tool(
        "find_best_day",
        _arguments(
            location={"city": "Madrid"},
            activity="outdoor_event",
            start_date=DEFAULT_DAY.isoformat(),
            end_date=(DEFAULT_DAY.replace(day=29)).isoformat(),
            top_n=2,
        ),
        fake,
        reference_date=DEFAULT_DAY,
    )

    assert result["activity"] == "outdoor_event"
    assert len(result["ranking"]) == 2
    assert result["range"]["start_label"] == "martes 27"
    assert result["range"]["end_label"] == "jueves 29"
    assert result["ranking"][0]["date_label"] == "martes 27"
    assert result["ranking"][0]["verdict_label"] == "ideal"


def test_date_label_omits_obvious_month_and_year():
    reference = date(2026, 10, 27)

    assert _format_date_label("2026-10-27", reference_date=reference) == "martes 27"
    assert (
        _format_date_label("2026-11-02", reference_date=reference)
        == "lunes 2 de noviembre"
    )
    assert (
        _format_date_label("2027-01-02", reference_date=date(2026, 12, 31))
        == "sábado 2 de enero de 2027"
    )


def test_find_best_day_drops_low_confidence_days():
    result = BestDayResult(
        activity=ActivityId.OUTDOOR_EVENT,
        location_label="Madrid",
        range=DateRange(start=DEFAULT_DAY, end=DEFAULT_DAY.replace(day=29)),
        ranking=[
            make_evaluation(
                day=DEFAULT_DAY,
                score=100,
                confidence=Confidence.LOW,
            ),
            make_evaluation(
                day=DEFAULT_DAY.replace(day=28),
                score=80,
                confidence=Confidence.HIGH,
            ),
        ],
        has_acceptable_day=True,
        caveats=[],
    )

    filtered = _drop_low_confidence(result, top_n=3)

    assert [evaluation.confidence for evaluation in filtered.ranking] == [
        Confidence.HIGH
    ]
    assert filtered.has_acceptable_day is True

    only_low = result.model_copy(
        update={"ranking": [result.ranking[0]], "has_acceptable_day": True}
    )
    empty = _drop_low_confidence(only_low, top_n=3)

    assert empty.ranking == []
    assert empty.has_acceptable_day is False
    assert any("confiable" in caveat for caveat in empty.caveats)


async def test_unknown_tool_returns_error():
    result = await execute_tool(
        "get_moon_phase",
        "{}",
        FakeWeatherApi(),
    )

    assert "desconocida" in result["error"]


async def test_invalid_json_returns_error():
    result = await execute_tool(
        "get_current_weather",
        "{no es json",
        FakeWeatherApi(),
    )

    assert "inválidos" in result["error"]


@pytest.mark.parametrize(
    "arguments",
    [
        _arguments(location={"city": "Madrid"}, days=99),
        _arguments(location={"city": "Madrid"}, extra="no permitido"),
        _arguments(location={"city": "Madrid", "lat": -34.6, "lon": -58.38}),
    ],
)
async def test_invalid_arguments_return_error(arguments):
    result = await execute_tool(
        "get_forecast",
        arguments,
        FakeWeatherApi(),
    )

    assert "inválidos" in result["error"]


async def test_invalid_hourly_arguments_return_error():
    result = await execute_tool(
        "get_hourly_forecast",
        _arguments(location={"city": "Madrid"}, hours=99),
        FakeWeatherApi(),
    )

    assert "inválidos" in result["error"]


async def test_unsupported_activity_returns_error():
    result = await execute_tool(
        "get_activity_advice",
        _arguments(
            location={"city": "Madrid"},
            activity="sunscreen",
            date=DEFAULT_DAY.isoformat(),
        ),
        FakeWeatherApi(),
    )

    assert "inválidos" in result["error"]


async def test_domain_error_is_returned_to_the_model():
    fake = FakeWeatherApi(error=LocationNotFound("no existe"))

    result = await execute_tool(
        "get_current_weather",
        _arguments(location={"city": "Madrid"}),
        fake,
    )

    assert result == {"error": "no existe"}
