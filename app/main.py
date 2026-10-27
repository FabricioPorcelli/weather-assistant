"""Punto de entrada de la aplicación.

Crea la instancia de FastAPI, administra el ciclo de vida del cliente HTTP,
configura CORS y monta los routers.
Se ejecuta con: uvicorn app.main:app
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.health import router as health_router
from app.clients.weather_api import WeatherApiClient
from app.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Abre recursos al arrancar y los cierra al apagar el servicio."""
    settings = get_settings()
    app.state.weather_client = WeatherApiClient(
        settings.weather_api_base_url,
        timeout=settings.weather_api_timeout_seconds,
    )
    try:
        yield
    finally:
        await app.state.weather_client.aclose()


app = FastAPI(
    title="Weather Assistant",
    description=(
        "Asistente conversacional que consulta weather-api y devuelve consejos "
        "deterministas sobre paraguas, ropa, riego y actividades."
    ),
    version=__version__,
    lifespan=lifespan,
)

settings = get_settings()
if settings.assistant_cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.assistant_cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

app.include_router(health_router)
