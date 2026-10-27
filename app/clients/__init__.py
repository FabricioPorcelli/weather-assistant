"""Clientes HTTP hacia servicios externos."""

from app.clients.request_cache import RequestWeatherClient
from app.clients.weather_api import (
    CurrentWeather,
    DailyForecast,
    Forecast,
    History,
    InvalidRequest,
    Location,
    LocationNotFound,
    RateLimited,
    UpstreamError,
    UpstreamTimeout,
    WeatherApi,
    WeatherApiClient,
    WeatherApiError,
)

__all__ = [
    "CurrentWeather",
    "DailyForecast",
    "Forecast",
    "History",
    "InvalidRequest",
    "Location",
    "LocationNotFound",
    "RateLimited",
    "RequestWeatherClient",
    "UpstreamError",
    "UpstreamTimeout",
    "WeatherApi",
    "WeatherApiClient",
    "WeatherApiError",
]
