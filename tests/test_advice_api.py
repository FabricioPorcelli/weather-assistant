"""Tests del motor y del endpoint de consejos."""

from datetime import timedelta

import httpx
import pytest

from app.advice.engine import build_advice
from app.advice.models import AdviceKind
from app.clients.weather_api import Location
from tests.helpers import (
    DEFAULT_DAY,
    make_current,
    make_day,
    make_forecast,
    make_history,
)


async def test_umbrella_by_city(api_client, api_mock):
    forecast = make_forecast([make_day(probability=70, precipitation_mm=2.0)])
    route = api_mock.get("/v1/forecast/Madrid", params={"days": 15}).mock(
        return_value=httpx.Response(200, json=forecast.model_dump(mode="json"))
    )

    response = await api_client.get("/v1/advice/umbrella", params={"city": "Madrid"})

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "umbrella"
    assert body["verdict"] == "yes"
    assert body["target_date"] == DEFAULT_DAY.isoformat()
    assert body["location_label"] == "Madrid, Spain"
    assert route.called


async def test_umbrella_with_target_date(api_client, api_mock):
    target_date = DEFAULT_DAY + timedelta(days=2)
    forecast = make_forecast(
        [
            make_day(day=DEFAULT_DAY),
            make_day(day=target_date, probability=0, precipitation_mm=0.0),
        ]
    )
    api_mock.get("/v1/forecast/Madrid", params={"days": 15}).mock(
        return_value=httpx.Response(200, json=forecast.model_dump(mode="json"))
    )

    response = await api_client.get(
        "/v1/advice/umbrella",
        params={"city": "Madrid", "date": target_date.isoformat()},
    )

    assert response.status_code == 200
    assert response.json()["target_date"] == target_date.isoformat()
    assert response.json()["verdict"] == "no"


async def test_umbrella_date_outside_horizon_returns_422(api_client, api_mock):
    forecast = make_forecast([make_day(probability=0)])
    api_mock.get("/v1/forecast/Madrid", params={"days": 15}).mock(
        return_value=httpx.Response(200, json=forecast.model_dump(mode="json"))
    )

    response = await api_client.get(
        "/v1/advice/umbrella",
        params={"city": "Madrid", "date": "2026-12-01"},
    )

    assert response.status_code == 422
    assert "no está dentro del pronóstico" in response.json()["detail"]


async def test_umbrella_by_coords_uses_label(api_client, api_mock):
    forecast = make_forecast([make_day(probability=10)])
    route = api_mock.get("/v1/forecast/coords/-34.60/-58.38", params={"days": 15}).mock(
        return_value=httpx.Response(200, json=forecast.model_dump(mode="json"))
    )

    response = await api_client.get(
        "/v1/advice/umbrella",
        params={"lat": -34.6, "lon": -58.38, "label": "Buenos Aires"},
    )

    assert response.status_code == 200
    assert response.json()["location_label"] == "Buenos Aires"
    assert route.called


async def test_missing_location_returns_422_without_calls(api_client, api_mock):
    response = await api_client.get("/v1/advice/umbrella")

    assert response.status_code == 422
    assert len(api_mock.calls) == 0


async def test_city_and_coords_together_return_422(api_client, api_mock):
    response = await api_client.get(
        "/v1/advice/umbrella",
        params={"city": "Madrid", "lat": -34.6, "lon": -58.38},
    )

    assert response.status_code == 422
    assert len(api_mock.calls) == 0


async def test_unknown_advice_kind_returns_422(api_client, api_mock):
    response = await api_client.get(
        "/v1/advice/sunscreen",
        params={"city": "Madrid"},
    )

    assert response.status_code == 422
    assert len(api_mock.calls) == 0


async def test_watering_with_date_returns_422_without_calls(api_client, api_mock):
    response = await api_client.get(
        "/v1/advice/watering",
        params={"city": "Madrid", "date": DEFAULT_DAY.isoformat()},
    )

    assert response.status_code == 422
    assert "no acepta una fecha" in response.json()["detail"]
    assert len(api_mock.calls) == 0


async def test_clothing_today_uses_current_weather(api_client, api_mock):
    forecast = make_forecast(
        [make_day(temp_max_c=25.0, temp_min_c=15.0, wind_speed_kmh=10.0)]
    )
    current = make_current(feels_like_c=14.0)
    api_mock.get("/v1/forecast/Madrid", params={"days": 15}).mock(
        return_value=httpx.Response(200, json=forecast.model_dump(mode="json"))
    )
    current_route = api_mock.get("/v1/weather/Madrid").mock(
        return_value=httpx.Response(200, json=current.model_dump(mode="json"))
    )

    response = await api_client.get("/v1/advice/clothing", params={"city": "Madrid"})

    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "campera"
    assert body["data_sources"] == ["/v1/weather", "/v1/forecast"]
    assert current_route.called


async def test_clothing_future_uses_daily_average(api_client, api_mock):
    target_date = DEFAULT_DAY + timedelta(days=1)
    forecast = make_forecast(
        [
            make_day(day=DEFAULT_DAY, temp_max_c=18.0, temp_min_c=12.0),
            make_day(day=target_date, temp_max_c=25.0, temp_min_c=14.2),
        ]
    )
    current = make_current(feels_like_c=30.0)
    api_mock.get("/v1/forecast/Madrid", params={"days": 15}).mock(
        return_value=httpx.Response(200, json=forecast.model_dump(mode="json"))
    )
    current_route = api_mock.get("/v1/weather/Madrid").mock(
        return_value=httpx.Response(200, json=current.model_dump(mode="json"))
    )

    response = await api_client.get(
        "/v1/advice/clothing",
        params={"city": "Madrid", "date": target_date.isoformat()},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "capa_intermedia"
    assert body["data_sources"] == ["/v1/forecast"]
    assert not current_route.called


async def test_clothing_comfort_offset_is_applied(weather_client, api_mock):
    forecast = make_forecast([make_day(temp_max_c=20.0, temp_min_c=10.0)])
    current = make_current(feels_like_c=14.0)
    api_mock.get("/v1/forecast/Madrid", params={"days": 15}).mock(
        return_value=httpx.Response(200, json=forecast.model_dump(mode="json"))
    )
    api_mock.get("/v1/weather/Madrid").mock(
        return_value=httpx.Response(200, json=current.model_dump(mode="json"))
    )

    advice = await build_advice(
        AdviceKind.CLOTHING,
        Location(city="Madrid"),
        weather_client,
        comfort_offset_c=4.0,
    )

    assert advice.verdict == "capa_intermedia"


async def test_watering_calls_forecast_and_history(api_client, api_mock):
    forecast = make_forecast(
        [
            make_day(day=DEFAULT_DAY, temp_max_c=35.0),
            make_day(day=DEFAULT_DAY + timedelta(days=1)),
        ]
    )
    history = make_history(
        [
            make_day(day=DEFAULT_DAY - timedelta(days=3)),
            make_day(day=DEFAULT_DAY - timedelta(days=2)),
            make_day(day=DEFAULT_DAY - timedelta(days=1)),
        ]
    )
    forecast_route = api_mock.get("/v1/forecast/Madrid", params={"days": 2}).mock(
        return_value=httpx.Response(200, json=forecast.model_dump(mode="json"))
    )
    history_route = api_mock.get(
        "/v1/history/Madrid",
        params={"start": "2026-10-24", "end": "2026-10-26"},
    ).mock(return_value=httpx.Response(200, json=history.model_dump(mode="json")))

    response = await api_client.get("/v1/advice/watering", params={"city": "Madrid"})

    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "yes"
    assert body["target_date"] == DEFAULT_DAY.isoformat()
    assert body["data_sources"] == ["/v1/history", "/v1/forecast"]
    assert forecast_route.called
    assert history_route.called


async def test_watering_waits_for_upcoming_rain(api_client, api_mock):
    forecast = make_forecast(
        [
            make_day(
                day=DEFAULT_DAY,
                temp_max_c=35.0,
                probability=70,
                precipitation_mm=6.0,
            ),
            make_day(day=DEFAULT_DAY + timedelta(days=1)),
        ]
    )
    history = make_history(
        [
            make_day(day=DEFAULT_DAY - timedelta(days=3)),
            make_day(day=DEFAULT_DAY - timedelta(days=2)),
            make_day(day=DEFAULT_DAY - timedelta(days=1)),
        ]
    )
    api_mock.get("/v1/forecast/Madrid", params={"days": 2}).mock(
        return_value=httpx.Response(200, json=forecast.model_dump(mode="json"))
    )
    api_mock.get(
        "/v1/history/Madrid",
        params={"start": "2026-10-24", "end": "2026-10-26"},
    ).mock(return_value=httpx.Response(200, json=history.model_dump(mode="json")))

    response = await api_client.get("/v1/advice/watering", params={"city": "Madrid"})

    assert response.status_code == 200
    assert response.json()["verdict"] == "no"
    assert "próximas 48 h" in response.json()["summary"]


@pytest.mark.parametrize(
    ("upstream_status", "expected_status"),
    [
        (400, 502),
        (404, 404),
        (422, 422),
        (429, 429),
        (500, 502),
        (502, 502),
        (504, 504),
    ],
)
async def test_upstream_errors_are_mapped_to_http(
    api_client, api_mock, upstream_status, expected_status
):
    api_mock.get("/v1/forecast/Madrid", params={"days": 15}).mock(
        return_value=httpx.Response(
            upstream_status,
            json={"detail": "error del proveedor"},
        )
    )

    response = await api_client.get("/v1/advice/umbrella", params={"city": "Madrid"})

    assert response.status_code == expected_status


async def test_upstream_timeout_is_mapped_to_504(api_client, api_mock):
    api_mock.get("/v1/forecast/Madrid", params={"days": 15}).mock(
        side_effect=httpx.TimeoutException("timeout")
    )

    response = await api_client.get("/v1/advice/umbrella", params={"city": "Madrid"})

    assert response.status_code == 504


async def test_connection_error_is_mapped_to_502(api_client, api_mock):
    api_mock.get("/v1/forecast/Madrid", params={"days": 15}).mock(
        side_effect=httpx.ConnectError("sin conexión")
    )

    response = await api_client.get("/v1/advice/umbrella", params={"city": "Madrid"})

    assert response.status_code == 502


async def test_invalid_json_is_mapped_to_502(api_client, api_mock):
    api_mock.get("/v1/forecast/Madrid", params={"days": 15}).mock(
        return_value=httpx.Response(200, text="no es JSON")
    )

    response = await api_client.get("/v1/advice/umbrella", params={"city": "Madrid"})

    assert response.status_code == 502


async def test_empty_forecast_is_mapped_to_502(api_client, api_mock):
    api_mock.get("/v1/forecast/Madrid", params={"days": 15}).mock(
        return_value=httpx.Response(
            200,
            json={"location": "Madrid, Spain", "days": []},
        )
    )

    response = await api_client.get("/v1/advice/umbrella", params={"city": "Madrid"})

    assert response.status_code == 502
