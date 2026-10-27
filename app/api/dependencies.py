"""Dependencias reutilizables por los routers de la API."""

from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request
from pydantic import ValidationError

from app.agent.llm import LLMClient
from app.clients.request_cache import RequestWeatherClient
from app.clients.weather_api import Location


def get_weather_client(request: Request) -> RequestWeatherClient:
    """Envuelve el cliente compartido con caché válida solo para este pedido."""
    return RequestWeatherClient(request.app.state.weather_client)


def get_llm_client(request: Request) -> LLMClient:
    """Devuelve el cliente LLM compartido o falla si no está configurado."""
    client = request.app.state.llm_client
    if client is None:
        raise HTTPException(
            status_code=503,
            detail="El LLM no está configurado en el servidor",
        )
    return client


def get_location(
    city: Annotated[str | None, Query(description="Nombre de la ciudad")] = None,
    lat: Annotated[
        float | None,
        Query(ge=-90, le=90, description="Latitud en grados decimales"),
    ] = None,
    lon: Annotated[
        float | None,
        Query(ge=-180, le=180, description="Longitud en grados decimales"),
    ] = None,
    label: Annotated[
        str | None,
        Query(max_length=200, description="Texto para mostrar la ubicación"),
    ] = None,
) -> Location:
    """Construye y valida una ubicación a partir de los query params."""
    try:
        return Location(city=city, lat=lat, lon=lon, label=label)
    except ValidationError as exc:
        detail = exc.errors()[0].get("msg", "Ubicación inválida")
        raise HTTPException(status_code=422, detail=detail) from exc


LocationDep = Annotated[Location, Depends(get_location)]
WeatherClientDep = Annotated[RequestWeatherClient, Depends(get_weather_client)]
LLMClientDep = Annotated[LLMClient, Depends(get_llm_client)]
