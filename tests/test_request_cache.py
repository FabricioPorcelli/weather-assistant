"""Tests de la caché temporal de un pedido."""

from datetime import date

import httpx

from app.clients.request_cache import RequestWeatherClient
from app.clients.weather_api import Location
from tests.helpers import (
    make_current,
    make_day,
    make_forecast,
    make_history,
)


async def test_forecast_is_reused_for_same_location_and_days(
    weather_client,
    api_mock,
):
    forecast = make_forecast([make_day()])
    route = api_mock.get("/v1/forecast/Madrid", params={"days": 15}).mock(
        return_value=httpx.Response(200, json=forecast.model_dump(mode="json"))
    )
    cached = RequestWeatherClient(weather_client)

    await cached.get_forecast(Location(city="Madrid"), days=15)
    await cached.get_forecast(Location(city="Madrid"), days=15)

    assert route.call_count == 1


async def test_different_day_counts_are_not_shared(weather_client, api_mock):
    forecast = make_forecast([make_day()])
    fifteen = api_mock.get("/v1/forecast/Madrid", params={"days": 15}).mock(
        return_value=httpx.Response(200, json=forecast.model_dump(mode="json"))
    )
    two = api_mock.get("/v1/forecast/Madrid", params={"days": 2}).mock(
        return_value=httpx.Response(200, json=forecast.model_dump(mode="json"))
    )
    cached = RequestWeatherClient(weather_client)

    await cached.get_forecast(Location(city="Madrid"), days=15)
    await cached.get_forecast(Location(city="Madrid"), days=2)

    assert fifteen.call_count == 1
    assert two.call_count == 1


async def test_city_cache_is_case_insensitive(weather_client, api_mock):
    forecast = make_forecast([make_day()])
    route = api_mock.get("/v1/forecast/Madrid", params={"days": 15}).mock(
        return_value=httpx.Response(200, json=forecast.model_dump(mode="json"))
    )
    cached = RequestWeatherClient(weather_client)

    await cached.get_forecast(Location(city="Madrid"), days=15)
    await cached.get_forecast(Location(city="madrid"), days=15)

    assert route.call_count == 1


async def test_coordinates_are_rounded_in_cache(weather_client, api_mock):
    forecast = make_forecast([make_day()])
    route = api_mock.get("/v1/forecast/coords/-34.60/-58.38", params={"days": 15}).mock(
        return_value=httpx.Response(200, json=forecast.model_dump(mode="json"))
    )
    cached = RequestWeatherClient(weather_client)

    await cached.get_forecast(
        Location(lat=-34.6, lon=-58.38),
        days=15,
    )
    await cached.get_forecast(
        Location(lat=-34.6001, lon=-58.3801),
        days=15,
    )

    assert route.call_count == 1


async def test_history_is_reused(weather_client, api_mock):
    history = make_history([make_day()])
    params = {"start": "2026-10-26", "end": "2026-10-26"}
    route = api_mock.get("/v1/history/Madrid", params=params).mock(
        return_value=httpx.Response(200, json=history.model_dump(mode="json"))
    )
    cached = RequestWeatherClient(weather_client)

    await cached.get_history(
        Location(city="Madrid"),
        date(2026, 10, 26),
        date(2026, 10, 26),
    )
    await cached.get_history(
        Location(city="Madrid"),
        date(2026, 10, 26),
        date(2026, 10, 26),
    )

    assert route.call_count == 1


async def test_current_weather_is_reused(weather_client, api_mock):
    current = make_current()
    route = api_mock.get("/v1/weather/Madrid").mock(
        return_value=httpx.Response(200, json=current.model_dump(mode="json"))
    )
    cached = RequestWeatherClient(weather_client)

    await cached.get_current(Location(city="Madrid"))
    await cached.get_current(Location(city="Madrid"))

    assert route.call_count == 1


async def test_separate_requests_do_not_share_cache(weather_client, api_mock):
    forecast = make_forecast([make_day()])
    route = api_mock.get("/v1/forecast/Madrid", params={"days": 15}).mock(
        return_value=httpx.Response(200, json=forecast.model_dump(mode="json"))
    )

    first_request = RequestWeatherClient(weather_client)
    second_request = RequestWeatherClient(weather_client)
    await first_request.get_forecast(Location(city="Madrid"), days=15)
    await second_request.get_forecast(Location(city="Madrid"), days=15)

    assert route.call_count == 2
