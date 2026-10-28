"""Traduce errores de dominio a respuestas HTTP."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.advice.errors import AdviceError, InvalidAdviceRequest, OutOfRangeError
from app.clients.weather_api import (
    InvalidRequest,
    LocationNotFound,
    RateLimited,
    UpstreamError,
    UpstreamTimeout,
    WeatherApiError,
)


def _error_response(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail})


async def _location_not_found(
    _request: Request, _exc: LocationNotFound
) -> JSONResponse:
    return _error_response(404, "No se encontró la ubicación solicitada")


async def _invalid_request(_request: Request, _exc: InvalidRequest) -> JSONResponse:
    return _error_response(422, "weather-api rechazó los parámetros enviados")


async def _rate_limited(_request: Request, _exc: RateLimited) -> JSONResponse:
    return _error_response(
        429,
        "Se alcanzó el límite de consultas a weather-api. Probá de nuevo en un minuto.",
    )


async def _upstream_timeout(_request: Request, _exc: UpstreamTimeout) -> JSONResponse:
    return _error_response(504, "weather-api no respondió a tiempo")


async def _upstream_error(
    _request: Request, _exc: UpstreamError | WeatherApiError
) -> JSONResponse:
    return _error_response(502, "weather-api no está disponible")


async def _advice_error(
    _request: Request, exc: OutOfRangeError | InvalidAdviceRequest
) -> JSONResponse:
    return _error_response(422, str(exc))


def register_exception_handlers(app: FastAPI) -> None:
    """Asocia cada excepción de dominio con su respuesta HTTP."""
    app.add_exception_handler(LocationNotFound, _location_not_found)
    app.add_exception_handler(InvalidRequest, _invalid_request)
    app.add_exception_handler(RateLimited, _rate_limited)
    app.add_exception_handler(UpstreamTimeout, _upstream_timeout)
    app.add_exception_handler(UpstreamError, _upstream_error)
    app.add_exception_handler(WeatherApiError, _upstream_error)
    app.add_exception_handler(OutOfRangeError, _advice_error)
    app.add_exception_handler(InvalidAdviceRequest, _advice_error)
    app.add_exception_handler(AdviceError, _advice_error)
