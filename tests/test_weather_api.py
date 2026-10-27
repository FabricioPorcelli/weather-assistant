"""Tests del cliente HTTP de weather-api.

Se cubren rutas, parámetros, parseo del contrato y traducción de errores.
"""

from datetime import UTC, date, datetime, time

import httpx
import pytest
from pydantic import ValidationError

from app.clients.weather_api import (
    InvalidRequest,
    Location,
    LocationNotFound,
    RateLimited,
    UpstreamError,
    UpstreamTimeout,
    WeatherApiClient,
)

CURRENT_PAYLOAD = {
    "location": "Madrid, Spain",
    "temperature_c": 21.5,
    "feels_like_c": 20.3,
    "humidity": 55,
    "conditions": "Parcialmente nublado",
    "wind_speed_kmh": 12.4,
    "precipitation_mm": 0.0,
    "updated_at": "2026-09-25T12:00:00+00:00",
}


def _day(day: str, probability: int | None = 10) -> dict:
    return {
        "date": day,
        "temp_max_c": 25.0,
        "temp_min_c": 14.2,
        "temp_c": 19.6,
        "precipitation_mm": 0.0,
        "precipitation_probability": probability,
        "conditions": "Parcialmente nublado",
        "wind_speed_kmh": 12.0,
        "sunrise": "07:10:00",
        "sunset": "19:40:00",
    }


FORECAST_PAYLOAD = {
    "location": "Madrid, Spain",
    "days": [
        _day("2026-09-25"),
        _day("2026-09-26"),
        _day("2026-09-27"),
    ],
}

HISTORY_PAYLOAD = {
    "location": "Madrid, Spain",
    "days": [
        _day("2026-09-20", probability=None),
        _day("2026-09-21", probability=None),
    ],
}


async def test_get_current_by_city(weather_client, api_mock):
    route = api_mock.get("/v1/weather/Madrid").mock(
        return_value=httpx.Response(200, json=CURRENT_PAYLOAD)
    )

    result = await weather_client.get_current(Location(city="  Madrid  "))

    assert route.called
    assert result.location == "Madrid, Spain"
    assert result.temperature_c == 21.5
    assert result.feels_like_c == 20.3
    assert result.humidity == 55
    assert result.updated_at == datetime(2026, 9, 25, 12, tzinfo=UTC)


async def test_city_with_spaces_is_url_encoded(weather_client, api_mock):
    payload = {**CURRENT_PAYLOAD, "location": "Buenos Aires, Argentina"}
    route = api_mock.get("/v1/weather/Buenos%20Aires").mock(
        return_value=httpx.Response(200, json=payload)
    )

    result = await weather_client.get_current(Location(city="Buenos Aires"))

    assert route.called
    assert result.location == "Buenos Aires, Argentina"


async def test_get_current_by_coords_rounds_to_two_decimals(weather_client, api_mock):
    route = api_mock.get("/v1/weather/coords/-34.60/-58.38").mock(
        return_value=httpx.Response(200, json=CURRENT_PAYLOAD)
    )

    result = await weather_client.get_current(Location(lat=-34.6, lon=-58.38))

    assert route.called
    assert result.location == "Madrid, Spain"


async def test_get_forecast_uses_default_days(weather_client, api_mock):
    route = api_mock.get("/v1/forecast/Madrid", params={"days": 5}).mock(
        return_value=httpx.Response(200, json=FORECAST_PAYLOAD)
    )

    result = await weather_client.get_forecast(Location(city="Madrid"))

    assert route.called
    assert len(result.days) == 3
    assert result.days[0].date == date(2026, 9, 25)
    assert result.days[0].precipitation_probability == 10
    assert route.calls.last.request.url.params["days"] == "5"


async def test_get_forecast_uses_custom_days(weather_client, api_mock):
    route = api_mock.get("/v1/forecast/Madrid", params={"days": 7}).mock(
        return_value=httpx.Response(200, json=FORECAST_PAYLOAD)
    )

    await weather_client.get_forecast(Location(city="Madrid"), days=7)

    assert route.called
    assert route.calls.last.request.url.params["days"] == "7"


@pytest.mark.parametrize("days", [0, 16, -1])
async def test_get_forecast_rejects_invalid_days_without_request(
    weather_client, api_mock, days
):
    with pytest.raises(ValueError):
        await weather_client.get_forecast(Location(city="Madrid"), days=days)

    assert len(api_mock.calls) == 0


async def test_get_history_sends_iso_dates(weather_client, api_mock):
    params = {"start": "2026-09-20", "end": "2026-09-21"}
    route = api_mock.get("/v1/history/Madrid", params=params).mock(
        return_value=httpx.Response(200, json=HISTORY_PAYLOAD)
    )

    result = await weather_client.get_history(
        Location(city="Madrid"),
        start=date(2026, 9, 20),
        end=date(2026, 9, 21),
    )

    assert route.called
    assert result.days[0].precipitation_probability is None
    assert result.days[0].sunrise == time(7, 10)
    assert route.calls.last.request.url.params["start"] == "2026-09-20"
    assert route.calls.last.request.url.params["end"] == "2026-09-21"


async def test_get_history_rejects_reversed_range_without_request(
    weather_client, api_mock
):
    with pytest.raises(ValueError):
        await weather_client.get_history(
            Location(city="Madrid"),
            start=date(2026, 9, 22),
            end=date(2026, 9, 20),
        )

    assert len(api_mock.calls) == 0


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"lat": -34.6},
        {"lon": -58.38},
        {"city": "Madrid", "lat": -34.6, "lon": -58.38},
        {"city": "A"},
        {"city": "   "},
        {"lat": 91, "lon": 0},
        {"lat": 0, "lon": 181},
    ],
)
def test_invalid_locations_are_rejected(payload):
    with pytest.raises(ValidationError):
        Location(**payload)


@pytest.mark.parametrize(
    ("status_code", "expected_error"),
    [
        (400, UpstreamError),
        (404, LocationNotFound),
        (422, InvalidRequest),
        (429, RateLimited),
        (500, UpstreamError),
        (502, UpstreamError),
        (504, UpstreamTimeout),
    ],
)
async def test_http_errors_are_mapped(
    weather_client, api_mock, status_code, expected_error
):
    api_mock.get("/v1/weather/Madrid").mock(
        return_value=httpx.Response(status_code, json={"detail": "error"})
    )

    with pytest.raises(expected_error):
        await weather_client.get_current(Location(city="Madrid"))


async def test_timeout_is_mapped(weather_client, api_mock):
    api_mock.get("/v1/weather/Madrid").mock(
        side_effect=httpx.TimeoutException("timeout")
    )

    with pytest.raises(UpstreamTimeout):
        await weather_client.get_current(Location(city="Madrid"))


async def test_connection_error_is_mapped(weather_client, api_mock):
    api_mock.get("/v1/weather/Madrid").mock(
        side_effect=httpx.ConnectError("sin conexión")
    )

    with pytest.raises(UpstreamError):
        await weather_client.get_current(Location(city="Madrid"))


async def test_invalid_json_is_mapped(weather_client, api_mock):
    api_mock.get("/v1/weather/Madrid").mock(
        return_value=httpx.Response(200, text="esto no es JSON")
    )

    with pytest.raises(UpstreamError):
        await weather_client.get_current(Location(city="Madrid"))


async def test_unexpected_schema_is_mapped(weather_client, api_mock):
    api_mock.get("/v1/weather/Madrid").mock(
        return_value=httpx.Response(200, json={"location": "Madrid"})
    )

    with pytest.raises(UpstreamError):
        await weather_client.get_current(Location(city="Madrid"))


@pytest.mark.parametrize(
    ("base_url", "timeout"),
    [
        ("", 10.0),
        ("http://weather-api", 0),
    ],
)
def test_invalid_client_configuration(base_url, timeout):
    with pytest.raises(ValueError):
        WeatherApiClient(base_url, timeout=timeout)


async def test_async_context_manager_closes_http_client():
    client = WeatherApiClient("http://weather-api")

    async with client as entered:
        assert entered is client

    assert client._http.is_closed
