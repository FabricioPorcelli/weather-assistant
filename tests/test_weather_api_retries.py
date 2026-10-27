"""Tests del reintento único para fallos transitorios de weather-api."""

import httpx
import pytest

from app.clients.weather_api import (
    Location,
    LocationNotFound,
    RateLimited,
    UpstreamError,
    UpstreamTimeout,
    WeatherApiClient,
)
from tests.helpers import make_current


def _payload() -> dict:
    return make_current().model_dump(mode="json")


@pytest.mark.parametrize("status_code", [502, 504])
async def test_transient_status_is_retried(api_mock, status_code):
    route = api_mock.get("/v1/weather/Madrid").mock(
        side_effect=[
            httpx.Response(status_code, json={"detail": "falló"}),
            httpx.Response(200, json=_payload()),
        ]
    )

    async with WeatherApiClient(
        "http://weather-api",
        retries=1,
        retry_delay=0,
    ) as client:
        result = await client.get_current(Location(city="Madrid"))

    assert result.location == "Madrid, Spain"
    assert route.call_count == 2


async def test_timeout_is_retried(api_mock):
    route = api_mock.get("/v1/weather/Madrid").mock(
        side_effect=[
            httpx.TimeoutException("timeout"),
            httpx.Response(200, json=_payload()),
        ]
    )

    async with WeatherApiClient(
        "http://weather-api",
        retries=1,
        retry_delay=0,
    ) as client:
        result = await client.get_current(Location(city="Madrid"))

    assert result.location == "Madrid, Spain"
    assert route.call_count == 2


@pytest.mark.parametrize(
    ("status_code", "expected_error"),
    [
        (404, LocationNotFound),
        (429, RateLimited),
    ],
)
async def test_client_errors_are_not_retried(
    api_mock,
    status_code,
    expected_error,
):
    route = api_mock.get("/v1/weather/Madrid").mock(
        return_value=httpx.Response(status_code, json={"detail": "error"})
    )

    async with WeatherApiClient(
        "http://weather-api",
        retries=1,
        retry_delay=0,
    ) as client:
        with pytest.raises(expected_error):
            await client.get_current(Location(city="Madrid"))

    assert route.call_count == 1


async def test_retry_exhaustion_returns_upstream_error(api_mock):
    route = api_mock.get("/v1/weather/Madrid").mock(
        return_value=httpx.Response(502, json={"detail": "falló"})
    )

    async with WeatherApiClient(
        "http://weather-api",
        retries=1,
        retry_delay=0,
    ) as client:
        with pytest.raises(UpstreamError):
            await client.get_current(Location(city="Madrid"))

    assert route.call_count == 2


async def test_retry_exhaustion_after_timeouts_returns_timeout(api_mock):
    api_mock.get("/v1/weather/Madrid").mock(
        side_effect=httpx.TimeoutException("timeout")
    )

    async with WeatherApiClient(
        "http://weather-api",
        retries=1,
        retry_delay=0,
    ) as client:
        with pytest.raises(UpstreamTimeout):
            await client.get_current(Location(city="Madrid"))


@pytest.mark.parametrize(
    ("retries", "retry_delay"),
    [(-1, 0), (4, 0), (1, -1)],
)
def test_invalid_retry_configuration(retries, retry_delay):
    with pytest.raises(ValueError):
        WeatherApiClient(
            "http://weather-api",
            retries=retries,
            retry_delay=retry_delay,
        )
