"""Clientes HTTP hacia servicios externos."""

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
    "UpstreamError",
    "UpstreamTimeout",
    "WeatherApiClient",
    "WeatherApiError",
]
