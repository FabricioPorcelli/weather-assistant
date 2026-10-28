"""Aplicación FastAPI del asistente."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app import __version__
from app.agent.llm import OpenAICompatClient
from app.api.activities import router as activities_router
from app.api.advice import router as advice_router
from app.api.chat import router as chat_router
from app.api.feedback import router as feedback_router
from app.api.health import router as health_router
from app.clients.weather_api import WeatherApiClient
from app.config import get_settings
from app.db.session import dispose_engine
from app.errors import register_exception_handlers
from app.limiter import limiter
from app.observability.logging import RequestLoggingMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Abre recursos al arrancar y los cierra al apagar el servicio."""
    settings = get_settings()
    app.state.weather_client = WeatherApiClient(
        settings.weather_api_base_url,
        timeout=settings.weather_api_timeout_seconds,
        retries=settings.weather_api_retries,
        retry_delay=settings.weather_api_retry_delay_seconds,
    )
    app.state.llm_client = None
    if settings.llm_base_url and settings.llm_model:
        app.state.llm_client = OpenAICompatClient(
            settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            timeout=settings.llm_timeout_seconds,
        )

    try:
        yield
    finally:
        if app.state.llm_client is not None:
            await app.state.llm_client.aclose()
        await app.state.weather_client.aclose()
        await dispose_engine()


app = FastAPI(
    title="Weather Assistant",
    description=(
        "Asistente conversacional que consulta weather-api y devuelve consejos "
        "deterministas sobre paraguas, ropa, riego y actividades."
    ),
    version=__version__,
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
register_exception_handlers(app)

settings = get_settings()
if settings.assistant_cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.assistant_cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

app.add_middleware(RequestLoggingMiddleware)

app.include_router(health_router)
app.include_router(advice_router)
app.include_router(activities_router)
app.include_router(chat_router)
app.include_router(feedback_router)
